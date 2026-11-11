"""
Tests for the converters
"""

import socket
import xml.etree.ElementTree as etree
from pathlib import Path
from shutil import copy
from tempfile import TemporaryDirectory

import numpy.random
import pytest
from numpy.testing import assert_allclose

from pyked._version import __version__
from pyked.chemked import ChemKED

# Local imports
from pyked.converters import (
    KeywordError,
    MissingAttributeError,
    MissingElementError,
    ParseError,
    ReSpecTh_to_ChemKED,
    apparatus_kinds,
    apparatus_kinds_by_experiment,
    attach_value_metadata,
    ck2respth,
    composition_unit_typos,
    composition_units,
    experiment_types,
    flame_modes,
    get_common_properties,
    get_composition_amount,
    get_datapoints,
    get_experiment_kind,
    get_file_metadata,
    get_ignition_type,
    get_lbv_datapoints,
    get_reference,
    get_speciation_datapoints,
    get_value_metadata,
    ignition_target_values,
    ignition_type_values,
    main,
    normalize_units,
    respth2ck,
)
from pyked.validation import schema
from pyked.validation import units as unit_registry


class TestErrors:
    """ """

    def test_parse_error(self):
        """(Very) basic test of ParseError."""
        with pytest.raises(ParseError) as excinfo:
            raise ParseError("this is an error")
        assert "this is an error" in str(excinfo.value)

    def test_keyword_error(self):
        """Basic test of KeywordError."""
        with pytest.raises(KeywordError) as excinfo:
            raise KeywordError("this is a test")
        assert "Error: this is a test." in str(excinfo.value)

    def test_missing_element_error(self):
        """Basic test of MissingElementError."""
        with pytest.raises(MissingElementError) as excinfo:
            raise MissingElementError("fileAuthor")
        assert "Error: required element fileAuthor is missing." in str(excinfo.value)

    def test_missing_attribute_error(self):
        """Basic test of MissingAttributeError."""
        with pytest.raises(MissingAttributeError) as excinfo:
            raise MissingAttributeError("preferredKey", "bibliographyLink")
        assert "Error: required attribute preferredKey of bibliographyLink is missing." in str(
            excinfo.value
        )


class TestFileMetadata:
    """ """

    def test_valid_metadata(self):
        """Ensure valid metadata validates properly."""
        root = etree.Element("experiment")
        author = etree.SubElement(root, "fileAuthor")
        author.text = "Kyle Niemeyer"
        version = etree.SubElement(root, "fileVersion")
        major_version = etree.SubElement(version, "major")
        major_version.text = "1"
        minor_version = etree.SubElement(version, "minor")
        minor_version.text = "0"

        meta = get_file_metadata(root)
        assert meta["chemked-version"] == __version__
        assert meta["file-authors"][0]["name"] == "Kyle Niemeyer"
        # ChemKED version will always start at 0
        assert meta["file-version"] == 0

    def test_missing_fileauthor(self):
        """Ensure missing file author raises error."""
        root = etree.Element("experiment")
        version = etree.SubElement(root, "fileVersion")
        major_version = etree.SubElement(version, "major")
        major_version.text = "1"
        minor_version = etree.SubElement(version, "minor")
        minor_version.text = "0"

        with pytest.raises(MissingElementError) as excinfo:
            get_file_metadata(root)
        assert "Error: required element fileAuthor is missing." in str(excinfo.value)

    def test_blank_fileauthor(self):
        """Ensure blank file author raises error."""
        root = etree.Element("experiment")
        author = etree.SubElement(root, "fileAuthor")
        author.text = ""
        version = etree.SubElement(root, "fileVersion")
        major_version = etree.SubElement(version, "major")
        major_version.text = "1"
        minor_version = etree.SubElement(version, "minor")
        minor_version.text = "0"

        with pytest.raises(MissingElementError) as excinfo:
            get_file_metadata(root)
        assert "Error: required element fileAuthor is missing" in str(excinfo.value)


class TestGetReference:
    """ """

    @pytest.fixture(scope="function")
    def disable_socket(self):
        """Disables socket to prevent network access."""
        old_socket = socket.socket

        def guard(*args, **kwargs):
            raise ConnectionError("No internet")

        socket.socket = guard
        yield
        socket.socket = old_socket

    def test_valid_reference(self, mock_crossref_api):
        """Ensure valid reference reads properly."""
        root = etree.Element("experiment")
        ref = etree.SubElement(root, "bibliographyLink")

        ref.set("doi", "10.1016/j.ijhydene.2007.04.008")
        ref.set(
            "preferredKey",
            "Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., "
            "International Journal of Hydrogen Energy, 2007, (32) 2216-2226, "
            "Fig. 12., right, open diamond",
        )

        with pytest.warns(UserWarning) as record:
            ref = get_reference(root)

        m = str(record.pop(UserWarning).message)
        assert m == "Using DOI to obtain reference information, rather than preferredKey."

        assert ref["doi"] == "10.1016/j.ijhydene.2007.04.008"
        assert ref["journal"] == "International Journal of Hydrogen Energy"
        assert ref["year"] == 2007
        assert ref["volume"] == 32
        assert ref["pages"] == "2216-2226"
        assert len(ref["authors"]) == 4
        assert {"name": "N. Chaumeix"} in ref["authors"]
        assert {"name": "S. Pichon"} in ref["authors"]
        assert {"name": "F. Lafosse"} in ref["authors"]
        assert {"name": "C.-E. Paillard"} in ref["authors"]

    def test_missing_bibliography(self):
        """Test for completely missing bibliography element."""
        root = etree.Element("experiment")
        with pytest.raises(MissingElementError) as excinfo:
            get_reference(root)
        assert "Error: required element bibliographyLink is missing" in str(excinfo.value)

    def test_missing_doi(self):
        """Ensure can handle missing DOI."""
        root = etree.Element("experiment")
        ref = etree.SubElement(root, "bibliographyLink")

        ref.set(
            "preferredKey",
            "Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., "
            "International Journal of Hydrogen Energy, 2007, (32) 2216-2226, "
            "Fig. 12., right, open diamond",
        )

        with pytest.warns(UserWarning) as record:
            ref = get_reference(root)

        m = str(record.pop(UserWarning).message)
        assert m == (
            'Missing doi attribute in bibliographyLink. Setting "detail" key as a '
            "fallback; please update to the appropriate fields."
        )

        assert ref["detail"] == (
            "Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., "
            "International Journal of Hydrogen Energy, 2007, (32) 2216-2226, "
            "Fig. 12., right, open diamond."
        )

    def test_missing_doi_period_at_end(self):
        """Ensure can handle missing DOI with period at end of reference."""
        root = etree.Element("experiment")
        ref = etree.SubElement(root, "bibliographyLink")

        ref.set(
            "preferredKey",
            "Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., "
            "International Journal of Hydrogen Energy, 2007, (32) 2216-2226, "
            "Fig. 12., right, open diamond.",
        )

        with pytest.warns(UserWarning) as record:
            ref = get_reference(root)
        m = str(record.pop(UserWarning).message)
        assert m == (
            'Missing doi attribute in bibliographyLink. Setting "detail" key as a '
            "fallback; please update to the appropriate fields."
        )

        assert ref["detail"] == (
            "Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., "
            "International Journal of Hydrogen Energy, 2007, (32) 2216-2226, "
            "Fig. 12., right, open diamond."
        )

    def test_missing_preferredkey(self, mock_crossref_api):
        """Ensure can handle DOI with missing ``preferredKey``."""
        root = etree.Element("experiment")
        ref = etree.SubElement(root, "bibliographyLink")

        ref.set("doi", "10.1016/j.ijhydene.2007.04.008")

        ref = get_reference(root)

        assert ref["doi"] == "10.1016/j.ijhydene.2007.04.008"
        assert ref["journal"] == "International Journal of Hydrogen Energy"
        assert ref["year"] == 2007
        assert ref["volume"] == 32
        assert ref["pages"] == "2216-2226"
        assert len(ref["authors"]) == 4
        assert {"name": "N. Chaumeix"} in ref["authors"]
        assert {"name": "S. Pichon"} in ref["authors"]
        assert {"name": "F. Lafosse"} in ref["authors"]
        assert {"name": "C.-E. Paillard"} in ref["authors"]

    def test_incorrect_doi(self, capfd, mock_crossref_api):
        """Ensure can handle invalid DOI."""
        root = etree.Element("experiment")
        ref = etree.SubElement(root, "bibliographyLink")
        ref.set("doi", "10.1000/invalid.doi")
        ref.set(
            "preferredKey",
            "Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., "
            "International Journal of Hydrogen Energy, 2007, (32) 2216-2226, "
            "Fig. 12., right, open diamond",
        )

        with pytest.warns(UserWarning) as record:
            ref = get_reference(root)

        m = str(record.pop(UserWarning).message)
        assert m == (
            'Missing doi attribute in bibliographyLink or lookup failed. Setting "detail" '
            "key as a fallback; please update to the appropriate fields."
        )

        assert ref["detail"] == (
            "Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., "
            "International Journal of Hydrogen Energy, 2007, (32) 2216-2226, "
            "Fig. 12., right, open diamond."
        )

    def test_incorrect_doi_period_at_end(self, capfd, mock_crossref_api):
        """Ensure can handle invalid DOI with period at end of reference."""
        root = etree.Element("experiment")
        ref = etree.SubElement(root, "bibliographyLink")
        ref.set("doi", "10.1000/invalid.doi")
        ref.set(
            "preferredKey",
            "Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., "
            "International Journal of Hydrogen Energy, 2007, (32) 2216-2226, "
            "Fig. 12., right, open diamond.",
        )

        with pytest.warns(UserWarning) as record:
            ref = get_reference(root)

        m = str(record.pop(UserWarning).message)
        assert m == (
            'Missing doi attribute in bibliographyLink or lookup failed. Setting "detail" '
            "key as a fallback; please update to the appropriate fields."
        )

        assert ref["detail"] == (
            "Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., "
            "International Journal of Hydrogen Energy, 2007, (32) 2216-2226, "
            "Fig. 12., right, open diamond."
        )

    def test_doi_missing_internet(self, disable_socket):
        """Ensure that DOI validation fails gracefully with no Internet."""
        root = etree.Element("experiment")
        ref = etree.SubElement(root, "bibliographyLink")
        ref.set("doi", "10.1016/j.ijhydene.2007.04.008")
        ref.set(
            "preferredKey",
            "Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., "
            "International Journal of Hydrogen Energy, 2007, (32) 2216-2226, "
            "Fig. 12., right, open diamond",
        )

        with pytest.warns(UserWarning) as record:
            ref = get_reference(root)
        m = str(record.pop(UserWarning).message)
        assert m == (
            'Missing doi attribute in bibliographyLink or lookup failed. Setting "detail" '
            "key as a fallback; please update to the appropriate fields."
        )

        assert ref["detail"] == (
            "Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., "
            "International Journal of Hydrogen Energy, 2007, (32) 2216-2226, "
            "Fig. 12., right, open diamond."
        )

    def test_missing_doi_preferredkey(self, mock_crossref_api):
        """Ensure error if missing both DOI and ``preferredKey``."""
        root = etree.Element("experiment")
        ref = etree.SubElement(root, "bibliographyLink")
        ref.set("doi", "10.1000/invalid.doi")

        with pytest.raises(KeywordError) as excinfo:
            ref = get_reference(root)
        assert "DOI not found and preferredKey attribute not set" in str(excinfo.value)

    def test_doi_missing_preferredkey(self):
        """Ensure error if missing ``preferredKey`` and not found DOI."""
        root = etree.Element("experiment")
        etree.SubElement(root, "bibliographyLink")

        with pytest.raises(MissingAttributeError) as excinfo:
            get_reference(root)
        assert "Error: required attribute preferredKey of bibliographyLink is missing." in str(
            excinfo.value
        )

    def test_doi_author_orcid(self, mock_crossref_api):
        """Test proper addition of author ORCID if present."""
        root = etree.Element("experiment")
        ref = etree.SubElement(root, "bibliographyLink")
        ref.set("doi", "10.1016/j.cpc.2017.02.004")

        ref = get_reference(root)

        assert ref["doi"] == "10.1016/j.cpc.2017.02.004"
        assert ref["journal"] == "Computer Physics Communications"
        assert ref["year"] == 2017
        assert ref["volume"] == 215
        assert ref["pages"] == "188-203"
        assert len(ref["authors"]) == 3
        assert {"name": "Kyle E. Niemeyer", "ORCID": "0000-0003-4425-7097"} in ref["authors"]
        assert {"name": "Nicholas J. Curtis", "ORCID": "0000-0002-0303-4711"} in ref["authors"]
        assert {"name": "Chih-Jen Sung"} in ref["authors"]


