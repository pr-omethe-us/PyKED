"""
Main ChemKED module
"""
# Standard libraries
from os.path import exists
from collections import namedtuple
from warnings import warn
from copy import deepcopy
import xml.etree.ElementTree as etree
import xml.dom.minidom as minidom

import numpy as np

# Local imports
from .validation import schema, OurValidator, yaml, Q_
from .converters import datagroup_properties, ReSpecTh_to_ChemKED

VolumeHistory = namedtuple('VolumeHistory', ['time', 'volume'])
VolumeHistory.__doc__ = 'Time history of the volume in an RCM experiment'
VolumeHistory.time.__doc__ = '(`~numpy.ndarray`): the time during the experiment'
VolumeHistory.volume.__doc__ = '(`~numpy.ndarray`): the volume during the experiment'

Reference = namedtuple('Reference',
                       ['volume', 'journal', 'doi', 'authors', 'detail', 'year', 'pages'])
Reference.__doc__ = 'Information about the article or report where the data can be found'
Reference.volume.__doc__ = '(`str`) The journal volume'
Reference.journal.__doc__ = '(`str`) The name of the journal'
Reference.doi.__doc__ = '(`str`) The Digital Object Identifier of the article'
Reference.authors.__doc__ = '(`list`) The list of authors of the article'
Reference.detail.__doc__ = '(`str`) Detail about where the data can be found in the article'
Reference.year.__doc__ = '(`str`) The year the article was published'
Reference.pages.__doc__ = '(`str`) The pages in the journal where the article was published'

Apparatus = namedtuple('Apparatus', ['kind', 'institution', 'facility'])
Apparatus.__doc__ = 'Information about the experimental apparatus used to generate the data'
Apparatus.kind.__doc__ = '(`str`) The kind of experimental apparatus'
Apparatus.institution.__doc__ = '(`str`) The institution where the experiment is located'
Apparatus.facility.__doc__ = '(`str`) The particular experimental facility at the location'

Composition = namedtuple('Composition', 'species_name InChI SMILES atomic_composition amount')


