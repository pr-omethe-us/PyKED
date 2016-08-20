"""
Main ChemKED module
"""
# Python 2 compatibility
from __future__ import print_function

# Local imports
from .validation import schema, OurValidator, yaml
from .utils import units

class ChemKED(object):
    """Main ChemKED class.
    """
    def __init__(self, yaml_file=None, yaml_string=None):
        if yaml_file:
            with open(yaml_file, 'r') as f:
                self.properties = yaml.load(f)
        elif yaml_string:
            self.properties = yaml_string

        self.validate_yaml()

    def validate_yaml(self):
        v = OurValidator(schema)
        if not v.validate(self.properties):
            for key, value in v.errors.items():
                if 'unallowed value' in value:
                    print(('{key} has an illegal value. Allowed values are {values} and are case '
                           'sensitive').format(key=key, values=schema[key]['allowed']))

            raise ValueError(v.errors)
