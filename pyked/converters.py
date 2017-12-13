"""Module with converters from other formats.
"""

# Standard libraries
import os
from argparse import ArgumentParser
from warnings import warn
import xml.etree.ElementTree as etree

from requests.exceptions import HTTPError, ConnectionError
import habanero
import pint

# Local imports
from .validation import yaml, property_units, crossref_api
from .validation import units as unit_registry
from ._version import __version__
from . import chemked

# Valid properties for ReSpecTh dataGroup
datagroup_properties = ['temperature', 'pressure', 'ignition delay',
                        'pressure rise',
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
        root (`~xml.etree.ElementTree.Element`): Root of ReSpecTh XML file

    Returns:
        properties (`dict`): Dictionary with file metadata
    """
    properties = {}

    file_author = getattr(root.find('fileAuthor'), 'text', False)
    # Test for missing attribute or empty string in the same statement
    if not file_author:
        raise MissingElementError('fileAuthor')
    else:
        properties['file-authors'] = [{'name': file_author}]

    # Default version is 0 for the ChemKED file
    properties['file-version'] = 0

    # Default ChemKED version
    properties['chemked-version'] = __version__

    return properties


def get_reference(root):
    """Read reference info from root of ReSpecTh XML file.

    Args:
        root (`~xml.etree.ElementTree.Element`): Root of ReSpecTh XML file

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
            ref = crossref_api.works(ids=ref_doi)['message']
        except (HTTPError, habanero.RequestError, ConnectionError):
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
        root (`~xml.etree.ElementTree.Element`): Root of ReSpecTh XML file

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
        root (`~xml.etree.ElementTree.Element`): Root of ReSpecTh XML file

    Returns:
        properties (`dict`): Dictionary with common properties
    """
    properties = {}

    for elem in root.iterfind('commonProperties/property'):
        name = elem.attrib['name']

        if name == 'initial composition':
            properties['composition'] = {'species': [], 'kind': None}

            for child in elem.iter('component'):
                spec = {}
                spec['species-name'] = child.find('speciesLink').attrib['preferredKey']
                units = child.find('amount').attrib['units']

                # use InChI for unique species identifier (if present)
                try:
                    spec['InChI'] = child.find('speciesLink').attrib['InChI']
                except KeyError:
                    # TODO: add InChI validator/search
                    warn('Missing InChI for species ' + spec['species-name'])
                    pass

                # If mole or mass fraction, just set value
                if units in ['mole fraction', 'mass fraction', 'mole percent']:
                    spec['amount'] = [float(child.find('amount').text)]
                elif units == 'percent':
                    # assume this means mole percent
                    warn('Assuming percent in composition means mole percent')
                    spec['amount'] = [float(child.find('amount').text)]
                    units = 'mole percent'
                elif units == 'ppm':
                    # assume molar ppm, convert to mole fraction
                    warn('Assuming molar ppm in composition and converting to mole fraction')
                    spec['amount'] = [float(child.find('amount').text) * 1.e-6]
                    units = 'mole fraction'
                elif units == 'ppb':
                    # assume molar ppb, convert to mole fraction
                    warn('Assuming molar ppb in composition and converting to mole fraction')
                    spec['amount'] = [float(child.find('amount').text) * 1.e-9]
                    units = 'mole fraction'
                else:
                    raise KeywordError('Composition units need to be one of: mole fraction, '
                                       'mass fraction, mole percent, percent, ppm, or ppb.'
                                       )

                properties['composition']['species'].append(spec)

                # check consistency of composition type
                if properties['composition']['kind'] is None:
                    properties['composition']['kind'] = units
                elif properties['composition']['kind'] != units:
                    raise KeywordError('composition units ' + units +
                                       ' not consistent with ' +
                                       properties['composition']['kind']
                                       )

        elif name in datagroup_properties:
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
        root (`~xml.etree.ElementTree.Element`): Root of ReSpecTh XML file

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
        if ign_type == 'baseline max intercept from d/dt':
            ign_type = 'd/dt max extrapolated'
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

    if ign_type not in ['max', 'd/dt max', '1/2 max', 'min', 'd/dt max extrapolated']:
        raise KeywordError(ign_type + ' not valid ignition type')

    properties['type'] = ign_type
    properties['target'] = ign_target

    return properties


def get_datapoints(root):
    """Parse datapoints with ignition delay from file.

    Args:
        root (`~xml.etree.ElementTree.Element`): Root of ReSpecTh XML file

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
    species_id = {}
    # get properties of dataGroup
    for prop in dataGroup.findall('property'):
        unit_id[prop.attrib['id']] = prop.attrib['units']
        temp_prop = prop.attrib['name']
        if temp_prop not in datagroup_properties + ['composition']:
            raise KeyError(temp_prop + ' not valid dataPoint property')
        property_id[prop.attrib['id']] = temp_prop

        if temp_prop == 'composition':
            spec = {'species-name': prop.find('speciesLink').attrib['preferredKey']}
            # use InChI for unique species identifier (if present)
            try:
                spec['InChI'] = prop.find('speciesLink').attrib['InChI']
            except KeyError:
                # TODO: add InChI validator/search
                warn('Missing InChI for species ' + spec['species-name'])
                pass
            species_id[prop.attrib['id']] = spec

    if not property_id:
        raise MissingElementError('property')

    # now get data points
    datapoints = []
    for dp in dataGroup.findall('dataPoint'):
        datapoint = {}
        if 'composition' in property_id.values():
            datapoint['composition'] = {'species': [], 'kind': None}

        for val in dp:
            # handle "regular" properties differently than composition
            if property_id.get(val.tag) in datagroup_properties:
                units = unit_id[val.tag]
                if units == 'Torr':
                    units = 'torr'
                datapoint[property_id[val.tag].replace(' ', '-')] = [val.text + ' ' + units]
            elif property_id.get(val.tag) == 'composition':
                spec = {}
                spec['species-name'] = species_id[val.tag]['species-name']
                spec['InChI'] = species_id[val.tag].get('InChI')

                units = unit_id[val.tag]
                # If mole or mass fraction, just set value
                if units in ['mole fraction', 'mass fraction', 'mole percent']:
                    spec['amount'] = [float(val.text)]
                elif units == 'percent':
                    # assume this means mole percent
                    warn('Assuming percent in composition means mole percent')
                    spec['amount'] = [float(val.text)]
                    units = 'mole percent'
                elif units == 'ppm':
                    # assume molar ppm, convert to mole fraction
                    warn('Assuming molar ppm in composition and converting to mole fraction')
                    spec['amount'] = [float(val.text) * 1.e-6]
                    units = 'mole fraction'
                elif units == 'ppb':
                    # assume molar ppb, convert to mole fraction
                    warn('Assuming molar ppb in composition and converting to mole fraction')
                    spec['amount'] = [float(val.text) * 1.e-9]
                    units = 'mole fraction'
                else:
                    raise KeywordError('composition units need to be one of: mole fraction, '
                                       'mass fraction, mole percent, percent, ppm, or ppb.'
                                       )

                # check consistency of composition type
                if datapoint['composition']['kind'] is None:
                    datapoint['composition']['kind'] = units
                elif datapoint['composition']['kind'] != units:
                    raise KeywordError(
                        'composition units ' + units +
                        ' not consistent with ' + datapoint['composition']['kind']
                        )

                datapoint['composition']['species'].append(spec)
            else:
                raise KeywordError('value missing from properties: ' + val.tag)

        datapoints.append(datapoint)

    if len(datapoints) == 0:
        raise MissingElementError('dataPoint')

    # ReSpecTh files can have other dataGroups with pressure, volume, or temperature histories
    if len(dataGroups) > 1:
        datapoints[0]['time-histories'] = []
        for dataGroup in dataGroups[1:]:
            time_tag = None
            quant_tags = []
            quant_dicts = []
            quant_types = []
            for prop in dataGroup.findall('property'):
                if prop.attrib['name'] == 'time':
                    time_dict = {'units': prop.attrib['units'], 'column': 0}
                    time_tag = prop.attrib['id']
                elif prop.attrib['name'] in ['volume', 'temperature', 'pressure']:
                    quant_types.append(prop.attrib['name'])
                    quant_dicts.append({'units': prop.attrib['units'], 'column': 1})
                    quant_tags.append(prop.attrib['id'])
                else:
                    raise KeywordError('Only volume, temperature, pressure, and time are allowed '
                                       'in a time-history dataGroup.')

            if time_tag is None or len(quant_tags) == 0:
                raise KeywordError('Both time and quantity properties required for time-history.')

            time_histories = [
                {'time': time_dict, 'quantity': q, 'type': t, 'values': []}
                for (q, t) in zip(quant_dicts, quant_types)
            ]
            # collect volume-time history
            for dp in dataGroup.findall('dataPoint'):
                time = None
                quants = {}
                for val in dp:
                    if val.tag == time_tag:
                        time = float(val.text)
                    elif val.tag in quant_tags:
                        quant = float(val.text)
                        tag_idx = quant_tags.index(val.tag)
                        quant_type = quant_types[tag_idx]
                        quants[quant_type] = quant
                    else:
                        raise KeywordError('Value tag {} not found in dataGroup tags: '
                                           '{}'.format(val.tag, quant_tags))
                if time is None or len(quants) == 0:
                    raise KeywordError('Both time and quantity values required in each '
                                       'time-history dataPoint.')
                for t in time_histories:
                    t['values'].append([time, quants[t['type']]])

            datapoints[0]['time-histories'].extend(time_histories)

    return datapoints


def ReSpecTh_to_ChemKED(filename_xml, file_author='', file_author_orcid='', *, validate=False):
    """Convert ReSpecTh XML file to ChemKED-compliant dictionary.

    Args:
        filename_xml (`str`): Name of ReSpecTh XML file to be converted.
        file_author (`str`, optional): Name to override original file author
        file_author_orcid (`str`, optional): ORCID of file author
        validate (`bool`, optional, keyword-only): Set to `True` to validate the resulting
            property dictionary with `ChemKED`. Set to `False` if the file is being loaded and will
            be validated at some other point before use.
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

    has_vol_hist = any(
        [t.get('type') == 'volume' for dp in properties['datapoints']
         for t in dp.get('time-histories', [{}])]
    )
    if has_vol_hist and properties['apparatus']['kind'] == 'shock tube':
        raise KeywordError('Volume history cannot be defined for shock tube.')

    # add any additional file authors
    if file_author_orcid and not file_author:
        raise KeywordError('If file_author_orcid is specified, file_author must be as well')

    if file_author:
        temp_author = {'name': file_author}
        if file_author_orcid:
            temp_author['ORCID'] = file_author_orcid
        properties['file-authors'].append(temp_author)

    # Now go through datapoints and apply common properties
    for idx in range(len(properties['datapoints'])):
        for prop in properties['common-properties']:
            properties['datapoints'][idx][prop] = properties['common-properties'][prop]

    if validate:
        chemked.ChemKED(dict_input=properties)

    return properties


def respth2ck(argv=None):
    """Command-line entry point for converting a ReSpecTh XML file to a ChemKED YAML file.
    """
    parser = ArgumentParser(
        description='Convert a ReSpecTh XML file to a ChemKED YAML file.'
        )
    parser.add_argument('-i', '--input',
                        type=str,
                        required=True,
                        help='Input filename (e.g., "file1.yaml")'
                        )
    parser.add_argument('-o', '--output',
                        type=str,
                        required=False,
                        default='',
                        help='Output filename (e.g., "file1.xml")'
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

    filename_ck = args.output
    filename_xml = args.input

    properties = ReSpecTh_to_ChemKED(filename_xml, args.file_author, args.file_author_orcid,
                                     validate=True)

    # set output filename and path
    if not filename_ck:
        filename_ck = os.path.join(os.path.dirname(filename_xml),
                                   os.path.splitext(os.path.basename(filename_xml))[0] + '.yaml'
                                   )

    with open(filename_ck, 'w') as outfile:
        yaml.dump(properties, outfile, default_flow_style=False)
    print('Converted to ' + filename_ck)


def ck2respth(argv=None):
    """Command-line entry point for converting a ChemKED YAML file to a ReSpecTh XML file.
    """
    parser = ArgumentParser(
        description='Convert a ChemKED YAML file to a ReSpecTh XML file.'
        )
    parser.add_argument('-i', '--input',
                        type=str,
                        required=True,
                        help='Input filename (e.g., "file1.xml")'
                        )
    parser.add_argument('-o', '--output',
                        type=str,
                        required=False,
                        default='',
                        help='Output filename (e.g., "file1.yaml")'
                        )

    args = parser.parse_args(argv)

    c = chemked.ChemKED(yaml_file=args.input)
    c.convert_to_ReSpecTh(args.output)


def main(argv=None):
    """General function for converting between ReSpecTh and ChemKED files based on extension.
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
        respth2ck(['-i', args.input, '-o', args.output, '-fa', args.file_author,
                   '-fo', args.file_author_orcid])

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
    main()