class ChemKED(object):
    """Main ChemKED class.

    The ChemKED class stores information about the contents of a ChemKED database
    file. It stores each datapoint associated with the database and provides access
    the the reference information, versions, and file author.

    Arguments:
        yaml_file (`str`, optional): The filename of the YAML database in ChemKED format.
        dict_input (`dict`, optional): A dictionary with the parsed ouput of YAML file in ChemKED
            format.
        skip_validation (`bool`, optional): Whether validation of the ChemKED should be done. Must
            be supplied as a keyword-argument.

    Attributes:
        datapoints (`list`): List of `DataPoint` objects storing each datapoint in the database.
        reference (`~collections.namedtuple`): Attributes include ``volume``, ``journal``, ``doi``,
            ``authors``, ``detail``, ``year``, and ``pages`` describing the reference from which the
            datapoints are derived.
        apparatus (`~collections.namedtuple`): Attributes include ``kind`` of experimental
            apparatus, and the ``institution`` and ``facility`` where the experimental apparatus is
            located.
        chemked_version (`str`): Version of the ChemKED database schema used in this file.
        experiment_type (`str`): Type of exeperimental data contained in this database.
        file_author (`dict`): Information about the author of the ChemKED database file.
        file_version (`str`): Version of the ChemKED database file.
        _properties (`dict`): Original dictionary read from ChemKED database file, meant for
            internal use.
    """
    def __init__(self, yaml_file=None, dict_input=None, *, skip_validation=False):
        if yaml_file is not None:
            with open(yaml_file, 'r') as f:
                self._properties = yaml.safe_load(f)
        elif dict_input is not None:
            self._properties = dict_input
        else:
            raise NameError("ChemKED needs either a YAML filename or dictionary as input.")

        if not skip_validation:
            self.validate_yaml(self._properties)

        self.datapoints = []
        for point in self._properties['datapoints']:
            self.datapoints.append(DataPoint(point))

        self.reference = Reference(
            volume=self._properties['reference'].get('volume'),
            journal=self._properties['reference'].get('journal'),
            doi=self._properties['reference'].get('doi'),
            authors=self._properties['reference'].get('authors'),
            detail=self._properties['reference'].get('detail'),
            year=self._properties['reference'].get('year'),
            pages=self._properties['reference'].get('pages'),
        )

        self.apparatus = Apparatus(
            kind=self._properties['apparatus'].get('kind'),
            institution=self._properties['apparatus'].get('institution'),
            facility=self._properties['apparatus'].get('facility'),
        )

        for prop in ['chemked-version', 'experiment-type', 'file-authors', 'file-version']:
            setattr(self, prop.replace('-', '_'), self._properties[prop])

    @classmethod
    def from_respecth(cls, filename_xml, file_author='', file_author_orcid=''):
        """Construct a ChemKED instance directly from a ReSpecTh file.

        Arguments:
            filename_xml (`str`): Filename of the ReSpecTh-formatted XML file to be imported
            file_author (`str`, optional): File author to be added to the list generated from the
                XML file
            file_author_orcid (`str`, optional): ORCID for the file author being added to the list
                of file authors

        Returns:
            `ChemKED`: Instance of the `ChemKED` class containing the data in ``filename_xml``.

        Examples:
            >>> ck = ChemKED.from_respecth('respecth_file.xml')
            >>> ck = ChemKED.from_respecth('respecth_file.xml', file_author='Bryan W. Weber')
            >>> ck = ChemKED.from_respecth('respecth_file.xml', file_author='Bryan W. Weber',
                                           file_author_orcid='0000-0000-0000-0000')
        """
        properties = ReSpecTh_to_ChemKED(filename_xml, file_author, file_author_orcid,
                                         validate=False)
        return cls(dict_input=properties)

    def validate_yaml(self, properties):
        """Validate the parsed YAML file for adherance to the ChemKED format.

        Arguments:
            properties (`dict`): Dictionary created from the parsed YAML file

        Raises:
            `ValueError`: If the YAML file cannot be validated, a `ValueError` is raised whose
                string contains the errors that are present.
        """
        validator = OurValidator(schema)
        if not validator.validate(properties):
            for key, value in validator.errors.items():
                if any(['unallowed value' in v for v in value]):
                    print(('{key} has an illegal value. Allowed values are {values} and are case '
                           'sensitive.').format(key=key, values=schema[key]['allowed']))

            raise ValueError(validator.errors)

    def get_dataframe(self, output_columns=None):
        """Get a Pandas DataFrame of the datapoints in this instance.

        Arguments:
            output_columns (`list`, optional): List of strings specifying the columns to include
                in the output DataFrame. The default is `None`, which outputs all of the
                columns. Options include (not case sensitive):

                    * ``Temperature``
                    * ``Pressure``
                    * ``Ignition Delay``
                    * ``Composition``
                    * ``Equivalence Ratio``
                    * ``Reference``
                    * ``Apparatus``
                    * ``Experiment Type``
                    * ``File Author``
                    * ``File Version``
                    * ``ChemKED Version``

                In addition, specific fields from the ``Reference`` and ``Apparatus`` attributes can
                be included by specifying the name after a colon. These options are:

                    * ``Reference:Volume``
                    * ``Reference:Journal``
                    * ``Reference:DOI``
                    * ``Reference:Authors``
                    * ``Reference:Detail``
                    * ``Reference:Year``
                    * ``Reference:Pages``
                    * ``Apparatus:Kind``
                    * ``Apparatus:Facility``
                    * ``Apparatus:Institution``

                Only the first author is printed when ``Reference`` or ``Reference:Authors`` is
                selected because the whole author list may be quite long.

        Note:
            If the Composition is selected as an output type, the composition specified in the
            `DataPoint` is used. No attempt is made to convert to a consistent basis; mole fractions
            will remain mole fractions, mass fractions will remain mass fractions, and mole percent
            will remain mole percent. Therefore, it is possible to end up with more than one type of
            composition specification in a given column. Caveat Emptor.

        Examples:
            >>> df = ChemKED(yaml_file).get_dataframe()
            >>> df = ChemKED(yaml_file).get_dataframe(['Temperature', 'Ignition Delay'])

        Returns:
            `~pandas.DataFrame`: Contains the information regarding each point in the ``datapoints``
                attribute
        """
        import pandas as pd

        valid_labels = [a.replace('_', ' ') for a in self.__dict__
                        if not (a.startswith('__') or a.startswith('_'))
                        ]
        valid_labels.remove('datapoints')
        valid_labels.extend(
            ['composition', 'ignition delay', 'temperature', 'pressure', 'equivalence ratio']
        )
        ref_index = valid_labels.index('reference')
        valid_labels[ref_index:ref_index + 1] = ['reference:' + a for a in Reference._fields]
        app_index = valid_labels.index('apparatus')
        valid_labels[app_index:app_index + 1] = ['apparatus:' + a for a in Apparatus._fields]

        species_list = list(set([s['species-name'] for d in self.datapoints for s in d.composition]))  # noqa: E501

        if output_columns is None or len(output_columns) == 0:
            col_labels = valid_labels
            comp_index = col_labels.index('composition')
            col_labels[comp_index:comp_index + 1] = species_list
        else:
            output_columns = [a.lower() for a in output_columns]
            col_labels = []
            for col in output_columns:
                if col in valid_labels or col in ['reference', 'apparatus']:
                    col_labels.append(col)
                else:
                    raise ValueError('{} is not a valid output column choice'.format(col))

            if 'composition' in col_labels:
                comp_index = col_labels.index('composition')
                col_labels[comp_index:comp_index + 1] = species_list
            if 'reference' in col_labels:
                ref_index = col_labels.index('reference')
                col_labels[ref_index:ref_index + 1] = ['reference:' + a for a in Reference._fields]
            if 'apparatus' in col_labels:
                app_index = col_labels.index('apparatus')
                col_labels[app_index:app_index + 1] = ['apparatus:' + a for a in Apparatus._fields]

        data = []
        for d in self.datapoints:
            row = []
            d_species = [s['species-name'] for s in d.composition]
            for col in col_labels:
                if col in species_list:
                    if col in d_species:
                        s_idx = d_species.index(col)
                        row.append(d.composition[s_idx]['amount'])
                    else:
                        row.append(Q_(0.0, 'dimensionless'))
                elif 'reference' in col or 'apparatus' in col:
                    split_col = col.split(':')
                    if split_col[1] == 'authors':
                        row.append(getattr(getattr(self, split_col[0]), split_col[1])[0]['name'])
                    else:
                        row.append(getattr(getattr(self, split_col[0]), split_col[1]))
                elif col in ['temperature', 'pressure', 'ignition delay', 'equivalence ratio']:
                    row.append(getattr(d, col.replace(' ', '_')))
                elif col == 'file authors':
                    row.append(getattr(self, col.replace(' ', '_'))[0]['name'])
                else:
                    row.append(getattr(self, col.replace(' ', '_')))
            data.append(row)

        col_labels = [a.title() for a in col_labels]
        columns = pd.Index(col_labels)
        return pd.DataFrame(data=data, columns=columns)

    def write_file(self, filename, *, overwrite=False):
        """Write new ChemKED YAML file based on object.

        Arguments:
            filename (`str`): Filename for target YAML file
            overwrite (`bool`, optional): Whether to overwrite file with given name if present.
                Must be supplied as a keyword-argument.

        Raises:
            `NameError`: If ``filename`` is already present, and ``overwrite`` is not ``True``.

        Example:
            >>> dataset = ChemKED(yaml_file)
            >>> dataset.write_file(new_yaml_file)
        """
        # Ensure file isn't already present
        if exists(filename) and not overwrite:
            raise OSError(filename + ' already present. Specify "overwrite=True" '
                          'to overwrite, or rename.'
                          )

        with open(filename, 'w') as yaml_file:
            yaml.dump(self._properties, yaml_file)

    def convert_to_ReSpecTh(self, filename):
        """Convert ChemKED record to ReSpecTh XML file.

        This converter uses common information in a ChemKED file to generate a
        ReSpecTh XML file. Note that some information may be lost, as ChemKED stores
        some additional attributes.

        Arguments:
            filename (`str`): Filename for output ReSpecTh XML file.

        Example:
            >>> dataset = ChemKED(yaml_file)
            >>> dataset.convert_to_ReSpecTh(xml_file)
        """
        root = etree.Element('experiment')

        file_author = etree.SubElement(root, 'fileAuthor')
        file_author.text = self.file_authors[0]['name']

        # right now ChemKED just uses an integer file version
        file_version = etree.SubElement(root, 'fileVersion')
        major_version = etree.SubElement(file_version, 'major')
        major_version.text = str(self.file_version)
        minor_version = etree.SubElement(file_version, 'minor')
        minor_version.text = '0'

        respecth_version = etree.SubElement(root, 'ReSpecThVersion')
        major_version = etree.SubElement(respecth_version, 'major')
        major_version.text = '1'
        minor_version = etree.SubElement(respecth_version, 'minor')
        minor_version.text = '0'

        # Only ignition delay currently supported
        exp = etree.SubElement(root, 'experimentType')
        if self.experiment_type == 'ignition delay':
            exp.text = 'Ignition delay measurement'
        else:
            raise NotImplementedError('Only ignition delay type supported for conversion.')

        reference = etree.SubElement(root, 'bibliographyLink')
        citation = ''
        for author in self.reference.authors:
            citation += author['name'] + ', '
        citation += (self.reference.journal + ' (' + str(self.reference.year) + ') ' +
                     str(self.reference.volume) + ':' + self.reference.pages + '. ' +
                     self.reference.detail
                     )
        reference.set('preferredKey', citation)
        reference.set('doi', self.reference.doi)

        apparatus = etree.SubElement(root, 'apparatus')
        kind = etree.SubElement(apparatus, 'kind')
        kind.text = self.apparatus.kind

        common_properties = etree.SubElement(root, 'commonProperties')
        # ChemKED objects have no common properties once loaded. Check for properties
        # among datapoints that tend to be common
        common = []
        composition = self.datapoints[0].composition

        # Composition type *has* to be the same
        composition_type = self.datapoints[0].composition_type
        if not all(dp.composition_type == composition_type for dp in self.datapoints):
            raise NotImplementedError('Error: ReSpecTh does not support varying composition '
                                      'type among datapoints.'
                                      )

        if all([composition == dp.composition for dp in self.datapoints]):
            # initial composition is common
            common.append('composition')
            prop = etree.SubElement(common_properties, 'property')
            prop.set('name', 'initial composition')

            for species in composition:
                component = etree.SubElement(prop, 'component')
                species_link = etree.SubElement(component, 'speciesLink')
                species_link.set('preferredKey', species['species-name'])
                if species.get('InChI') is not None:
                    species_link.set('InChI', species['InChI'])

                amount = etree.SubElement(component, 'amount')
                amount.set('units', composition_type)
                amount.text = str(species['amount'].magnitude)

        # If multiple datapoints present, then find any common properties. If only
        # one datapoint, then composition should be the only "common" property.
        if len(self.datapoints) > 1:
            for prop_name in datagroup_properties:
                attribute = prop_name.replace(' ', '_')
                quantities = [getattr(dp, attribute, False) for dp in self.datapoints]

                # All quantities must have the property in question and all the
                # values must be equal
                if all(quantities) and quantities.count(quantities[0]) == len(quantities):
                    common.append(prop_name)
                    prop = etree.SubElement(common_properties, 'property')
                    prop.set('description', '')
                    prop.set('name', prop_name)
                    prop.set('units', str(quantities[0].units))

                    value = etree.SubElement(prop, 'value')
                    value.text = str(quantities[0].magnitude)

        # Ignition delay can't be common, unless only a single datapoint.

        datagroup = etree.SubElement(root, 'dataGroup')
        datagroup.set('id', 'dg1')
        datagroup_link = etree.SubElement(datagroup, 'dataGroupLink')
        datagroup_link.set('dataGroupID', '')
        datagroup_link.set('dataPointID', '')

        property_idx = {}
        labels = {'temperature': 'T', 'pressure': 'P',
                  'ignition delay': 'tau', 'pressure rise': 'dP/dt',
                  }

        for prop_name in datagroup_properties:
            attribute = prop_name.replace(' ', '_')
            # This can't be hasattr because properties are set to the value None
            # if no value is specified in the file, so the attribute always exists
            prop_indices = [i for i, dp in enumerate(self.datapoints)
                            if getattr(dp, attribute) is not None
                            ]
            if prop_name in common or not prop_indices:
                continue

            prop = etree.SubElement(datagroup, 'property')
            prop.set('description', '')
            prop.set('name', prop_name)
            units = str(getattr(self.datapoints[prop_indices[0]], attribute).units)
            prop.set('units', units)
            idx = 'x{}'.format(len(property_idx) + 1)
            property_idx[idx] = {'name': prop_name, 'units': units}
            prop.set('id', idx)
            prop.set('label', labels[prop_name])

        # Need to handle datapoints with possibly different species in the initial composition
        if 'composition' not in common:
            for dp in self.datapoints:
                for species in dp.composition:
                    # Only add new property for species not already considered
                    has_spec = any([species['species-name'] in d.values()
                                    for d in property_idx.values()
                                    ])
                    if not has_spec:
                        prop = etree.SubElement(datagroup, 'property')
                        prop.set('description', '')

                        idx = 'x{}'.format(len(property_idx) + 1)
                        property_idx[idx] = {'name': species['species-name']}
                        prop.set('id', idx)
                        prop.set('label', '[' + species['species-name'] + ']')
                        prop.set('name', 'composition')
                        prop.set('units', self.datapoints[0].composition_type)

                        species_link = etree.SubElement(prop, 'speciesLink')
                        species_link.set('preferredKey', species['species-name'])
                        if species.get('InChI'):
                            species_link.set('InChI', species['InChI'])

        for dp in self.datapoints:
            datapoint = etree.SubElement(datagroup, 'dataPoint')
            for idx, val in property_idx.items():
                # handle regular properties a bit differently than composition
                if val['name'] in datagroup_properties:
                    value = etree.SubElement(datapoint, idx)
                    quantity = getattr(dp, val['name'].replace(' ', '_')).to(val['units'])
                    value.text = str(quantity.magnitude)
                else:
                    # composition
                    for item in dp.composition:
                        if item['species-name'] == val['name']:
                            value = etree.SubElement(datapoint, idx)
                            value.text = str(item['amount'].magnitude)

        # if RCM and has volume history, need a second dataGroup
        has_volume_history = any([dp.volume_history is not None for dp in self.datapoints])
        if len(self.datapoints) > 1 and has_volume_history:
            raise NotImplementedError('Error: ReSpecTh files do not support multiple datapoints '
                                      'with a volume history.'
                                      )

        elif self.datapoints[0].volume_history is not None:
            datagroup = etree.SubElement(root, 'dataGroup')
            datagroup.set('id', 'dg2')
            datagroup_link = etree.SubElement(datagroup, 'dataGroupLink')
            datagroup_link.set('dataGroupID', '')
            datagroup_link.set('dataPointID', '')

            # Volume history has two properties: time and volume.
            volume_history = self.datapoints[0].volume_history
            prop = etree.SubElement(datagroup, 'property')
            prop.set('description', '')
            prop.set('name', 'time')
            prop.set('units', str(volume_history.time.units))
            time_idx = 'x{}'.format(len(property_idx) + 1)
            prop.set('id', time_idx)
            prop.set('label', 't')

            prop = etree.SubElement(datagroup, 'property')
            prop.set('description', '')
            prop.set('name', 'volume')
            prop.set('units', str(volume_history.volume.units))
            volume_idx = 'x{}'.format(len(property_idx) + 2)
            prop.set('id', volume_idx)
            prop.set('label', 'V')

            for time, volume in zip(volume_history.time, volume_history.volume):
                datapoint = etree.SubElement(datagroup, 'dataPoint')
                value = etree.SubElement(datapoint, time_idx)
                value.text = str(time.magnitude)
                value = etree.SubElement(datapoint, volume_idx)
                value.text = str(volume.magnitude)

        ign_types = [getattr(dp, 'ignition_type', False) for dp in self.datapoints]
        # All datapoints must have the same ignition target and type
        if all(ign_types) and ign_types.count(ign_types[0]) == len(ign_types):
            # In ReSpecTh files all datapoints must share ignition type
            ignition = etree.SubElement(root, 'ignitionType')
            if ign_types[0]['target'] in ['pressure', 'temperature']:
                ignition.set('target', ign_types[0]['target'][0].upper())
            else:
                # options left are species
                ignition.set('target', self.datapoints[0].ignition_type['target'])
            if ign_types[0]['type'] == 'd/dt max extrapolated':
                ignition.set('type', 'baseline max intercept from d/dt')
            else:
                ignition.set('type', self.datapoints[0].ignition_type['type'])
        else:
            raise NotImplementedError('Different ignition targets or types for multiple datapoints '
                                      'are not supported in ReSpecTh.')

        et = etree.ElementTree(root)
        et.write(filename, encoding='utf-8', xml_declaration=True)

        # now do a "pretty" rewrite
        xml = minidom.parse(filename)
        xml_string = xml.toprettyxml(indent='    ')
        with open(filename, 'w') as f:
            f.write(xml_string)

        print('Converted to ' + filename)


