"""
Test module for chemked.py
"""

# Standard libraries
import itertools
import os
import warnings
import xml.etree.ElementTree as etree
from copy import deepcopy
from tempfile import TemporaryDirectory

# Third-party libraries
import numpy as np
import pytest

from pyked._version import __version__
from pyked.chemked import ChemKED, Composition, DataPoint
from pyked.converters import get_common_properties, get_datapoints

# Local imports
from pyked.validation import Q_, OurValidator, schema, yaml

schema["chemked-version"]["allowed"].append(__version__)

warnings.simplefilter("always")


@pytest.mark.usefixtures("mock_all_apis")
class TestChemKED:
    """ """

    def test_create_chemked(self):
        file_path = os.path.join("tests", "testfile_st.yaml")
        ChemKED(file_path)

    def test_skip_validation(self):
        file_path = os.path.join("tests", "testfile_bad.yaml")
        ChemKED(file_path, skip_validation=True)

    def test_datapoints(self):
        file_path = os.path.join("tests", "testfile_st.yaml")
        c = ChemKED(file_path)
        assert len(c.datapoints) == 5

        temperatures = Q_([1164.48, 1164.97, 1264.2, 1332.57, 1519.18], "K")
        ignition_delays = Q_([471.54, 448.03, 291.57, 205.93, 88.11], "us")

        for i, d in enumerate(c.datapoints):
            assert np.isclose(d.ignition_delay, ignition_delays[i])
            assert np.isclose(d.pressure, Q_(220.0, "kPa"))
            assert np.isclose(d.temperature, temperatures[i])
            assert d.pressure_rise is None
            assert d.volume_history is None
            assert d.rcm_data is None
            assert d.ignition_type["type"] == "d/dt max"
            assert d.ignition_type["target"] == "pressure"

    def test_no_input(self):
        """Test that no input raises an exception"""
        with pytest.raises(NameError):
            ChemKED()

    def test_dict_input(self):
        file_path = os.path.join("tests", "testfile_required.yaml")
        with open(file_path) as f:
            properties = yaml.safe_load(f)

        ChemKED(dict_input=properties)

    def test_unallowed_input(self, capfd):
        file_path = os.path.join("tests", "testfile_required.yaml")
        with open(file_path) as f:
            properties = yaml.safe_load(f)

        properties["experiment-type"] = "Ignition Delay"  # should be 'ignition delay'

        with pytest.raises(ValueError):
            ChemKED(dict_input=properties)

        out, _err = capfd.readouterr()
        assert out == (
            "experiment-type has an illegal value. Allowed values are ['ignition "
            "delay'] and are case sensitive.\n"
        )

    def test_missing_input(self, capfd):
        file_path = os.path.join("tests", "testfile_required.yaml")
        with open(file_path) as f:
            properties = yaml.safe_load(f)

        properties.pop("apparatus")

        with pytest.raises(ValueError):
            ChemKED(dict_input=properties)


@pytest.mark.usefixtures("mock_all_apis")
class TestDataFrameOutput:
    """ """

    @pytest.fixture(scope="session")
    def pd(self):
        return pytest.importorskip("pandas")

    @pytest.fixture(scope="session")
    def pdt(self, pd):
        return pd.testing

    def test_get_dataframe(self, pd, pdt):
        yaml_filename = os.path.join("tests", "testfile_st.yaml")
        c = ChemKED(yaml_filename).get_dataframe()
        csv_filename = os.path.join("tests", "dataframe_st.csv")
        converters = {
            "Ignition Delay": Q_,
            "Temperature": Q_,
            "Pressure": Q_,
            "H2": Q_,
            "Ar": Q_,
            "O2": Q_,
        }
        df = pd.read_csv(csv_filename, index_col=0, converters=converters)
        pdt.assert_frame_equal(c.sort_index(axis=1), df.sort_index(axis=1), check_names=True)

    def test_custom_dataframe(self, pd, pdt):
        yaml_filename = os.path.join("tests", "testfile_st.yaml")
        cols_to_get = [
            "composition",
            "Reference",
            "apparatus",
            "temperature",
            "ignition delay",
        ]
        c = ChemKED(yaml_filename).get_dataframe(cols_to_get)
        csv_filename = os.path.join("tests", "dataframe_st.csv")
        converters = {
            "Ignition Delay": Q_,
            "Temperature": Q_,
            "Pressure": Q_,
            "H2": Q_,
            "Ar": Q_,
            "O2": Q_,
        }
        use_cols = [
            "Apparatus:Kind",
            "Apparatus:Institution",
            "Apparatus:Facility",
            "Reference:Volume",
            "Reference:Journal",
            "Reference:Doi",
            "Reference:Authors",
            "Reference:Detail",
            "Reference:Year",
            "Reference:Pages",
            "Temperature",
            "Ignition Delay",
            "H2",
            "Ar",
            "O2",
            "Composition:Kind",
        ]
        df = pd.read_csv(csv_filename, converters=converters, usecols=use_cols)
        pdt.assert_frame_equal(c.sort_index(axis=1), df.sort_index(axis=1), check_names=True)

    def test_custom_dataframe_2(self, pd, pdt):
        yaml_filename = os.path.join("tests", "testfile_st.yaml")
        cols_to_get = ["temperature", "ignition delay", "Pressure"]
        c = ChemKED(yaml_filename).get_dataframe(cols_to_get)
        csv_filename = os.path.join("tests", "dataframe_st.csv")
        converters = {
            "Ignition Delay": Q_,
            "Temperature": Q_,
            "Pressure": Q_,
            "H2": Q_,
            "Ar": Q_,
            "O2": Q_,
        }
        use_cols = ["Temperature", "Ignition Delay", "Pressure"]
        df = pd.read_csv(csv_filename, converters=converters, usecols=use_cols)
        pdt.assert_frame_equal(c.sort_index(axis=1), df.sort_index(axis=1), check_names=True)

    def test_invalid_column(self, pd):
        yaml_filename = os.path.join("tests", "testfile_st.yaml")
        with pytest.raises(ValueError):
            ChemKED(yaml_filename).get_dataframe(["bad column"])

    def test_many_species(self, pd):
        yaml_filename = os.path.join("tests", "testfile_many_species.yaml")
        c = ChemKED(yaml_filename).get_dataframe()
        assert c.iloc[0]["New-Species-1"] == Q_(0.0, "dimensionless")
        assert c.iloc[0]["New-Species-2"] == Q_(0.0, "dimensionless")
        assert c.iloc[1]["H2"] == Q_(0.0, "dimensionless")
        assert c.iloc[1]["O2"] == Q_(0.0, "dimensionless")


