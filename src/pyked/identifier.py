"""Validation helpers for chemical species and author identifiers.

Provides InChI/SMILES parsing checks backed by RDKit and ORCID lookups
against the ORCID public API.
"""

import httpx2 as httpx
from rdkit import Chem, rdBase
from rdkit.Chem import inchi

INCHI_PREFIX = "InChI="

headers = {"Accept": "application/json"}

def search_orcid(orcid):
    """
    Search the ORCID public API

    Specfically, return a dictionary with the personal details
    (name, etc.) of the person associated with the given ORCID

    Args:
        orcid (`str`): The ORCID to be searched

    Returns:
        `dict`: Dictionary with the JSON response from the API

    Raises:
        `~httpx.HTTPStatusError`: If the given ORCID cannot be found, an
            `~httpx.HTTPStatusError` is raised with status code 404
    """
    url = f"https://pub.orcid.org/v3.0/{orcid}/person"
    r = httpx.get(url, headers=headers)
    r.raise_for_status()
    return r.json()


"""Validation helpers for chemical species identifiers."""

def normalize_inchi(value: str):
    """Return an InChI with the conventional ``InChI=`` prefix.

    ChemKED historically permits both complete InChIs and the prefixless form
    used by existing PyKED files, such as ``1S/H2/h1H``.
    """
    value = value.strip()
    if value.startswith(INCHI_PREFIX):
        return value
    return f"{INCHI_PREFIX}{value}"


def valid_inchi(value: str):
    """Return whether *value* can be parsed as an InChI."""
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        with rdBase.BlockLogs():
            molecule = inchi.MolFromInchi(
                normalize_inchi(value)
            )
    except (inchi.InchiReadWriteError, RuntimeError, ValueError):
        return False
    return molecule is not None


def valid_smiles(value: str):
    """Return whether *value* can be parsed and sanitized as SMILES."""
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        with rdBase.BlockLogs():
            molecule = Chem.MolFromSmiles(value.strip(), sanitize=True)
    except (RuntimeError, ValueError):
        return False
    return molecule is not None