class TestGetExperiment:
    """ """

    @pytest.mark.parametrize(
        "apparatus",
        [
            "shock tube",
            "rapid compression machine",
        ],
    )
    def test_proper_experiment_types(self, apparatus):
        """Ensure proper validation of accepted experiment types."""
        root = etree.Element("experiment")
        exp = etree.SubElement(root, "experimentType")
        exp.text = "Ignition delay measurement"
        app = etree.SubElement(root, "apparatus")
        kind = etree.SubElement(app, "kind")
        kind.text = apparatus

        ref = get_experiment_kind(root)
        assert ref["experiment-type"] == "ignition delay"
        assert ref["apparatus"]["kind"] == apparatus

    @pytest.mark.parametrize(
        "respecth_type, chemked_type",
        [
            # ReSpecTh 1.x capitalizes the type, 2.x does not
            ("Ignition delay measurement", "ignition delay"),
            ("ignition delay measurement", "ignition delay"),
            ("laminar burning velocity measurement", "laminar burning velocity measurement"),
            ("Laminar flame speed measurement", "laminar burning velocity measurement"),
            # ReSpecTh keeps four speciation types that ChemKED represents as one
            ("concentration time profile measurement", "speciation measurement"),
            ("outlet concentration measurement", "speciation measurement"),
            ("jet stirred reactor measurement", "speciation measurement"),
            ("burner stabilized flame speciation measurement", "speciation measurement"),
        ],
    )
    def test_experiment_type_mapping(self, respecth_type, chemked_type):
        """Every ReSpecTh experiment type maps onto a ChemKED experiment-type."""
        root = etree.Element("experiment")
        exp = etree.SubElement(root, "experimentType")
        exp.text = respecth_type
        app = etree.SubElement(root, "apparatus")
        kind = etree.SubElement(app, "kind")
        kind.text = "shock tube"

        assert get_experiment_kind(root)["experiment-type"] == chemked_type

    def test_experiment_types_match_schema(self):
        """Everything the converter emits must be an allowed experiment-type."""
        assert set(experiment_types.values()) <= set(schema["experiment-type"]["allowed"])

    @pytest.mark.parametrize(
        "experiment_type",
        ["Direct rate coefficient measurement", "Unknown measurement"],
    )
    def test_invalid_experiment_types(self, experiment_type):
        """Ensure types outside the ChemKED schema raise correct errors."""
        root = etree.Element("experiment")
        exp = etree.SubElement(root, "experimentType")
        exp.text = experiment_type

        with pytest.raises(NotImplementedError) as excinfo:
            get_experiment_kind(root)
        assert experiment_type + " not (yet) supported" in str(excinfo.value)

    @pytest.mark.parametrize(
        "respecth_kind, chemked_kind",
        [
            ("shock tube", "shock tube"),
            ("rapid compression machine", "rapid compression machine"),
            # ReSpecTh appends the vessel material, which ChemKED has no field for
            ("flow reactor", "flow reactor"),
            ("flow reactor (quartz)", "flow reactor"),
            ("jet stirred reactor", "jet stirred reactor"),
            ("heat flux burner", "heat flux burner"),
            ("flame cone method", "bunsen burner"),
            ("outwardly propagating spherical flame", "outwardly propagating spherical flame"),
        ],
    )
    def test_apparatus_kind_mapping(self, respecth_kind, chemked_kind):
        """ReSpecTh apparatus kinds map onto the ChemKED vocabulary."""
        root = etree.Element("experiment")
        exp = etree.SubElement(root, "experimentType")
        exp.text = "ignition delay measurement"
        app = etree.SubElement(root, "apparatus")
        kind = etree.SubElement(app, "kind")
        kind.text = respecth_kind

        assert get_experiment_kind(root)["apparatus"]["kind"] == chemked_kind

    @pytest.mark.parametrize(
        "respecth_kind",
        ["stirred reactor", "stirred reactor (quartz)", "stirred reactor (fused silica)"],
    )
    def test_stirred_reactor_needs_the_experiment_type(self, respecth_kind):
        """"Stirred reactor" says the mixture is stirred, not which reactor it is.

        Only the experiment type says the reactor is jet stirred, so the kind is mapped when it
        agrees and refused when there is nothing to corroborate it.
        """
        root = etree.Element("experiment")
        exp = etree.SubElement(root, "experimentType")
        exp.text = "jet stirred reactor measurement"
        app = etree.SubElement(root, "apparatus")
        kind = etree.SubElement(app, "kind")
        kind.text = respecth_kind

        assert get_experiment_kind(root)["apparatus"]["kind"] == "jet stirred reactor"

        exp.text = "outlet concentration measurement"
        with pytest.raises(NotImplementedError) as excinfo:
            get_experiment_kind(root)
        assert "does not identify a ChemKED apparatus kind" in str(excinfo.value)

    @pytest.mark.parametrize(
        "modes, chemked_kind",
        [
            (["premixed", "laminar", "OPF"], "outwardly propagating spherical flame"),
            (["premixed", "laminar", "HFM"], "heat flux burner"),
            (["premixed", "laminar", "CTF"], "counterflow twin flame"),
            (["premixed", "laminar", "FCM"], "bunsen burner"),
            (["burner-stabilized"], "burner stabilized flame"),
            (["constant volume combustion chamber", "premixed"], "outwardly propagating spherical flame"),
        ],
    )
    def test_generic_flame_apparatus_uses_mode(self, modes, chemked_kind):
        """A generic flame apparatus is identified from its modes."""
        root = etree.Element("experiment")
        exp = etree.SubElement(root, "experimentType")
        exp.text = "laminar burning velocity measurement"
        app = etree.SubElement(root, "apparatus")
        kind = etree.SubElement(app, "kind")
        kind.text = "flame"
        for mode in modes:
            etree.SubElement(app, "mode").text = mode

        assert get_experiment_kind(root)["apparatus"]["kind"] == chemked_kind

    @pytest.mark.parametrize(
        "modes",
        [
            # These describe the mixture or the flow, not the burner
            ["premixed", "laminar"],
            ["premixed"],
            # ReSpecTh marks a mode it is unsure of with a question mark
            ["premixed", "laminar", "FCM?"],
        ],
    )
    def test_undecidable_flame_apparatus(self, modes):
        """A generic flame apparatus with no identifying mode has to be curated by hand."""
        root = etree.Element("experiment")
        exp = etree.SubElement(root, "experimentType")
        exp.text = "laminar burning velocity measurement"
        app = etree.SubElement(root, "apparatus")
        kind = etree.SubElement(app, "kind")
        kind.text = "flame"
        for mode in modes:
            etree.SubElement(app, "mode").text = mode

        with pytest.raises(NotImplementedError) as excinfo:
            get_experiment_kind(root)
        assert "does not identify a ChemKED apparatus kind" in str(excinfo.value)

        # The caller can supply the kind that only the article states
        assert (
            get_experiment_kind(root, apparatus_kind="heat flux burner")["apparatus"]["kind"]
            == "heat flux burner"
        )

    def test_apparatus_kinds_match_schema(self):
        """Everything the converter emits must be an allowed apparatus kind."""
        allowed = set(schema["apparatus"]["schema"]["kind"]["allowed"])
        assert set(apparatus_kinds.values()) <= allowed
        assert set(flame_modes.values()) <= allowed
        assert set(apparatus_kinds_by_experiment.values()) <= allowed

    @pytest.mark.parametrize(
        "apparatus",
        ["internal combustion engine", "single cylinder engine"],
    )
    def test_invalid_apparatus_types(self, apparatus):
        """Ensure apparatus kinds outside the ChemKED schema raise correct errors."""
        root = etree.Element("experiment")
        exp = etree.SubElement(root, "experimentType")
        exp.text = "Ignition delay measurement"
        app = etree.SubElement(root, "apparatus")
        kind = etree.SubElement(app, "kind")
        kind.text = apparatus

        with pytest.raises(NotImplementedError) as excinfo:
            get_experiment_kind(root)
        assert "does not identify a ChemKED apparatus kind" in str(excinfo.value)

    def test_missing_apparatus_kind(self):
        """Ensure proper error raised if missing apparatus kind."""
        root = etree.Element("experiment")
        exp = etree.SubElement(root, "experimentType")
        exp.text = "Ignition delay measurement"
        etree.SubElement(root, "apparatus")

        with pytest.raises(MissingElementError) as excinfo:
            get_experiment_kind(root)
        assert "Error: required element apparatus/kind is missing." in str(excinfo.value)

    def test_missing_apparatus(self):
        """Ensure proper error raised if missing apparatus."""
        root = etree.Element("experiment")
        exp = etree.SubElement(root, "experimentType")
        exp.text = "Ignition delay measurement"

        with pytest.raises(MissingElementError) as excinfo:
            get_experiment_kind(root)
        assert "Error: required element apparatus/kind is missing." in str(excinfo.value)


