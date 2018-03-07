"""
Test module for chemked.py
"""
# Standard libraries
import os
import pkg_resources
import warnings
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as etree
from copy import deepcopy

# Third-party libraries
import numpy as np
import pytest

# Local imports
from ..validation import schema, OurValidator, yaml, Q_
from ..chemked import ChemKED, DataPoint, Composition
from ..converters import get_datapoints, get_common_properties
from .._version import __version__

schema['chemked-version']['allowed'].append(__version__)

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
            assert d.rcm_data is None
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
    @pytest.fixture(scope='session')
    def pd(self):
        return pytest.importorskip('pandas')

    @pytest.fixture(scope='session')
    def pdt(self):
        return pytest.importorskip('pandas.util.testing')

    def test_get_dataframe(self, pd, pdt):
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

    def test_custom_dataframe(self, pd, pdt):
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

    def test_custom_dataframe_2(self, pd, pdt):
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

    def test_invalid_column(self, pd):
        yaml_file = os.path.join('testfile_st.yaml')
        yaml_filename = pkg_resources.resource_filename(__name__, yaml_file)
        with pytest.raises(ValueError):
            ChemKED(yaml_filename).get_dataframe(['bad column'])

    def test_many_species(self, pd):
        yaml_file = os.path.join('testfile_many_species.yaml')
        yaml_filename = pkg_resources.resource_filename(__name__, yaml_file)
        c = ChemKED(yaml_filename).get_dataframe()
        assert c.iloc[0]['New-Species-1'] == Q_(0.0, 'dimensionless')
        assert c.iloc[0]['New-Species-2'] == Q_(0.0, 'dimensionless')
        assert c.iloc[1]['H2'] == Q_(0.0, 'dimensionless')
        assert c.iloc[1]['O2'] == Q_(0.0, 'dimensionless')


class TestWriteFile(object):
    """
    """
    def test_file_exists(self):
        """
        """
        yaml_file = 'testfile_st.yaml'
        yaml_filename = pkg_resources.resource_filename(__name__, yaml_file)
        c = ChemKED(yaml_filename)

        with pytest.raises(OSError):
            c.write_file(yaml_filename)

    def test_overwrite(self):
        """
        """
        yaml_file = 'testfile_st.yaml'
        yaml_filename = pkg_resources.resource_filename(__name__, yaml_file)
        with open(yaml_filename, 'r') as f:
            lines = f.readlines()

        with TemporaryDirectory() as temp_dir:
            newfile_path = os.path.join(temp_dir, 'testfile.yaml')
            with open(newfile_path, 'w') as f:
                f.writelines(lines)
            c = ChemKED(newfile_path)

            # Expected error
            with pytest.raises(OSError):
                c.write_file(newfile_path)

            # Now successful
            assert c.write_file(newfile_path, overwrite=True) is None

    @pytest.mark.parametrize("filename", [
        'testfile_st.yaml', 'testfile_st2.yaml', 'testfile_rcm.yaml',
        'testfile_required.yaml', 'testfile_uncertainty.yaml'
        ])
    @pytest.mark.filterwarnings('ignore:Asymmetric uncertainties')
    def test_write_files(self, filename):
        """Test proper writing of ChemKED files.
        """
        file_path = os.path.join(filename)
        filename = pkg_resources.resource_filename(__name__, file_path)
        c = ChemKED(filename)

        with TemporaryDirectory() as temp_dir:
            c.write_file(os.path.join(temp_dir, 'testfile.yaml'))

            # Now read in the file
            with open(os.path.join(temp_dir, 'testfile.yaml'), 'r') as f:
                properties = yaml.safe_load(f)

        assert properties == c._properties


