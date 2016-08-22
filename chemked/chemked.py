"""
Main ChemKED module
"""
from __future__ import print_function

from collections import namedtuple

import numpy as np
from cerberus import Validator
from .validation import schema, yaml
from .utils import Q_

vol_hist = namedtuple('VolumeHistory', ['time', 'volume'])
reference = namedtuple('Reference',
                       ['volume', 'journal', 'doi', 'authors', 'detail', 'year', 'pages'])
apparatus = namedtuple('Apparatus', ['kind', 'institution', 'facility'])


class ChemKED(object):
    """Main ChemKED class.
    """
    def __init__(self, yaml_file=None, dict_input=None):
        if yaml_file:
            with open(yaml_file, 'r') as f:
                properties = yaml.safe_load(f)
        elif dict_input:
            properties = dict_input

        self.validate_yaml(properties)

        self.datapoints = []
        for point in properties['datapoints']:
            self.datapoints.append(DataPoint(point))

        self.reference = reference(
            volume=properties['reference']['volume'],
            journal=properties['reference']['journal'],
            doi=properties['reference']['doi'],
            authors=properties['reference']['authors'],
            detail=properties['reference']['detail'],
            year=properties['reference']['year'],
            pages=properties['reference']['pages'],
        )

        self.apparatus = apparatus(
            kind=properties['apparatus']['kind'],
            institution=properties['apparatus']['institution'],
            facility=properties['apparatus']['facility'],
        )

        for prop in ['chemked-version', 'experiment-type', 'file-author', 'file-version']:
            setattr(self, prop.replace('-', '_'), properties[prop])

    def validate_yaml(self, properties):
        v = Validator(schema)
        if not v.validate(properties):
            for key, value in v.errors.items():
                if 'unallowed value' in value:
                    print(('{key} has an illegal value. Allowed values are {values} and are case '
                           'sensitive').format(key=key, values=schema[key]['allowed']))

            raise ValueError(v.errors)


class DataPoint(object):
    """Class for a single datapoint
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
            self.volume_history = vol_hist(
                time=Q_(values[:, time_col], time_units),
                volume=Q_(values[:, volume_col], volume_units),
            )

    def get_cantera_composition(self):
        return ', '.join(map(lambda c: '{}: {}'.format(c['species'], c['mole-fraction']),
                             self.composition))