class TestCommonProperties:
    """ """

    @pytest.mark.parametrize(
        "physical_property, value, units",
        [
            ("pressure", "2.18", "atm"),
            ("pressure", "700", "Torr"),
            ("pressure", "700", "torr"),
            ("pressure", "1", "bar"),
            ("pressure", "1000", "mbar"),
            ("temperature", "1000.0", "K"),
            ("pressure rise", "0.10", "1/ms"),
        ],
    )
    def test_proper_common_properties(self, physical_property, value, units):
        """Ensure proper handling of correct common properties."""
        root = etree.Element("experiment")
        properties = etree.SubElement(root, "commonProperties")

        prop = etree.SubElement(properties, "property")
        prop.set("name", physical_property)
        prop.set("units", units)
        prop_value = etree.SubElement(prop, "value")
        prop_value.text = value

        # not sure how else to handle this...
        if units == "Torr":
            units = "torr"

        common = get_common_properties(root)
        assert common[physical_property.replace(" ", "-")] == [" ".join([value, units])]

    @pytest.mark.parametrize(
        "physical_property, value, units",
        [
            ("pressure", "2.18", "K"),
            ("temperature", "1000.0", "Pa"),
            ("pressure rise", "0.10", "ms"),
        ],
    )
    def test_common_property_invalid_units(self, physical_property, value, units):
        """Ensure error raised when improper units given for common properties."""
        root = etree.Element("experiment")
        properties = etree.SubElement(root, "commonProperties")
        prop = etree.SubElement(properties, "property")
        prop.set("name", physical_property)
        prop.set("units", units)
        prop_value = etree.SubElement(prop, "value")
        prop_value.text = value

        with pytest.raises(KeywordError) as excinfo:
            get_common_properties(root)
        assert "Error: units incompatible for property " + physical_property in str(excinfo.value)

    @pytest.mark.parametrize("composition_type", ["mole fraction", "mass fraction"])
    def test_proper_common_initial_composition(self, composition_type):
        """Ensure proper handling of initial composition common property."""
        root = etree.Element("experiment")
        properties = etree.SubElement(root, "commonProperties")
        initial_composition = etree.SubElement(properties, "property")
        initial_composition.set("name", "initial composition")

        species_refs = [
            {"name": "H2", "inchi": "1S/H2/h1H", "amount": 0.00444},
            {"name": "O2", "inchi": "1S/O2/c1-2", "amount": 0.00566},
            {"name": "Ar", "inchi": "1S/Ar", "amount": 0.9899},
        ]
        for spec in species_refs:
            component = etree.SubElement(initial_composition, "component")
            species = etree.SubElement(component, "speciesLink")
            species.set("preferredKey", spec["name"])
            species.set("InChI", spec["inchi"])
            amount = etree.SubElement(component, "amount")
            amount.set("units", composition_type)
            amount.text = str(spec["amount"])

        common = get_common_properties(root)
        assert common["composition"]["kind"] == composition_type
        assert len(common["composition"]["species"]) == 3
        for spec_ref, spec in zip(species_refs, common["composition"]["species"]):
            assert spec["species-name"] == spec_ref["name"]
            assert spec["InChI"] == spec_ref["inchi"]
            assert spec["amount"] == [spec_ref["amount"]]

    def test_common_property_invalid_property(self):
        """Ensure error raised when invalid property given in common properties."""
        root = etree.Element("experiment")
        properties = etree.SubElement(root, "commonProperties")
        prop = etree.SubElement(properties, "property")
        prop.set("name", "compression time")

        with pytest.raises(KeywordError) as excinfo:
            get_common_properties(root)
        assert "Error: Property compression time not supported as common property." in str(
            excinfo.value
        )

    def test_species_missing_inchi(self, capfd):
        """Check for warning when species missing InChI."""
        root = etree.Element("experiment")
        properties = etree.SubElement(root, "commonProperties")
        initial_composition = etree.SubElement(properties, "property")
        initial_composition.set("name", "initial composition")

        component = etree.SubElement(initial_composition, "component")
        species = etree.SubElement(component, "speciesLink")
        species.set("preferredKey", "H2")
        amount = etree.SubElement(component, "amount")
        amount.set("units", "mole fraction")
        amount.text = "1.0"

        with pytest.warns(UserWarning) as record:
            get_common_properties(root)
        m = str(record.pop(UserWarning).message)
        assert m == "Missing InChI for species H2"

    def test_inconsistent_composition_type(self):
        """Check for error when inconsistent composition types."""
        root = etree.Element("experiment")
        properties = etree.SubElement(root, "commonProperties")
        initial_composition = etree.SubElement(properties, "property")
        initial_composition.set("name", "initial composition")

        component = etree.SubElement(initial_composition, "component")
        species = etree.SubElement(component, "speciesLink")
        species.set("preferredKey", "H2")
        species.set("InChI", "1S/H2/h1H")
        amount = etree.SubElement(component, "amount")
        amount.set("units", "mole fraction")
        amount.text = "0.5"

        component = etree.SubElement(initial_composition, "component")
        species = etree.SubElement(component, "speciesLink")
        species.set("preferredKey", "O2")
        species.set("InChI", "1S/O2/c1-2")
        amount = etree.SubElement(component, "amount")
        amount.set("units", "mass fraction")
        amount.text = "0.5"

        with pytest.raises(KeywordError) as excinfo:
            get_common_properties(root)
        assert ("Error: composition units mass fraction not consistent with mole fraction") in str(
            excinfo.value
        )

    def test_common_composition_units_ppm_ppb(self):
        """Test proper handling of common composition unit conversion for ppm and ppb."""
        root = etree.Element("experiment")
        properties = etree.SubElement(root, "commonProperties")
        initial_composition = etree.SubElement(properties, "property")
        initial_composition.set("name", "initial composition")

        species_refs = [
            {"name": "H2", "inchi": "1S/H2/h1H", "amount": 100, "units": "ppb"},
            {
                "name": "O2",
                "inchi": "1S/O2/c1-2",
                "amount": 10,
                "units": "ppm",
            },
            {
                "name": "Ar",
                "inchi": "1S/Ar",
                "amount": 0.999985,
                "units": "mole fraction",
            },
        ]
        for spec in species_refs:
            component = etree.SubElement(initial_composition, "component")
            species = etree.SubElement(component, "speciesLink")
            species.set("preferredKey", spec["name"])
            species.set("InChI", spec["inchi"])
            amount = etree.SubElement(component, "amount")
            amount.set("units", spec["units"])
            amount.text = str(spec["amount"])

        with pytest.warns(UserWarning) as record:
            common = get_common_properties(root)

        m = str(record.pop(UserWarning).message)
        assert m == "Assuming molar ppb in composition and converting to mole fraction"
        m = str(record.pop(UserWarning).message)
        assert m == "Assuming molar ppm in composition and converting to mole fraction"

        assert common["composition"]["kind"] == "mole fraction"
        assert len(common["composition"]["species"]) == 3
        assert common["composition"]["species"][0]["species-name"] == "H2"
        assert common["composition"]["species"][0]["InChI"] == "1S/H2/h1H"
        assert_allclose(common["composition"]["species"][0]["amount"], [100.0e-9])
        assert common["composition"]["species"][1]["species-name"] == "O2"
        assert common["composition"]["species"][1]["InChI"] == "1S/O2/c1-2"
        assert_allclose(common["composition"]["species"][1]["amount"], [10.0e-6])
        assert common["composition"]["species"][2]["species-name"] == "Ar"
        assert common["composition"]["species"][2]["InChI"] == "1S/Ar"
        assert_allclose(common["composition"]["species"][2]["amount"], [0.999985])

    def test_common_composition_units_percent(self):
        """Test proper handling of common composition unit conversion for (mole) percent."""
        root = etree.Element("experiment")
        properties = etree.SubElement(root, "commonProperties")
        initial_composition = etree.SubElement(properties, "property")
        initial_composition.set("name", "initial composition")

        species_refs = [{"name": "Ar", "inchi": "1S/Ar", "amount": 1.0, "units": "percent"}]
        for spec in species_refs:
            component = etree.SubElement(initial_composition, "component")
            species = etree.SubElement(component, "speciesLink")
            species.set("preferredKey", spec["name"])
            species.set("InChI", spec["inchi"])
            amount = etree.SubElement(component, "amount")
            amount.set("units", spec["units"])
            amount.text = str(spec["amount"])

        with pytest.warns(UserWarning) as record:
            common = get_common_properties(root)
        m = str(record.pop(UserWarning).message)
        assert m == "Assuming percent in composition means mole percent"

        assert common["composition"]["kind"] == "mole percent"
        assert len(common["composition"]["species"]) == 1
        assert common["composition"]["species"][0]["species-name"] == "Ar"
        assert common["composition"]["species"][0]["InChI"] == "1S/Ar"
        assert_allclose(common["composition"]["species"][0]["amount"], [1.0])

    def test_common_composition_units_error(self):
        """Test error for inappropriate common composition units."""
        root = etree.Element("experiment")
        properties = etree.SubElement(root, "commonProperties")
        initial_composition = etree.SubElement(properties, "property")
        initial_composition.set("name", "initial composition")

        species_refs = [
            {"name": "H2", "inchi": "1S/H2/h1H", "amount": 100, "units": "grams"},
        ]

        for spec in species_refs:
            component = etree.SubElement(initial_composition, "component")
            species = etree.SubElement(component, "speciesLink")
            species.set("preferredKey", spec["name"])
            species.set("InChI", spec["inchi"])
            amount = etree.SubElement(component, "amount")
            amount.set("units", spec["units"])
            amount.text = str(spec["amount"])

        with pytest.raises(KeywordError) as excinfo:
            get_common_properties(root)

        # The message lists whatever the converter actually accepts
        assert "Composition units need to be one of: " in str(excinfo.value)
        for supported in ["mole fraction", "mole percent", "ppm", "mol/cm3"]:
            assert supported in str(excinfo.value)
        assert "mole faction" not in str(excinfo.value)


class TestIgnitionType:
    """ """

    @pytest.mark.parametrize(
        "ignition_target", ["P", "T", "OH", "OH*", "CH*", "CH", "OHEX", "CHEX", "CO2", "CH3OH"]
    )
    @pytest.mark.parametrize(
        "ignition_type",
        [
            "max",
            "d/dt max",
            "1/2 max",
            "min",
            "baseline max intercept from d/dt",
            "baseline min intercept from d/dt",
            "concentration",
            "relative concentration",
            "d/dt second max",
            "relative increase",
        ],
    )
    def test_valid_ignition_types(self, ignition_target, ignition_type):
        """Check for proper parsing of valid ignition types."""
        root = etree.Element("experiment")
        ignition = etree.SubElement(root, "ignitionType")
        ignition.set("target", ignition_target)
        ignition.set("type", ignition_type)

        ignition = get_ignition_type(root)

    @pytest.mark.parametrize(
        "respecth_name, chemked_name",
        [
            ("P", "pressure"),
            ("T", "temperature"),
            ("OHEX", "OH*"),
            ("CHEX", "CH*"),
            ("p;", "pressure"),
            ("CH4", "CH4"),
        ],
    )
    def test_ignition_target_names(self, respecth_name, chemked_name):
        """ReSpecTh abbreviations are mapped, and species names keep their case."""
        root = etree.Element("experiment")
        ignition = etree.SubElement(root, "ignitionType")
        ignition.set("target", respecth_name)
        ignition.set("type", "max")

        assert get_ignition_type(root)["target"] == chemked_name

    @pytest.mark.parametrize(
        "respecth_name, chemked_name",
        [
            ("baseline max intercept from d/dt", "d/dt max extrapolated"),
            ("baseline min intercept from d/dt", "d/dt min extrapolated"),
            ("d/dt max", "d/dt max"),
        ],
    )
    def test_ignition_type_names(self, respecth_name, chemked_name):
        """ReSpecTh spells the extrapolated types differently from ChemKED."""
        root = etree.Element("experiment")
        ignition = etree.SubElement(root, "ignitionType")
        ignition.set("target", "P")
        ignition.set("type", respecth_name)

        assert get_ignition_type(root)["type"] == chemked_name

    def test_ignition_vocabulary_matches_schema(self):
        """The converter's ignition vocabulary must not drift from the schema's."""
        ignition_schema = schema["datapoints"]["anyof"][0]["schema"]["schema"]["ignition-type"]
        assert set(ignition_target_values) == set(ignition_schema["schema"]["target"]["allowed"])
        assert set(ignition_type_values) == set(ignition_schema["schema"]["type"]["allowed"])

    def test_missing_attributes(self):
        """Check for error upon missing attributes"""
        root = etree.Element("experiment")
        with pytest.raises(MissingElementError) as excinfo:
            ignition = get_ignition_type(root)
        assert "Error: required element ignitionType is missing." in str(excinfo.value)

        root = etree.Element("experiment")
        ignition = etree.SubElement(root, "ignitionType")
        ignition.set("target", "P")
        with pytest.raises(MissingAttributeError) as excinfo:
            ignition = get_ignition_type(root)
        assert "Error: required attribute type of ignitionType is missing." in str(excinfo.value)

        root = etree.Element("experiment")
        ignition = etree.SubElement(root, "ignitionType")
        ignition.set("type", "max")
        with pytest.raises(MissingAttributeError) as excinfo:
            ignition = get_ignition_type(root)
        assert "Error: required attribute target of ignitionType is missing." in str(excinfo.value)

    @pytest.mark.parametrize(
        "ignition_type",
        ["baseline mean intercept from d/dt", "inflection", "d/dt third max"],
    )
    def test_unsupported_ignition_types(self, ignition_type):
        """Check error returned for unsupported/invalid ignition types."""
        root = etree.Element("experiment")
        ignition = etree.SubElement(root, "ignitionType")
        ignition.set("target", "P")
        ignition.set("type", ignition_type)

        with pytest.raises(KeywordError) as excinfo:
            ignition = get_ignition_type(root)
        assert "Error: " + ignition_type + " not valid ignition type" in str(excinfo.value)

    @pytest.mark.parametrize("ignition_target", ["density", "[O]*[CO]", "velocity"])
    def test_unsupported_ignition_targets(self, ignition_target):
        """Check error returned for unsupported/invalid ignition targets."""
        root = etree.Element("experiment")
        ignition = etree.SubElement(root, "ignitionType")
        ignition.set("target", ignition_target)
        ignition.set("type", "max")

        with pytest.raises(KeywordError) as excinfo:
            ignition = get_ignition_type(root)
        assert "Error: " + ignition_target + " not valid ignition target" in str(excinfo.value)

    def test_multiple_targets(self):
        """Check for error with multiple ignition targets."""
        root = etree.Element("experiment")
        ignition = etree.SubElement(root, "ignitionType")
        ignition.set("target", "OH;CH")
        ignition.set("type", "max")

        with pytest.raises(NotImplementedError) as excinfo:
            ignition = get_ignition_type(root)
        assert "Multiple ignition targets not supported." in str(excinfo.value)