class TestConvertToReSpecTh(object):
    """Tests for conversion of ChemKED to ReSpecTh
    """
    @pytest.mark.parametrize('filename_ck', ['testfile_st.yaml', 'testfile_rcm.yaml'])
    def test_conversion_to_respecth(self, filename_ck):
        """Test proper conversion to ReSpecTh XML.
        """
        file_path = os.path.join(filename_ck)
        filename = pkg_resources.resource_filename(__name__, file_path)
        c_true = ChemKED(filename)

        with TemporaryDirectory() as temp_dir:
            newfile = os.path.join(temp_dir, 'test.xml')
            c_true.convert_to_ReSpecTh(newfile)
            with pytest.warns(UserWarning) as record:
                c = ChemKED.from_respecth(newfile)

        m = str(record.pop(UserWarning).message)
        assert m == 'Using DOI to obtain reference information, rather than preferredKey.'

        assert c.file_authors[0]['name'] == c_true.file_authors[0]['name']

        assert c.reference.detail == 'Converted from ReSpecTh XML file {}'.format(os.path.split(newfile)[1])

        assert c.apparatus.kind == c_true.apparatus.kind
        assert c.experiment_type == c_true.experiment_type
        assert c.reference.doi == c_true.reference.doi
        assert len(c.datapoints) == len(c_true.datapoints)

    @pytest.mark.parametrize('history_type, unit',
                             [('volume', 'cm3'), ('temperature', 'K'), ('pressure', 'bar')])
    def test_time_history_conversion_to_respecth(self, history_type, unit):
        """Test proper conversion to ReSpecTh XML with time histories.
        """
        file_path = os.path.join('testfile_rcm.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)
        with open(filename, 'r') as yaml_file:
            properties = yaml.safe_load(yaml_file)
        properties['datapoints'][0]['time-histories'][0]['type'] = history_type
        properties['datapoints'][0]['time-histories'][0]['quantity']['units'] = unit
        c_true = ChemKED(dict_input=properties)

        with TemporaryDirectory() as temp_dir:
            newfile = os.path.join(temp_dir, 'test.xml')
            c_true.convert_to_ReSpecTh(newfile)
            with pytest.warns(UserWarning) as record:
                c = ChemKED.from_respecth(newfile)

        m = str(record.pop(UserWarning).message)
        assert m == 'Using DOI to obtain reference information, rather than preferredKey.'

        assert c.file_authors[0]['name'] == c_true.file_authors[0]['name']

        assert c.reference.detail == 'Converted from ReSpecTh XML file {}'.format(os.path.split(newfile)[1])

        assert c.apparatus.kind == c_true.apparatus.kind
        assert c.experiment_type == c_true.experiment_type
        assert c.reference.doi == c_true.reference.doi
        assert len(c.datapoints) == len(c_true.datapoints)
        assert getattr(c.datapoints[0], '{}_history'.format(history_type)) is not None

    @pytest.mark.parametrize('history_type, unit',
                             zip(['piston position', 'light emission', 'OH emission', 'absorption'],
                                 ['cm', 'dimensionless', 'dimensionless', 'dimensionless']))
    def test_time_history_conversion_to_respecth_unsupported(self, history_type, unit):
        """Test proper conversion to ReSpecTh XML with unsupported time histories.
        """
        file_path = os.path.join('testfile_rcm.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)
        with open(filename, 'r') as yaml_file:
            properties = yaml.safe_load(yaml_file)
        properties['datapoints'][0]['time-histories'][0]['type'] = history_type
        properties['datapoints'][0]['time-histories'][0]['quantity']['units'] = unit
        c_true = ChemKED(dict_input=properties)
        with TemporaryDirectory() as temp_dir:
            newfile = os.path.join(temp_dir, 'test.xml')
            with pytest.warns(UserWarning) as record:
                c_true.convert_to_ReSpecTh(newfile)
            m = str(record.pop(UserWarning).message)
            assert m == ('The time-history type {} is not supported by ReSpecTh for '
                         'ignition delay experiments'.format(history_type))
            with pytest.warns(UserWarning) as record:
                c = ChemKED.from_respecth(newfile)

        m = str(record.pop(UserWarning).message)
        assert m == 'Using DOI to obtain reference information, rather than preferredKey.'

        assert c.file_authors[0]['name'] == c_true.file_authors[0]['name']

        assert c.reference.detail == 'Converted from ReSpecTh XML file {}'.format(os.path.split(newfile)[1])

        assert c.apparatus.kind == c_true.apparatus.kind
        assert c.experiment_type == c_true.experiment_type
        assert c.reference.doi == c_true.reference.doi
        assert len(c.datapoints) == len(c_true.datapoints)
        assert getattr(c.datapoints[0], '{}_history'.format(history_type.replace(' ', '_'))) is None

    @pytest.mark.parametrize('experiment_type', [
        'Laminar flame speed measurement', 'Species profile measurement',
        'Outlet concentration measurement', 'Burner stabilized flame speciation measurement',
        'Jet-stirred reactor measurement', 'Reaction rate coefficient measurement'
        ])
    def test_conversion_to_respecth_error(self, experiment_type):
        """Test for conversion errors.
        """
        file_path = os.path.join('testfile_st.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)
        c = ChemKED(filename)

        c.experiment_type = experiment_type

        with pytest.raises(NotImplementedError) as excinfo:
            c.convert_to_ReSpecTh('test.xml')
        assert 'Only ignition delay type supported for conversion.' in str(excinfo.value)

    def test_conversion_datapoints_composition_missing_inchi(self):
        """Test for appropriate handling of composition with missing InChI.
        """
        file_path = os.path.join('testfile_st.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)
        c = ChemKED(filename)

        for idx, dp in enumerate(c.datapoints):
            c.datapoints[idx].composition = dict(
                H2=Composition(**{'amount': Q_(0.1, 'dimensionless'), 'species_name': 'H2',
                                  'InChI': None, 'SMILES': None, 'atomic_composition': None}),
                O2=Composition(**{'amount': Q_(0.1, 'dimensionless'), 'species_name': 'O2',
                                  'InChI': None, 'SMILES': None, 'atomic_composition': None}),
                Ar=Composition(**{'amount': Q_(0.8, 'dimensionless'), 'species_name': 'Ar',
                                  'InChI': None, 'SMILES': None, 'atomic_composition': None})
            )

        with TemporaryDirectory() as temp_dir:
            newfile = os.path.join(temp_dir, 'test.xml')
            c.convert_to_ReSpecTh(newfile)
            tree = etree.parse(newfile)
        root = tree.getroot()

        with pytest.warns(UserWarning) as record:
            common = get_common_properties(root)
        messages = [str(record.pop(UserWarning).message) for i in range(3)]
        assert 'Missing InChI for species H2' in messages
        assert 'Missing InChI for species O2' in messages
        assert 'Missing InChI for species Ar' in messages
        assert len(common['composition']['species']) == 3
        for spec in common['composition']['species']:
            assert spec in [{'amount': [0.1], 'species-name': 'H2'},
                            {'amount': [0.1], 'species-name': 'O2'},
                            {'amount': [0.8], 'species-name': 'Ar'}
                            ]

    def test_conversion_datapoints_different_composition(self):
        """Test for appropriate handling of datapoints with different composition.
        """
        file_path = os.path.join('testfile_st.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)
        c = ChemKED(filename)

        c.datapoints[0].composition = {'H2': Composition(**{'InChI': '1S/H2/h1H',
                                        'amount': Q_(0.1, 'dimensionless'),
                                        'species_name': 'H2', 'SMILES': None, 'atomic_composition': None}),
                                       'O2': Composition(**{'InChI': '1S/O2/c1-2',
                                        'amount': Q_(0.1, 'dimensionless'),
                                        'species_name': 'O2', 'SMILES': None, 'atomic_composition': None}),
                                       'N2': Composition(**{'amount': Q_(0.8, 'dimensionless'),
                                        'species_name': 'N2',
                                        'SMILES': 'N#N', 'InChI': None, 'atomic_composition': None})
                                       }

        with TemporaryDirectory() as temp_dir:
            newfile = os.path.join(temp_dir, 'test.xml')
            c.convert_to_ReSpecTh(newfile)

            tree = etree.parse(newfile)
        root = tree.getroot()
        with pytest.warns(UserWarning) as record:
            datapoints = get_datapoints(root)
        m = str(record.pop(UserWarning).message)
        assert m == 'Missing InChI for species N2'

        assert len(datapoints[0]['composition']['species']) == 3
        for spec in datapoints[0]['composition']['species']:
            assert spec in [{'InChI': '1S/H2/h1H',
                             'amount': [0.1],
                             'species-name': 'H2'},
                            {'InChI': '1S/O2/c1-2',
                             'amount': [0.1],
                             'species-name': 'O2'},
                            {'amount': [0.8],
                             'species-name': 'N2',
                             'InChI': None}
                            ]

    def test_conversion_error_datapoints_different_composition_type(self):
        """Test for appropriate erorr of datapoints with different composition type.
        """
        file_path = os.path.join('testfile_st.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)
        c = ChemKED(filename)
        c.datapoints[0].composition_type = 'mass fraction'

        with pytest.raises(NotImplementedError) as excinfo:
            c.convert_to_ReSpecTh('test.xml')
        assert ('Error: ReSpecTh does not support varying composition '
                'type among datapoints.') in str(excinfo.value)

    def test_conversion_to_respecth_error_volume_history_datapoints(self):
        """Test for error raised if RCM with multiple datapoints with volume history.
        """
        file_path = os.path.join('testfile_rcm.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)
        c = ChemKED(filename)

        # Repeat datapoint, such that two with volume histories
        c.datapoints.append(c.datapoints[0])

        with pytest.raises(NotImplementedError) as excinfo:
            c.convert_to_ReSpecTh('test.xml')
        assert ('Error: ReSpecTh files do not support multiple datapoints with a '
                'time history.' in str(excinfo.value)
                )

    @pytest.mark.parametrize('ignition_target', ['pressure', 'temperature', 'OH', 'CH', 'OH*', 'CH*'])
    def test_conversion_to_respecth_ignition_targets(self, ignition_target):
        """Test proper conversion for different ignition targets.
        """
        file_path = os.path.join('testfile_st.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)
        c = ChemKED(filename)

        for dp in c.datapoints:
            dp.ignition_type['target'] = ignition_target

        with TemporaryDirectory() as temp_dir:
            newfile = os.path.join(temp_dir, 'test.xml')
            c.convert_to_ReSpecTh(newfile)

            tree = etree.parse(newfile)
        root = tree.getroot()
        elem = root.find('ignitionType')
        elem = elem.attrib

        if ignition_target == 'pressure':
            assert elem['target'] == 'P'
        elif ignition_target == 'temperature':
            assert elem['target'] == 'T'
        else:
            assert elem['target'] == ignition_target

    @pytest.mark.parametrize('ignition_type', ['d/dt max', 'max', '1/2 max', 'min', 'd/dt max extrapolated'])
    def test_conversion_to_respecth_ignition_types(self, ignition_type):
        """Test proper conversion for different ignition types.
        """
        file_path = os.path.join('testfile_st.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)
        c = ChemKED(filename)

        for dp in c.datapoints:
            dp.ignition_type['type'] = ignition_type

        with TemporaryDirectory() as temp_dir:
            newfile = os.path.join(temp_dir, 'test.xml')
            c.convert_to_ReSpecTh(newfile)

            tree = etree.parse(newfile)
        root = tree.getroot()
        elem = root.find('ignitionType')
        elem = elem.attrib

        if ignition_type == 'd/dt max extrapolated':
            assert elem['type'] == 'baseline max intercept from d/dt'
        else:
            assert elem['type'] == ignition_type

    def test_conversion_multiple_ignition_targets(self):
        """Test that multiple ignition targets for datapoints fails
        """
        file_path = os.path.join('testfile_st.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)
        c = ChemKED(filename)

        c.datapoints[0].ignition_type['target'] = 'temperature'
        with TemporaryDirectory() as temp_dir:
            newfile = os.path.join(temp_dir, 'test.xml')
            with pytest.raises(NotImplementedError) as e:
                c.convert_to_ReSpecTh(newfile)

        assert ('Different ignition targets or types for multiple datapoints are not supported in '
                'ReSpecTh.' in str(e.value))


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

    def test_cantera_unknown_composition_type(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[0])
        d.composition_type = 'unknown type'
        with pytest.raises(ValueError):
            d.get_cantera_composition_string()

    def test_cantera_composition_mole_fraction(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[0])
        # The order of the keys should not change between calls provided the contents of the
        # dictionary don't change. Therefore, spec_order should be the same order as the
        # Cantera mole fraction string constructed in a loop in the code
        comps = {'H2': 'H2:4.4400e-03', 'O2': 'O2:5.5600e-03', 'Ar': 'Ar:9.9000e-01'}
        compare_str = ', '.join([comps[s] for s in d.composition.keys()])
        assert d.composition_type == 'mole fraction'
        assert d.get_cantera_mole_fraction() == compare_str

    def test_cantera_composition_mole_fraction_bad(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[1])
        assert d.composition_type == 'mass fraction'
        with pytest.raises(ValueError):
            d.get_cantera_mole_fraction()

    def test_cantera_composition_mass_fraction(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[1])
        # The order of the keys should not change between calls provided the contents of the
        # dictionary don't change. Therefore, spec_order should be the same order as the
        # Cantera mole fraction string constructed in a loop in the code
        comps = {'H2': 'H2:2.2525e-04', 'O2': 'O2:4.4775e-03', 'Ar': 'Ar:9.9530e-01'}
        compare_str = ', '.join([comps[s] for s in d.composition.keys()])
        assert d.composition_type == 'mass fraction'
        assert d.get_cantera_mass_fraction() == compare_str

    def test_cantera_composition_mass_fraction_bad(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[0])
        assert d.composition_type == 'mole fraction'
        with pytest.raises(ValueError):
            d.get_cantera_mass_fraction()

    def test_cantera_composition_mole_percent(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[2])
        # The order of the keys should not change between calls provided the contents of the
        # dictionary don't change. Therefore, spec_order should be the same order as the
        # Cantera mole fraction string constructed in a loop in the code
        comps = {'H2': 'H2:4.4400e-03', 'O2': 'O2:5.5600e-03', 'Ar': 'Ar:9.9000e-01'}
        compare_str = ', '.join([comps[s] for s in d.composition.keys()])
        assert d.composition_type == 'mole percent'
        assert d.get_cantera_mole_fraction() == compare_str

    def test_cantera_change_species_by_name_mole_fraction(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[0])
        # The order of the keys should not change between calls provided the contents of the
        # dictionary don't change. Therefore, spec_order should be the same order as the
        # Cantera mole fraction string constructed in a loop in the code
        comps = {'H2': 'h2:4.4400e-03', 'O2': 'o2:5.5600e-03', 'Ar': 'Ar:9.9000e-01'}
        compare_str = ', '.join([comps[s] for s in d.composition.keys()])
        species_conversion = {'H2': 'h2', 'O2': 'o2'}
        assert d.get_cantera_mole_fraction(species_conversion) == compare_str

    def test_cantera_change_species_by_inchi_mole_fraction(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[0])
        # The order of the keys should not change between calls provided the contents of the
        # dictionary don't change. Therefore, spec_order should be the same order as the
        # Cantera mole fraction string constructed in a loop in the code
        comps = {'H2': 'h2:4.4400e-03', 'O2': 'o2:5.5600e-03', 'Ar': 'Ar:9.9000e-01'}
        compare_str = ', '.join([comps[s] for s in d.composition.keys()])
        species_conversion = {'1S/H2/h1H': 'h2', '1S/O2/c1-2': 'o2'}
        assert d.get_cantera_mole_fraction(species_conversion) == compare_str

    def test_cantera_change_species_by_name_mole_percent(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[2])
        # The order of the keys should not change between calls provided the contents of the
        # dictionary don't change. Therefore, spec_order should be the same order as the
        # Cantera mole fraction string constructed in a loop in the code
        comps = {'H2': 'h2:4.4400e-03', 'O2': 'o2:5.5600e-03', 'Ar': 'Ar:9.9000e-01'}
        compare_str = ', '.join([comps[s] for s in d.composition.keys()])
        species_conversion = {'H2': 'h2', 'O2': 'o2'}
        assert d.get_cantera_mole_fraction(species_conversion) == compare_str

    def test_cantera_change_species_by_inchi_mole_percent(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[2])
        # The order of the keys should not change between calls provided the contents of the
        # dictionary don't change. Therefore, spec_order should be the same order as the
        # Cantera mole fraction string constructed in a loop in the code
        comps = {'H2': 'h2:4.4400e-03', 'O2': 'o2:5.5600e-03', 'Ar': 'Ar:9.9000e-01'}
        compare_str = ', '.join([comps[s] for s in d.composition.keys()])
        species_conversion = {'1S/H2/h1H': 'h2', '1S/O2/c1-2': 'o2'}
        assert d.get_cantera_mole_fraction(species_conversion) == compare_str

    def test_cantera_change_species_by_name_mass_fraction(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[1])
        # The order of the keys should not change between calls provided the contents of the
        # dictionary don't change. Therefore, spec_order should be the same order as the
        # Cantera mole fraction string constructed in a loop in the code
        comps = {'H2': 'h2:2.2525e-04', 'O2': 'o2:4.4775e-03', 'Ar': 'Ar:9.9530e-01'}
        compare_str = ', '.join([comps[s] for s in d.composition.keys()])
        species_conversion = {'H2': 'h2', 'O2': 'o2'}
        assert d.get_cantera_mass_fraction(species_conversion) == compare_str

    def test_cantera_change_species_by_inchi_mass_fraction(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[1])
        # The order of the keys should not change between calls provided the contents of the
        # dictionary don't change. Therefore, spec_order should be the same order as the
        # Cantera mole fraction string constructed in a loop in the code
        comps = {'H2': 'h2:2.2525e-04', 'O2': 'o2:4.4775e-03', 'Ar': 'Ar:9.9530e-01'}
        compare_str = ', '.join([comps[s] for s in d.composition.keys()])
        species_conversion = {'1S/H2/h1H': 'h2', '1S/O2/c1-2': 'o2'}
        assert d.get_cantera_mass_fraction(species_conversion) == compare_str

    def test_cantera_change_species_missing_mole_fraction(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[0])
        species_conversion = {'this-does-not-exist': 'h2', 'O2': 'o2'}
        with pytest.raises(ValueError):
            d.get_cantera_mole_fraction(species_conversion)

    def test_cantera_change_species_missing_mass_fraction(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[1])
        species_conversion = {'this-does-not-exist': 'h2', 'O2': 'o2'}
        with pytest.raises(ValueError):
            d.get_cantera_mass_fraction(species_conversion)

    def test_cantera_change_species_duplicate_mole_fraction(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[0])
        species_conversion = {'H2': 'h2', '1S/H2/h1H': 'h2'}
        with pytest.raises(ValueError):
            d.get_cantera_mole_fraction(species_conversion)

    def test_cantera_change_species_duplicate_mass_fraction(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[1])
        species_conversion = {'H2': 'h2', '1S/H2/h1H': 'h2'}
        with pytest.raises(ValueError):
            d.get_cantera_mass_fraction(species_conversion)

    def test_composition(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[2])
        assert len(d.composition) == 3
        assert np.isclose(d.composition['H2'].amount, Q_(0.444))
        assert d.composition['H2'].species_name == 'H2'
        assert np.isclose(d.composition['O2'].amount, Q_(0.556))
        assert d.composition['O2'].species_name == 'O2'
        assert np.isclose(d.composition['Ar'].amount, Q_(99.0))
        assert d.composition['Ar'].species_name == 'Ar'

    def test_ignition_delay(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[0])
        assert np.isclose(d.ignition_delay, Q_(471.54, 'us'))

    def test_first_stage_ignition_delay(self):
        properties = self.load_properties('testfile_rcm2.yaml')
        d = DataPoint(properties[0])
        assert np.isclose(d.first_stage_ignition_delay.value, Q_(0.5, 'ms'))
        assert np.isclose(d.first_stage_ignition_delay.error, Q_(0.005, 'ms'))

    def test_temperature(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[0])
        assert np.isclose(d.temperature, Q_(1164.48, 'K'))

    def test_rcm_data(self):
        properties = self.load_properties('testfile_rcm2.yaml')
        d = DataPoint(properties[0])
        assert np.isclose(d.rcm_data.compression_time, Q_(38.0, 'ms'))
        assert np.isclose(d.rcm_data.compressed_temperature.value, Q_(765, 'K'))
        assert np.isclose(d.rcm_data.compressed_temperature.error, Q_(7.65, 'K'))
        assert np.isclose(d.rcm_data.compressed_pressure, Q_(7.1, 'bar'))
        assert np.isclose(d.rcm_data.stroke, Q_(10.0, 'inch'))
        assert np.isclose(d.rcm_data.clearance, Q_(2.5, 'cm'))
        assert np.isclose(d.rcm_data.compression_ratio, Q_(12.0, 'dimensionless'))

    def test_pressure(self):
        properties = self.load_properties('testfile_required.yaml')
        d = DataPoint(properties[0])
        assert np.isclose(d.pressure, Q_(220.0, 'kPa'))

    def test_pressure_rise(self):
        properties = self.load_properties('testfile_st2.yaml')
        d = DataPoint(properties[0])
        assert np.isclose(d.pressure_rise, Q_(0.1, '1/ms'))

    @pytest.mark.filterwarnings('ignore:Asymmetric uncertainties')
    def test_absolute_sym_uncertainty(self):
        properties = self.load_properties('testfile_uncertainty.yaml')
        d = DataPoint(properties[0])
        assert np.isclose(d.temperature.value, Q_(1164.48, 'K'))
        assert np.isclose(d.temperature.error, Q_(10, 'K'))

    @pytest.mark.filterwarnings('ignore:Asymmetric uncertainties')
    def test_absolute_sym_comp_uncertainty(self):
        properties = self.load_properties('testfile_uncertainty.yaml')
        d = DataPoint(properties[0])
        assert np.isclose(d.composition['O2'].amount.value, Q_(0.556))
        assert np.isclose(d.composition['O2'].amount.error, Q_(0.002))

    @pytest.mark.filterwarnings('ignore:Asymmetric uncertainties')
    def test_relative_sym_uncertainty(self):
        properties = self.load_properties('testfile_uncertainty.yaml')
        d = DataPoint(properties[1])
        assert np.isclose(d.ignition_delay.value, Q_(471.54, 'us'))
        assert np.isclose(d.ignition_delay.error, Q_(47.154, 'us'))
        assert np.isclose(d.ignition_delay.rel, 0.1)

    @pytest.mark.filterwarnings('ignore:Asymmetric uncertainties')
    def test_relative_sym_comp_uncertainty(self):
        properties = self.load_properties('testfile_uncertainty.yaml')
        d = DataPoint(properties[0])
        assert np.isclose(d.composition['H2'].amount.value, Q_(0.444))
        assert np.isclose(d.composition['H2'].amount.error, Q_(0.00444))
        assert np.isclose(d.composition['H2'].amount.rel, 0.01)

    def test_absolute_asym_uncertainty(self):
        properties = self.load_properties('testfile_uncertainty.yaml')
        with pytest.warns(UserWarning) as record:
            d = DataPoint(properties[2])
        m = str(record.pop(UserWarning).message)
        assert m == ('Asymmetric uncertainties are not supported. The maximum of lower-uncertainty '
                     'and upper-uncertainty has been used as the symmetric uncertainty.')
        assert np.isclose(d.temperature.value, Q_(1164.48, 'K'))
        assert np.isclose(d.temperature.error, Q_(10, 'K'))
        assert np.isclose(d.ignition_delay.value, Q_(471.54, 'us'))
        assert np.isclose(d.ignition_delay.error, Q_(10, 'us'))

    def test_relative_asym_uncertainty(self):
        properties = self.load_properties('testfile_uncertainty.yaml')
        with pytest.warns(UserWarning) as record:
            d = DataPoint(properties[3])
        m = str(record.pop(UserWarning).message)
        assert m == ('Asymmetric uncertainties are not supported. The maximum of lower-uncertainty '
                     'and upper-uncertainty has been used as the symmetric uncertainty.')
        assert np.isclose(d.ignition_delay.value, Q_(471.54, 'us'))
        assert np.isclose(d.ignition_delay.error, Q_(47.154, 'us'))
        assert np.isclose(d.ignition_delay.rel, 0.1)
        assert np.isclose(d.temperature.value, Q_(1164.48, 'K'))
        assert np.isclose(d.temperature.error, Q_(116.448, 'K'))
        assert np.isclose(d.temperature.rel, 0.1)

    def test_absolute_asym_comp_uncertainty(self):
        properties = self.load_properties('testfile_uncertainty.yaml')
        with pytest.warns(UserWarning) as record:
            d = DataPoint(properties[0])
        m = str(record.pop(UserWarning).message)
        assert m == ('Asymmetric uncertainties are not supported. The maximum of lower-uncertainty '
                     'and upper-uncertainty has been used as the symmetric uncertainty.')
        assert np.isclose(d.composition['Ar'].amount.value, Q_(99.0))
        assert np.isclose(d.composition['Ar'].amount.error, Q_(1.0))

        with pytest.warns(UserWarning) as record:
            d = DataPoint(properties[1])
        m = str(record.pop(UserWarning).message)
        assert m == ('Asymmetric uncertainties are not supported. The maximum of lower-uncertainty '
                     'and upper-uncertainty has been used as the symmetric uncertainty.')
        assert np.isclose(d.composition['Ar'].amount.value, Q_(99.0))
        assert np.isclose(d.composition['Ar'].amount.error, Q_(1.0))

    def test_relative_asym_comp_uncertainty(self):
        properties = self.load_properties('testfile_uncertainty.yaml')
        with pytest.warns(UserWarning) as record:
            d = DataPoint(properties[1])
        m = str(record.pop(UserWarning).message)
        assert m == ('Asymmetric uncertainties are not supported. The maximum of lower-uncertainty '
                     'and upper-uncertainty has been used as the symmetric uncertainty.')
        assert np.isclose(d.composition['H2'].amount.value, Q_(0.444))
        assert np.isclose(d.composition['H2'].amount.error, Q_(0.0444))
        assert np.isclose(d.composition['H2'].amount.rel, 0.1)

        assert np.isclose(d.composition['O2'].amount.value, Q_(0.556))
        assert np.isclose(d.composition['O2'].amount.error, Q_(0.0556))
        assert np.isclose(d.composition['O2'].amount.rel, 0.1)

    @pytest.mark.filterwarnings('ignore:Asymmetric uncertainties')
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

    @pytest.mark.filterwarnings('ignore:Asymmetric uncertainties')
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
        """Test that volume history works properly.

        Tests for deprecated code, to be removed after PyKED 0.4
        """
        properties = self.load_properties('testfile_rcm_old.yaml')
        with pytest.warns(DeprecationWarning) as record:
            d = DataPoint(properties[0])
        m = str(record.pop(DeprecationWarning).message)
        assert m == ('The volume-history field should be replaced by time-histories. '
                     'volume-history will be removed after PyKED 0.4')
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

    def test_time_and_volume_histories_error(self):
        """Test that time-histories and volume-history together raise an error"""
        properties = self.load_properties('testfile_rcm.yaml')
        properties[0]['volume-history'] = {}
        with pytest.raises(TypeError) as record:
            DataPoint(properties[0])

        assert 'time-histories and volume-history are mutually exclusive' in str(record.value)

    time_history_types = ['volume', 'temperature', 'pressure', 'piston_position',
                          'light_emission', 'OH_emission', 'absorption']

    @pytest.mark.parametrize('history_type', time_history_types)
    def test_time_histories_array(self, history_type):
        """Check that all of the history types are set properly"""
        properties = self.load_properties('testfile_rcm.yaml')
        properties[0]['time-histories'][0]['type'] = history_type
        d = DataPoint(properties[0])

        np.testing.assert_allclose(getattr(d, '{}_history'.format(history_type)).time,
                                   Q_(np.arange(0, 9.7e-2, 1.e-3), 's')
                                   )

        quants = Q_(np.array([
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
        np.testing.assert_allclose(getattr(d, '{}_history'.format(history_type)).quantity, quants)
        assert all([getattr(d, '{}_history'.format(h)) is None for h in self.time_history_types if h != history_type])

    @pytest.mark.parametrize('history_type', time_history_types)
    def test_time_histories_file(self, history_type):
        """Check that all of the history types are set properly"""
        properties = self.load_properties('testfile_rcm.yaml')
        properties[0]['time-histories'][0]['type'] = history_type
        file_path = os.path.join('rcm_history.csv')
        filename = pkg_resources.resource_filename(__name__, file_path)
        properties[0]['time-histories'][0]['values'] = {'filename': filename}
        d = DataPoint(properties[0])

        np.testing.assert_allclose(getattr(d, '{}_history'.format(history_type)).time,
                                   Q_(np.arange(0, 9.7e-2, 1.e-3), 's')
                                   )

        quants = Q_(np.array([
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
        np.testing.assert_allclose(getattr(d, '{}_history'.format(history_type)).quantity, quants)
        assert all([getattr(d, '{}_history'.format(h)) is None for h in self.time_history_types if h != history_type])

    @pytest.mark.parametrize('history_type', zip(time_history_types[:-1], time_history_types[1:]))
    def test_multiple_time_histories(self, history_type):
        """Check that multiple of the history types are set properly.

        Note the units aren't correct for the history types, but that doesn't get checked here, it
        gets checked in the validation of the YAML file by Cerberus.
        """
        properties = self.load_properties('testfile_rcm.yaml')
        properties[0]['time-histories'][0]['type'] = history_type[0]
        properties[0]['time-histories'].append(deepcopy(properties[0]['time-histories'][0]))
        properties[0]['time-histories'][1]['type'] = history_type[1]
        d = DataPoint(properties[0])

        np.testing.assert_allclose(getattr(d, '{}_history'.format(history_type[0])).time,
                                   Q_(np.arange(0, 9.7e-2, 1.e-3), 's'))

        np.testing.assert_allclose(getattr(d, '{}_history'.format(history_type[1])).time,
                                   Q_(np.arange(0, 9.7e-2, 1.e-3), 's'))

        quants = Q_(np.array([
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
        np.testing.assert_allclose(getattr(d, '{}_history'.format(history_type[0])).quantity, quants)
        np.testing.assert_allclose(getattr(d, '{}_history'.format(history_type[1])).quantity, quants)
        assert all([getattr(d, '{}_history'.format(h)) is None for h in self.time_history_types if h not in history_type])

    @pytest.mark.parametrize('history_type', zip(time_history_types, time_history_types))
    def test_duplicate_time_histories(self, history_type):
        """Check that duplicates of the history types raise an error"""
        properties = self.load_properties('testfile_rcm.yaml')
        properties[0]['time-histories'][0]['type'] = history_type[0]
        properties[0]['time-histories'].append(deepcopy(properties[0]['time-histories'][0]))
        properties[0]['time-histories'][1]['type'] = history_type[1]
        with pytest.raises(ValueError) as record:
            DataPoint(properties[0])
        assert ('Each history type may only be specified once. {} was '
                'specified multiple times'.format(history_type[0])) in str(record.value)

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

        # CH, min
        properties = self.load_properties('testfile_required.yaml')
        datapoints = [DataPoint(d) for d in properties]
        assert datapoints[0].ignition_type['target'] == 'CH'
        assert datapoints[0].ignition_type['type'] == 'min'

        # CH*, d/dt max extrapolated
        assert datapoints[1].ignition_type['target'] == 'CH*'
        assert datapoints[1].ignition_type['type'] == 'd/dt max extrapolated'

    def test_changing_ignition_type(self):
        properties = self.load_properties('testfile_st.yaml')
        datapoints = [DataPoint(d) for d in properties]
        datapoints[0].ignition_type['target'] = 'temperature'
        assert datapoints[0].ignition_type['target'] == 'temperature'
        for d in datapoints[1:]:
            assert d.ignition_type['target'] == 'pressure'
