"""
Test module for chemked.py
"""
# Standard libraries
import os
import pkg_resources

# Third-party libraries
import numpy as np
import pytest

# Local imports
from ..validation import schema, OurValidator, yaml
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

        temperatures = Q_([1164.48, 1164.97, 1264.2, 1332.57, 1519.18], 'K')
        ignition_delays = Q_([471.54, 448.03, 291.57, 205.93, 88.11], 'us')

        for i, d in enumerate(c.datapoints):
            assert d.ignition_delay == ignition_delays[i]
            assert d.pressure == Q_(220., 'kPa')
            assert d.temperature == temperatures[i]
            assert 'pressure_rise' not in d.__dict__
            assert 'volume_history' not in d.__dict__


class TestDataPoint(object):
    """
    """
    def load_properties(self, test_file):
        file_path = os.path.join(test_file)
        filename = pkg_resources.resource_filename(__name__, file_path)
        with open(filename, 'r') as f:
            properties = yaml.safe_load(f)

        v = OurValidator(schema)
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

    def test_pressure_rise(self):
        properties = self.load_properties('testfile_st2.yaml')
        d = DataPoint(properties)
        assert d.pressure_rise == Q_(0.1, '1/ms')

    def test_volume_history(self):
        properties = self.load_properties('testfile_rcm.yaml')
        d = DataPoint(properties)

        # Check other data group with volume history
        np.testing.assert_allclose(d.volume_history.time,
                                   Q_(np.arange(0, 9.7e-2, 1.e-3), 's')
                                   )

        volumes = Q_(np.array([
            5.47669375000E+002, 5.46608789894E+002, 5.43427034574E+002,
            5.38124109043E+002, 5.30700013298E+002, 5.21154747340E+002,
            5.09488311170E+002, 4.95700704787E+002, 4.79791928191E+002,
            4.61761981383E+002, 4.41610864362E+002, 4.20399162234E+002,
            3.99187460106E+002, 3.77975757979E+002, 3.56764055851E+002,
            3.35552353723E+002, 3.14340651596E+002, 2.93128949468E+002,
            2.71917247340E+002, 2.50705545213E+002, 2.29493843085E+002,
            2.08282140957E+002, 1.87070438830E+002, 1.65858736702E+002,
            1.44647034574E+002, 1.23435332447E+002, 1.02223630319E+002,
            8.10119281915E+001, 6.33355097518E+001, 5.27296586879E+001,
            4.91943750000E+001, 4.97137623933E+001, 5.02063762048E+001,
            5.06454851923E+001, 5.10218564529E+001, 5.13374097598E+001,
            5.16004693977E+001, 5.18223244382E+001, 5.20148449242E+001,
            5.21889350372E+001, 5.23536351113E+001, 5.25157124459E+001,
            5.26796063730E+001, 5.28476160610E+001, 5.30202402028E+001,
            5.31965961563E+001, 5.33748623839E+001, 5.35527022996E+001,
            5.37276399831E+001, 5.38973687732E+001, 5.40599826225E+001,
            5.42141273988E+001, 5.43590751578E+001, 5.44947289126E+001,
            5.46215686913E+001, 5.47405518236E+001, 5.48529815402E+001,
            5.49603582190E+001, 5.50642270863E+001, 5.51660349836E+001,
            5.52670070646E+001, 5.53680520985E+001, 5.54697025392E+001,
            5.55720927915E+001, 5.56749762728E+001, 5.57777790517E+001,
            5.58796851466E+001, 5.59797461155E+001, 5.60770054561E+001,
            5.61706266985E+001, 5.62600130036E+001, 5.63449057053E+001,
            5.64254496625E+001, 5.65022146282E+001, 5.65761642150E+001,
            5.66485675508E+001, 5.67208534842E+001, 5.67944133373E+001,
            5.68703658198E+001, 5.69493069272E+001, 5.70310785669E+001,
            5.71146023893E+001, 5.71978399741E+001, 5.72779572372E+001,
            5.73517897984E+001, 5.74167271960E+001, 5.74721573687E+001,
            5.75216388520E+001, 5.75759967785E+001, 5.76575701358E+001,
            5.78058719368E+001, 5.80849611077E+001, 5.85928651155E+001,
            5.94734357453E+001, 6.09310671165E+001, 6.32487551103E+001,
            6.68100309742E+001
            ]), 'cm**3')
        np.testing.assert_allclose(d.volume_history.volume, volumes)