class TestGetDatapoints:
    """ """

    def test_valid_datapoints_single_datagroup(self):
        """Test valid parsing of datapoints when in a single dataGroup."""
        root = etree.Element("experiment")
        datagroup = etree.SubElement(root, "dataGroup")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x1")
        prop.set("name", "temperature")
        prop.set("units", "K")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x2")
        prop.set("name", "ignition delay")
        prop.set("units", "us")

        num_points = 10
        rng = numpy.random.default_rng()
        temps = rng.uniform(low=300.0, high=1000.0, size=(num_points,))
        ignition_delays = rng.uniform(low=100.0, high=700.0, size=(num_points,))

        for temp, ignition_delay in zip(temps, ignition_delays):
            datapoint = etree.SubElement(datagroup, "dataPoint")
            x1 = etree.SubElement(datapoint, "x1")
            x1.text = str(temp)
            x2 = etree.SubElement(datapoint, "x2")
            x2.text = str(ignition_delay)

        datapoints = get_datapoints(root)
        assert len(datapoints) == num_points
        for datapoint, temp, ignition_delay in zip(datapoints, temps, ignition_delays):
            assert datapoint["temperature"] == [str(temp) + " K"]
            assert datapoint["ignition-delay"] == [str(ignition_delay) + " us"]

    def test_valid_datapoints_two_datagroup(self):
        """Test valid parsing of datapoints when in a two dataGroups."""
        root = etree.Element("experiment")
        apparatus = etree.SubElement(root, "apparatus")
        kind = etree.SubElement(apparatus, "kind")
        kind.text = "rapid compression machine"

        datagroup = etree.SubElement(root, "dataGroup")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x1")
        prop.set("name", "temperature")
        prop.set("units", "K")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x2")
        prop.set("name", "ignition delay")
        prop.set("units", "us")

        rng = numpy.random.default_rng()
        temp = rng.uniform(low=300.0, high=1000.0)
        ignition_delay = rng.uniform(low=100.0, high=700.0)
        datapoint = etree.SubElement(datagroup, "dataPoint")
        x1 = etree.SubElement(datapoint, "x1")
        x1.text = str(temp)
        x2 = etree.SubElement(datapoint, "x2")
        x2.text = str(ignition_delay)

        datagroup = etree.SubElement(root, "dataGroup")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x4")
        prop.set("name", "time")
        prop.set("units", "s")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x5")
        prop.set("name", "volume")
        prop.set("units", "cm3")

        num_points = 100
        times = numpy.linspace(0.0, 10.0e-2, num_points)
        volumes = numpy.cos(times * 20.0 * numpy.pi)
        for time, volume in zip(times, volumes):
            datapoint = etree.SubElement(datagroup, "dataPoint")
            x1 = etree.SubElement(datapoint, "x4")
            x1.text = str(time)
            x2 = etree.SubElement(datapoint, "x5")
            x2.text = str(volume)

        datapoints = get_datapoints(root)

        assert len(datapoints) == 1
        datapoint = datapoints[0]
        assert datapoint["temperature"] == [str(temp) + " K"]
        assert datapoint["ignition-delay"] == [str(ignition_delay) + " us"]

        volume_history = datapoint["time-histories"][0]
        assert len(volume_history["values"]) == num_points
        assert volume_history["time"]["units"] == "s"
        assert volume_history["time"]["column"] == 0
        assert volume_history["quantity"]["units"] == "cm3"
        assert volume_history["quantity"]["column"] == 1
        for datapoint, time, volume in zip(volume_history["values"], times, volumes):
            assert datapoint == [float(str(time)), float(str(volume))]

    def test_missing_datagroup_property_datapoint(self):
        """Raise error when missing a dataGroup, property, or dataPoint."""
        root = etree.Element("experiment")
        with pytest.raises(MissingElementError) as excinfo:
            get_datapoints(root)
        assert "Error: required element dataGroup is missing." in str(excinfo.value)

        datagroup = etree.SubElement(root, "dataGroup")
        with pytest.raises(MissingElementError) as excinfo:
            get_datapoints(root)
        assert "Error: required element property is missing." in str(excinfo.value)

        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x1")
        prop.set("name", "temperature")
        prop.set("units", "K")

        with pytest.raises(MissingElementError) as excinfo:
            get_datapoints(root)
        assert "Error: required element dataPoint is missing." in str(excinfo.value)

    def test_datapoint_invalid_property(self):
        """Raise error when invalid property for a ``dataPoint``."""
        root = etree.Element("experiment")
        exp = etree.SubElement(root, "experimentType")
        exp.text = "Ignition delay measurement"
        app = etree.SubElement(root, "apparatus")
        kind = etree.SubElement(app, "kind")
        kind.text = "shock tube"

        datagroup = etree.SubElement(root, "dataGroup")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x1")
        prop.set("name", "compression time")
        prop.set("units", "ms")
        datapoint = etree.SubElement(datagroup, "dataPoint")
        x1 = etree.SubElement(datapoint, "x1")
        x1.text = str(30.0)

        datagroup = etree.SubElement(root, "dataGroup")
        with pytest.raises(KeyError) as excinfo:
            get_datapoints(root)
        assert "compression time not valid dataPoint property" in str(excinfo.value)

    def test_datapoint_extra_value(self):
        """Raise error when value without associated property definition"""
        root = etree.Element("experiment")
        exp = etree.SubElement(root, "experimentType")
        exp.text = "Ignition delay measurement"
        app = etree.SubElement(root, "apparatus")
        kind = etree.SubElement(app, "kind")
        kind.text = "shock tube"

        datagroup = etree.SubElement(root, "dataGroup")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x1")
        prop.set("name", "temperature")
        prop.set("units", "K")

        datapoint = etree.SubElement(datagroup, "dataPoint")
        x1 = etree.SubElement(datapoint, "x1")
        x1.text = str(1000.0)
        x2 = etree.SubElement(datapoint, "x2")
        x2.text = str(100.0)

        with pytest.raises(KeywordError) as excinfo:
            get_datapoints(root)
        assert "value missing from properties: x2" in str(excinfo.value)

    def test_time_history_extra_property(self):
        """Ensure error when extra property in volume history dataGroup."""
        root = etree.Element("experiment")
        apparatus = etree.SubElement(root, "apparatus")
        kind = etree.SubElement(apparatus, "kind")
        kind.text = "rapid compression machine"

        datagroup = etree.SubElement(root, "dataGroup")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x1")
        prop.set("name", "temperature")
        prop.set("units", "K")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x2")
        prop.set("name", "ignition delay")
        prop.set("units", "us")

        datapoint = etree.SubElement(datagroup, "dataPoint")
        x1 = etree.SubElement(datapoint, "x1")
        x1.text = str(1000.0)
        x2 = etree.SubElement(datapoint, "x2")
        x2.text = str(100.0)

        datagroup = etree.SubElement(root, "dataGroup")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x3")
        prop.set("name", "time")
        prop.set("units", "s")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x4")
        prop.set("name", "volume")
        prop.set("units", "cm3")

        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x5")
        prop.set("name", "not allowed property")
        prop.set("units", "Pa")

        datapoint = etree.SubElement(datagroup, "dataPoint")
        x3 = etree.SubElement(datapoint, "x3")
        x3.text = str(0.0)
        x4 = etree.SubElement(datapoint, "x4")
        x4.text = str(50.0)
        x5 = etree.SubElement(datapoint, "x5")
        x5.text = str(101325.0)

        with pytest.raises(KeywordError) as excinfo:
            get_datapoints(root)
        assert (
            "Only volume, temperature, pressure, and time are allowed in a time-history dataGroup."
        ) in str(excinfo.value)

        # remove bad property description, but retain bad extra dataPoint value
        datagroup.remove(prop)
        with pytest.raises(KeywordError) as excinfo:
            get_datapoints(root)
        assert "Value tag {} not found in dataGroup tags: {}".format("x5", ["x4"]) in str(
            excinfo.value
        )

    def test_volume_history_missing_property(self):
        """Ensure error when missing property in volume history dataGroup."""
        root = etree.Element("experiment")
        apparatus = etree.SubElement(root, "apparatus")
        kind = etree.SubElement(apparatus, "kind")
        kind.text = "rapid compression machine"

        datagroup = etree.SubElement(root, "dataGroup")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x1")
        prop.set("name", "temperature")
        prop.set("units", "K")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x2")
        prop.set("name", "ignition delay")
        prop.set("units", "us")

        datapoint = etree.SubElement(datagroup, "dataPoint")
        x1 = etree.SubElement(datapoint, "x1")
        x1.text = str(1000.0)
        x2 = etree.SubElement(datapoint, "x2")
        x2.text = str(100.0)

        datagroup = etree.SubElement(root, "dataGroup")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x3")
        prop.set("name", "time")
        prop.set("units", "s")

        datapoint = etree.SubElement(datagroup, "dataPoint")
        x3 = etree.SubElement(datapoint, "x3")
        x3.text = str(0.0)

        with pytest.raises(KeywordError) as excinfo:
            get_datapoints(root)
        assert "Both time and quantity properties required for time-history." in str(excinfo.value)

        # try the same with volume, and time missing
        datagroup.remove(prop)
        datagroup.remove(datapoint)
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x4")
        prop.set("name", "volume")
        prop.set("units", "cm3")
        datapoint = etree.SubElement(datagroup, "dataPoint")
        x3 = etree.SubElement(datapoint, "x4")
        x3.text = str(50.0)

        with pytest.raises(KeywordError) as excinfo:
            get_datapoints(root)
        assert "Both time and quantity properties required for time-history." in str(excinfo.value)

    def test_volume_history_missing_value(self):
        """Ensure error when missing value in volume history dataGroup."""
        root = etree.Element("experiment")
        apparatus = etree.SubElement(root, "apparatus")
        kind = etree.SubElement(apparatus, "kind")
        kind.text = "rapid compression machine"

        datagroup = etree.SubElement(root, "dataGroup")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x1")
        prop.set("name", "temperature")
        prop.set("units", "K")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x2")
        prop.set("name", "ignition delay")
        prop.set("units", "us")

        datapoint = etree.SubElement(datagroup, "dataPoint")
        x1 = etree.SubElement(datapoint, "x1")
        x1.text = str(1000.0)
        x2 = etree.SubElement(datapoint, "x2")
        x2.text = str(100.0)

        datagroup = etree.SubElement(root, "dataGroup")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x3")
        prop.set("name", "time")
        prop.set("units", "s")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x4")
        prop.set("name", "volume")
        prop.set("units", "cm3")

        # Have time, but missing volume
        datapoint = etree.SubElement(datagroup, "dataPoint")
        x3 = etree.SubElement(datapoint, "x3")
        x3.text = str(0.0)
        with pytest.raises(KeywordError) as excinfo:
            get_datapoints(root)
        assert "Both time and quantity values required in each time-history dataPoint." in str(
            excinfo.value
        )

        # try again with volume, but missing time
        datapoint.remove(x3)
        x4 = etree.SubElement(datapoint, "x4")
        x4.text = str(50.0)
        with pytest.raises(KeywordError) as excinfo:
            get_datapoints(root)
        assert "Both time and quantity values required in each time-history dataPoint." in str(
            excinfo.value
        )

    @pytest.mark.parametrize(
        "type, value",
        [
            ("mole fraction", 1.0),
            ("mass fraction", 1.0),
            ("mole percent", 100.0),
        ],
    )
    @pytest.mark.filterwarnings("ignore:Missing InChI for species H2")
    def test_datapoints_composition(self, type, value):
        """Test valid parsing of datapoints with composition."""
        root = etree.Element("experiment")
        datagroup = etree.SubElement(root, "dataGroup")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x1")
        prop.set("name", "temperature")
        prop.set("units", "K")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x2")
        prop.set("name", "ignition delay")
        prop.set("units", "us")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x3")
        prop.set("name", "composition")
        prop.set("units", type)
        specieslink = etree.SubElement(prop, "speciesLink")
        specieslink.set("preferredKey", "H2")

        datapoint = etree.SubElement(datagroup, "dataPoint")
        x1 = etree.SubElement(datapoint, "x1")
        x1.text = str(1000.0)
        x2 = etree.SubElement(datapoint, "x2")
        x2.text = str(100.0)
        x3 = etree.SubElement(datapoint, "x3")
        x3.text = str(value)

        datapoints = get_datapoints(root)
        assert len(datapoints) == 1
        datapoint = datapoints[0]
        assert datapoint["temperature"] == [str(1000.0) + " K"]
        assert datapoint["ignition-delay"] == [str(100.0) + " us"]
        assert datapoint["composition"]["kind"] == type
        assert datapoint["composition"]["species"][0] == {
            "amount": [value],
            "species-name": "H2",
            "InChI": None,
        }

    @pytest.mark.parametrize(
        "kind, value",
        [
            ("percent", 100.0),
            ("ppm", 1.0),
            ("ppb", 1.0),
        ],
    )
    def test_datapoints_composition_warning(self, kind, value):
        """Test valid parsing of datapoints with composition with warnings."""
        root = etree.Element("experiment")
        datagroup = etree.SubElement(root, "dataGroup")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x1")
        prop.set("name", "temperature")
        prop.set("units", "K")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x2")
        prop.set("name", "ignition delay")
        prop.set("units", "us")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x3")
        prop.set("name", "composition")
        prop.set("units", kind)
        specieslink = etree.SubElement(prop, "speciesLink")
        specieslink.set("preferredKey", "H2")

        datapoint = etree.SubElement(datagroup, "dataPoint")
        x1 = etree.SubElement(datapoint, "x1")
        x1.text = str(1000.0)
        x2 = etree.SubElement(datapoint, "x2")
        x2.text = str(100.0)
        x3 = etree.SubElement(datapoint, "x3")
        x3.text = str(value)

        with pytest.warns(UserWarning) as record:
            datapoints = get_datapoints(root)
        m = str(record.pop(UserWarning).message)
        assert m == "Missing InChI for species H2"
        m = str(record.pop(UserWarning).message)
        if kind == "percent":
            assert m == "Assuming percent in composition means mole percent"
            kind = "mole percent"
        elif kind == "ppm":
            assert m == "Assuming molar ppm in composition and converting to mole fraction"
            kind = "mole fraction"
            value *= 1e-6
        elif kind == "ppb":
            assert m == "Assuming molar ppb in composition and converting to mole fraction"
            kind = "mole fraction"
            value *= 1e-9

        assert len(datapoints) == 1
        datapoint = datapoints[0]
        assert datapoint["temperature"] == [str(1000.0) + " K"]
        assert datapoint["ignition-delay"] == [str(100.0) + " us"]
        assert datapoint["composition"]["kind"] == kind
        assert datapoint["composition"]["species"][0] == {
            "amount": [value],
            "species-name": "H2",
            "InChI": None,
        }

    def test_datapoints_composition_error(self):
        """Test valid parsing of datapoints with improper unit error."""
        root = etree.Element("experiment")
        datagroup = etree.SubElement(root, "dataGroup")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x1")
        prop.set("name", "temperature")
        prop.set("units", "K")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x2")
        prop.set("name", "ignition delay")
        prop.set("units", "us")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x3")
        prop.set("name", "composition")
        prop.set("units", "grams")
        specieslink = etree.SubElement(prop, "speciesLink")
        specieslink.set("preferredKey", "H2")
        specieslink.set("InChI", "1S/H2/h1H")

        datapoint = etree.SubElement(datagroup, "dataPoint")
        x1 = etree.SubElement(datapoint, "x1")
        x1.text = str(1000.0)
        x2 = etree.SubElement(datapoint, "x2")
        x2.text = str(100.0)
        x3 = etree.SubElement(datapoint, "x3")
        x3.text = str(10.0)

        with pytest.raises(KeywordError) as excinfo:
            get_datapoints(root)
        assert "composition units need to be one of: " in str(excinfo.value)
        for supported in ["mole fraction", "mole percent", "ppm", "mol/cm3"]:
            assert supported in str(excinfo.value)

    def test_datapoints_inconsistent_composition_error(self):
        """Test error raised for datapoint with inconsistent composition type."""
        root = etree.Element("experiment")
        datagroup = etree.SubElement(root, "dataGroup")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x1")
        prop.set("name", "temperature")
        prop.set("units", "K")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x2")
        prop.set("name", "ignition delay")
        prop.set("units", "us")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x3")
        prop.set("name", "composition")
        prop.set("units", "mass fraction")
        specieslink = etree.SubElement(prop, "speciesLink")
        specieslink.set("preferredKey", "H2")
        specieslink.set("InChI", "1S/H2/h1H")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x4")
        prop.set("name", "composition")
        prop.set("units", "mole fraction")
        specieslink = etree.SubElement(prop, "speciesLink")
        specieslink.set("preferredKey", "O2")
        specieslink.set("InChI", "1S/O2/c1-2")

        datapoint = etree.SubElement(datagroup, "dataPoint")
        x1 = etree.SubElement(datapoint, "x1")
        x1.text = str(1000.0)
        x2 = etree.SubElement(datapoint, "x2")
        x2.text = str(100.0)
        x3 = etree.SubElement(datapoint, "x3")
        x3.text = str(0.5)
        x3 = etree.SubElement(datapoint, "x4")
        x3.text = str(0.5)

        with pytest.raises(KeywordError) as excinfo:
            get_datapoints(root)
        assert ("Error: composition units mole fraction not consistent with mass fraction") in str(
            excinfo.value
        )


