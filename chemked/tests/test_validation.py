"""
Tests for the utils
"""

# Standard libraries
import os
import pkg_resources

import pytest
try:
    import ruamel.yaml as yaml
except ImportError:
    import yaml

from ..validation import schema, OurValidator
print(schema)

v = OurValidator(schema)

class TestValidator(object):
    """
    """
    def test_valid_shock_tube(self):
        """Ensure shock tube experiment can be detected.
        """
        file_path = os.path.join('testfile_st.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)

        with open(filename, 'r') as f:
            properties = yaml.load(f)

        if not v.validate(properties):
            print(v.errors)
            assert False
        else:
            assert True

    def test_valid_shock_tube_with_pressure_rise(self):
        """Ensure shock tube experiment can be detected with pressure rise.
        """
        file_path = os.path.join('testfile_st2.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)

        with open(filename, 'r') as f:
            properties = yaml.load(f)

        if not v.validate(properties):
            print(v.errors)
            assert False
        else:
            assert True

    def test_valid_rcm_experiment(self):
        """Ensure RCM experiment can be detected.
        """
        file_path = os.path.join('testfile_rcm.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)

        with open(filename, 'r') as f:
            properties = yaml.load(f)

        if not v.validate(properties):
            print(v.errors)
            assert False
        else:
            assert True

    def test_invalid_experiment_type(self):
        """Ensure that an invalid experiment type raises an exception.
        """
        # update=True means to ignore required keys that are left out for testing
        v.validate({'experiment-type': 'invalid experiment'}, update=True)
        assert v.errors['experiment-type'] == 'unallowed value invalid experiment'

    def test_valid_experiment_types(self):
        """Ensure that all the valid experiment types are validated
        """
        # update=True means to ignore required keys that are left out for testing
        valid_experiment_types = ['ignition delay']
        for exp in valid_experiment_types:
            assert v.validate({'experiment-type': exp}, update=True)
