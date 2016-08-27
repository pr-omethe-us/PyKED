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
                quant = Q_(properties[prop]['value'], properties[prop]['units'])
                setattr(self, prop.replace('-', '_'), quant)

        self.composition = properties['composition']
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

    def get_cantera_composition(self):
        """Get the composition in a string format suitable for input to Cantera.

        Returns:
            str: String in the ``SPEC: AMT, SPEC: AMT`` format
        """
        return ', '.join(map(lambda c: '{}: {}'.format(c['species'], c['mole-fraction']),
                             self.composition))