class TestUnits:
    """ReSpecTh unit strings have to reach Pint in a form it can parse."""

    @pytest.mark.parametrize(
        "respecth_units, pint_units",
        [
            ("cm/s", "cm/s"),
            ("K", "K"),
            # ReSpecTh writes reciprocal units with a bare negative exponent
            ("ms-1", "ms**-1"),
            ("kg m-2 s-1", "kg * m**-2 * s**-1"),
            ("Torr", "torr"),
            ("unitless", "dimensionless"),
            ("[-]", "dimensionless"),
        ],
    )
    def test_normalize_units(self, respecth_units, pint_units):
        """Ensure ReSpecTh unit spellings are translated for Pint."""
        assert normalize_units(respecth_units) == pint_units

    @pytest.mark.parametrize("respecth_units", ["ms-1", "kg m-2 s-1", "cm/s", "unitless"])
    def test_normalized_units_are_parseable(self, respecth_units):
        """Every normalized unit string must actually parse."""
        assert unit_registry(normalize_units(respecth_units)) is not None

    def test_reciprocal_units_in_common_property(self):
        """A pressure rise in ms-1 must convert rather than raise a Pint error.

        Pint reads the ReSpecTh spelling "ms-1" as a subtraction, so parsing it outside a guarded
        block used to escape as a DimensionalityError instead of a KeywordError.
        """
        root = etree.Element("experiment")
        properties = etree.SubElement(root, "commonProperties")
        prop = etree.SubElement(properties, "property")
        prop.set("name", "pressure rise")
        prop.set("units", "ms-1")
        etree.SubElement(prop, "value").text = "0.10"

        assert get_common_properties(root)["pressure-rise"] == ["0.10 ms**-1"]

    def test_unparseable_units_raise_keyword_error(self):
        """Units Pint cannot parse are reported as a keyword error, not a Pint error."""
        root = etree.Element("experiment")
        properties = etree.SubElement(root, "commonProperties")
        prop = etree.SubElement(properties, "property")
        prop.set("name", "temperature")
        prop.set("units", "degrees Fahrenheit-ish")
        etree.SubElement(prop, "value").text = "1000"

        with pytest.raises(KeywordError) as excinfo:
            get_common_properties(root)
        assert "units incompatible for property temperature" in str(excinfo.value)


