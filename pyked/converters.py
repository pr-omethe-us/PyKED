"""Module with converters from other formats.
"""

# Standard libraries
import sys
import os
from argparse import ArgumentParser
from warnings import warn
import xml.etree.ElementTree as etree

from requests.exceptions import HTTPError, ConnectionError
import habanero
import pint

# Local imports
from .validation import yaml, property_units
from .utils import units as unit_registry
from ._version import __version__
from . import chemked

# Valid properties for ReSpecTh dataGroup
datagroup_properties = ['temperature', 'pressure', 'ignition delay',
                        'pressure rise', 'composition'
                        ]
"""`list`: Valid properties for a ReSpecTh dataGroup"""


class ParseError(Exception):
    """Base class for errors."""
    pass


class KeywordError(ParseError):
    """Raised for errors in keyword parsing."""

    def __init__(self, *keywords):
        self.keywords = keywords

    def __str__(self):
        return repr('Error: {}.'.format(self.keywords[0]))


class MissingElementError(KeywordError):
    """Raised for missing required elements."""

    def __str__(self):
        return repr('Error: required element {} is missing.'.format(
            self.keywords[0]))


class MissingAttributeError(KeywordError):
    """Raised for missing required attribute."""

    def __str__(self):
        return repr('Error: required attribute {} of {} is missing.'.format(
            self.keywords[0], self.keywords[1])
            )


def get_file_metadata(root):
    """Read and parse ReSpecTh XML file metadata (file author, version, etc.)

    Args:
        root (`etree.Element`): Root of ReSpecTh XML file

    Returns:
        properties (`dict`): Dictionary with file metadata
    """
    properties = {}

    file_author = getattr(root.find('fileAuthor'), 'text', False)
    # Test for missing attribute or empty string in the same statement
    if not file_author:
        raise MissingElementError('fileAuthor')
    else:
        properties['file-author'] = {'name': file_author}

    # Default version is 0 for the ChemKED file
    properties['file-version'] = 0

    # Default ChemKED version
    properties['chemked-version'] = __version__

    return properties


def get_reference(root):
    """Read reference info from root of ReSpecTh XML file.

    Args:
        root (`etree.Element`): Root of ReSpecTh XML file

    Returns:
        properties (`dict`): Dictionary with reference information
    """
    reference = {}
    elem = root.find('bibliographyLink')
    if elem is None:
        raise MissingElementError('bibliographyLink')

    # Try to get reference info via DOI, fall back on preferredKey if necessary.
    ref_doi = elem.get('doi', None)
    ref_key = elem.get('preferredKey', None)

    if ref_doi is not None:
        try:
            ref = habanero.Crossref().works(ids=ref_doi)['message']
        except (HTTPError, habanero.RequestError, ConnectionError, UnboundLocalError):
            if ref_key is None:
                raise KeywordError('DOI not found and preferredKey attribute not set')
            else:
                warn('Missing doi attribute in bibliographyLink or lookup failed. '
                     'Setting "detail" key as a fallback; please update to the appropriate fields.'
                     )
                reference['detail'] = ref_key
                if reference['detail'][-1] != '.':
                    reference['detail'] += '.'
        else:
            if ref_key is not None:
                warn('Using DOI to obtain reference information, rather than preferredKey.')
            reference['doi'] = elem.attrib['doi']
            # Now get elements of the reference data
            # Assume that the reference returned by the DOI lookup always has a container-title
            reference['journal'] = ref.get('container-title')[0]
            ref_year = ref.get('published-print') or ref.get('published-online')
            reference['year'] = int(ref_year['date-parts'][0][0])
            reference['volume'] = int(ref.get('volume'))
            reference['pages'] = ref.get('page')
            reference['authors'] = []
            for author in ref['author']:
                auth = {}
                auth['name'] = ' '.join([author['given'], author['family']])
                # Add ORCID if available
                orcid = author.get('ORCID')
                if orcid:
                    auth['ORCID'] = orcid.lstrip('http://orcid.org/')
                reference['authors'].append(auth)

    elif ref_key is not None:
        warn('Missing doi attribute in bibliographyLink. '
             'Setting "detail" key as a fallback; please update to the appropriate fields.'
             )
        reference['detail'] = ref_key
        if reference['detail'][-1] != '.':
            reference['detail'] += '.'
    else:
        # Need one of DOI or preferredKey
        raise MissingAttributeError('preferredKey', 'bibliographyLink')

    return reference