@pytest.mark.usefixtures("mock_all_apis")
class TestWriteFile:
    """ """

    def test_file_exists(self):
        """ """
        yaml_filename = os.path.join("tests", "testfile_st.yaml")
        c = ChemKED(yaml_filename)
        with pytest.raises(OSError):
            c.write_file(yaml_filename)

    def test_overwrite(self):
        """ """
        yaml_filename = os.path.join("tests", "testfile_st.yaml")
        with open(yaml_filename) as f:
            lines = f.readlines()

        with TemporaryDirectory() as temp_dir:
            newfile_path = os.path.join(temp_dir, "testfile.yaml")
            with open(newfile_path, "w") as f:
                f.writelines(lines)
            c = ChemKED(newfile_path)

            # Expected error
            with pytest.raises(OSError):
                c.write_file(newfile_path)

            # Now successful
            assert c.write_file(newfile_path, overwrite=True) is None

    @pytest.mark.parametrize(
        "filename",
        [
            "testfile_st.yaml",
            "testfile_st2.yaml",
            "testfile_rcm.yaml",
            "testfile_required.yaml",
            "testfile_uncertainty.yaml",
        ],
    )
    @pytest.mark.filterwarnings("ignore:Asymmetric uncertainties")
    def test_write_files(self, filename):
        """Test proper writing of ChemKED files."""
        filename = os.path.join("tests", filename)
        c = ChemKED(filename)

        with TemporaryDirectory() as temp_dir:
            c.write_file(os.path.join(temp_dir, "testfile.yaml"))

            # Now read in the file
            with open(os.path.join(temp_dir, "testfile.yaml")) as f:
                properties = yaml.safe_load(f)

        assert properties == c._properties