class TestReSpecThVersion2:
    """ReSpecTh 2.x states the reference and the properties differently from 1.x."""

    def build_reference(self, **details):
        root = etree.Element("experiment")
        biblio = etree.SubElement(root, "bibliographyLink")
        etree.SubElement(biblio, "description").text = "S. Adusumilli, Combust. Flame 233 (2021)."
        etree.SubElement(biblio, "referenceDOI").text = "10.1016/j.combustflame.2021.111564"
        elem = etree.SubElement(biblio, "details")
        for name, text in details.items():
            etree.SubElement(elem, name).text = text
        return root

    def test_reference_from_details(self):
        """The reference is read from the file, with no DOI lookup."""
        root = self.build_reference(
            author="Adusumilli, Sampath and Seitzman, Jerry",
            journal="Combustion and Flame",
            volume="233",
            pages="111564",
            year="2021",
        )

        reference = get_reference(root)
        assert reference["doi"] == "10.1016/j.combustflame.2021.111564"
        assert reference["journal"] == "Combustion and Flame"
        assert reference["year"] == 2021
        assert reference["volume"] == 233
        # ReSpecTh writes authors family name first
        assert reference["authors"] == [
            {"name": "Sampath Adusumilli"},
            {"name": "Jerry Seitzman"},
        ]

    @pytest.mark.parametrize("respecth_pages", ["13--22", "13–22", "13-22"])
    def test_page_ranges_are_normalized(self, respecth_pages):
        """ReSpecTh writes page ranges with en dashes or doubled hyphens."""
        root = self.build_reference(author="Doe, Jane", year="2021", pages=respecth_pages)
        assert get_reference(root)["pages"] == "13-22"

    def test_details_without_year_falls_back(self, mock_crossref_api):
        """Details that cannot make a valid reference fall back to the DOI lookup."""
        root = self.build_reference(author="Doe, Jane")
        # The stubbed lookup answers for this DOI
        biblio = root.find("bibliographyLink")
        biblio.find("referenceDOI").text = "10.1016/j.cpc.2017.02.004"

        assert get_reference(root)["journal"] == "Computer Physics Communications"

    @pytest.mark.parametrize(
        "name, field, value, units",
        [
            ("residence time", "residence-time", "120", "ms"),
            ("volume", "reactor-volume", "31.6", "cm3"),
            ("flow rate", "flow-rate", "0.3148", "kg m-2 s-1"),
            ("equivalence ratio", "equivalence-ratio", "0.7", "unitless"),
            ("reactor length", "reactor-length", "10", "cm"),
            ("environment temperature", "environment-temperature", "298", "K"),
        ],
    )
    def test_common_property_vocabulary(self, name, field, value, units):
        """ReSpecTh 2.x uses common properties beyond the four dataGroup quantities."""
        root = etree.Element("experiment")
        properties = etree.SubElement(root, "commonProperties")
        prop = etree.SubElement(properties, "property")
        prop.set("name", name)
        prop.set("units", units)
        etree.SubElement(prop, "value").text = value

        assert get_common_properties(root)[field] == [
            " ".join([value, normalize_units(units)])
        ]

    def test_composition_units_error_lists_what_is_accepted(self):
        """The error message is built from the table, so it cannot fall behind it."""
        with pytest.raises(KeywordError) as excinfo:
            get_composition_amount("furlongs", "1")

        message = str(excinfo.value)
        for units in composition_units:
            if units in composition_unit_typos:
                # A tolerated misspelling is accepted but not advertised
                assert units not in message
            else:
                assert units in message

    def test_misspelled_composition_units(self):
        """Part of the corpus misspells mole fraction as "mole faction"."""
        root = etree.Element("experiment")
        properties = etree.SubElement(root, "commonProperties")
        composition = etree.SubElement(properties, "property")
        composition.set("name", "initial composition")
        component = etree.SubElement(composition, "component")
        species = etree.SubElement(component, "speciesLink")
        species.set("preferredKey", "H2")
        species.set("InChI", "1S/H2/h1H")
        amount = etree.SubElement(component, "amount")
        amount.set("units", "mole faction")
        amount.text = "1.0"

        with pytest.warns(UserWarning, match="mole faction"):
            common = get_common_properties(root)
        assert common["composition"]["kind"] == "mole fraction"

    def test_mixed_mole_percent_and_fraction(self):
        """Mole percent and mole fraction convert exactly, so a mixture is reconciled."""
        root = etree.Element("experiment")
        properties = etree.SubElement(root, "commonProperties")
        composition = etree.SubElement(properties, "property")
        composition.set("name", "initial composition")
        for name, inchi, amount_units, amount_text in [
            ("H2", "1S/H2/h1H", "mole percent", "10.0"),
            ("Ar", "1S/Ar", "mole fraction", "0.9"),
        ]:
            component = etree.SubElement(composition, "component")
            species = etree.SubElement(component, "speciesLink")
            species.set("preferredKey", name)
            species.set("InChI", inchi)
            amount = etree.SubElement(component, "amount")
            amount.set("units", amount_units)
            amount.text = amount_text

        with pytest.warns(UserWarning, match="mixes mole fraction and mole percent"):
            common = get_common_properties(root)

        assert common["composition"]["kind"] == "mole fraction"
        assert common["composition"]["species"][0]["amount"] == [0.1]
        assert common["composition"]["species"][1]["amount"] == [0.9]


class TestValueMetadata:
    """ReSpecTh states uncertainties as properties that point at another quantity."""

    def build_metadata(self, name, reference, kind, value, units=None, species=None, **attrib):
        root = etree.Element("experiment")
        properties = etree.SubElement(root, "commonProperties")
        prop = etree.SubElement(properties, "property")
        prop.set("name", name)
        prop.set("reference", reference)
        prop.set("kind", kind)
        if units is not None:
            prop.set("units", units)
        for key, item in attrib.items():
            prop.set(key, item)
        if species is not None:
            etree.SubElement(prop, "speciesLink").set("preferredKey", species)
        etree.SubElement(prop, "value").text = value
        return root

    def test_metadata_is_not_a_common_property(self):
        """An uncertainty describes another quantity, so it is not a property of its own."""
        root = self.build_metadata(
            "evaluated standard deviation", "laminar burning velocity", "relative", "0.039"
        )
        assert get_common_properties(root) == {}
        assert len(get_value_metadata(root)) == 1

    def test_missing_reference(self):
        """An uncertainty with nothing to point at is an error."""
        root = etree.Element("experiment")
        properties = etree.SubElement(root, "commonProperties")
        prop = etree.SubElement(properties, "property")
        prop.set("name", "uncertainty")
        prop.set("kind", "absolute")
        etree.SubElement(prop, "value").text = "1.0"

        with pytest.raises(MissingAttributeError) as excinfo:
            get_value_metadata(root)
        assert "required attribute reference of uncertainty is missing" in str(excinfo.value)

    def test_relative_esd_attaches_to_every_datapoint(self):
        """A file-wide relative deviation belongs to the value in each datapoint."""
        root = self.build_metadata(
            "evaluated standard deviation",
            "laminar burning velocity",
            "relative",
            "0.039",
            units="unitless",
            sourcetype="estimated",
            method="statistical scatter",
        )
        properties = {
            "common-properties": {},
            "datapoints": [
                {"laminar-burning-velocity": ["59.48 cm/s"]},
                {"laminar-burning-velocity": ["91.48 cm/s"]},
            ],
        }

        attach_value_metadata(properties, get_value_metadata(root))

        for datapoint in properties["datapoints"]:
            metadata = datapoint["laminar-burning-velocity"][1]
            assert metadata["evaluated-standard-deviation"] == "0.039"
            assert metadata["evaluated-standard-deviation-type"] == "relative"
            assert metadata["evaluated-standard-deviation-sourcetype"] == "estimated"
            assert metadata["evaluated-standard-deviation-method"] == "statistical scatter"

    def test_absolute_uncertainty_keeps_units(self):
        """An absolute uncertainty is stored with the units it was given in."""
        root = self.build_metadata(
            "uncertainty", "ignition delay", "absolute", "12.0", units="us", bound="plusminus"
        )
        properties = {"common-properties": {}, "datapoints": [{"ignition-delay": ["120 us"]}]}

        attach_value_metadata(properties, get_value_metadata(root))

        metadata = properties["datapoints"][0]["ignition-delay"][1]
        assert metadata["uncertainty"] == "12.0 us"
        assert metadata["uncertainty-type"] == "absolute"

    def test_initial_composition_reference(self):
        """An uncertainty about the mixture belongs to that species' amount."""
        root = self.build_metadata(
            "uncertainty", "initial composition", "relative", "0.04", units="unitless", species="NH3"
        )
        properties = {
            "common-properties": {
                "composition": {
                    "kind": "mole fraction",
                    "species": [
                        {"species-name": "NH3", "amount": [0.00076]},
                        {"species-name": "N2", "amount": [0.99924]},
                    ],
                }
            },
            "datapoints": [{}],
        }

        attach_value_metadata(properties, get_value_metadata(root))

        species = properties["common-properties"]["composition"]["species"]
        # A composition amount is a bare number, so its uncertainty is stored as one too
        assert species[0]["amount"][1] == {
            "uncertainty-type": "relative",
            "uncertainty": 0.04,
        }
        # The other species was not given an uncertainty
        assert len(species[1]["amount"]) == 1

    @pytest.mark.parametrize("reference", ["Sl", "x1"])
    def test_reference_by_label_or_id(self, reference):
        """Part of the corpus points at a column by its label or its id, not by name."""
        root = self.build_metadata("uncertainty", reference, "absolute", "1.83", units="cm/s")
        datagroup = etree.SubElement(root, "dataGroup")
        datagroup.set("id", "dg1")
        prop = etree.SubElement(datagroup, "property")
        prop.set("name", "laminar burning velocity")
        prop.set("id", "x1")
        prop.set("label", "Sl")
        prop.set("units", "cm/s")

        properties = {
            "common-properties": {},
            "datapoints": [{"laminar-burning-velocity": ["16.89 cm/s"]}],
        }
        attach_value_metadata(properties, get_value_metadata(root))

        metadata = properties["datapoints"][0]["laminar-burning-velocity"][1]
        assert metadata["uncertainty"] == "1.83 cm/s"

    def test_uncertainty_and_esd_on_one_value(self):
        """The two kinds of uncertainty describe a value together, not exclusively."""
        root = etree.Element("experiment")
        properties_elem = etree.SubElement(root, "commonProperties")
        for name, kind, value, method in [
            ("uncertainty", "absolute", "1.83", None),
            ("evaluated standard deviation", "absolute", "2.0", "generic uncertainty"),
        ]:
            prop = etree.SubElement(properties_elem, "property")
            prop.set("name", name)
            prop.set("reference", "laminar burning velocity")
            prop.set("kind", kind)
            prop.set("units", "cm/s")
            if method is not None:
                prop.set("method", method)
            etree.SubElement(prop, "value").text = value

        properties = {
            "common-properties": {},
            "datapoints": [{"laminar-burning-velocity": ["16.89 cm/s"]}],
        }
        attach_value_metadata(properties, get_value_metadata(root))

        metadata = properties["datapoints"][0]["laminar-burning-velocity"][1]
        assert metadata["uncertainty"] == "1.83 cm/s"
        assert metadata["evaluated-standard-deviation"] == "2.0 cm/s"
        assert metadata["evaluated-standard-deviation-method"] == "generic uncertainty"

    def test_metadata_attaches_to_common_property(self):
        """A deviation about a shared value is stored with that shared value."""
        root = self.build_metadata("uncertainty", "temperature", "absolute", "5", units="K")
        properties = {"common-properties": {"temperature": ["1000 K"]}, "datapoints": [{}]}

        attach_value_metadata(properties, get_value_metadata(root))

        assert properties["common-properties"]["temperature"][1]["uncertainty"] == "5 K"

    def test_metadata_with_no_target_is_dropped(self):
        """An uncertainty about a quantity the file never states cannot be kept."""
        root = self.build_metadata("uncertainty", "pressure rise", "absolute", "5", units="ms-1")
        properties = {"common-properties": {}, "datapoints": [{"temperature": ["1000 K"]}]}

        with pytest.warns(UserWarning, match="Dropping uncertainty that refers to pressure rise"):
            attach_value_metadata(properties, get_value_metadata(root))

    def test_invalid_kind(self):
        """ReSpecTh states whether a deviation is absolute or relative."""
        root = self.build_metadata("uncertainty", "temperature", "sort of big", "5", units="K")
        properties = {"common-properties": {"temperature": ["1000 K"]}, "datapoints": [{}]}

        with pytest.raises(KeywordError) as excinfo:
            attach_value_metadata(properties, get_value_metadata(root))
        assert "sort of big not a valid kind for uncertainty" in str(excinfo.value)


