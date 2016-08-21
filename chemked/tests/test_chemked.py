"""
Test module for chemked.py
"""


# Standard libraries
import os
import pkg_resources

import pytest

from cerberus import Validator
from ..validation import schema, yaml
from ..chemked import ChemKED, DataPoint
from ..utils import Q_


class TestChemKED(object):
    """
    """
    def test_create_chemked(self):
        file_path = os.path.join('testfile_st.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)
        ChemKED(filename)

    def test_datapoints(self):
        file_path = os.path.join('testfile_st.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)
        c = ChemKED(filename)
        assert len(c.datapoints) == 5


class TestDataPoint(object):
    """
    """
    def load_properties(self, test_file):
        file_path = os.path.join(test_file)
        filename = pkg_resources.resource_filename(__name__, file_path)
        with open(filename, 'r') as f:
            properties = yaml.safe_load(f)

        v = Validator(schema)
        if not v.validate(properties):
            raise ValueError(v.errors)

        return properties['datapoints'][0]

    def test_create_datapoint(self):
        properties = self.load_properties('testfile_st.yaml')
        DataPoint(properties)

    def test_cantera_composition_string(self):
        properties = self.load_properties('testfile_st.yaml')
        d = DataPoint(properties)
        assert d.get_cantera_composition() == 'H2: 0.00444, O2: 0.00566, Ar: 0.9899'

    def test_ignition_delay(self):
        properties = self.load_properties('testfile_st.yaml')
        d = DataPoint(properties)
        assert d.ignition_delay == Q_(471.54, 'us')

    def test_temperature(self):
        properties = self.load_properties('testfile_st.yaml')
        d = DataPoint(properties)
        assert d.temperature == Q_(1164.48, 'K')

    def test_pressure(self):
        properties = self.load_properties('testfile_st.yaml')
        d = DataPoint(properties)
        assert d.pressure == Q_(220.0, 'kPa')