def get_experiment_kind(root):
    """Read common properties from root of ReSpecTh XML file.

    Args:
        root (`etree.Element`): Root of ReSpecTh XML file

    Returns:
        properties (`dict`): Dictionary with experiment type and apparatus information.
    """
    properties = {}
    if root.find('experimentType').text == 'Ignition delay measurement':
        properties['experiment-type'] = 'ignition delay'
    else:
        raise NotImplementedError(root.find('experimentType').text + ' not (yet) supported')

    properties['apparatus'] = {'kind': '', 'institution': '', 'facility': ''}
    kind = getattr(root.find('apparatus/kind'), 'text', False)
    # Test for missing attribute or empty string
    if not kind:
        raise MissingElementError('apparatus/kind')
    elif kind in ['shock tube', 'rapid compression machine']:
        properties['apparatus']['kind'] = kind
    else:
        raise NotImplementedError(kind + ' experiment not (yet) supported')

    return properties


def get_common_properties(root):
    """Read common properties from root of ReSpecTh XML file.

    Args:
        root (`etree.Element`): Root of ReSpecTh XML file

    Returns:
        properties (`dict`): Dictionary with common properties
    """
    properties = {}

    for elem in root.iterfind('commonProperties/property'):
        name = elem.attrib['name']

        if name == 'initial composition':
            properties['composition'] = {'species': []}
            composition_type = None

            for child in elem.iter('component'):
                spec = {}
                spec['species-name'] = child.find('speciesLink').attrib['preferredKey']

                # use InChI for unique species identifier (if present)
                try:
                    spec['InChI'] = child.find('speciesLink').attrib['InChI']
                except KeyError:
                    # TODO: add InChI validator/search
                    warn('Missing InChI for species ' + spec['species-name'])
                    pass

                # amount of that species
                spec['amount'] = [float(child.find('amount').text)]

                properties['composition']['species'].append(spec)

                # check consistency of composition type
                if composition_type is None:
                    composition_type = child.find('amount').attrib['units']
                elif composition_type != child.find('amount').attrib['units']:
                    raise KeywordError(
                        'composition units ' + child.find('amount').attrib['units'] +
                        ' not consistent with ' + composition_type
                        )

            assert composition_type in ['mole fraction', 'mass fraction', 'mole percent'], \
                'Composition needs to be one of: mole fraction, mass fraction, mole percent.'

            properties['composition']['kind'] = composition_type

        elif name in ['temperature', 'pressure', 'pressure rise', ]:
            field = name.replace(' ', '-')
            units = elem.attrib['units']
            if units == 'Torr':
                units = 'torr'
            quantity = 1.0 * unit_registry(units)
            try:
                quantity.to(property_units[field])
            except pint.DimensionalityError:
                raise KeywordError('units incompatible for property ' + name)

            properties[field] = [' '.join([elem.find('value').text, units])]

        else:
            raise KeywordError('Property ' + name + ' not supported as common property')

    return properties


def get_ignition_type(root):
    """Gets ignition type and target.

    Args:
        root (`etree.Element`): Root of ReSpecTh XML file

    Returns:
        properties (`dict`): Dictionary with ignition type/target information
    """
    properties = {}
    elem = root.find('ignitionType')

    if elem is None:
        raise MissingElementError('ignitionType')
    elem = elem.attrib

    if 'target' in elem:
        ign_target = elem['target'].rstrip(';').upper()
    else:
        raise MissingAttributeError('target', 'ignitionType')

    if 'type' in elem:
        ign_type = elem['type']
    else:
        raise MissingAttributeError('type', 'ignitionType')

    # ReSpecTh allows multiple ignition targets
    if len(ign_target.split(';')) > 1:
        raise NotImplementedError('Multiple ignition targets not supported.')

    # Acceptable ignition targets include pressure, temperature, and species
    # concentrations
    if ign_target == 'OHEX':
        ign_target = 'OH*'
    elif ign_target == 'CHEX':
        ign_target = 'CH*'
    elif ign_target == 'P':
        ign_target = 'pressure'
    elif ign_target == 'T':
        ign_target = 'temperature'

    if ign_target not in ['pressure', 'temperature', 'OH', 'OH*', 'CH*', 'CH']:
        raise KeywordError(ign_target + ' not valid ignition target')

    if ign_type not in ['max', 'd/dt max', '1/2 max', 'min']:
        raise KeywordError(ign_type + ' not valid ignition type')

    properties['type'] = ign_type
    properties['target'] = ign_target

    return properties


