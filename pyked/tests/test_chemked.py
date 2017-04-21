"""
Test module for chemked.py
"""
# Standard libraries
import os
import pkg_resources
import warnings

# Third-party libraries
import numpy as np
import pytest

# Local imports
from ..validation import schema, OurValidator, yaml
from ..chemked import ChemKED, DataPoint
from ..utils import Q_

warnings.simplefilter('always')


class TestChemKED(object):
    """
    """
    def test_create_chemked(self):
        file_path = os.path.join('testfile_st.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)
        ChemKED(filename)

    def test_skip_validation(self):
        file_path = os.path.join('testfile_bad.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)
        ChemKED(filename, skip_validation=True)

    def test_datapoints(self):
        file_path = os.path.join('testfile_st.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)
        c = ChemKED(filename)
        assert len(c.datapoints) == 5

        temperatures = Q_([1164.48, 1164.97, 1264.2, 1332.57, 1519.18], 'K')
        ignition_delays = Q_([471.54, 448.03, 291.57, 205.93, 88.11], 'us')

        for i, d in enumerate(c.datapoints):
            assert np.isclose(d.ignition_delay, ignition_delays[i])
            assert np.isclose(d.pressure, Q_(220., 'kPa'))
            assert np.isclose(d.temperature, temperatures[i])
            assert d.pressure_rise is None
            assert d.volume_history is None
            assert d.compression_time is None
            assert d.ignition_type['type'] == 'd/dt max'
            assert d.ignition_type['target'] == 'pressure'

    def test_no_input(self):
        """Test that no input raises an exception
        """
        with pytest.raises(NameError):
            ChemKED()

    def test_dict_input(self):
        file_path = os.path.join('testfile_required.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)
        with open(filename, 'r') as f:
            properties = yaml.safe_load(f)

        ChemKED(dict_input=properties)

    def test_unallowed_input(self, capfd):
        file_path = os.path.join('testfile_required.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)
        with open(filename, 'r') as f:
            properties = yaml.safe_load(f)

        properties['experiment-type'] = 'Ignition Delay'  # should be 'ignition delay'

        with pytest.raises(ValueError):
            ChemKED(dict_input=properties)

        out, err = capfd.readouterr()
        assert out == ("experiment-type has an illegal value. Allowed values are ['ignition "
                       "delay'] and are case sensitive.\n")

    def test_missing_input(self, capfd):
        file_path = os.path.join('testfile_required.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)
        with open(filename, 'r') as f:
            properties = yaml.safe_load(f)

        properties.pop('apparatus')

        with pytest.raises(ValueError):
            ChemKED(dict_input=properties)


class TestDataFrameOutput(object):
    """
    """
    def test_get_dataframe(self):
        pd = pytest.importorskip('pandas')
        pdt = pytest.importorskip('pandas.util.testing')
        yaml_file = os.path.join('testfile_st.yaml')
        yaml_filename = pkg_resources.resource_filename(__name__, yaml_file)
        c = ChemKED(yaml_filename).get_dataframe()
        csv_file = os.path.join('dataframe_st.csv')
        csv_filename = pkg_resources.resource_filename(__name__, csv_file)
        converters = {
            'Ignition Delay': Q_,
            'Temperature': Q_,
            'Pressure': Q_,
            'H2': Q_,
            'Ar': Q_,
            'O2': Q_,
        }
        df = pd.read_csv(csv_filename, index_col=0, converters=converters)
        pdt.assert_frame_equal(c.sort_index(axis=1), df.sort_index(axis=1), check_names=True)

    def test_custom_dataframe(self):
        pd = pytest.importorskip('pandas')
        pdt = pytest.importorskip('pandas.util.testing')
        yaml_file = os.path.join('testfile_st.yaml')
        yaml_filename = pkg_resources.resource_filename(__name__, yaml_file)
        cols_to_get = ['composition', 'Reference', 'apparatus', 'temperature', 'ignition delay']
        c = ChemKED(yaml_filename).get_dataframe(cols_to_get)
        csv_file = os.path.join('dataframe_st.csv')
        csv_filename = pkg_resources.resource_filename(__name__, csv_file)
        converters = {
            'Ignition Delay': Q_,
            'Temperature': Q_,
            'Pressure': Q_,
            'H2': Q_,
            'Ar': Q_,
            'O2': Q_,
        }
        use_cols = ['Apparatus:Kind', 'Apparatus:Institution', 'Apparatus:Facility',
                    'Reference:Volume', 'Reference:Journal', 'Reference:Doi', 'Reference:Authors',
                    'Reference:Detail', 'Reference:Year', 'Reference:Pages', 'Temperature',
                    'Ignition Delay', 'H2', 'Ar', 'O2',
                    ]
        df = pd.read_csv(csv_filename, converters=converters, usecols=use_cols)
        pdt.assert_frame_equal(c.sort_index(axis=1), df.sort_index(axis=1), check_names=True)

    def test_custom_dataframe_2(self):
        pd = pytest.importorskip('pandas')
        pdt = pytest.importorskip('pandas.util.testing')
        yaml_file = os.path.join('testfile_st.yaml')
        yaml_filename = pkg_resources.resource_filename(__name__, yaml_file)
        cols_to_get = ['temperature', 'ignition delay', 'Pressure']
        c = ChemKED(yaml_filename).get_dataframe(cols_to_get)
        csv_file = os.path.join('dataframe_st.csv')
        csv_filename = pkg_resources.resource_filename(__name__, csv_file)
        converters = {
            'Ignition Delay': Q_,
            'Temperature': Q_,
            'Pressure': Q_,
            'H2': Q_,
            'Ar': Q_,
            'O2': Q_,
        }
        use_cols = ['Temperature', 'Ignition Delay', 'Pressure']
        df = pd.read_csv(csv_filename, converters=converters, usecols=use_cols)
        pdt.assert_frame_equal(c.sort_index(axis=1), df.sort_index(axis=1), check_names=True)

    def test_invalid_column(self):
        pytest.importorskip('pandas')
        pytest.importorskip('pandas.util.testing')

        yaml_file = os.path.join('testfile_st.yaml')
        yaml_filename = pkg_resources.resource_filename(__name__, yaml_file)
        with pytest.raises(ValueError):
            ChemKED(yaml_filename).get_dataframe(['bad column'])


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

        return properties['datapoints']

    def test_create_datapoint(self):
        properties = self.load_properties('testfile_required.yaml')
        DataPoint(properties[0])

    def test_cantera_composition_mole_fraction(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[0])
        assert d.get_cantera_mole_fraction() == 'H2: 4.4400e-03, O2: 5.5600e-03, Ar: 9.9000e-01'

    def test_cantera_composition_mole_fraction_bad(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[1])
        with pytest.raises(ValueError):
            d.get_cantera_mole_fraction()

    def test_cantera_composition_mass_fraction(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[1])
        assert d.get_cantera_mass_fraction() == 'H2: 2.2525e-04, O2: 4.4775e-03, Ar: 9.9530e-01'

    def test_cantera_composition_mass_fraction_bad(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[0])
        with pytest.raises(ValueError):
            d.get_cantera_mass_fraction()

    def test_cantera_composition_mole_percent(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[2])
        assert d.get_cantera_mole_fraction() == 'H2: 4.4400e-03, O2: 5.5600e-03, Ar: 9.9000e-01'

    def test_composition(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[2])
        assert len(d.composition) == 3
        assert np.isclose(d.composition[0]['amount'], Q_(0.444))
        assert d.composition[0]['species-name'] == 'H2'
        assert np.isclose(d.composition[1]['amount'], Q_(0.556))
        assert d.composition[1]['species-name'] == 'O2'
        assert np.isclose(d.composition[2]['amount'], Q_(99.0))
        assert d.composition[2]['species-name'] == 'Ar'

    def test_ignition_delay(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[0])
        assert np.isclose(d.ignition_delay, Q_(471.54, 'us'))

    def test_temperature(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[0])
        assert np.isclose(d.temperature, Q_(1164.48, 'K'))

    def test_pressure(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[0])
        assert np.isclose(d.pressure, Q_(220.0, 'kPa'))

    def test_pressure_rise(self):
        properties = self.load_properties('testfile_st2.yaml')
        d = DataPoint(properties[0])
        assert np.isclose(d.pressure_rise, Q_(0.1, '1/ms'))

    def test_absolute_sym_uncertainty(self):
        properties = self.load_properties('testfile_uncertainty.yaml')
        d = DataPoint(properties[0])
        assert np.isclose(d.temperature.value, Q_(1164.48, 'K'))
        assert np.isclose(d.temperature.error, Q_(10, 'K'))

    def test_absolute_sym_comp_uncertainty(self):
        properties = self.load_properties('testfile_uncertainty.yaml')
        d = DataPoint(properties[0])
        assert np.isclose(d.composition[1]['amount'].value, Q_(0.556))
        assert np.isclose(d.composition[1]['amount'].error, Q_(0.002))

    def test_relative_sym_uncertainty(self):
        properties = self.load_properties('testfile_uncertainty.yaml')
        d = DataPoint(properties[1])
        assert np.isclose(d.ignition_delay.value, Q_(471.54, 'us'))
        assert np.isclose(d.ignition_delay.error, Q_(47.154, 'us'))
        assert np.isclose(d.ignition_delay.rel, 0.1)

    def test_relative_sym_comp_uncertainty(self):
        properties = self.load_properties('testfile_uncertainty.yaml')
        d = DataPoint(properties[0])
        assert np.isclose(d.composition[0]['amount'].value, Q_(0.444))
        assert np.isclose(d.composition[0]['amount'].error, Q_(0.00444))
        assert np.isclose(d.composition[0]['amount'].rel, 0.01)

    def test_absolute_asym_uncertainty(self):
        properties = self.load_properties('testfile_uncertainty.yaml')
        with pytest.warns(UserWarning) as w:
            d = DataPoint(properties[2])
        assert w[0].message.args[0] == ('Asymmetric uncertainties are not supported. The '
                                        'maximum of lower-uncertainty and upper-uncertainty '
                                        'has been used as the symmetric uncertainty.')
        assert np.isclose(d.temperature.value, Q_(1164.48, 'K'))
        assert np.isclose(d.temperature.error, Q_(10, 'K'))
        assert np.isclose(d.ignition_delay.value, Q_(471.54, 'us'))
        assert np.isclose(d.ignition_delay.error, Q_(10, 'us'))

    def test_relative_asym_uncertainty(self):
        properties = self.load_properties('testfile_uncertainty.yaml')
        with pytest.warns(UserWarning) as w:
            d = DataPoint(properties[3])
        assert w[0].message.args[0] == ('Asymmetric uncertainties are not supported. The '
                                        'maximum of lower-uncertainty and upper-uncertainty '
                                        'has been used as the symmetric uncertainty.')
        assert np.isclose(d.ignition_delay.value, Q_(471.54, 'us'))
        assert np.isclose(d.ignition_delay.error, Q_(47.154, 'us'))
        assert np.isclose(d.ignition_delay.rel, 0.1)
        assert np.isclose(d.temperature.value, Q_(1164.48, 'K'))
        assert np.isclose(d.temperature.error, Q_(116.448, 'K'))
        assert np.isclose(d.temperature.rel, 0.1)

    def test_absolute_asym_comp_uncertainty(self):
        properties = self.load_properties('testfile_uncertainty.yaml')
        with pytest.warns(UserWarning) as w:
            d = DataPoint(properties[0])
        assert w[0].message.args[0] == ('Asymmetric uncertainties are not supported. The '
                                        'maximum of lower-uncertainty and upper-uncertainty '
                                        'has been used as the symmetric uncertainty.')
        assert np.isclose(d.composition[2]['amount'].value, Q_(99.0))
        assert np.isclose(d.composition[2]['amount'].error, Q_(1.0))

        with pytest.warns(UserWarning) as w:
            d = DataPoint(properties[1])
        assert w[0].message.args[0] == ('Asymmetric uncertainties are not supported. The '
                                        'maximum of lower-uncertainty and upper-uncertainty '
                                        'has been used as the symmetric uncertainty.')
        assert np.isclose(d.composition[2]['amount'].value, Q_(99.0))
        assert np.isclose(d.composition[2]['amount'].error, Q_(1.0))

    def test_relative_asym_comp_uncertainty(self):
        properties = self.load_properties('testfile_uncertainty.yaml')
        with pytest.warns(UserWarning) as w:
            d = DataPoint(properties[1])
        assert w[0].message.args[0] == ('Asymmetric uncertainties are not supported. The '
                                        'maximum of lower-uncertainty and upper-uncertainty '
                                        'has been used as the symmetric uncertainty.')
        assert np.isclose(d.composition[0]['amount'].value, Q_(0.444))
        assert np.isclose(d.composition[0]['amount'].error, Q_(0.0444))
        assert np.isclose(d.composition[0]['amount'].rel, 0.1)

        assert np.isclose(d.composition[1]['amount'].value, Q_(0.556))
        assert np.isclose(d.composition[1]['amount'].error, Q_(0.0556))
        assert np.isclose(d.composition[1]['amount'].rel, 0.1)

    def test_missing_uncertainty_parts(self):
        properties = self.load_properties('testfile_uncertainty.yaml')
        for prop in ['uncertainty', 'uncertainty-type']:
            save = properties[0]['temperature'][1].pop(prop)
            with pytest.raises(ValueError):
                DataPoint(properties[0])
            properties[0]['temperature'][1][prop] = save

            save = properties[1]['ignition-delay'][1].pop(prop)
            with pytest.raises(ValueError):
                DataPoint(properties[1])
            properties[1]['ignition-delay'][1][prop] = save

        for prop in ['upper-uncertainty', 'lower-uncertainty']:
            save = properties[2]['temperature'][1].pop(prop)
            with pytest.raises(ValueError):
                DataPoint(properties[2])
            properties[0]['temperature'][1][prop] = save

            save = properties[3]['ignition-delay'][1].pop(prop)
            with pytest.raises(ValueError):
                DataPoint(properties[3])
            properties[1]['ignition-delay'][1][prop] = save

    def test_missing_comp_uncertainty_parts(self):
        properties = self.load_properties('testfile_uncertainty.yaml')
        for prop in ['uncertainty', 'uncertainty-type']:
            save = properties[0]['composition']['species'][0]['amount'][1].pop(prop)
            with pytest.raises(ValueError):
                DataPoint(properties[0])
            properties[0]['composition']['species'][0]['amount'][1][prop] = save

            save = properties[0]['composition']['species'][1]['amount'][1].pop(prop)
            with pytest.raises(ValueError):
                DataPoint(properties[0])
            properties[0]['composition']['species'][1]['amount'][1][prop] = save

        for prop in ['upper-uncertainty', 'lower-uncertainty']:
            save = properties[0]['composition']['species'][2]['amount'][1].pop(prop)
            with pytest.raises(ValueError):
                DataPoint(properties[0])
            properties[0]['composition']['species'][2]['amount'][1][prop] = save

            save = properties[1]['composition']['species'][2]['amount'][1].pop(prop)
            with pytest.raises(ValueError):
                DataPoint(properties[1])
            properties[1]['composition']['species'][2]['amount'][1][prop] = save

    def test_volume_history(self):
        properties = self.load_properties('testfile_rcm.yaml')
        d = DataPoint(properties[0])

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

    def test_supported_ignition_types(self):
        # pressure d/dt max
        properties = self.load_properties('testfile_st.yaml')
        datapoints = [DataPoint(d) for d in properties]
        for d in datapoints:
            assert d.ignition_type['target'] == 'pressure'
            assert d.ignition_type['type'] == 'd/dt max'

        # OH, max
        properties = self.load_properties('testfile_st2.yaml')
        datapoints = [DataPoint(d) for d in properties]
        for d in datapoints:
            assert d.ignition_type['target'] == 'OH'
            assert d.ignition_type['type'] == 'max'

        # OH*, 1/2 max
        properties = self.load_properties('testfile_st_p5.yaml')
        datapoints = [DataPoint(d) for d in properties]
        for d in datapoints:
            assert d.ignition_type['target'] == 'OH*'
            assert d.ignition_type['type'] == '1/2 max'
