"""

.. moduleauthor:: Kyle Niemeyer <kyle.niemeyer@gmail.com>
"""
from __future__ import print_function

import datetime

import pint

now = datetime.datetime.now()
units = pint.UnitRegistry()

units.define('cm3 = centimeter**3')

get_temp_unit = {'K': 'kelvin',
                 'C': 'degC',
                 'F': 'degF',
                 'R': 'degR'
                 }

# YAML schema for ChemKED YAML files
schema = {
    'file-author': {'type': 'dict', 'required': True, 'schema': {  # TODO: DRY about the attributes a person can have
        'name': {'type': 'string', 'required': True},
        'ORCID': {'type': 'string'},  # TODO: Write ORCID validator
        }
    },
    'file-version': {'type': 'string', 'required': True},
    'chemked-version': {'type': 'string', 'required': True, 'allowed': '0.0.1'},  # TODO: Implement proper version comparison
    'reference': {'type': 'dict', 'required': True, 'schema': {
        'doi': {'type': 'string'},  # TODO: Write DOI validator
        'authors': {'type': 'list', 'schema': {'type': 'dict', 'schema': {
            'name': {'type': 'string', 'required': True},
            'ORCID': {'type': 'string'},
            },
        }},
        'journal': {'type': 'string', 'required': True},
        'year': {'type': 'integer', 'min': 1600, 'max': now.year + 1, 'required': True},
        'volume': {'type': 'integer', 'min': 0, 'required': True},
        'pages': {'type': 'string', 'required': True},
        'detail': {'type': 'string'},
        },
    },
    'apparatus': {'type': 'dict', 'required': True, 'schema': {
        'kind': {'type': 'string', 'required': True, 'allowed': ['shock tube', 'rapid compression machine']},
        'institution': {'type': 'string'},
        'facility': {'type': 'string'},
        },
    },
    'common-properties': {'type': 'dict', 'schema': {  # TODO: DRY with these options
        'pressure': {'type': 'dict', 'schema': {
            'value': {'type': 'float', 'min': 0.0, 'required': True},  # TODO: Write unit validator
            'units': {'type': 'string', 'required': True},  # TODO: Write unit validator
            },
        },
        'composition': {'type': 'list', 'schema': {'type': 'dict', 'schema': {
            'species': {'type': 'string', 'required': True},
            'InChI': {'type': 'string', 'required': True},  # TODO: Write InChI validator
            'mole-fraction': {'type': 'float', 'required': True},  # TODO: Allow mass fraction
            },
        }},
        'ignition-type': {'type': 'dict', 'schema': {
            'target': {'type': 'string', 'required': True},
            'type': {'type': 'string', 'allowed': ['d/dt max', 'max', 'min'], 'required': True}
            },
        },
        'pressure-rise': {'type': 'dict', 'schema': {
            'value': {'type': 'float', 'required': True, 'min': 0.0},  # TODO: Write unit validator
            'units': {'type': 'string', 'required': True},  # TODO: Write unit validator
            },
        },
    }},
    'datapoints': {'type': 'list', 'required': True, 'schema': {'type': 'dict', 'schema': {
        'temperature': {'type': 'dict', 'required': True, 'schema': {
            'value': {'type': 'float', 'required': True, 'min': 0.0, 'max': 5000.0},  # TODO: Write unit validator
            'units': {'type': 'string', 'required': True},  # TODO: Write unit validator
            }},
        'ignition-delay': {'type': 'dict', 'schema': {
            'value': {'type': 'float', 'required': True, 'min': 0.0},  # TODO: Write unit validator
            'units': {'type': 'string', 'required': True},  # TODO: Write unit validator
            },
        },
        'pressure': {'type': 'dict', 'schema': {
            'value': {'type': 'float', 'min': 0.0, 'required': True},  # TODO: Write unit validator
            'units': {'type': 'string', 'required': True},  # TODO: Write unit validator
            },
        },
        'composition': {'type': 'list', 'schema': {'type': 'dict', 'schema': {
            'species': {'type': 'string', 'required': True},
            'InChI': {'type': 'string', 'required': True},  # TODO: Write InChI validator
            'mole-fraction': {'type': 'float', 'required': True},  # TODO: Allow mass fraction
            },
        }},
        'ignition-type': {'type': 'dict', 'schema': {
            'target': {'type': 'string', 'required': True},
            'type': {'type': 'string', 'allowed': ['d/dt max', 'max', 'min'], 'required': True}
            },
        },
        'compression-time': {'type': 'dict', 'schema': {
            'value': {'type': 'float', 'required': True, 'min': 0.0},  # TODO: Write unit validator
            'units': {'type': 'string', 'required': True},  # TODO: Write unit validator
            },
        },
        'volume-history': {'type': 'dict', 'schema': {
            'time': {'type': 'dict', 'required': True, 'schema': {
                'units': {'type': 'string', 'required': True},  # TODO: Write unit validator
                'column': {'type': 'integer', 'required': True},
                },
            },
            'volume': {'type': 'dict', 'required': True, 'schema': {
                'units': {'type': 'string', 'required': True},  # TODO: Write unit validator
                'column': {'type': 'integer', 'required': True},
                },
            },
            'values': {'type': 'list', 'schema': {'type': 'list', 'items': [{'type': 'float'}, {'type': 'float'}]}},
            },
        },
        'pressure-rise': {'type': 'dict', 'schema': {
            'value': {'type': 'float', 'required': True, 'min': 0.0},  # TODO: Write unit validator
            'units': {'type': 'string', 'required': True},  # TODO: Write unit validator
            },
        },
    }},
    },
    'experiment-type': {'type': 'string', 'required': True, 'allowed': ['ignition delay']},
}