def get_datapoints(root):
    """Parse datapoints with ignition delay from file.

    Args:
        root (`etree.Element`): Root of ReSpecTh XML file

    Returns:
        properties (`dict`): Dictionary with ignition delay data
    """
    # Shock tube experiment will have one data group, while RCM may have one
    # or two (one for ignition delay, one for volume-history)
    dataGroups = root.findall('dataGroup')
    if not dataGroups:
        raise MissingElementError('dataGroup')

    # all situations will have main experimental data in first dataGroup
    dataGroup = dataGroups[0]
    property_id = {}
    unit_id = {}
    # get properties of dataGroup
    for prop in dataGroup.findall('property'):
        unit_id[prop.attrib['id']] = prop.attrib['units']
        temp_prop = prop.attrib['name']
        if temp_prop not in datagroup_properties:
            raise KeyError(temp_prop + ' not valid dataPoint property')
        property_id[prop.attrib['id']] = temp_prop

    if not property_id:
        raise MissingElementError('property')

    # now get data points
    datapoints = []
    for dp in dataGroup.findall('dataPoint'):
        datapoint = {}
        for val in dp:
            units = unit_id[val.tag]
            if units == 'Torr':
                units = 'torr'
            datapoint[property_id[val.tag].replace(' ', '-')] = [val.text + ' ' + units]
        datapoints.append(datapoint)

    if len(datapoints) == 0:
        raise MissingElementError('dataPoint')

    # RCM files may have a second dataGroup with volume-time history
    if len(dataGroups) == 2:
        dataGroup = dataGroups[1]
        time_tag = None
        volume_tag = None
        for prop in dataGroup.findall('property'):
            if prop.attrib['name'] == 'time':
                time_dict = {'units': prop.attrib['units'], 'column': 0}
                time_tag = prop.attrib['id']
            elif prop.attrib['name'] == 'volume':
                volume_dict = {'units': prop.attrib['units'], 'column': 1}
                volume_tag = prop.attrib['id']
            else:
                raise KeywordError('Only volume and time allowed in volume history dataGroup.')

        if time_tag is None or volume_tag is None:
            raise KeywordError('Both time and volume properties required for volume history.')
        volume_history = {'time': time_dict, 'volume': volume_dict, 'values': []}

        # collect volume-time history
        for dp in dataGroup.findall('dataPoint'):
            time = None
            volume = None
            for val in dp:
                if val.tag == time_tag:
                    time = float(val.text)
                elif val.tag == volume_tag:
                    volume = float(val.text)
                else:
                    raise KeywordError('Only volume and time values allowed in '
                                       'volume-history dataPoint.'
                                       )
            if time is None or volume is None:
                raise KeywordError('Both time and volume values required in each '
                                   'volume-history dataPoint.'
                                   )
            volume_history['values'].append([time, volume])

        datapoints[0]['volume-history'] = volume_history

    elif len(dataGroups) > 2:
        raise NotImplementedError('More than two DataGroups not supported.')

    return datapoints


