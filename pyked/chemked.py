"""
Main ChemKED module
"""
# Python 2 compatibility
from __future__ import print_function

from collections import namedtuple

import numpy as np

# Local imports
from .validation import schema, OurValidator, yaml
from .utils import Q_

VolumeHistory = namedtuple('VolumeHistory', ['time', 'volume'])
Reference = namedtuple('Reference',
                       ['volume', 'journal', 'doi', 'authors', 'detail', 'year', 'pages'])
Apparatus = namedtuple('Apparatus', ['kind', 'institution', 'facility'])


class ChemKED(object):
    """Main ChemKED class.

    The ChemKED class stores information about the contents of a ChemKED database
    file. It stores each datapoint associated with the database and provides access
    the the reference information, versions, and file author.

    Args:
        yaml_file (str, optional): The filename of the YAML database in ChemKED format.
        dict_input (str, optional): A dictionary with the parsed ouput of YAML file in ChemKED
            format.

    Attributes:
        datapoints (list): List of `DataPoint` objects storing each datapoint in the database.
        reference (namedtuple): Attributes include ``volume``, ``journal``, ``doi``, ``authors``,
            ``detail``, ``year``, and ``pages`` describing the reference from which the datapoints
            are derived.
        apparatus (namedtuple): Attributes include ``kind`` of experimental apparatus, and the
            ``institution`` and ``facility`` where the experimental apparatus is located.
        chemked_version (str): Version of the ChemKED database schema used in this file.
        experiment_type (str): Type of exeperimental data contained in this database.
        file_author (dict): Information about the author of the ChemKED database file.
        file_version (str): Version of the ChemKED database file.
    """
    def __init__(self, yaml_file=None, dict_input=None):
        if yaml_file is not None:
            with open(yaml_file, 'r') as f:
                properties = yaml.safe_load(f)
        elif dict_input is not None:
            properties = dict_input
        else:
            raise NameError("ChemKED needs either a YAML filename or dictionary as input.")

        self.validate_yaml(properties)

        self.datapoints = []
        for point in properties['datapoints']:
            self.datapoints.append(DataPoint(point))

        self.reference = Reference(
            volume=properties['reference'].get('volume'),
            journal=properties['reference'].get('journal'),
            doi=properties['reference'].get('doi'),
            authors=properties['reference'].get('authors'),
            detail=properties['reference'].get('detail'),
            year=properties['reference'].get('year'),
            pages=properties['reference'].get('pages'),
        )

        self.apparatus = Apparatus(
            kind=properties['apparatus'].get('kind'),
            institution=properties['apparatus'].get('institution'),
            facility=properties['apparatus'].get('facility'),
        )

        for prop in ['chemked-version', 'experiment-type', 'file-author', 'file-version']:
            setattr(self, prop.replace('-', '_'), properties[prop])

    def validate_yaml(self, properties):
        """Validate the parsed YAML file for adherance to the ChemKED format.

        Arguments:
            properties (dict): Dictionary created from the parsed YAML file

        Raises:
            ValueError: If the YAML file cannot be validated, a ``ValueError`` is raised whose
                string contains the errors that are present.
        """
        validator = OurValidator(schema)
        if not validator.validate(properties):
            for key, value in validator.errors.items():
                if 'unallowed value' in value:
                    print(('{key} has an illegal value. Allowed values are {values} and are case '
                           'sensitive').format(key=key, values=schema[key]['allowed']))

            raise ValueError(validator.errors)

    def get_dataframe(self, output_columns=None):
        """Get a Pandas DataFrame of the datapoints in this instance.

        Arguments:
            output_columns (list, optional): List of strings specifying the columns to include
                in the output DataFrame. The default is ``None``, which outputs all of the
                columns. Options include (not case sensitive):
                    * Temperature
                    * Pressure
                    * Ignition Delay
                    * Composition
                    * Equivalence Ratio
                    * Reference
                    * Apparatus
                    * Experiment Type
                    * File Author
                    * File Version
                    * ChemKED Version
                In addition, specific fields from the Reference and Apparatus attributes can
                be included by specifying the name after a colon. These options are:
                    * Reference:Volume
                    * Reference:Journal
                    * Reference:DOI
                    * Reference:Authors
                    * Reference:Detail
                    * Reference:Year
                    * Reference:Pages
                    * Apparatus:Kind
                    * Apparatus:Facility
                    * Apparatus:Institution
                Only the first author is printed when ``Reference`` or ``Reference:Authors`` is
                selected because the whole author list may be quite long.

        Examples:
            >>> df = ChemKED(yaml_file).get_dataframe()
            >>> df = ChemKED(yaml_file).get_dataframe(['Temperature', 'Ignition Delay'])

        Returns:
            DataFrame: Contains the information regarding each point in the ``datapoints`` attribute
        """
        import pandas as pd

        valid_labels = [a.replace('_', ' ') for a in self.__dict__ if not a.startswith('__')]
        valid_labels.remove('datapoints')
        valid_labels.extend(
            ['composition', 'ignition delay', 'temperature', 'pressure', 'equivalence ratio']
        )
        ref_index = valid_labels.index('reference')
        valid_labels[ref_index:ref_index + 1] = ['reference:' + a for a in Reference._fields]
        app_index = valid_labels.index('apparatus')
        valid_labels[app_index:app_index + 1] = ['apparatus:' + a for a in Apparatus._fields]

        species_list = list(set([s['species-name'] for d in self.datapoints for s in d.composition]))

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
            for col in col_labels:
                if col in species_list:
                    for s in d.composition:
                        if col == s['species-name']:
                            row.append(s['mole-fraction'])
                elif 'reference' in col or 'apparatus' in col:
                    split_col = col.split(':')
                    if split_col[1] == 'authors':
                        row.append(getattr(getattr(self, split_col[0]), split_col[1])[0]['name'])
                    else:
                        row.append(getattr(getattr(self, split_col[0]), split_col[1]))
                elif col in ['temperature', 'pressure', 'ignition delay', 'equivalence ratio']:
                    row.append(getattr(d, col.replace(' ', '_')))
                elif col == 'file author':
                    row.append(getattr(self, col.replace(' ', '_'))['name'])
                else:
                    row.append(getattr(self, col.replace(' ', '_')))
            data.append(row)

        col_labels = [a.title() for a in col_labels]
        columns = pd.Index(col_labels)
        return pd.DataFrame(data=data, columns=columns)