# Unique InChI identifier for species
SPEC_KEY = {'1S/C7H16/c1-3-5-7-6-4-2/h3-7H2,1-2H3': 'nC7H16',
            '1S/C8H18/c1-7(2)6-8(3,4)5/h7H,6H2,1-5H3': 'iC8H18',
            '1S/C7H8/c1-7-5-3-2-4-6-7/h2-6H,1H3': 'C6H5CH3',
            '1S/C2H6O/c1-2-3/h3H,2H2,1H3': 'C2H5OH',
            '1S/O2/c1-2': 'O2',
            '1S/N2/c1-2': 'N2',
            '1S/Ar': 'Ar',
            '1S/He': 'He',
            '1S/CO2/c2-1-3': 'CO2',
            '1S/H2/h1H': 'H2',
            '1S/H2O/h1H2': 'H2O',
            }

SPEC_KEY_REV = {'nC7H16': '1S/C7H16/c1-3-5-7-6-4-2/h3-7H2,1-2H3',
                'iC8H18': '1S/C8H18/c1-7(2)6-8(3,4)5/h7H,6H2,1-5H3',
                'C6H5CH3': '1S/C7H8/c1-7-5-3-2-4-6-7/h2-6H,1H3',
                'C2H5OH': '1S/C2H6O/c1-2-3/h3H,2H2,1H3',
                'O2': '1S/O2/c1-2',
                'N2': '1S/N2/c1-2',
                'Ar': '1S/Ar',
                'He': '1S/He',
                'CO2': '1S/CO2/c2-1-3',
                'H2': '1S/H2/h1H',
                'H2O': '1S/H2O/h1H2',
                }

SPEC_NAMES = {'nC7H16': 'n-heptane',
              'iC8H18': 'isooctane',
              'C6H5CH3': 'toluene',
              'C2H5OH': 'ethanol',
              'O2': 'oxygen',
              'N2': 'nitrogen',
              'Ar': 'argon',
              'He': 'helium',
              'CO2': 'carbon dioxide',
              'H2': 'hydrogen',
              'H2O': 'water',
              }


def print_species_names():
    """Print species names, internal short name, and InChI identifiers."""

    len_longest = max([len(sp) for sp in SPEC_NAMES.values()])
    header = '{:<{}s} Short name\tInChI key'.format('Species name', len_longest)

    print(header)
    print('-' * len(header.expandtabs()))
    for spec in SPEC_KEY_REV.items():
        print('{:<{}s} {:10}\t{}'.format(SPEC_NAMES[spec[0]], len_longest,
              spec[0], spec[1])
              )