class TestLBVDatapoints:
    """Laminar burning velocity files give one datapoint per dataPoint row."""

    def build_root(self, columns, rows):
        root = etree.Element("experiment")
        datagroup = etree.SubElement(root, "dataGroup")
        datagroup.set("id", "dg1")
        for column in columns:
            prop = etree.SubElement(datagroup, "property")
            for key, value in column.items():
                if key == "species":
                    link = etree.SubElement(prop, "speciesLink")
                    link.set("preferredKey", value)
                    link.set("InChI", "1S/" + value)
                else:
                    prop.set(key, value)
        for row in rows:
            datapoint = etree.SubElement(datagroup, "dataPoint")
            for tag, text in row.items():
                etree.SubElement(datapoint, tag).text = text
        return root

    def test_lbv_datapoints(self):
        """Each row becomes a datapoint with its own composition."""
        root = self.build_root(
            [
                {"name": "laminar burning velocity", "id": "x1", "units": "cm/s"},
                {"name": "equivalence ratio", "id": "x2", "units": "unitless"},
                {"name": "composition", "id": "x3", "units": "mole fraction", "species": "H2"},
                {"name": "composition", "id": "x4", "units": "mole fraction", "species": "O2"},
            ],
            [
                {"x1": "59.48", "x2": "0.7", "x3": "0.3", "x4": "0.7"},
                {"x1": "91.48", "x2": "1.0", "x3": "0.4", "x4": "0.6"},
            ],
        )

        datapoints = get_lbv_datapoints(root)

        assert len(datapoints) == 2
        assert datapoints[0]["laminar-burning-velocity"] == ["59.48 cm/s"]
        assert datapoints[0]["equivalence-ratio"] == ["0.7 dimensionless"]
        assert datapoints[0]["composition"]["kind"] == "mole fraction"
        assert datapoints[1]["composition"]["species"][0]["amount"] == [0.4]

    def test_pointwise_uncertainty_columns(self):
        """A column of uncertainties belongs to the value it describes, row by row."""
        root = self.build_root(
            [
                {"name": "laminar burning velocity", "id": "x1", "units": "cm/s"},
                {"name": "composition", "id": "x2", "units": "mole fraction", "species": "H2"},
                {
                    "name": "uncertainty",
                    "id": "x3",
                    "units": "cm/s",
                    "reference": "laminar burning velocity",
                    "kind": "absolute",
                    "bound": "plusminus",
                    "sourcetype": "reported",
                },
                {
                    "name": "evaluated standard deviation",
                    "id": "x4",
                    "units": "cm/s",
                    "reference": "laminar burning velocity",
                    "kind": "absolute",
                    "method": "statistical scatter",
                },
            ],
            [{"x1": "20.16", "x2": "1.0", "x3": "0.97", "x4": "0.558"}],
        )

        metadata = get_lbv_datapoints(root)[0]["laminar-burning-velocity"][1]

        assert metadata["uncertainty"] == "0.97 cm/s"
        assert metadata["uncertainty-sourcetype"] == "reported"
        assert metadata["evaluated-standard-deviation"] == "0.558 cm/s"
        assert metadata["evaluated-standard-deviation-method"] == "statistical scatter"

    def test_invalid_column(self):
        """A column that is not a laminar burning velocity quantity is an error."""
        root = self.build_root(
            [{"name": "compression time", "id": "x1", "units": "ms"}], [{"x1": "1.0"}]
        )

        with pytest.raises(KeyError) as excinfo:
            get_lbv_datapoints(root)
        assert "compression time not valid dataPoint property" in str(excinfo.value)


class TestSpeciationDatapoints:
    """Speciation files give one datapoint per dataGroup, holding profiles."""

    def build_root(self, columns, rows):
        return TestLBVDatapoints.build_root(self, columns, rows)

    def test_temperature_sweep(self):
        """The first column is the swept axis and species columns become profiles."""
        root = self.build_root(
            [
                {"name": "temperature", "id": "x1", "units": "K"},
                {"name": "composition", "id": "x2", "units": "mole fraction", "species": "H2"},
                {"name": "composition", "id": "x3", "units": "ppm", "species": "CO"},
            ],
            [
                {"x1": "849", "x2": "0.00722", "x3": "100"},
                {"x1": "899", "x2": "0.00356", "x3": "200"},
            ],
        )

        with pytest.warns(UserWarning, match="molar ppm"):
            datapoints = get_speciation_datapoints(root)

        assert len(datapoints) == 1
        assert datapoints[0]["independent-variables"] == [
            {"name": "temperature", "units": "K", "primary": True}
        ]
        profiles = datapoints[0]["concentration-profiles"]
        assert profiles[0]["species-name"] == "H2"
        assert profiles[0]["values"] == [[849.0, 0.00722], [899.0, 0.00356]]
        # ppm is converted, so the profile is in mole fraction
        assert profiles[1]["quantity"] == {"units": "mole fraction"}
        assert profiles[1]["values"][0] == pytest.approx([849.0, 1.0e-4])
        assert profiles[1]["values"][1] == pytest.approx([899.0, 2.0e-4])

    def test_auxiliary_profile(self):
        """A measured quantity that is not a species becomes an auxiliary profile."""
        root = self.build_root(
            [
                {"name": "distance", "id": "x1", "units": "mm"},
                {"name": "composition", "id": "x2", "units": "mole fraction", "species": "N2"},
                {"name": "temperature", "id": "x3", "units": "K"},
            ],
            [
                {"x1": "0.674", "x2": "0.1", "x3": "1662"},
                {"x1": "1.058", "x2": "0.2", "x3": "1659"},
            ],
        )

        auxiliary = get_speciation_datapoints(root)[0]["auxiliary-profiles"]

        assert auxiliary[0]["type"] == "temperature"
        assert auxiliary[0]["independent"] == {"name": "distance", "units": "mm"}
        assert auxiliary[0]["values"] == [[0.674, 1662.0], [1.058, 1659.0]]

    def test_auxiliary_profile_against_residence_time(self):
        """A residence time is a time coordinate, so an auxiliary profile can use it."""
        root = self.build_root(
            [
                {"name": "residence time", "id": "x1", "units": "ms"},
                {"name": "composition", "id": "x2", "units": "mole fraction", "species": "N2"},
                {"name": "temperature", "id": "x3", "units": "K"},
            ],
            [
                {"x1": "100", "x2": "0.1", "x3": "1000"},
                {"x1": "200", "x2": "0.2", "x3": "1010"},
            ],
        )

        datapoint = get_speciation_datapoints(root)[0]

        assert datapoint["independent-variables"][0]["name"] == "residence-time"
        # auxiliary-profiles.independent.name is a coordinate, and allows time
        assert datapoint["auxiliary-profiles"][0]["independent"] == {
            "name": "time",
            "units": "ms",
        }
        assert datapoint["auxiliary-profiles"][0]["values"] == [[100.0, 1000.0], [200.0, 1010.0]]

    def test_covariates_of_a_sweep(self):
        """Quantities that vary with the swept axis are co-variates, not profiles.

        A shock-tube outlet-concentration file gives one experiment per row, each with its own
        temperature, residence time and pressure, so none of them is a profile of another.
        """
        root = self.build_root(
            [
                {"name": "temperature", "id": "x1", "units": "K"},
                {"name": "composition", "id": "x2", "units": "mole fraction", "species": "CO"},
                {"name": "residence time", "id": "x3", "units": "s"},
                {"name": "pressure", "id": "x4", "units": "atm"},
            ],
            [
                {"x1": "995", "x2": "0.0004079", "x3": "0.00184", "x4": "21.8"},
                {"x1": "1037", "x2": "0.0004047", "x3": "0.00163", "x4": "22.3"},
            ],
        )

        datapoint = get_speciation_datapoints(root)[0]

        assert [item["name"] for item in datapoint["independent-variables"]] == [
            "temperature",
            "residence-time",
            "pressure",
        ]
        assert [item["primary"] for item in datapoint["independent-variables"]] == [
            True,
            False,
            False,
        ]
        assert "auxiliary-profiles" not in datapoint
        # Every row carries one value per independent variable, then the amount
        assert datapoint["concentration-profiles"][0]["values"][0] == [
            995.0,
            0.00184,
            21.8,
            0.0004079,
        ]

    def test_profile_of_a_quantity_that_is_not_an_axis(self):
        """A volume profile needs a coordinate to be measured against."""
        root = self.build_root(
            [
                {"name": "temperature", "id": "x1", "units": "K"},
                {"name": "composition", "id": "x2", "units": "mole fraction", "species": "N2"},
                {"name": "volume", "id": "x3", "units": "cm3"},
            ],
            [
                {"x1": "1000", "x2": "0.1", "x3": "1.0"},
                {"x1": "1100", "x2": "0.2", "x3": "1.5"},
            ],
        )

        with pytest.raises(NotImplementedError) as excinfo:
            get_speciation_datapoints(root)
        assert "only as a single value or as a profile against distance or time" in str(
            excinfo.value
        )

    def test_constant_column_is_a_condition(self):
        """A column with one repeated value states a condition, not a profile."""
        root = self.build_root(
            [
                {"name": "temperature", "id": "x1", "units": "K"},
                {"name": "composition", "id": "x2", "units": "mole fraction", "species": "N2"},
                {"name": "environment temperature", "id": "x3", "units": "K"},
            ],
            [
                {"x1": "849", "x2": "0.1", "x3": "298"},
                {"x1": "899", "x2": "0.2", "x3": "298"},
            ],
        )

        datapoint = get_speciation_datapoints(root)[0]
        assert datapoint["environment-temperature"] == ["298 K"]
        assert "auxiliary-profiles" not in datapoint

    def test_concentration_column_is_a_species(self):
        """ReSpecTh names a species column "concentration" when it holds a concentration."""
        root = self.build_root(
            [
                {"name": "time", "id": "x1", "units": "s"},
                {"name": "concentration", "id": "x2", "units": "mol/cm3", "species": "OH"},
            ],
            [{"x1": "0.0", "x2": "1e-9"}, {"x1": "0.1", "x2": "2e-9"}],
        )

        profile = get_speciation_datapoints(root)[0]["concentration-profiles"][0]
        assert profile["species-name"] == "OH"
        assert profile["quantity"] == {"units": "mol/cm3"}

    def test_pointwise_and_constant_uncertainty_columns(self):
        """A varying uncertainty goes in the row, a constant one describes the profile."""
        root = self.build_root(
            [
                {"name": "temperature", "id": "x1", "units": "K"},
                {"name": "composition", "id": "x2", "units": "mole fraction", "species": "H2"},
                {
                    "name": "evaluated standard deviation",
                    "id": "x3",
                    "units": "mole fraction",
                    "reference": "composition",
                    "kind": "absolute",
                    "species": "H2",
                },
                {
                    "name": "uncertainty",
                    "id": "x4",
                    "units": "unitless",
                    "reference": "composition",
                    "kind": "relative",
                    "species": "H2",
                },
            ],
            [
                {"x1": "849", "x2": "0.1", "x3": "0.01", "x4": "0.05"},
                {"x1": "899", "x2": "0.2", "x3": "0.02", "x4": "0.05"},
            ],
        )

        profile = get_speciation_datapoints(root)[0]["concentration-profiles"][0]

        # The evaluated standard deviation varies, so it is the trailing column of each row
        assert profile["values"] == [[849.0, 0.1, 0.01], [899.0, 0.2, 0.02]]
        # The relative uncertainty is the same for every point, so it describes the profile
        assert profile["uncertainty"][0]["uncertainty"] == 0.05
        assert profile["uncertainty"][0]["uncertainty-type"] == "relative"

    def test_two_varying_uncertainty_columns(self):
        """A profile row holds only one uncertainty, so two varying columns cannot fit."""
        root = self.build_root(
            [
                {"name": "temperature", "id": "x1", "units": "K"},
                {"name": "composition", "id": "x2", "units": "mole fraction", "species": "H2"},
                {
                    "name": "evaluated standard deviation",
                    "id": "x3",
                    "units": "mole fraction",
                    "reference": "composition",
                    "kind": "absolute",
                    "species": "H2",
                },
                {
                    "name": "uncertainty",
                    "id": "x4",
                    "units": "mole fraction",
                    "reference": "composition",
                    "kind": "absolute",
                    "species": "H2",
                },
            ],
            [
                {"x1": "849", "x2": "0.1", "x3": "0.01", "x4": "0.03"},
                {"x1": "899", "x2": "0.2", "x3": "0.02", "x4": "0.04"},
            ],
        )

        with pytest.raises(NotImplementedError) as excinfo:
            get_speciation_datapoints(root)
        assert "more than one uncertainty column that varies" in str(excinfo.value)

    def test_multiple_datagroups(self):
        """Each dataGroup is a separate set of conditions, so a separate datapoint."""
        root = self.build_root(
            [
                {"name": "temperature", "id": "x1", "units": "K"},
                {"name": "composition", "id": "x2", "units": "mole fraction", "species": "H2"},
            ],
            [{"x1": "849", "x2": "0.1"}, {"x1": "899", "x2": "0.2"}],
        )
        second = etree.SubElement(root, "dataGroup")
        second.set("id", "dg2")
        prop = etree.SubElement(second, "property")
        prop.set("name", "distance")
        prop.set("id", "y1")
        prop.set("units", "cm")
        prop = etree.SubElement(second, "property")
        prop.set("name", "composition")
        prop.set("id", "y2")
        prop.set("units", "mole fraction")
        etree.SubElement(prop, "speciesLink").set("preferredKey", "OH")
        for distance, amount in [("1.0", "0.01"), ("2.0", "0.02")]:
            datapoint = etree.SubElement(second, "dataPoint")
            etree.SubElement(datapoint, "y1").text = distance
            etree.SubElement(datapoint, "y2").text = amount

        datapoints = get_speciation_datapoints(root)

        assert len(datapoints) == 2
        assert datapoints[0]["independent-variables"][0]["name"] == "temperature"
        assert datapoints[1]["independent-variables"][0]["name"] == "distance"

    def test_datagroup_without_species(self):
        """A dataGroup with no species column is not a speciation datapoint."""
        root = self.build_root(
            [
                {"name": "distance", "id": "x1", "units": "cm"},
                {"name": "temperature", "id": "x2", "units": "K"},
            ],
            [{"x1": "1.0", "x2": "1600"}, {"x1": "2.0", "x2": "1500"}],
        )

        with pytest.raises(NotImplementedError) as excinfo:
            get_speciation_datapoints(root)
        assert "without composition columns cannot be a speciation datapoint" in str(excinfo.value)