@pytest.mark.usefixtures("mock_all_apis")
class TestConvertToReSpecTh:
    """Tests for conversion of ChemKED to ReSpecTh"""

    @pytest.mark.parametrize("filename_ck", ["testfile_st.yaml", "testfile_rcm.yaml"])
    def test_conversion_to_respecth(self, filename_ck):
        """Test proper conversion to ReSpecTh XML."""
        filename = os.path.join("tests", filename_ck)
        c_true = ChemKED(filename)

        with TemporaryDirectory() as temp_dir:
            newfile = os.path.join(temp_dir, "test.xml")
            c_true.convert_to_ReSpecTh(newfile)
            with pytest.warns(UserWarning) as record:
                c = ChemKED.from_respecth(newfile)

        m = str(record.pop(UserWarning).message)
        assert m == "Using DOI to obtain reference information, rather than preferredKey."

        assert c.file_authors[0]["name"] == c_true.file_authors[0]["name"]

        assert c.reference.detail == f"Converted from ReSpecTh XML file {os.path.split(newfile)[1]}"

        assert c.apparatus.kind == c_true.apparatus.kind
        assert c.experiment_type == c_true.experiment_type
        assert c.reference.doi == c_true.reference.doi
        assert len(c.datapoints) == len(c_true.datapoints)

    @pytest.mark.parametrize(
        "history_type, unit",
        [("volume", "cm3"), ("temperature", "K"), ("pressure", "bar")],
    )
    def test_time_history_conversion_to_respecth(self, history_type, unit):
        """Test proper conversion to ReSpecTh XML with time histories."""
        filename = os.path.join("tests", "testfile_rcm.yaml")
        with open(filename) as yaml_file:
            properties = yaml.safe_load(yaml_file)
        properties["datapoints"][0]["time-histories"][0]["type"] = history_type
        properties["datapoints"][0]["time-histories"][0]["quantity"]["units"] = unit
        c_true = ChemKED(dict_input=properties)

        with TemporaryDirectory() as temp_dir:
            newfile = os.path.join(temp_dir, "test.xml")
            c_true.convert_to_ReSpecTh(newfile)
            with pytest.warns(UserWarning) as record:
                c = ChemKED.from_respecth(newfile)

        m = str(record.pop(UserWarning).message)
        assert m == "Using DOI to obtain reference information, rather than preferredKey."

        assert c.file_authors[0]["name"] == c_true.file_authors[0]["name"]

        assert c.reference.detail == f"Converted from ReSpecTh XML file {os.path.split(newfile)[1]}"

        assert c.apparatus.kind == c_true.apparatus.kind
        assert c.experiment_type == c_true.experiment_type
        assert c.reference.doi == c_true.reference.doi
        assert len(c.datapoints) == len(c_true.datapoints)
        assert getattr(c.datapoints[0], f"{history_type}_history") is not None

    @pytest.mark.parametrize(
        "history_type, unit",
        zip(
            ["piston position", "light emission", "OH emission", "absorption"],
            ["cm", "dimensionless", "dimensionless", "dimensionless"],
        ),
    )
    def test_time_history_conversion_to_respecth_unsupported(self, history_type, unit):
        """Test proper conversion to ReSpecTh XML with unsupported time histories."""
        filename = os.path.join("tests", "testfile_rcm.yaml")
        with open(filename) as yaml_file:
            properties = yaml.safe_load(yaml_file)
        properties["datapoints"][0]["time-histories"][0]["type"] = history_type
        properties["datapoints"][0]["time-histories"][0]["quantity"]["units"] = unit
        c_true = ChemKED(dict_input=properties)
        with TemporaryDirectory() as temp_dir:
            newfile = os.path.join(temp_dir, "test.xml")
            with pytest.warns(UserWarning) as record:
                c_true.convert_to_ReSpecTh(newfile)
            m = str(record.pop(UserWarning).message)
            assert m == (
                f"The time-history type {history_type} is not supported by ReSpecTh for "
                "ignition delay experiments"
            )
            with pytest.warns(UserWarning) as record:
                c = ChemKED.from_respecth(newfile)

        m = str(record.pop(UserWarning).message)
        assert m == "Using DOI to obtain reference information, rather than preferredKey."

        assert c.file_authors[0]["name"] == c_true.file_authors[0]["name"]

        assert c.reference.detail == f"Converted from ReSpecTh XML file {os.path.split(newfile)[1]}"

        assert c.apparatus.kind == c_true.apparatus.kind
        assert c.experiment_type == c_true.experiment_type
        assert c.reference.doi == c_true.reference.doi
        assert len(c.datapoints) == len(c_true.datapoints)
        assert getattr(c.datapoints[0], "{}_history".format(history_type.replace(" ", "_"))) is None

    @pytest.mark.parametrize(
        "experiment_type",
        [
            "Laminar flame speed measurement",
            "Species profile measurement",
            "Outlet concentration measurement",
            "Burner stabilized flame speciation measurement",
            "Jet-stirred reactor measurement",
            "Reaction rate coefficient measurement",
        ],
    )
    def test_conversion_to_respecth_error(self, experiment_type):
        """Test for conversion errors."""
        filename = os.path.join("tests", "testfile_st.yaml")
        c = ChemKED(filename)

        c.experiment_type = experiment_type

        with pytest.raises(NotImplementedError) as excinfo:
            c.convert_to_ReSpecTh("test.xml")
        assert "Only ignition delay type supported for conversion." in str(excinfo.value)

    def test_conversion_datapoints_composition_missing_inchi(self):
        """Test for appropriate handling of composition with missing InChI."""
        filename = os.path.join("tests", "testfile_st.yaml")
        c = ChemKED(filename)

        for idx, _dp in enumerate(c.datapoints):
            c.datapoints[idx].composition = {
                "H2": Composition(
                    **{
                        "amount": Q_(0.1, "dimensionless"),
                        "species_name": "H2",
                        "InChI": None,
                        "SMILES": None,
                        "atomic_composition": None,
                    }
                ),
                "O2": Composition(
                    **{
                        "amount": Q_(0.1, "dimensionless"),
                        "species_name": "O2",
                        "InChI": None,
                        "SMILES": None,
                        "atomic_composition": None,
                    }
                ),
                "Ar": Composition(
                    **{
                        "amount": Q_(0.8, "dimensionless"),
                        "species_name": "Ar",
                        "InChI": None,
                        "SMILES": None,
                        "atomic_composition": None,
                    }
                ),
            }

        with TemporaryDirectory() as temp_dir:
            newfile = os.path.join(temp_dir, "test.xml")
            c.convert_to_ReSpecTh(newfile)
            tree = etree.parse(newfile)
        root = tree.getroot()

        with pytest.warns(UserWarning) as record:
            common = get_common_properties(root)
        messages = [str(record.pop(UserWarning).message) for i in range(3)]
        assert "Missing InChI for species H2" in messages
        assert "Missing InChI for species O2" in messages
        assert "Missing InChI for species Ar" in messages
        assert len(common["composition"]["species"]) == 3
        for spec in common["composition"]["species"]:
            assert spec in [
                {"amount": [0.1], "species-name": "H2"},
                {"amount": [0.1], "species-name": "O2"},
                {"amount": [0.8], "species-name": "Ar"},
            ]

    def test_conversion_datapoints_different_composition(self):
        """Test for appropriate handling of datapoints with different composition."""
        filename = os.path.join("tests", "testfile_st.yaml")
        c = ChemKED(filename)

        c.datapoints[0].composition = {
            "H2": Composition(
                **{
                    "InChI": "1S/H2/h1H",
                    "amount": Q_(0.1, "dimensionless"),
                    "species_name": "H2",
                    "SMILES": None,
                    "atomic_composition": None,
                }
            ),
            "O2": Composition(
                **{
                    "InChI": "1S/O2/c1-2",
                    "amount": Q_(0.1, "dimensionless"),
                    "species_name": "O2",
                    "SMILES": None,
                    "atomic_composition": None,
                }
            ),
            "N2": Composition(
                **{
                    "amount": Q_(0.8, "dimensionless"),
                    "species_name": "N2",
                    "SMILES": "N#N",
                    "InChI": None,
                    "atomic_composition": None,
                }
            ),
        }

        with TemporaryDirectory() as temp_dir:
            newfile = os.path.join(temp_dir, "test.xml")
            c.convert_to_ReSpecTh(newfile)

            tree = etree.parse(newfile)
        root = tree.getroot()
        with pytest.warns(UserWarning) as record:
            datapoints = get_datapoints(root)
        m = str(record.pop(UserWarning).message)
        assert m == "Missing InChI for species N2"

        assert len(datapoints[0]["composition"]["species"]) == 3
        for spec in datapoints[0]["composition"]["species"]:
            assert spec in [
                {"InChI": "1S/H2/h1H", "amount": [0.1], "species-name": "H2"},
                {"InChI": "1S/O2/c1-2", "amount": [0.1], "species-name": "O2"},
                {"amount": [0.8], "species-name": "N2", "InChI": None},
            ]

    def test_conversion_error_datapoints_different_composition_type(self):
        """Test for appropriate erorr of datapoints with different composition type."""
        filename = os.path.join("tests", "testfile_st.yaml")
        c = ChemKED(filename)
        c.datapoints[0].composition_type = "mass fraction"

        with pytest.raises(NotImplementedError) as excinfo:
            c.convert_to_ReSpecTh("test.xml")
        assert (
            "Error: ReSpecTh does not support varying composition type among datapoints."
        ) in str(excinfo.value)

    def test_conversion_to_respecth_error_volume_history_datapoints(self):
        """Test for error raised if RCM with multiple datapoints with volume history."""
        filename = os.path.join("tests", "testfile_rcm.yaml")
        c = ChemKED(filename)

        # Repeat datapoint, such that two with volume histories
        c.datapoints.append(c.datapoints[0])

        with pytest.raises(NotImplementedError) as excinfo:
            c.convert_to_ReSpecTh("test.xml")
        assert (
            "Error: ReSpecTh files do not support multiple datapoints with a "
            "time history." in str(excinfo.value)
        )

    @pytest.mark.parametrize(
        "ignition_target", ["pressure", "temperature", "OH", "CH", "OH*", "CH*"]
    )
    def test_conversion_to_respecth_ignition_targets(self, ignition_target):
        """Test proper conversion for different ignition targets."""
        filename = os.path.join("tests", "testfile_st.yaml")
        c = ChemKED(filename)

        for dp in c.datapoints:
            dp.ignition_type["target"] = ignition_target

        with TemporaryDirectory() as temp_dir:
            newfile = os.path.join(temp_dir, "test.xml")
            c.convert_to_ReSpecTh(newfile)

            tree = etree.parse(newfile)
        root = tree.getroot()
        elem = root.find("ignitionType")
        elem = elem.attrib

        if ignition_target == "pressure":
            assert elem["target"] == "P"
        elif ignition_target == "temperature":
            assert elem["target"] == "T"
        else:
            assert elem["target"] == ignition_target

    @pytest.mark.parametrize(
        "ignition_type", ["d/dt max", "max", "1/2 max", "min", "d/dt max extrapolated"]
    )
    def test_conversion_to_respecth_ignition_types(self, ignition_type):
        """Test proper conversion for different ignition types."""
        filename = os.path.join("tests", "testfile_st.yaml")
        c = ChemKED(filename)

        for dp in c.datapoints:
            dp.ignition_type["type"] = ignition_type

        with TemporaryDirectory() as temp_dir:
            newfile = os.path.join(temp_dir, "test.xml")
            c.convert_to_ReSpecTh(newfile)

            tree = etree.parse(newfile)
        root = tree.getroot()
        elem = root.find("ignitionType")
        elem = elem.attrib

        if ignition_type == "d/dt max extrapolated":
            assert elem["type"] == "baseline max intercept from d/dt"
        else:
            assert elem["type"] == ignition_type

    def test_conversion_multiple_ignition_targets(self):
        """Test that multiple ignition targets for datapoints fails"""
        filename = os.path.join("tests", "testfile_st.yaml")
        c = ChemKED(filename)

        c.datapoints[0].ignition_type["target"] = "temperature"
        with TemporaryDirectory() as temp_dir:
            newfile = os.path.join(temp_dir, "test.xml")
            with pytest.raises(NotImplementedError) as e:
                c.convert_to_ReSpecTh(newfile)

        assert (
            "Different ignition targets or types for multiple datapoints are not supported in "
            "ReSpecTh." in str(e.value)
        )