class DataPoint(object):
    """Class for a single datapoint.

    The DataPoint class stores the information associated with a single data point in the dataset
    parsed from the ChemKED YAML input.

    Arguments:
        properties (dict): Dictionary adhering to the ChemKED format for ``datapoints``

    Attributes:
        composition (list): List of dictionaries representing the species and their quantities
        ignition_delay (pint.Quantity): The ignition delay of the experiment
        temperature (pint.Quantity): The temperature of the experiment
        pressure (pint.Quantity): The pressure of the experiment
        pressure_rise (pint.Quantity, optional): The amount of pressure rise during the induction
            period of a shock tube experiment.
        volume_history (namedtuple, optional): The volume history of the reactor during an RCM
            experiment.
    """
    def __init__(self, properties):
        for prop in ['ignition-delay', 'temperature', 'pressure', 'pressure-rise']:
            if prop in properties:
                quant = Q_(properties[prop])
                setattr(self, prop.replace('-', '_'), quant)
            else:
                setattr(self, prop.replace('-', '_'), None)

        self.composition = properties['composition']
        self.composition_type = set([q for q in ['mole-fraction', 'mass-fraction', 'mole-percent']
                                     for species in self.composition if q in species])
        if len(self.composition_type) > 1:
            raise TypeError('More than one of mole-fraction, mass-fraction, or mole-percent '
                            'were specified in the data point.\n{}'.format(self.composition))
        self.composition_type = self.composition_type.pop()
        comp_sum = np.sum([species.get(self.composition_type) for species in self.composition])
        if self.composition_type == 'mole-percent':
            if not np.isclose(comp_sum, 100.0):
                raise ValueError('mole-percent for the data point do not sum to '
                                 '100.0.\n{}'.format(self.composition))
        else:
            if not np.isclose(comp_sum, 1.0):
                raise ValueError('{} for the data point do not sum to '
                                 '1.0.\n{}'.format(self.composition_type, self.composition))

        self.equivalence_ratio = properties.get('equivalence-ratio')

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

    def get_cantera_composition(self):
        """Get the composition in a string format suitable for input to Cantera.

        Returns:
            str: String in the ``SPEC: AMT, SPEC: AMT`` format
        """
        return ', '.join(map(lambda c: '{}: {}'.format(c['species-name'], c['mole-fraction']),
                             self.composition))
