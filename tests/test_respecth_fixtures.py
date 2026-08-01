"""Validate structurally distinct ReSpecTh/ChemKED fixture pairs."""

import xml.etree.ElementTree as etree
from copy import deepcopy
from pathlib import Path

import pytest

from pyked.chemked import ChemKED
from pyked.converters import ReSpecTh_to_ChemKED
from pyked.validation import OurValidator, schema, yaml

DATA_DIR = Path(__file__).parent / "data" / "respecth"

# The apparatus kind is only stated in the article for files whose XML says just "flame", so
# those pairs were curated with the kind supplied by hand.
CASES = [
    (
        "laminar-burning-velocity",
        "x20014048",
        "laminar burning velocity measurement",
        (),
        "outwardly propagating spherical flame",
    ),
    (
        "laminar-burning-velocity",
        "x20004235",
        "laminar burning velocity measurement",
        (),
        "outwardly propagating spherical flame",
    ),
    (
        "laminar-burning-velocity",
        "x20100072",
        "laminar burning velocity measurement",
        (),
        None,
    ),
    (
        "speciation",
        "x00201001",
        "jet stirred reactor measurement",
        ("temperature",),
        None,
    ),
    (
        "speciation",
        "x60200017",
        "burner stabilized flame speciation measurement",
        ("distance",),
        None,
    ),
]


def load_pair(group, stem):
    """Load the XML tree and YAML mapping for a fixture pair."""
    fixture_dir = DATA_DIR / group
    xml_path = fixture_dir / f"{stem}.xml"
    yaml_path = fixture_dir / f"{stem}.yaml"
    with yaml_path.open() as stream:
        document = yaml.safe_load(stream)
    return etree.parse(xml_path).getroot(), document


def test_all_respecth_fixtures_are_paired():
    """Every checked-in source XML has exactly one converted YAML partner."""
    xml_pairs = {path.relative_to(DATA_DIR).with_suffix("") for path in DATA_DIR.rglob("*.xml")}
    yaml_pairs = {
        path.relative_to(DATA_DIR).with_suffix("") for path in DATA_DIR.rglob("*.yaml")
    }
    expected = {Path(group) / stem for group, stem, *_ in CASES}

    assert xml_pairs == yaml_pairs == expected


def as_comparable(value):
    """Reduce a converted value to something that compares across formatting choices.

    ReSpecTh writes numbers in whatever form the curator used, so ``6.500000e+001 cm/s`` and
    ``65 cm/s`` are the same measurement. The converter keeps the source text as written, which
    means comparing to a hand-authored fixture has to compare magnitudes, not strings.
    """
    if isinstance(value, dict):
        return {key: as_comparable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [as_comparable(item) for item in value]
    if isinstance(value, (int, float)):
        return round(float(value), 12)
    if isinstance(value, str):
        magnitude, _, units = value.partition(" ")
        try:
            return (round(float(magnitude), 12), units) if units else round(float(magnitude), 12)
        except ValueError:
            return value
    return value


@pytest.mark.parametrize(("group", "stem", "apparatus_kind"), [
    (group, stem, kind) for group, stem, _, _, kind in CASES
])
def test_converter_reproduces_fixture(group, stem, apparatus_kind):
    """Converting the source XML gives back the checked-in ChemKED file."""
    _, document = load_pair(group, stem)
    converted = ReSpecTh_to_ChemKED(
        str(DATA_DIR / group / f"{stem}.xml"), apparatus_kind=apparatus_kind
    )

    # The fixtures were written against a specific PyKED version
    converted.pop("chemked-version")
    document.pop("chemked-version")

    assert as_comparable(converted) == as_comparable(document)


@pytest.mark.parametrize(
    ("group", "stem", "source_type", "independent_variables", "apparatus_kind"), CASES
)
def test_respecth_pair_validates(
    group, stem, source_type, independent_variables, apparatus_kind
):
    """Each YAML conversion validates and retains its source structure."""
    root, document = load_pair(group, stem)

    assert root.findtext("experimentType").strip() == source_type
    assert document["reference"]["detail"].endswith(f"{stem}.xml")

    # DOI validation is an external service concern and is intentionally excluded
    # from this local schema-fixture test.
    local_document = deepcopy(document)
    local_document["reference"].pop("doi", None)
    validator = OurValidator(schema)
    assert validator.validate(local_document), validator.errors
    ChemKED(dict_input=local_document)

    for value in document.get("common-properties", {}).values():
        assert not (
            isinstance(value, list)
            and len(value) == 1
            and isinstance(value[0], dict)
        )

    if group == "laminar-burning-velocity":
        assert document["experiment-type"] == "laminar burning velocity measurement"
        source_points = root.find("dataGroup").findall("dataPoint")
        assert len(document["datapoints"]) == len(source_points)
    else:
        assert document["experiment-type"] == "speciation measurement"
        datapoint = document["datapoints"][0]
        names = tuple(item["name"] for item in datapoint["independent-variables"])
        assert names == independent_variables
        source_points = root.find("dataGroup").findall("dataPoint")
        assert all(
            len(profile["values"]) == len(source_points)
            for profile in datapoint["concentration-profiles"]
        )


def test_common_lbv_esd_is_attached_to_each_measured_value():
    """Shared ReSpecTh ESD metadata is distributed to LBV datapoints."""
    root, document = load_pair("laminar-burning-velocity", "x20014048")
    common_esd = root.find(
        "commonProperties/property[@name='evaluated standard deviation']"
    )

    assert common_esd is not None
    assert "laminar-burning-velocity" not in document["common-properties"]
    for datapoint in document["datapoints"]:
        metadata = datapoint["laminar-burning-velocity"][1]
        assert metadata["evaluated-standard-deviation-type"] == "relative"
        assert metadata["evaluated-standard-deviation"] == "0.039"


def test_pointwise_lbv_uncertainty_and_esd_are_combined():
    """Reported uncertainty and evaluated scatter coexist on each LBV value."""
    _, document = load_pair("laminar-burning-velocity", "x20100072")

    for datapoint in document["datapoints"]:
        metadata = datapoint["laminar-burning-velocity"][1]
        assert metadata["uncertainty-type"] == "absolute"
        assert "uncertainty" in metadata
        assert metadata["evaluated-standard-deviation-type"] == "absolute"
        assert "evaluated-standard-deviation" in metadata


@pytest.mark.parametrize("stem", ["x00201001", "x60200017"])
def test_speciation_esd_is_attached_to_measured_profile(stem):
    """Composition-referenced ESD metadata belongs to a measured profile."""
    _, document = load_pair("speciation", stem)
    profiles = document["datapoints"][0]["concentration-profiles"]

    assert any(
        "evaluated-standard-deviation" in profile.get("uncertainty", [{}])[0]
        for profile in profiles
    )


def test_auxiliary_profile_scenario():
    """The flame profile fixture carries an auxiliary temperature profile."""
    _, flame_profile = load_pair("speciation", "x60200017")

    auxiliary = flame_profile["datapoints"][0]["auxiliary-profiles"]
    assert auxiliary[0]["type"] == "temperature"
    assert auxiliary[0]["independent"]["name"] == "distance"