def ReSpecTh_to_ChemKED(filename_xml, filename_ck='', file_author='', file_author_orcid=''):
    """Convert ReSpecTh XML file to ChemKED YAML file.

    Args:
        filename_xml (`str`): Name of ReSpecTh XML file to be converted.
        filename_ck (`str`, optional): Name of output ChemKED file to be produced.
        file_author (`str`, optional): Name to override original file author
        file_author_orcid (`str`, optional): ORCID of file author
    """
    # get all information from XML file
    tree = etree.parse(filename_xml)
    root = tree.getroot()

    # get file metadata
    properties = get_file_metadata(root)

    # get reference info
    properties['reference'] = get_reference(root)
    # Save name of original data filename
    properties['reference']['detail'] = (properties['reference'].get('detail', '') +
                                         'Converted from ReSpecTh XML file ' +
                                         os.path.basename(filename_xml)
                                         )

    # Ensure ignition delay, and get which kind of experiment
    properties.update(get_experiment_kind(root))

    # Get properties shared across the file
    properties['common-properties'] = get_common_properties(root)

    # Determine definition of ignition delay
    properties['common-properties']['ignition-type'] = get_ignition_type(root)

    # Now parse ignition delay datapoints
    properties['datapoints'] = get_datapoints(root)

    # Ensure inclusion of pressure rise or volume history matches apparatus.
    has_pres_rise = ('pressure-rise' in properties['common-properties'] or
                     any([True for dp in properties['datapoints'] if 'pressure-rise' in dp])
                     )
    if has_pres_rise and properties['apparatus']['kind'] == 'rapid compression machine':
        raise KeywordError('Pressure rise cannot be defined for RCM.')

    has_vol_hist = ('volume-history' in properties['common-properties'] or
                    any([True for dp in properties['datapoints'] if 'volume-history' in dp])
                    )
    if has_vol_hist and properties['apparatus']['kind'] == 'shock tube':
        raise KeywordError('Volume history cannot be defined for shock tube.')

    # apply any overrides
    if file_author:
        properties['reference']['detail'] += '. Original author: ' + properties['file-author']['name']
        properties['file-author']['name'] = file_author
    if file_author_orcid:
        properties['file-author']['ORCID'] = file_author_orcid

    # Now go through datapoints and apply common properties
    for idx in range(len(properties['datapoints'])):
        for prop in properties['common-properties']:
            properties['datapoints'][idx][prop] = properties['common-properties'][prop]

    # set output filename and path
    if not filename_ck:
        filename_ck = os.path.splitext(os.path.basename(filename_xml))[0] + '.yaml'

    with open(filename_ck, 'w') as outfile:
        yaml.dump(properties, outfile, default_flow_style=False)
    print('Converted to ' + filename_ck)

    # now validate
    chemked.ChemKED(yaml_file=filename_ck)


def main(argv):
    """
    """
    parser = ArgumentParser(
        description='Convert between ReSpecTh XML file and ChemKED YAML file '
                    'automatically based on file extension.'
        )
    parser.add_argument('-i', '--input',
                        type=str,
                        required=True,
                        help='Input filename (e.g., "file1.yaml" or "file2.xml")'
                        )
    parser.add_argument('-o', '--output',
                        type=str,
                        required=False,
                        default='',
                        help='Output filename (e.g., "file1.xml" or "file2.yaml")'
                        )
    parser.add_argument('-fa', '--file-author',
                        dest='file_author',
                        type=str,
                        required=False,
                        default='',
                        help='File author name to override original'
                        )
    parser.add_argument('-fo', '--file-author-orcid',
                        dest='file_author_orcid',
                        type=str,
                        required=False,
                        default='',
                        help='File author ORCID'
                        )

    args = parser.parse_args(argv)

    if os.path.splitext(args.input)[1] == '.xml' and os.path.splitext(args.output)[1] == '.yaml':
        ReSpecTh_to_ChemKED(args.input, args.output, args.file_author, args.file_author_orcid)

    elif os.path.splitext(args.input)[1] == '.yaml' and os.path.splitext(args.output)[1] == '.xml':
        c = chemked.ChemKED(yaml_file=args.input)
        c.convert_to_ReSpecTh(args.output)

    elif os.path.splitext(args.input)[1] == '.xml' and os.path.splitext(args.output)[1] == '.xml':
        raise KeywordError('Cannot convert .xml to .xml')

    elif os.path.splitext(args.input)[1] == '.yaml' and os.path.splitext(args.output)[1] == '.yaml':
        raise KeywordError('Cannot convert .yaml to .yaml')

    else:
        raise KeywordError('Input/output args need to be .xml/.yaml')


if __name__ == '__main__':
    main(sys.argv[1:])