@pytest.mark.usefixtures("mock_crossref_api")
class TestConvertReSpecTh:
    """ """

    @pytest.mark.parametrize("filename_xml", ["testfile_st.xml", "testfile_rcm.xml"])
    @pytest.mark.filterwarnings("ignore:Using DOI")
    def test_valid_conversion(self, filename_xml):
        """Test proper conversion of ReSpecTh files."""
        file_path = Path("tests") / filename_xml
        file_author = "Kyle Niemeyer"
        file_author_orcid = "0000-0003-4425-7097"
        # Skip all the validation because we know the test files are correct and we're not
        # testing the validation methods here
        properties = ReSpecTh_to_ChemKED(file_path, file_author, file_author_orcid, validate=False)
        c = ChemKED(dict_input=properties, skip_validation=True)

        # compare with ChemKED file of same experiment
        file_path = Path("tests") / Path(filename_xml).with_suffix(".yaml")
        c_true = ChemKED(yaml_file=file_path, skip_validation=True)

        assert c.file_authors[1]["name"] == file_author
        assert c.file_authors[1]["ORCID"] == file_author_orcid

        assert c.reference.detail == f"Converted from ReSpecTh XML file {filename_xml}"

        assert c.apparatus.kind == c_true.apparatus.kind
        assert c.experiment_type == c_true.experiment_type
        assert c.reference.doi == c_true.reference.doi
        assert len(c.datapoints) == len(c_true.datapoints)

    @pytest.mark.filterwarnings("ignore:Using DOI")
    def test_error_rcm_pressurerise(self):
        """Test for appropriate error if RCM file has pressure rise."""
        file_path = Path("tests") / "testfile_rcm.xml"

        # add pressure rise to common properties
        tree = etree.parse(file_path)
        root = tree.getroot()
        properties = root.find("commonProperties")
        prop = etree.SubElement(properties, "property")
        prop.set("name", "pressure rise")
        prop.set("units", "1/ms")
        prop_value = etree.SubElement(prop, "value")
        prop_value.text = "0.10"

        # write new file, and try to load
        et = etree.ElementTree(root)
        with TemporaryDirectory() as temp_dir:
            filename = Path(temp_dir) / "test.xml"
            et.write(filename, encoding="utf-8", xml_declaration=True)

            with pytest.raises(KeywordError) as excinfo:
                ReSpecTh_to_ChemKED(filename)
            assert "Pressure rise cannot be defined for RCM." in str(excinfo.value)

    @pytest.mark.filterwarnings("ignore:Using DOI")
    def test_error_st_volumehistory(self):
        """Test for appropriate error if shock tube file has volume history."""
        file_path = Path("tests") / "testfile_st.xml"

        tree = etree.parse(file_path)
        root = tree.getroot()
        datagroup = etree.SubElement(root, "dataGroup")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x1")
        prop.set("name", "time")
        prop.set("units", "s")
        prop = etree.SubElement(datagroup, "property")
        prop.set("id", "x2")
        prop.set("name", "volume")
        prop.set("units", "cm3")
        datapoint = etree.SubElement(datagroup, "dataPoint")
        x1 = etree.SubElement(datapoint, "x1")
        x1.text = str(0.0)
        x2 = etree.SubElement(datapoint, "x2")
        x2.text = str(10.0)

        # write new file, and try to load
        et = etree.ElementTree(root)
        with TemporaryDirectory() as temp_dir:
            filename = Path(temp_dir) / "test.xml"
            et.write(filename, encoding="utf-8", xml_declaration=True)

            with pytest.raises(KeywordError) as excinfo:
                ReSpecTh_to_ChemKED(filename)
            assert "Volume history cannot be defined for shock tube." in str(excinfo.value)

    @pytest.mark.filterwarnings("ignore:Using DOI")
    def test_author_orcid_no_name(self):
        """Test that passing an ORCID to the conversion without a name raises an error"""
        file_path = Path("tests") / "testfile_st.xml"
        file_author_orcid = "0000-0003-4425-7097"
        # Skip all the validation because we know the test files are correct and we're not
        # testing the validation methods here
        with pytest.raises(KeywordError) as e:
            ReSpecTh_to_ChemKED(file_path, file_author_orcid=file_author_orcid)
        assert "If file_author_orcid is specified, file_author must be as well" in str(e.value)

    @pytest.mark.filterwarnings("ignore:Using DOI")
    def test_file_author_only(self):
        """Test that passing the file author only works properly"""
        file_path = Path("tests") / "testfile_st.xml"
        file_author = "Kyle Niemeyer"
        # Skip all the validation because we know the test files are correct and we're not
        # testing the validation methods here
        properties = ReSpecTh_to_ChemKED(file_path, file_author, validate=False)
        c = ChemKED(dict_input=properties, skip_validation=True)

        assert c.file_authors[1]["name"] == file_author
        assert c.file_authors[1].get("ORCID", None) is None


@pytest.mark.usefixtures("mock_all_apis")
class TestConverterMain:
    """ """

    def test_conversion_main_xml_to_yaml(self):
        """Test detection in converter for xml->yaml"""
        file_path = Path("tests") / "testfile_st.xml"
        file_author = "Kyle E Niemeyer"
        file_author_orcid = "0000-0003-4425-7097"

        with TemporaryDirectory() as temp_dir:
            newfile = Path(temp_dir) / "test.yaml"
            with pytest.warns(UserWarning) as record:
                main(
                    [
                        "-i",
                        str(file_path),
                        "-o",
                        str(newfile),
                        "-fa",
                        file_author,
                        "-fo",
                        file_author_orcid,
                    ]
                )
            c = ChemKED(yaml_file=newfile)

        m = str(record.pop(UserWarning).message)
        assert m == "Using DOI to obtain reference information, rather than preferredKey."
        true_yaml = Path("tests") / "testfile_st.yaml"
        c_true = ChemKED(yaml_file=true_yaml)

        assert c.file_authors[0]["name"] == c_true.file_authors[0]["name"]
        assert c.file_authors[1]["name"] == file_author
        assert c.file_authors[1]["ORCID"] == file_author_orcid

        assert c.reference.detail == f"Converted from ReSpecTh XML file {Path(file_path).name}"

        assert c.apparatus.kind == c_true.apparatus.kind
        assert c.experiment_type == c_true.experiment_type
        assert c.reference.doi == c_true.reference.doi
        assert len(c.datapoints) == len(c_true.datapoints)

    def test_conversion_main_yaml_to_xml(self):
        """Test detection in converter for yaml->xml"""
        file_path = Path("tests") / "testfile_st.yaml"
        fa_name = "Kyle Niemeyer"
        fa_orcid = "0000-0003-4425-7097"

        with TemporaryDirectory() as temp_dir:
            newfile = Path(temp_dir) / "test.xml"
            main(["-i", str(file_path), "-o", str(newfile), "-fa", fa_name, "-fo", fa_orcid])

            assert Path(newfile).exists()

    def test_conversion_respth2ck_default_output(self):
        """Test respth2ck converter when used via command-line arguments."""
        file_path = Path("tests") / "testfile_st.xml"

        with TemporaryDirectory() as temp_dir:
            xml_file = copy(file_path, temp_dir)
            with pytest.warns(UserWarning) as record:
                respth2ck(["-i", str(xml_file)])

            newfile = Path(xml_file).with_suffix(".yaml")
            assert Path(newfile).exists()

        m = str(record.pop(UserWarning).message)
        assert m == "Using DOI to obtain reference information, rather than preferredKey."

    def test_conversion_respth2ck_with_output(self):
        """Test respth2ck converter when used via command-line arguments."""
        file_path = Path("tests") / "testfile_st.xml"

        with TemporaryDirectory() as temp_dir:
            newfile = Path(temp_dir) / "test.yaml"
            with pytest.warns(UserWarning) as record:
                respth2ck(["-i", str(file_path), "-o", str(newfile)])

            assert Path(newfile).exists()

        m = str(record.pop(UserWarning).message)
        assert m == "Using DOI to obtain reference information, rather than preferredKey."

    def test_conversion_ck2respth(self):
        """Test ck2respth converter when used via command-line arguments."""
        file_path = Path("tests") / "testfile_st.yaml"

        with TemporaryDirectory() as temp_dir:
            newfile = Path(temp_dir) / "test.xml"
            ck2respth(["-i", str(file_path), "-o", str(newfile)])

            assert Path(newfile).exists()

    def test_conversion_invalid_xml_xml(self):
        """Test converter main raises errors when two xml files are passed."""
        file_path = Path("tests") / "testfile_st.xml"

        with pytest.raises(KeywordError) as excinfo:
            main(["-i", str(file_path), "-o", "test.xml"])
        assert "Cannot convert .xml to .xml" in str(excinfo.value)

    def test_conversion_invalid_yaml_yaml(self):
        """Test converter main raises errors when two yaml files are passed."""
        file_path = Path("tests") / "testfile_st.yaml"

        with pytest.raises(KeywordError) as excinfo:
            main(["-i", str(file_path), "-o", "test.yaml"])
        assert "Cannot convert .yaml to .yaml" in str(excinfo.value)

    def test_conversion_invalid_file_type(self):
        """Test converter main raises errors when an invalid file extension is passed."""
        file_path = Path("tests") / "dataframe_st.csv"

        with pytest.raises(KeywordError) as excinfo:
            main(["-i", str(file_path), "-o", "test.py"])
        assert "Input/output args need to be .xml/.yaml" in str(excinfo.value)
