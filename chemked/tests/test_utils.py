"""
Tests for the utils
"""

# Standard libraries
import os
import pkg_resources

import yaml
import pytest

from cerberus import Validator
from ..utils import schema

v = Validator(schema)


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
