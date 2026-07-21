"""Tests for offline validation of chemical species identifiers."""

import pytest

from pyked.species_validation import normalize_inchi, valid_inchi, valid_smiles
from pyked.validation import OurValidator, schema


@pytest.mark.parametrize(
    "value",
    [
        "1S/H2/h1H",
        "InChI=1S/CH4/h1H4",
        "1S/O2/c1-2",
        "1S/Ar",
    ],
)
def test_valid_inchi(value):
    assert valid_inchi(value)


@pytest.mark.parametrize("value", ["", "not-an-inchi", "1S/", "InChI=invalid"])
def test_invalid_inchi(value):
    assert not valid_inchi(value)


@pytest.mark.parametrize("value", ["N#N", "[O][O]", "c1ccccc1", "[NH4+]"])
def test_valid_smiles(value):
    assert valid_smiles(value)


@pytest.mark.parametrize("value", ["", "not a smiles", "C1CC", "C(C", "[CH5]"])
def test_invalid_smiles(value):
    assert not valid_smiles(value)


def test_normalize_inchi_preserves_complete_identifier():
    value = "InChI=1S/CH4/h1H4"
    assert normalize_inchi(value) == value


def test_normalize_inchi_adds_prefix():
    assert normalize_inchi("1S/CH4/h1H4") == "InChI=1S/CH4/h1H4"


def _composition(identifier_key, identifier_value):
    """Return a minimal composition using one species identifier."""
    return {
        "kind": "mole fraction",
        "species": [
            {
                "species-name": "test species",
                identifier_key: identifier_value,
                "amount": [1.0],
            }
        ],
    }


@pytest.mark.parametrize(
    "identifier_key, identifier_value",
    [
        ("InChI", "1S/H2/h1H"),
        ("InChI", "InChI=1S/CH4/h1H4"),
        ("SMILES", "N#N"),
    ],
)
def test_composition_schema_accepts_valid_identifier(identifier_key, identifier_value):
    composition_rule = schema["common-properties"]["schema"]["composition"]
    validator = OurValidator({"composition": composition_rule})

    assert validator.validate({"composition": _composition(identifier_key, identifier_value)})


@pytest.mark.parametrize(
    "identifier_key, identifier_value, message",
    [
        ("InChI", "not-an-inchi", "Invalid InChI string"),
        ("SMILES", "C1CC", "Invalid SMILES string"),
    ],
)
def test_composition_schema_rejects_invalid_identifier(identifier_key, identifier_value, message):
    composition_rule = schema["common-properties"]["schema"]["composition"]
    validator = OurValidator({"composition": composition_rule})

    assert not validator.validate({"composition": _composition(identifier_key, identifier_value)})
    assert message in str(validator.errors)


def test_composition_schema_defines_identifier_validation_rules():
    species_schema = schema["common-properties"]["schema"]["composition"]["schema"]["species"][
        "schema"
    ]["schema"]

    assert species_schema["InChI"]["isvalid_inchi"] is True
    assert species_schema["SMILES"]["isvalid_smiles"] is True
