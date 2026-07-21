"""Offline validation helpers for chemical species identifiers."""

from rdkit import Chem, rdBase
from rdkit.Chem import inchi

INCHI_PREFIX = "InChI="


def normalize_inchi(value: str) -> str:
    """Return an InChI with the conventional ``InChI=`` prefix.

    ChemKED historically permits both complete InChIs and the prefixless form
    used by existing PyKED files, such as ``1S/H2/h1H``.
    """
    value = value.strip()
    if value.startswith(INCHI_PREFIX):
        return value
    return f"{INCHI_PREFIX}{value}"


def valid_inchi(value: str) -> bool:
    """Return whether *value* can be parsed as an InChI."""
    if not isinstance(value, str) or not value.strip():
        return False

    try:
        # RDKit may emit parser diagnostics for invalid input. Cerberus reports
        # the validation error, so avoid duplicating those diagnostics on stderr.
        with rdBase.BlockLogs():
            molecule = inchi.MolFromInchi(
                normalize_inchi(value),
                sanitize=True,
                removeHs=True,
                treatWarningAsError=False,
            )
    except (inchi.InchiReadWriteError, RuntimeError, ValueError):
        return False

    return molecule is not None


def valid_smiles(value: str) -> bool:
    """Return whether *value* can be parsed and sanitized as SMILES."""
    if not isinstance(value, str) or not value.strip():
        return False

    try:
        with rdBase.BlockLogs():
            molecule = Chem.MolFromSmiles(value.strip(), sanitize=True)
    except (RuntimeError, ValueError):
        return False

    return molecule is not None