@pytest.mark.usefixtures("mock_all_apis")
class TestDataPoint:
    """ """

    def load_properties(self, test_file):
        filename = os.path.join("tests", test_file)
        with open(filename) as f:
            properties = yaml.safe_load(f)

        v = OurValidator(schema)
        if not v.validate(properties):
            raise ValueError(v.errors)

        return properties["datapoints"]

    def test_create_datapoint(self):
        properties = self.load_properties("testfile_required.yaml")
        DataPoint(properties[0])

    def test_cantera_unknown_composition_type(self):
        properties = self.load_properties("testfile_required.yaml")
        d = DataPoint(properties[0])
        d.composition_type = "unknown type"
        with pytest.raises(ValueError):
            d.get_cantera_composition_string()

    def test_cantera_composition_mole_fraction(self):
        properties = self.load_properties("testfile_required.yaml")
        d = DataPoint(properties[0])
        # The order of the keys should not change between calls provided the contents of the
        # dictionary don't change. Therefore, spec_order should be the same order as the
        # Cantera mole fraction string constructed in a loop in the code
        comps = {"H2": "H2:4.4400e-03", "O2": "O2:5.5600e-03", "Ar": "Ar:9.9000e-01"}
        compare_str = ", ".join([comps[s] for s in d.composition.keys()])
        assert d.composition_type == "mole fraction"
        assert d.get_cantera_mole_fraction() == compare_str

    def test_cantera_composition_mole_fraction_bad(self):
        properties = self.load_properties("testfile_required.yaml")
        d = DataPoint(properties[1])
        assert d.composition_type == "mass fraction"
        with pytest.raises(ValueError):
            d.get_cantera_mole_fraction()

    def test_cantera_composition_mass_fraction(self):
        properties = self.load_properties("testfile_required.yaml")
        d = DataPoint(properties[1])
        # The order of the keys should not change between calls provided the contents of the
        # dictionary don't change. Therefore, spec_order should be the same order as the
        # Cantera mole fraction string constructed in a loop in the code
        comps = {"H2": "H2:2.2525e-04", "O2": "O2:4.4775e-03", "Ar": "Ar:9.9530e-01"}
        compare_str = ", ".join([comps[s] for s in d.composition.keys()])
        assert d.composition_type == "mass fraction"
        assert d.get_cantera_mass_fraction() == compare_str

    def test_cantera_composition_mass_fraction_bad(self):
        properties = self.load_properties("testfile_required.yaml")
        d = DataPoint(properties[0])
        assert d.composition_type == "mole fraction"
        with pytest.raises(ValueError):
            d.get_cantera_mass_fraction()

    def test_cantera_composition_mole_percent(self):
        properties = self.load_properties("testfile_required.yaml")
        d = DataPoint(properties[2])
        # The order of the keys should not change between calls provided the contents of the
        # dictionary don't change. Therefore, spec_order should be the same order as the
        # Cantera mole fraction string constructed in a loop in the code
        comps = {"H2": "H2:4.4400e-03", "O2": "O2:5.5600e-03", "Ar": "Ar:9.9000e-01"}
        compare_str = ", ".join([comps[s] for s in d.composition.keys()])
        assert d.composition_type == "mole percent"
        assert d.get_cantera_mole_fraction() == compare_str

    def test_cantera_change_species_by_name_mole_fraction(self):
        properties = self.load_properties("testfile_required.yaml")
        d = DataPoint(properties[0])
        # The order of the keys should not change between calls provided the contents of the
        # dictionary don't change. Therefore, spec_order should be the same order as the
        # Cantera mole fraction string constructed in a loop in the code
        comps = {"H2": "h2:4.4400e-03", "O2": "o2:5.5600e-03", "Ar": "Ar:9.9000e-01"}
        compare_str = ", ".join([comps[s] for s in d.composition.keys()])
        species_conversion = {"H2": "h2", "O2": "o2"}
        assert d.get_cantera_mole_fraction(species_conversion) == compare_str

    def test_cantera_change_species_by_inchi_mole_fraction(self):
        properties = self.load_properties("testfile_required.yaml")
        d = DataPoint(properties[0])
        # The order of the keys should not change between calls provided the contents of the
        # dictionary don't change. Therefore, spec_order should be the same order as the
        # Cantera mole fraction string constructed in a loop in the code
        comps = {"H2": "h2:4.4400e-03", "O2": "o2:5.5600e-03", "Ar": "Ar:9.9000e-01"}
        compare_str = ", ".join([comps[s] for s in d.composition.keys()])
        species_conversion = {"1S/H2/h1H": "h2", "1S/O2/c1-2": "o2"}
        assert d.get_cantera_mole_fraction(species_conversion) == compare_str

    def test_cantera_change_species_by_name_mole_percent(self):
        properties = self.load_properties("testfile_required.yaml")
        d = DataPoint(properties[2])
        # The order of the keys should not change between calls provided the contents of the
        # dictionary don't change. Therefore, spec_order should be the same order as the
        # Cantera mole fraction string constructed in a loop in the code
        comps = {"H2": "h2:4.4400e-03", "O2": "o2:5.5600e-03", "Ar": "Ar:9.9000e-01"}
        compare_str = ", ".join([comps[s] for s in d.composition.keys()])
        species_conversion = {"H2": "h2", "O2": "o2"}
        assert d.get_cantera_mole_fraction(species_conversion) == compare_str

    def test_cantera_change_species_by_inchi_mole_percent(self):
        properties = self.load_properties("testfile_required.yaml")
        d = DataPoint(properties[2])
        # The order of the keys should not change between calls provided the contents of the
        # dictionary don't change. Therefore, spec_order should be the same order as the
        # Cantera mole fraction string constructed in a loop in the code
        comps = {"H2": "h2:4.4400e-03", "O2": "o2:5.5600e-03", "Ar": "Ar:9.9000e-01"}
        compare_str = ", ".join([comps[s] for s in d.composition.keys()])
        species_conversion = {"1S/H2/h1H": "h2", "1S/O2/c1-2": "o2"}
        assert d.get_cantera_mole_fraction(species_conversion) == compare_str

    def test_cantera_change_species_by_name_mass_fraction(self):
        properties = self.load_properties("testfile_required.yaml")
        d = DataPoint(properties[1])
        # The order of the keys should not change between calls provided the contents of the
        # dictionary don't change. Therefore, spec_order should be the same order as the
        # Cantera mole fraction string constructed in a loop in the code
        comps = {"H2": "h2:2.2525e-04", "O2": "o2:4.4775e-03", "Ar": "Ar:9.9530e-01"}
        compare_str = ", ".join([comps[s] for s in d.composition.keys()])
        species_conversion = {"H2": "h2", "O2": "o2"}
        assert d.get_cantera_mass_fraction(species_conversion) == compare_str

    def test_cantera_change_species_by_inchi_mass_fraction(self):
        properties = self.load_properties("testfile_required.yaml")
        d = DataPoint(properties[1])
        # The order of the keys should not change between calls provided the contents of the
        # dictionary don't change. Therefore, spec_order should be the same order as the
        # Cantera mole fraction string constructed in a loop in the code
        comps = {"H2": "h2:2.2525e-04", "O2": "o2:4.4775e-03", "Ar": "Ar:9.9530e-01"}
        compare_str = ", ".join([comps[s] for s in d.composition.keys()])
        species_conversion = {"1S/H2/h1H": "h2", "1S/O2/c1-2": "o2"}
        assert d.get_cantera_mass_fraction(species_conversion) == compare_str

    def test_cantera_change_species_missing_mole_fraction(self):
        properties = self.load_properties("testfile_required.yaml")
        d = DataPoint(properties[0])
        species_conversion = {"this-does-not-exist": "h2", "O2": "o2"}
        with pytest.raises(ValueError):
            d.get_cantera_mole_fraction(species_conversion)

    def test_cantera_change_species_missing_mass_fraction(self):
        properties = self.load_properties("testfile_required.yaml")
        d = DataPoint(properties[1])
        species_conversion = {"this-does-not-exist": "h2", "O2": "o2"}
        with pytest.raises(ValueError):
            d.get_cantera_mass_fraction(species_conversion)

    def test_cantera_change_species_duplicate_mole_fraction(self):
        properties = self.load_properties("testfile_required.yaml")
        d = DataPoint(properties[0])
        species_conversion = {"H2": "h2", "1S/H2/h1H": "h2"}
        with pytest.raises(ValueError):
            d.get_cantera_mole_fraction(species_conversion)

    def test_cantera_change_species_duplicate_mass_fraction(self):
        properties = self.load_properties("testfile_required.yaml")
        d = DataPoint(properties[1])
        species_conversion = {"H2": "h2", "1S/H2/h1H": "h2"}
        with pytest.raises(ValueError):
            d.get_cantera_mass_fraction(species_conversion)

    def test_composition(self):
        properties = self.load_properties("testfile_required.yaml")
        d = DataPoint(properties[2])
        assert len(d.composition) == 3
        assert np.isclose(d.composition["H2"].amount, Q_(0.444))
        assert d.composition["H2"].species_name == "H2"
        assert np.isclose(d.composition["O2"].amount, Q_(0.556))
        assert d.composition["O2"].species_name == "O2"
        assert np.isclose(d.composition["Ar"].amount, Q_(99.0))
        assert d.composition["Ar"].species_name == "Ar"

    def test_ignition_delay(self):
        properties = self.load_properties("testfile_required.yaml")
        d = DataPoint(properties[0])
        assert np.isclose(d.ignition_delay, Q_(471.54, "us"))

    def test_first_stage_ignition_delay(self):
        properties = self.load_properties("testfile_rcm2.yaml")
        d = DataPoint(properties[0])
        assert np.isclose(d.first_stage_ignition_delay.value, Q_(0.5, "ms"))
        assert np.isclose(d.first_stage_ignition_delay.error, Q_(0.005, "ms"))

    def test_temperature(self):
        properties = self.load_properties("testfile_required.yaml")
        d = DataPoint(properties[0])
        assert np.isclose(d.temperature, Q_(1164.48, "K"))

    def test_rcm_data(self):
        properties = self.load_properties("testfile_rcm2.yaml")
        d = DataPoint(properties[0])
        assert np.isclose(d.rcm_data.compression_time, Q_(38.0, "ms"))
        assert np.isclose(d.rcm_data.compressed_temperature.value, Q_(765, "K"))
        assert np.isclose(d.rcm_data.compressed_temperature.error, Q_(7.65, "K"))
        assert np.isclose(d.rcm_data.compressed_pressure, Q_(7.1, "bar"))
        assert np.isclose(d.rcm_data.stroke, Q_(10.0, "inch"))
        assert np.isclose(d.rcm_data.clearance, Q_(2.5, "cm"))
        assert np.isclose(d.rcm_data.compression_ratio, Q_(12.0, "dimensionless"))

    def test_pressure(self):
        properties = self.load_properties("testfile_required.yaml")
        d = DataPoint(properties[0])
        assert np.isclose(d.pressure, Q_(220.0, "kPa"))

    def test_pressure_rise(self):
        properties = self.load_properties("testfile_st2.yaml")
        d = DataPoint(properties[0])
        assert np.isclose(d.pressure_rise, Q_(0.1, "1/ms"))

    @pytest.mark.filterwarnings("ignore:Asymmetric uncertainties")
    def test_absolute_sym_uncertainty(self):
        properties = self.load_properties("testfile_uncertainty.yaml")
        d = DataPoint(properties[0])
        assert np.isclose(d.temperature.value, Q_(1164.48, "K"))
        assert np.isclose(d.temperature.error, Q_(10, "K"))

    @pytest.mark.filterwarnings("ignore:Asymmetric uncertainties")
    def test_absolute_sym_comp_uncertainty(self):
        properties = self.load_properties("testfile_uncertainty.yaml")
        d = DataPoint(properties[0])
        assert np.isclose(d.composition["O2"].amount.value, Q_(0.556))
        assert np.isclose(d.composition["O2"].amount.error, Q_(0.002))

    @pytest.mark.filterwarnings("ignore:Asymmetric uncertainties")
    def test_relative_sym_uncertainty(self):
        properties = self.load_properties("testfile_uncertainty.yaml")
        d = DataPoint(properties[1])
        assert np.isclose(d.ignition_delay.value, Q_(471.54, "us"))
        assert np.isclose(d.ignition_delay.error, Q_(47.154, "us"))
        assert np.isclose(d.ignition_delay.rel, 0.1)

    @pytest.mark.filterwarnings("ignore:Asymmetric uncertainties")
    def test_relative_sym_comp_uncertainty(self):
        properties = self.load_properties("testfile_uncertainty.yaml")
        d = DataPoint(properties[0])
        assert np.isclose(d.composition["H2"].amount.value, Q_(0.444))
        assert np.isclose(d.composition["H2"].amount.error, Q_(0.00444))
        assert np.isclose(d.composition["H2"].amount.rel, 0.01)

    def test_absolute_asym_uncertainty(self):
        properties = self.load_properties("testfile_uncertainty.yaml")
        with pytest.warns(UserWarning) as record:
            d = DataPoint(properties[2])
        m = str(record.pop(UserWarning).message)
        assert m == (
            "Asymmetric uncertainties are not supported. The maximum of lower-uncertainty "
            "and upper-uncertainty has been used as the symmetric uncertainty."
        )
        assert np.isclose(d.temperature.value, Q_(1164.48, "K"))
        assert np.isclose(d.temperature.error, Q_(10, "K"))
        assert np.isclose(d.ignition_delay.value, Q_(471.54, "us"))
        assert np.isclose(d.ignition_delay.error, Q_(10, "us"))

    def test_relative_asym_uncertainty(self):
        properties = self.load_properties("testfile_uncertainty.yaml")
        with pytest.warns(UserWarning) as record:
            d = DataPoint(properties[3])
        m = str(record.pop(UserWarning).message)
        assert m == (
            "Asymmetric uncertainties are not supported. The maximum of lower-uncertainty "
            "and upper-uncertainty has been used as the symmetric uncertainty."
        )
        assert np.isclose(d.ignition_delay.value, Q_(471.54, "us"))
        assert np.isclose(d.ignition_delay.error, Q_(47.154, "us"))
        assert np.isclose(d.ignition_delay.rel, 0.1)
        assert np.isclose(d.temperature.value, Q_(1164.48, "K"))
        assert np.isclose(d.temperature.error, Q_(116.448, "K"))
        assert np.isclose(d.temperature.rel, 0.1)

    def test_absolute_asym_comp_uncertainty(self):
        properties = self.load_properties("testfile_uncertainty.yaml")
        with pytest.warns(UserWarning) as record:
            d = DataPoint(properties[0])
        m = str(record.pop(UserWarning).message)
        assert m == (
            "Asymmetric uncertainties are not supported. The maximum of lower-uncertainty "
            "and upper-uncertainty has been used as the symmetric uncertainty."
        )
        assert np.isclose(d.composition["Ar"].amount.value, Q_(99.0))
        assert np.isclose(d.composition["Ar"].amount.error, Q_(1.0))

        with pytest.warns(UserWarning) as record:
            d = DataPoint(properties[1])
        m = str(record.pop(UserWarning).message)
        assert m == (
            "Asymmetric uncertainties are not supported. The maximum of lower-uncertainty "
            "and upper-uncertainty has been used as the symmetric uncertainty."
        )
        assert np.isclose(d.composition["Ar"].amount.value, Q_(99.0))
        assert np.isclose(d.composition["Ar"].amount.error, Q_(1.0))

    def test_relative_asym_comp_uncertainty(self):
        properties = self.load_properties("testfile_uncertainty.yaml")
        with pytest.warns(UserWarning) as record:
            d = DataPoint(properties[1])
        m = str(record.pop(UserWarning).message)
        assert m == (
            "Asymmetric uncertainties are not supported. The maximum of lower-uncertainty "
            "and upper-uncertainty has been used as the symmetric uncertainty."
        )
        assert np.isclose(d.composition["H2"].amount.value, Q_(0.444))
        assert np.isclose(d.composition["H2"].amount.error, Q_(0.0444))
        assert np.isclose(d.composition["H2"].amount.rel, 0.1)

        assert np.isclose(d.composition["O2"].amount.value, Q_(0.556))
        assert np.isclose(d.composition["O2"].amount.error, Q_(0.0556))
        assert np.isclose(d.composition["O2"].amount.rel, 0.1)

    @pytest.mark.filterwarnings("ignore:Asymmetric uncertainties")
    def test_missing_uncertainty_parts(self):
        properties = self.load_properties("testfile_uncertainty.yaml")
        for prop in ["uncertainty", "uncertainty-type"]:
            save = properties[0]["temperature"][1].pop(prop)
            with pytest.raises(ValueError):
                DataPoint(properties[0])
            properties[0]["temperature"][1][prop] = save

            save = properties[1]["ignition-delay"][1].pop(prop)
            with pytest.raises(ValueError):
                DataPoint(properties[1])
            properties[1]["ignition-delay"][1][prop] = save

        for prop in ["upper-uncertainty", "lower-uncertainty"]:
            save = properties[2]["temperature"][1].pop(prop)
            with pytest.raises(ValueError):
                DataPoint(properties[2])
            properties[0]["temperature"][1][prop] = save

            save = properties[3]["ignition-delay"][1].pop(prop)
            with pytest.raises(ValueError):
                DataPoint(properties[3])
            properties[1]["ignition-delay"][1][prop] = save

    @pytest.mark.filterwarnings("ignore:Asymmetric uncertainties")
    def test_missing_comp_uncertainty_parts(self):
        properties = self.load_properties("testfile_uncertainty.yaml")
        for prop in ["uncertainty", "uncertainty-type"]:
            save = properties[0]["composition"]["species"][0]["amount"][1].pop(prop)
            with pytest.raises(ValueError):
                DataPoint(properties[0])
            properties[0]["composition"]["species"][0]["amount"][1][prop] = save

            save = properties[0]["composition"]["species"][1]["amount"][1].pop(prop)
            with pytest.raises(ValueError):
                DataPoint(properties[0])
            properties[0]["composition"]["species"][1]["amount"][1][prop] = save

        for prop in ["upper-uncertainty", "lower-uncertainty"]:
            save = properties[0]["composition"]["species"][2]["amount"][1].pop(prop)
            with pytest.raises(ValueError):
                DataPoint(properties[0])
            properties[0]["composition"]["species"][2]["amount"][1][prop] = save

            save = properties[1]["composition"]["species"][2]["amount"][1].pop(prop)
            with pytest.raises(ValueError):
                DataPoint(properties[1])
            properties[1]["composition"]["species"][2]["amount"][1][prop] = save

    def test_volume_history(self):
        """Test that volume history works properly.

        Tests for deprecated code, to be removed after PyKED 0.4
        """
        properties = self.load_properties("testfile_rcm_old.yaml")
        with pytest.warns(DeprecationWarning) as record:
            d = DataPoint(properties[0])
        m = str(record.pop(DeprecationWarning).message)
        assert m == (
            "The volume-history field should be replaced by time-histories. "
            "volume-history will be removed after PyKED 0.4"
        )
        # Check other data group with volume history
        np.testing.assert_allclose(d.volume_history.time, Q_(np.arange(0, 9.7e-2, 1.0e-3), "s"))

        volumes = Q_(
            np.array(
                [
                    5.47669375000e002,
                    5.46608789894e002,
                    5.43427034574e002,
                    5.38124109043e002,
                    5.30700013298e002,
                    5.21154747340e002,
                    5.09488311170e002,
                    4.95700704787e002,
                    4.79791928191e002,
                    4.61761981383e002,
                    4.41610864362e002,
                    4.20399162234e002,
                    3.99187460106e002,
                    3.77975757979e002,
                    3.56764055851e002,
                    3.35552353723e002,
                    3.14340651596e002,
                    2.93128949468e002,
                    2.71917247340e002,
                    2.50705545213e002,
                    2.29493843085e002,
                    2.08282140957e002,
                    1.87070438830e002,
                    1.65858736702e002,
                    1.44647034574e002,
                    1.23435332447e002,
                    1.02223630319e002,
                    8.10119281915e001,
                    6.33355097518e001,
                    5.27296586879e001,
                    4.91943750000e001,
                    4.97137623933e001,
                    5.02063762048e001,
                    5.06454851923e001,
                    5.10218564529e001,
                    5.13374097598e001,
                    5.16004693977e001,
                    5.18223244382e001,
                    5.20148449242e001,
                    5.21889350372e001,
                    5.23536351113e001,
                    5.25157124459e001,
                    5.26796063730e001,
                    5.28476160610e001,
                    5.30202402028e001,
                    5.31965961563e001,
                    5.33748623839e001,
                    5.35527022996e001,
                    5.37276399831e001,
                    5.38973687732e001,
                    5.40599826225e001,
                    5.42141273988e001,
                    5.43590751578e001,
                    5.44947289126e001,
                    5.46215686913e001,
                    5.47405518236e001,
                    5.48529815402e001,
                    5.49603582190e001,
                    5.50642270863e001,
                    5.51660349836e001,
                    5.52670070646e001,
                    5.53680520985e001,
                    5.54697025392e001,
                    5.55720927915e001,
                    5.56749762728e001,
                    5.57777790517e001,
                    5.58796851466e001,
                    5.59797461155e001,
                    5.60770054561e001,
                    5.61706266985e001,
                    5.62600130036e001,
                    5.63449057053e001,
                    5.64254496625e001,
                    5.65022146282e001,
                    5.65761642150e001,
                    5.66485675508e001,
                    5.67208534842e001,
                    5.67944133373e001,
                    5.68703658198e001,
                    5.69493069272e001,
                    5.70310785669e001,
                    5.71146023893e001,
                    5.71978399741e001,
                    5.72779572372e001,
                    5.73517897984e001,
                    5.74167271960e001,
                    5.74721573687e001,
                    5.75216388520e001,
                    5.75759967785e001,
                    5.76575701358e001,
                    5.78058719368e001,
                    5.80849611077e001,
                    5.85928651155e001,
                    5.94734357453e001,
                    6.09310671165e001,
                    6.32487551103e001,
                    6.68100309742e001,
                ]
            ),
            "cm**3",
        )
        np.testing.assert_allclose(d.volume_history.volume, volumes)

    def test_time_and_volume_histories_error(self):
        """Test that time-histories and volume-history together raise an error"""
        properties = self.load_properties("testfile_rcm.yaml")
        properties[0]["volume-history"] = {}
        with pytest.raises(TypeError) as record:
            DataPoint(properties[0])

        assert "time-histories and volume-history are mutually exclusive" in str(record.value)

    time_history_types = [
        "volume",
        "temperature",
        "pressure",
        "piston_position",
        "light_emission",
        "OH_emission",
        "absorption",
    ]

    @pytest.mark.parametrize("history_type", time_history_types)
    def test_time_histories_array(self, history_type):
        """Check that all of the history types are set properly"""
        properties = self.load_properties("testfile_rcm.yaml")
        properties[0]["time-histories"][0]["type"] = history_type
        d = DataPoint(properties[0])

        np.testing.assert_allclose(
            getattr(d, f"{history_type}_history").time,
            Q_(np.arange(0, 9.7e-2, 1.0e-3), "s"),
        )

        quants = Q_(
            np.array(
                [
                    5.47669375000e002,
                    5.46608789894e002,
                    5.43427034574e002,
                    5.38124109043e002,
                    5.30700013298e002,
                    5.21154747340e002,
                    5.09488311170e002,
                    4.95700704787e002,
                    4.79791928191e002,
                    4.61761981383e002,
                    4.41610864362e002,
                    4.20399162234e002,
                    3.99187460106e002,
                    3.77975757979e002,
                    3.56764055851e002,
                    3.35552353723e002,
                    3.14340651596e002,
                    2.93128949468e002,
                    2.71917247340e002,
                    2.50705545213e002,
                    2.29493843085e002,
                    2.08282140957e002,
                    1.87070438830e002,
                    1.65858736702e002,
                    1.44647034574e002,
                    1.23435332447e002,
                    1.02223630319e002,
                    8.10119281915e001,
                    6.33355097518e001,
                    5.27296586879e001,
                    4.91943750000e001,
                    4.97137623933e001,
                    5.02063762048e001,
                    5.06454851923e001,
                    5.10218564529e001,
                    5.13374097598e001,
                    5.16004693977e001,
                    5.18223244382e001,
                    5.20148449242e001,
                    5.21889350372e001,
                    5.23536351113e001,
                    5.25157124459e001,
                    5.26796063730e001,
                    5.28476160610e001,
                    5.30202402028e001,
                    5.31965961563e001,
                    5.33748623839e001,
                    5.35527022996e001,
                    5.37276399831e001,
                    5.38973687732e001,
                    5.40599826225e001,
                    5.42141273988e001,
                    5.43590751578e001,
                    5.44947289126e001,
                    5.46215686913e001,
                    5.47405518236e001,
                    5.48529815402e001,
                    5.49603582190e001,
                    5.50642270863e001,
                    5.51660349836e001,
                    5.52670070646e001,
                    5.53680520985e001,
                    5.54697025392e001,
                    5.55720927915e001,
                    5.56749762728e001,
                    5.57777790517e001,
                    5.58796851466e001,
                    5.59797461155e001,
                    5.60770054561e001,
                    5.61706266985e001,
                    5.62600130036e001,
                    5.63449057053e001,
                    5.64254496625e001,
                    5.65022146282e001,
                    5.65761642150e001,
                    5.66485675508e001,
                    5.67208534842e001,
                    5.67944133373e001,
                    5.68703658198e001,
                    5.69493069272e001,
                    5.70310785669e001,
                    5.71146023893e001,
                    5.71978399741e001,
                    5.72779572372e001,
                    5.73517897984e001,
                    5.74167271960e001,
                    5.74721573687e001,
                    5.75216388520e001,
                    5.75759967785e001,
                    5.76575701358e001,
                    5.78058719368e001,
                    5.80849611077e001,
                    5.85928651155e001,
                    5.94734357453e001,
                    6.09310671165e001,
                    6.32487551103e001,
                    6.68100309742e001,
                ]
            ),
            "cm**3",
        )
        np.testing.assert_allclose(getattr(d, f"{history_type}_history").quantity, quants)
        assert all(
            getattr(d, f"{h}_history") is None for h in self.time_history_types if h != history_type
        )

    @pytest.mark.parametrize("history_type", time_history_types)
    def test_time_histories_file(self, history_type):
        """Check that all of the history types are set properly"""
        properties = self.load_properties("testfile_rcm.yaml")
        properties[0]["time-histories"][0]["type"] = history_type
        filename = os.path.join("tests", "rcm_history.csv")
        properties[0]["time-histories"][0]["values"] = {"filename": filename}
        d = DataPoint(properties[0])

        np.testing.assert_allclose(
            getattr(d, f"{history_type}_history").time,
            Q_(np.arange(0, 9.7e-2, 1.0e-3), "s"),
        )

        quants = Q_(
            np.array(
                [
                    5.47669375000e002,
                    5.46608789894e002,
                    5.43427034574e002,
                    5.38124109043e002,
                    5.30700013298e002,
                    5.21154747340e002,
                    5.09488311170e002,
                    4.95700704787e002,
                    4.79791928191e002,
                    4.61761981383e002,
                    4.41610864362e002,
                    4.20399162234e002,
                    3.99187460106e002,
                    3.77975757979e002,
                    3.56764055851e002,
                    3.35552353723e002,
                    3.14340651596e002,
                    2.93128949468e002,
                    2.71917247340e002,
                    2.50705545213e002,
                    2.29493843085e002,
                    2.08282140957e002,
                    1.87070438830e002,
                    1.65858736702e002,
                    1.44647034574e002,
                    1.23435332447e002,
                    1.02223630319e002,
                    8.10119281915e001,
                    6.33355097518e001,
                    5.27296586879e001,
                    4.91943750000e001,
                    4.97137623933e001,
                    5.02063762048e001,
                    5.06454851923e001,
                    5.10218564529e001,
                    5.13374097598e001,
                    5.16004693977e001,
                    5.18223244382e001,
                    5.20148449242e001,
                    5.21889350372e001,
                    5.23536351113e001,
                    5.25157124459e001,
                    5.26796063730e001,
                    5.28476160610e001,
                    5.30202402028e001,
                    5.31965961563e001,
                    5.33748623839e001,
                    5.35527022996e001,
                    5.37276399831e001,
                    5.38973687732e001,
                    5.40599826225e001,
                    5.42141273988e001,
                    5.43590751578e001,
                    5.44947289126e001,
                    5.46215686913e001,
                    5.47405518236e001,
                    5.48529815402e001,
                    5.49603582190e001,
                    5.50642270863e001,
                    5.51660349836e001,
                    5.52670070646e001,
                    5.53680520985e001,
                    5.54697025392e001,
                    5.55720927915e001,
                    5.56749762728e001,
                    5.57777790517e001,
                    5.58796851466e001,
                    5.59797461155e001,
                    5.60770054561e001,
                    5.61706266985e001,
                    5.62600130036e001,
                    5.63449057053e001,
                    5.64254496625e001,
                    5.65022146282e001,
                    5.65761642150e001,
                    5.66485675508e001,
                    5.67208534842e001,
                    5.67944133373e001,
                    5.68703658198e001,
                    5.69493069272e001,
                    5.70310785669e001,
                    5.71146023893e001,
                    5.71978399741e001,
                    5.72779572372e001,
                    5.73517897984e001,
                    5.74167271960e001,
                    5.74721573687e001,
                    5.75216388520e001,
                    5.75759967785e001,
                    5.76575701358e001,
                    5.78058719368e001,
                    5.80849611077e001,
                    5.85928651155e001,
                    5.94734357453e001,
                    6.09310671165e001,
                    6.32487551103e001,
                    6.68100309742e001,
                ]
            ),
            "cm**3",
        )
        np.testing.assert_allclose(getattr(d, f"{history_type}_history").quantity, quants)
        assert all(
            getattr(d, f"{h}_history") is None for h in self.time_history_types if h != history_type
        )

    @pytest.mark.parametrize("history_type", itertools.pairwise(time_history_types))
    def test_multiple_time_histories(self, history_type):
        """Check that multiple of the history types are set properly.

        Note the units aren't correct for the history types, but that doesn't get checked here, it
        gets checked in the validation of the YAML file by Cerberus.
        """
        properties = self.load_properties("testfile_rcm.yaml")
        properties[0]["time-histories"][0]["type"] = history_type[0]
        properties[0]["time-histories"].append(deepcopy(properties[0]["time-histories"][0]))
        properties[0]["time-histories"][1]["type"] = history_type[1]
        d = DataPoint(properties[0])

        np.testing.assert_allclose(
            getattr(d, f"{history_type[0]}_history").time,
            Q_(np.arange(0, 9.7e-2, 1.0e-3), "s"),
        )

        np.testing.assert_allclose(
            getattr(d, f"{history_type[1]}_history").time,
            Q_(np.arange(0, 9.7e-2, 1.0e-3), "s"),
        )

        quants = Q_(
            np.array(
                [
                    5.47669375000e002,
                    5.46608789894e002,
                    5.43427034574e002,
                    5.38124109043e002,
                    5.30700013298e002,
                    5.21154747340e002,
                    5.09488311170e002,
                    4.95700704787e002,
                    4.79791928191e002,
                    4.61761981383e002,
                    4.41610864362e002,
                    4.20399162234e002,
                    3.99187460106e002,
                    3.77975757979e002,
                    3.56764055851e002,
                    3.35552353723e002,
                    3.14340651596e002,
                    2.93128949468e002,
                    2.71917247340e002,
                    2.50705545213e002,
                    2.29493843085e002,
                    2.08282140957e002,
                    1.87070438830e002,
                    1.65858736702e002,
                    1.44647034574e002,
                    1.23435332447e002,
                    1.02223630319e002,
                    8.10119281915e001,
                    6.33355097518e001,
                    5.27296586879e001,
                    4.91943750000e001,
                    4.97137623933e001,
                    5.02063762048e001,
                    5.06454851923e001,
                    5.10218564529e001,
                    5.13374097598e001,
                    5.16004693977e001,
                    5.18223244382e001,
                    5.20148449242e001,
                    5.21889350372e001,
                    5.23536351113e001,
                    5.25157124459e001,
                    5.26796063730e001,
                    5.28476160610e001,
                    5.30202402028e001,
                    5.31965961563e001,
                    5.33748623839e001,
                    5.35527022996e001,
                    5.37276399831e001,
                    5.38973687732e001,
                    5.40599826225e001,
                    5.42141273988e001,
                    5.43590751578e001,
                    5.44947289126e001,
                    5.46215686913e001,
                    5.47405518236e001,
                    5.48529815402e001,
                    5.49603582190e001,
                    5.50642270863e001,
                    5.51660349836e001,
                    5.52670070646e001,
                    5.53680520985e001,
                    5.54697025392e001,
                    5.55720927915e001,
                    5.56749762728e001,
                    5.57777790517e001,
                    5.58796851466e001,
                    5.59797461155e001,
                    5.60770054561e001,
                    5.61706266985e001,
                    5.62600130036e001,
                    5.63449057053e001,
                    5.64254496625e001,
                    5.65022146282e001,
                    5.65761642150e001,
                    5.66485675508e001,
                    5.67208534842e001,
                    5.67944133373e001,
                    5.68703658198e001,
                    5.69493069272e001,
                    5.70310785669e001,
                    5.71146023893e001,
                    5.71978399741e001,
                    5.72779572372e001,
                    5.73517897984e001,
                    5.74167271960e001,
                    5.74721573687e001,
                    5.75216388520e001,
                    5.75759967785e001,
                    5.76575701358e001,
                    5.78058719368e001,
                    5.80849611077e001,
                    5.85928651155e001,
                    5.94734357453e001,
                    6.09310671165e001,
                    6.32487551103e001,
                    6.68100309742e001,
                ]
            ),
            "cm**3",
        )
        np.testing.assert_allclose(getattr(d, f"{history_type[0]}_history").quantity, quants)
        np.testing.assert_allclose(getattr(d, f"{history_type[1]}_history").quantity, quants)
        assert all(
            getattr(d, f"{h}_history") is None
            for h in self.time_history_types
            if h not in history_type
        )

    @pytest.mark.parametrize("history_type", zip(time_history_types, time_history_types))
    def test_duplicate_time_histories(self, history_type):
        """Check that duplicates of the history types raise an error"""
        properties = self.load_properties("testfile_rcm.yaml")
        properties[0]["time-histories"][0]["type"] = history_type[0]
        properties[0]["time-histories"].append(deepcopy(properties[0]["time-histories"][0]))
        properties[0]["time-histories"][1]["type"] = history_type[1]
        with pytest.raises(ValueError) as record:
            DataPoint(properties[0])
        assert (
            f"Each history type may only be specified once. {history_type[0]} was "
            "specified multiple times"
        ) in str(record.value)

    def test_supported_ignition_types(self):
        # pressure d/dt max
        properties = self.load_properties("testfile_st.yaml")
        datapoints = [DataPoint(d) for d in properties]
        for d in datapoints:
            assert d.ignition_type["target"] == "pressure"
            assert d.ignition_type["type"] == "d/dt max"

        # OH, max
        properties = self.load_properties("testfile_st2.yaml")
        datapoints = [DataPoint(d) for d in properties]
        for d in datapoints:
            assert d.ignition_type["target"] == "OH"
            assert d.ignition_type["type"] == "max"

        # OH*, 1/2 max
        properties = self.load_properties("testfile_st_p5.yaml")
        datapoints = [DataPoint(d) for d in properties]
        for d in datapoints:
            assert d.ignition_type["target"] == "OH*"
            assert d.ignition_type["type"] == "1/2 max"

        # CH, min
        properties = self.load_properties("testfile_required.yaml")
        datapoints = [DataPoint(d) for d in properties]
        assert datapoints[0].ignition_type["target"] == "CH"
        assert datapoints[0].ignition_type["type"] == "min"

        # CH*, d/dt max extrapolated
        assert datapoints[1].ignition_type["target"] == "CH*"
        assert datapoints[1].ignition_type["type"] == "d/dt max extrapolated"

    def test_changing_ignition_type(self):
        properties = self.load_properties("testfile_st.yaml")
        datapoints = [DataPoint(d) for d in properties]
        datapoints[0].ignition_type["target"] = "temperature"
        assert datapoints[0].ignition_type["target"] == "temperature"
        for d in datapoints[1:]:
            assert d.ignition_type["target"] == "pressure"