class DataPoint(object):
    """Class for a single datapoint.

    The `DataPoint` class stores the information associated with a single data point in the dataset
    parsed from the `ChemKED` YAML input.

    Arguments:
        properties (`dict`): Dictionary adhering to the ChemKED format for ``datapoints``

    Attributes:
        composition (`list`): List of dictionaries representing the species and their quantities
        ignition_delay (pint.Quantity): The ignition delay of the experiment
        temperature (pint.Quantity): The temperature of the experiment
        pressure (pint.Quantity): The pressure of the experiment
        pressure_rise (pint.Quantity, optional): The amount of pressure rise during the induction
            period of a shock tube experiment.
        compression_time (pint.Quantity, optional): The compression time for an RCM experiment.
        compressed_pressure (pint.Quantity, optional): The pressure at the end of compression for
            an RCM experiment.
        compressed_temperature (pint.Quantity, optional): The temperature at the end of compression
            for an RCM experiment.
        first_stage_ignition_delay (pint.Quantity, optional): The first stage ignition delay of the
            experiment.
        compression_time (pint.Quantity, optional): The compression time for an RCM experiment.
        ignition_type (`dict`): Dictionary with the ignition target and type.
        volume_history (`~collections.namedtuple`, optional): The volume history of the reactor
            during an RCM experiment.
    """
    def __init__(self, properties):
        value_unit_props = [
            'ignition-delay', 'temperature', 'pressure', 'pressure-rise', 'compression-time',
            'compressed-temperature', 'compressed-pressure', 'first-stage-ignition-delay',
        ]
        for prop in value_unit_props:
            if prop in properties:
                quant = Q_(properties[prop][0])
                if len(properties[prop]) > 1:
                    unc = properties[prop][1]
                    uncertainty = unc.get('uncertainty', False)
                    upper_uncertainty = unc.get('upper-uncertainty', False)
                    lower_uncertainty = unc.get('lower-uncertainty', False)
                    uncertainty_type = unc.get('uncertainty-type')
                    if uncertainty_type == 'relative':
                        if uncertainty:
                            quant = quant.plus_minus(float(uncertainty), relative=True)
                        elif upper_uncertainty and lower_uncertainty:
                            warn('Asymmetric uncertainties are not supported. The '
                                 'maximum of lower-uncertainty and upper-uncertainty '
                                 'has been used as the symmetric uncertainty.')
                            uncertainty = max(float(upper_uncertainty), float(lower_uncertainty))
                            quant = quant.plus_minus(uncertainty, relative=True)
                        else:
                            raise ValueError('Either "uncertainty" or "upper-uncertainty" and '
                                             '"lower-uncertainty" need to be specified.')
                    elif uncertainty_type == 'absolute':
                        if uncertainty:
                            uncertainty = Q_(uncertainty)
                            quant = quant.plus_minus(uncertainty.to(quant.units).magnitude)
                        elif upper_uncertainty and lower_uncertainty:
                            warn('Asymmetric uncertainties are not supported. The '
                                 'maximum of lower-uncertainty and upper-uncertainty '
                                 'has been used as the symmetric uncertainty.')
                            uncertainty = max(Q_(upper_uncertainty), Q_(lower_uncertainty))
                            quant = quant.plus_minus(uncertainty.to(quant.units).magnitude)
                        else:
                            raise ValueError('Either "uncertainty" or "upper-uncertainty" and '
                                             '"lower-uncertainty" need to be specified.')
                    else:
                        raise ValueError('uncertainty-type must be one of "absolute" or "relative"')

                setattr(self, prop.replace('-', '_'), quant)
            else:
                setattr(self, prop.replace('-', '_'), None)

        self.composition_type = properties['composition']['kind']
        # composition = deepcopy(properties['composition']['species'])
        composition = []
        for spec in properties['composition']['species']:
            species_name = spec['species-name']
            amount = spec['amount']
            InChI = spec.get('InChI')
            SMILES = spec.get('SMILES')
            atomic_composition = spec.get('atomic-composition')
            composition.append(Composition(species_name=species_name, InChI=InChI, SMILES=SMILES, atomic_composition=atomic_composition, amount=amount))
        print(composition)
        for idx, species in enumerate(composition):
            quant = Q_(species.amount[0])
            if len(species.amount) > 1:
                unc = species.amount[1]
                uncertainty = unc.get('uncertainty', False)
                upper_uncertainty = unc.get('upper-uncertainty', False)
                lower_uncertainty = unc.get('lower-uncertainty', False)
                uncertainty_type = unc.get('uncertainty-type')
                if uncertainty_type == 'relative':
                    if uncertainty:
                        quant = quant.plus_minus(float(uncertainty), relative=True)
                    elif upper_uncertainty and lower_uncertainty:
                        warn('Asymmetric uncertainties are not supported. The '
                             'maximum of lower-uncertainty and upper-uncertainty '
                             'has been used as the symmetric uncertainty.')
                        uncertainty = max(float(upper_uncertainty), float(lower_uncertainty))
                        quant = quant.plus_minus(uncertainty, relative=True)
                    else:
                        raise ValueError('Either "uncertainty" or "upper-uncertainty" and '
                                         '"lower-uncertainty" need to be specified.')
                elif uncertainty_type == 'absolute':
                    if uncertainty:
                        uncertainty = Q_(uncertainty)
                        quant = quant.plus_minus(uncertainty.to(quant.units).magnitude)
                    elif upper_uncertainty and lower_uncertainty:
                        warn('Asymmetric uncertainties are not supported. The '
                             'maximum of lower-uncertainty and upper-uncertainty '
                             'has been used as the symmetric uncertainty.')
                        uncertainty = max(Q_(upper_uncertainty), Q_(lower_uncertainty))
                        quant = quant.plus_minus(uncertainty.to(quant.units).magnitude)
                    else:
                        raise ValueError('Either "uncertainty" or "upper-uncertainty" and '
                                         '"lower-uncertainty" need to be specified.')
                else:
                    raise ValueError('uncertainty-type must be one of "absolute" or "relative"')

            #composition[idx]['amount'] = quant

            setattr(self, 'composition', composition)

        self.equivalence_ratio = properties.get('equivalence-ratio')
        self.ignition_type = deepcopy(properties.get('ignition-type'))

        if 'volume-history' in properties:
            time_col = properties['volume-history']['time']['column']
            time_units = properties['volume-history']['time']['units']
            volume_col = properties['volume-history']['volume']['column']
            volume_units = properties['volume-history']['volume']['units']
            values = np.array(properties['volume-history']['values'])
            self.volume_history = VolumeHistory(
                time=Q_(values[:, time_col], time_units),
                volume=Q_(values[:, volume_col], volume_units),
            )
        else:
            self.volume_history = None

    def get_cantera_composition_string(self, species_conversion=None):
        """Get the composition in a string format suitable for input to Cantera.

        Returns a formatted string no matter the type of composition. As such, this method
        is not recommended for end users; instead, prefer the `get_cantera_mole_fraction`
        or `get_cantera_mass_fraction` methods.

        Arguments:
            species_conversion (`dict`, optional): Mapping of species identifier to a
                species name. This argument should be supplied when the name of the
                species in the ChemKED YAML file does not match the name of the same
                species in a chemical kinetic mechanism. The species identifier (the key
                of the mapping) can be the name, InChI, or SMILES provided in the ChemKED
                file, while the value associated with a key should be the desired name in
                the Cantera format output string.

        Returns:
            `str`: String in the ``SPEC:AMT, SPEC:AMT`` format

        Raises:
            `ValueError`: If the composition type of the `DataPoint` is not one of
                ``'mass fraction'``, ``'mole fraction'``, or ``'mole percent'``
        """
        if self.composition_type in ['mole fraction', 'mass fraction']:
            factor = 1.0
        elif self.composition_type == 'mole percent':
            factor = 100.0
        else:
            raise ValueError('Unknown composition type: {}'.format(self.composition_type))

        if species_conversion is None:
            comps = ['{!s}:{:.4e}'.format(c['species-name'],
                     c['amount'].magnitude/factor) for c in self.composition]
        else:
            comps = []
            for c in self.composition:
                amount = c['amount'].magnitude/factor
                idents = [c.get(s) for s in ['species-name', 'InChI', 'SMILES'] if c.get(s, False)]
                present = [i in species_conversion for i in idents]
                if not any(present):
                    comps.append('{!s}:{:.4e}'.format(c['species-name'], amount))
                else:
                    if len([i for i in present if i]) > 1:
                        raise ValueError('More than one conversion present for species {}'.format(
                                         c['species-name']))

                    ident = idents[present.index(True)]
                    species_replacement_name = species_conversion.pop(ident)
                    comps.append('{!s}:{:.4e}'.format(species_replacement_name, amount))

            if len(species_conversion) > 0:
                raise ValueError('Unknown species in conversion: {}'.format(species_conversion))

        return ', '.join(comps)

    def get_cantera_mole_fraction(self, species_conversion=None):
        """Get the mole fractions in a string format suitable for input to Cantera.

        Arguments:
            species_conversion (`dict`, optional): Mapping of species identifier to a
                species name. This argument should be supplied when the name of the
                species in the ChemKED YAML file does not match the name of the same
                species in a chemical kinetic mechanism. The species identifier (the key
                of the mapping) can be the name, InChI, or SMILES provided in the ChemKED
                file, while the value associated with a key should be the desired name in
                the Cantera format output string.

        Returns:
            `str`: String of mole fractions in the ``SPEC:AMT, SPEC:AMT`` format

        Raises:
            `ValueError`: If the composition type is ``'mass fraction'``, the conversion cannot
                be done because no molecular weight information is known

        Examples:
            >>> dp = DataPoint(properties)
            >>> dp.get_cantera_mole_fraction()
            'H2:4.4400e-03, O2:5.5600e-03, Ar:9.9000e-01'
            >>> species_conversion = {'H2': 'h2', 'O2': 'o2'}
            >>> dp.get_cantera_mole_fraction(species_conversion)
            'h2:4.4400e-03, o2:5.5600e-03, Ar:9.9000e-01'
            >>> species_conversion = {'1S/H2/h1H': 'h2', '1S/O2/c1-2': 'o2'}
            >>> dp.get_cantera_mole_fraction(species_conversion)
            'h2:4.4400e-03, o2:5.5600e-03, Ar:9.9000e-01'
        """
        if self.composition_type == 'mass fraction':
            raise ValueError('Cannot get mole fractions from the given composition.\n'
                             '{}'.format(self.composition))
        else:
            return self.get_cantera_composition_string(species_conversion)

    def get_cantera_mass_fraction(self, species_conversion=None):
        """Get the mass fractions in a string format suitable for input to Cantera.

        Arguments:
            species_conversion (`dict`, optional): Mapping of species identifier to a
                species name. This argument should be supplied when the name of the
                species in the ChemKED YAML file does not match the name of the same
                species in a chemical kinetic mechanism. The species identifier (the key
                of the mapping) can be the name, InChI, or SMILES provided in the ChemKED
                file, while the value associated with a key should be the desired name in
                the Cantera format output string.

        Returns:
            `str`: String of mass fractions in the ``SPEC:AMT, SPEC:AMT`` format

        Raises:
            `ValueError`: If the composition type is ``'mole fraction'`` or
                ``'mole percent'``, the conversion cannot be done because no molecular
                weight information is known

        Examples:
            >>> dp = DataPoint(properties)
            >>> dp.get_cantera_mass_fraction()
            'H2:2.2525e-04, O2:4.4775e-03, Ar:9.9530e-01'
            >>> species_conversion = {'H2': 'h2', 'O2': 'o2'}
            >>> dp.get_cantera_mass_fraction(species_conversion)
            'h2:2.2525e-04, o2:4.4775e-03, Ar:9.9530e-01'
            >>> species_conversion = {'1S/H2/h1H': 'h2', '1S/O2/c1-2': 'o2'}
            >>> dp.get_cantera_mass_fraction(species_conversion)
            'h2:2.2525e-04, o2:4.4775e-03, Ar:9.9530e-01'
        """
        if self.composition_type in ['mole fraction', 'mole percent']:
            raise ValueError('Cannot get mass fractions from the given composition.\n'
                             '{}'.format(self.composition)
                             )
        else:
            return self.get_cantera_composition_string(species_conversion)
