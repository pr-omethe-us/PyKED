"""Module with converters from other formats."""

# Standard libraries
import re
import xml.etree.ElementTree as etree
from argparse import ArgumentParser
from itertools import chain
from pathlib import Path
from typing import Any
from warnings import warn

import habanero
import httpx2 as httpx
import pint

from . import chemked
from ._version import __version__

# Local imports
from .validation import _normalize_unit_str, crossref_api, property_units, yaml
from .validation import units as unit_registry

# Valid properties for ReSpecTh dataGroup
datagroup_properties = [
    "temperature",
    "pressure",
    "ignition delay",
    "pressure rise",
]
"""`list`: Valid properties for a ReSpecTh dataGroup"""

experiment_types = {
    "ignition delay measurement": "ignition delay",
    "laminar burning velocity measurement": "laminar burning velocity measurement",
    # ReSpecTh 1.x name for the same measurement
    "laminar flame speed measurement": "laminar burning velocity measurement",
    # ReSpecTh keeps four separate speciation types that ChemKED represents as one
    "concentration time profile measurement": "speciation measurement",
    "outlet concentration measurement": "speciation measurement",
    "jet stirred reactor measurement": "speciation measurement",
    "burner stabilized flame speciation measurement": "speciation measurement",
}
"""`dict`: ReSpecTh ``experimentType`` mapped to ChemKED ``experiment-type``"""

apparatus_kinds = {
    "shock tube": "shock tube",
    "rapid compression machine": "rapid compression machine",
    "flow reactor": "flow reactor",
    "jet stirred reactor": "jet stirred reactor",
    "burner stabilized flame": "burner stabilized flame",
    "counterflow twin flame": "counterflow twin flame",
    "heat flux burner": "heat flux burner",
    "flame cone method": "bunsen burner",
    "bunsen burner": "bunsen burner",
    "outwardly propagating spherical flame": "outwardly propagating spherical flame",
}
"""`dict`: ReSpecTh ``apparatus/kind`` mapped to ChemKED ``apparatus.kind``

Only names that identify the apparatus on their own. The vessel material that ReSpecTh appends in
parentheses, as in ``flow reactor (quartz)``, is stripped before lookup because ChemKED has no
field for it.
"""

apparatus_kinds_by_experiment = {
    # "stirred reactor" says the mixture is stirred, not how, so on its own it does not say which
    # stirred reactor was used. ReSpecTh names the apparatus a second time in the experiment type,
    # and that is what identifies it.
    ("stirred reactor", "jet stirred reactor measurement"): "jet stirred reactor",
}
"""`dict`: (ReSpecTh ``apparatus/kind``, ``experimentType``) mapped to ChemKED ``apparatus.kind``

For kinds that name how a reactor is operated rather than which apparatus it is, and so can only
be mapped when the experiment type corroborates them.
"""

flame_modes = {
    "opf": "outwardly propagating spherical flame",
    "spherical": "outwardly propagating spherical flame",
    "constant volume combustion chamber": "outwardly propagating spherical flame",
    "hfm": "heat flux burner",
    "heat flux burner": "heat flux burner",
    "ctf": "counterflow twin flame",
    "counterflow": "counterflow twin flame",
    "twin flat": "counterflow twin flame",
    "fcm": "bunsen burner",
    "flame cone method": "bunsen burner",
    "burner-stabilized": "burner stabilized flame",
    "burner stabilized": "burner stabilized flame",
}
"""`dict`: ReSpecTh ``apparatus/mode`` mapped to ChemKED ``apparatus.kind``

Only consulted when ``apparatus/kind`` is the generic ``flame``. Modes that only describe the
mixture or flow, such as ``premixed`` and ``laminar``, are absent on purpose: they do not identify
a burner, so a file carrying nothing else cannot be converted without curation.
"""

common_property_fields = {
    "temperature": "temperature",
    "pressure": "pressure",
    "ignition delay": "ignition-delay",
    "pressure rise": "pressure-rise",
    "equivalence ratio": "equivalence-ratio",
    "laminar burning velocity": "laminar-burning-velocity",
    "volume": "reactor-volume",
    "residence time": "residence-time",
    "flow rate": "flow-rate",
    "environment temperature": "environment-temperature",
    "global heat exchange coefficient": "global-heat-exchange-coefficient",
    "exchange area": "exchange-area",
    "reactor length": "reactor-length",
    "reactor diameter": "reactor-diameter",
    "pressure in reference state": "pressure-in-reference-state",
    "temperature in reference state": "temperature-in-reference-state",
    "volumetric flow rate in reference state": "volumetric-flow-in-reference-state",
}
"""`dict`: ReSpecTh ``commonProperties`` property name mapped to ChemKED field name"""

independent_variables = {
    "temperature": "temperature",
    "residence time": "residence-time",
    "distance": "distance",
    "time": "time",
    "equivalence ratio": "equivalence-ratio",
    "initial composition": "initial-composition",
    "pressure": "pressure",
}
"""`dict`: ReSpecTh dataGroup property name mapped to a speciation independent-variable name"""

auxiliary_profile_types = ["temperature", "pressure", "volume", "velocity"]
"""`list`: Quantities that a speciation datapoint can carry as an auxiliary profile"""

auxiliary_axes = {"distance": "distance", "time": "time", "residence-time": "time"}
"""`dict`: Speciation axis name mapped to the axis name of an auxiliary profile against it

``auxiliary-profiles.independent.name`` is a coordinate along the reactor or flame rather than the
full set of names ``independent-variables`` allows, and a residence time is a time coordinate.
"""

ignition_targets = {"P": "pressure", "T": "temperature", "OHEX": "OH*", "CHEX": "CH*"}
"""`dict`: ReSpecTh ``ignitionType`` target abbreviations mapped to ChemKED target names"""

ignition_types = {
    "baseline max intercept from d/dt": "d/dt max extrapolated",
    "baseline min intercept from d/dt": "d/dt min extrapolated",
}
"""`dict`: ReSpecTh ``ignitionType`` type names mapped to ChemKED type names"""

ignition_target_values = [
    "temperature",
    "pressure",
    "OH",
    "OH*",
    "CH",
    "CH*",
    "NH3",
    "CO2",
    "N2O",
    "CH4",
    "CO",
    "H2O",
    "C2",
    "O",
    "CH3OH",
    "CH3",
    "O2",
    "soot",
]
"""`list`: Ignition targets the ChemKED schema allows

Kept in step with ``ignition-type.target`` in ``ignition_delay_schema.yaml``.
"""

ignition_type_values = [
    "d/dt max",
    "max",
    "1/2 max",
    "min",
    "d/dt max extrapolated",
    "d/dt min extrapolated",
    "relative concentration",
    "d/dt second max",
    "concentration",
    "relative increase",
]
"""`list`: Ignition types the ChemKED schema allows

Kept in step with ``ignition-type.type`` in ``ignition_delay_schema.yaml``.
"""

composition_units = {
    "mole fraction": ("mole fraction", 1.0, None),
    "mass fraction": ("mass fraction", 1.0, None),
    "mole percent": ("mole percent", 1.0, None),
    # ReSpecTh writes bare "percent" and misspells "mole fraction" in part of the corpus
    "percent": ("mole percent", 1.0, "Assuming percent in composition means mole percent"),
    "mole faction": (
        "mole fraction",
        1.0,
        'Assuming misspelled composition units "mole faction" mean mole fraction',
    ),
    "ppm": (
        "mole fraction",
        1.0e-6,
        "Assuming molar ppm in composition and converting to mole fraction",
    ),
    "ppb": (
        "mole fraction",
        1.0e-9,
        "Assuming molar ppb in composition and converting to mole fraction",
    ),
    # Concentrations, which the ChemKED composition schema accepts as their own kinds
    "mol/cm3": ("mol/cm3", 1.0, None),
    "mol/m3": ("mol/m3", 1.0, None),
    "mol/dm3": ("mol/dm3", 1.0, None),
    "mol/L": ("mol/L", 1.0, None),
}
"""`dict`: ReSpecTh composition units mapped to (ChemKED kind, scale factor, warning)"""

dimensionless_units = ["unitless", "[-]", "dimensionless", "-", ""]
"""`list`: Ways ReSpecTh spells a dimensionless quantity"""

unit_aliases = {"Torr": "torr"}
"""`dict`: ReSpecTh unit strings that Pint spells differently"""


def normalize_units(unit_str):
    """Convert a ReSpecTh unit string into one Pint can parse.

    Args:
        unit_str (`str`): Unit string as written in the ReSpecTh file

    Returns:
        `str`: Equivalent unit string in Pint syntax
    """
    if unit_str is None or unit_str.strip().lower() in dimensionless_units:
        return "dimensionless"

    unit_str = unit_aliases.get(unit_str.strip(), unit_str)

    # _normalize_unit_str expects a magnitude, and turns "kg m-2 s-1" into Pint syntax
    return _normalize_unit_str(f"1.0 {unit_str.strip()}").split(" ", 1)[1]


def value_with_units(value, unit_str):
    """Build a ChemKED value-with-units string from ReSpecTh text.

    Args:
        value (`str`): Value as written in the ReSpecTh file
        unit_str (`str`): Units as written in the ReSpecTh file

    Returns:
        `str`: Value and units joined in a form the ChemKED schema accepts
    """
    return f"{value.strip()} {normalize_units(unit_str)}"


def check_units(name, field, unit_str):
    """Ensure ReSpecTh units are dimensionally consistent with the ChemKED field.

    Args:
        name (`str`): ReSpecTh property name, used in the error message
        field (`str`): ChemKED field name, used to look up the expected units
        unit_str (`str`): Units as written in the ReSpecTh file

    Raises:
        `KeywordError`: If the units cannot be parsed or are incompatible with the field
    """
    if field not in property_units:
        return

    try:
        quantity = 1.0 * unit_registry(normalize_units(unit_str))
        quantity.to(property_units[field])
    except (pint.DimensionalityError, pint.UndefinedUnitError, TypeError) as err:
        raise KeywordError("units incompatible for property " + name) from err


class ParseError(Exception):
    """Base class for errors."""

    pass


class KeywordError(ParseError):
    """Raised for errors in keyword parsing."""

    def __init__(self, *keywords):
        self.keywords = keywords

    def __str__(self):
        return repr(f"Error: {self.keywords[0]}.")


class MissingElementError(KeywordError):
    """Raised for missing required elements."""

    def __str__(self):
        return repr(f"Error: required element {self.keywords[0]} is missing.")


class MissingAttributeError(KeywordError):
    """Raised for missing required attribute."""

    def __str__(self):
        return repr(
            f"Error: required attribute {self.keywords[0]} of {self.keywords[1]} is missing."
        )


def get_file_metadata(root):
    """Read and parse ReSpecTh XML file metadata (file author, version, etc.)

    Args:
        root (`~xml.etree.ElementTree.Element`): Root of ReSpecTh XML file

    Returns:
        properties (`dict`): Dictionary with file metadata
    """
    properties: dict[str, Any] = {}

    file_author = getattr(root.find("fileAuthor"), "text", False)
    # Test for missing attribute or empty string in the same statement
    if not file_author:
        raise MissingElementError("fileAuthor")
    else:
        properties["file-authors"] = [{"name": file_author}]

    # Default version is 0 for the ChemKED file
    properties["file-version"] = 0

    # Default ChemKED version
    properties["chemked-version"] = __version__

    return properties


def get_reference_details(elem):
    """Read bibliographic details written directly in a ReSpecTh 2.x ``bibliographyLink``.

    ReSpecTh 2.x records the reference in child elements rather than the ``doi`` and
    ``preferredKey`` attributes used by 1.x, so the citation can be built without a DOI lookup.

    Args:
        elem (`~xml.etree.ElementTree.Element`): The ``bibliographyLink`` element

    Returns:
        `dict`: Reference information, empty if the element carries no usable ``details``
    """
    details = elem.find("details")
    if details is None:
        return {}

    reference = {}
    year = details.findtext("year")
    if year is None:
        # Year is required by the ChemKED schema, so details without one are not usable
        return {}
    reference["year"] = int(year.strip())

    authors = details.findtext("author")
    if authors is None:
        return {}

    # ReSpecTh writes authors BibTeX style: "Family, Given and Family, Given"
    reference["authors"] = []
    for author in authors.split(" and "):
        name = author.strip()
        if "," in name:
            family, _, given = name.partition(",")
            name = " ".join([given.strip(), family.strip()])
        reference["authors"].append({"name": name})

    journal = details.findtext("journal")
    if journal is not None:
        reference["journal"] = journal.strip()

    volume = details.findtext("volume")
    if volume is not None and volume.strip().isdigit():
        reference["volume"] = int(volume.strip())

    pages = details.findtext("pages")
    if pages is not None:
        # ReSpecTh writes page ranges with en dashes or doubled hyphens; ChemKED uses one hyphen
        reference["pages"] = re.sub(r"[-–—]+", "-", pages.strip())

    return reference


def get_reference(root):
    """Read reference info from root of ReSpecTh XML file.

    Args:
        root (`~xml.etree.ElementTree.Element`): Root of ReSpecTh XML file

    Returns:
        properties (`dict`): Dictionary with reference information
    """
    reference = {}
    elem = root.find("bibliographyLink")
    if elem is None:
        raise MissingElementError("bibliographyLink")

    # Try to get reference info via DOI, fall back on preferredKey if necessary.
    ref_doi = elem.get("doi", None)
    ref_key = elem.get("preferredKey", None)

    # ReSpecTh 2.x keeps the same information in child elements
    if ref_doi is None:
        ref_doi = getattr(elem.find("referenceDOI"), "text", None)
        if ref_doi is not None:
            ref_doi = ref_doi.strip() or None
    if ref_key is None:
        ref_key = getattr(elem.find("description"), "text", None)
        if ref_key is not None:
            ref_key = " ".join(ref_key.split()) or None

    details = get_reference_details(elem)
    if details:
        # The file states the reference itself, so no DOI lookup is needed
        reference.update(details)
        if ref_doi is not None:
            reference["doi"] = ref_doi
        return reference

    if ref_doi is not None:
        try:
            ref = crossref_api.works(ids=ref_doi)["message"]
        except (
            httpx.HTTPStatusError,
            habanero.RequestError,
            httpx.ConnectError,
        ):
            if ref_key is None:
                raise KeywordError("DOI not found and preferredKey attribute not set") from None
            else:
                warn(
                    "Missing doi attribute in bibliographyLink or lookup failed. "
                    'Setting "detail" key as a fallback; please update to the appropriate fields.'
                )
                reference["detail"] = ref_key
                if reference["detail"][-1] != ".":
                    reference["detail"] += "."
        else:
            if ref_key is not None:
                warn("Using DOI to obtain reference information, rather than preferredKey.")
            reference["doi"] = ref_doi
            # Now get elements of the reference data
            # Assume that the reference returned by the DOI lookup always has a container-title
            reference["journal"] = ref.get("container-title")[0]
            ref_year = ref.get("published-print") or ref.get("published-online")
            reference["year"] = int(ref_year["date-parts"][0][0])
            reference["volume"] = int(ref.get("volume"))
            reference["pages"] = ref.get("page")
            reference["authors"] = []
            for author in ref["author"]:
                auth = {}
                auth["name"] = " ".join([author["given"], author["family"]])
                # Add ORCID if available
                orcid = author.get("ORCID")
                if orcid:
                    auth["ORCID"] = orcid[orcid.rfind("/") + 1 :]
                reference["authors"].append(auth)

    elif ref_key is not None:
        warn(
            "Missing doi attribute in bibliographyLink. "
            'Setting "detail" key as a fallback; please update to the appropriate fields.'
        )
        reference["detail"] = ref_key
        if reference["detail"][-1] != ".":
            reference["detail"] += "."
    else:
        # Need one of DOI or preferredKey
        raise MissingAttributeError("preferredKey", "bibliographyLink")

    return reference


def get_apparatus_kind(root, experiment_type=None):
    """Map the ReSpecTh apparatus onto a ChemKED apparatus kind.

    ReSpecTh often gives the generic kind ``flame`` and leaves the configuration to one or more
    ``mode`` elements, so both are consulted. Modes that ReSpecTh flags as uncertain with a
    trailing question mark are ignored.

    Args:
        root (`~xml.etree.ElementTree.Element`): Root of ReSpecTh XML file
        experiment_type (`str`, optional): The ReSpecTh ``experimentType``, which names the
            apparatus a second time for kinds that do not identify it on their own

    Returns:
        `str`: The ChemKED ``apparatus.kind``

    Raises:
        `MissingElementError`: If ``apparatus/kind`` is absent or empty
        `NotImplementedError`: If the apparatus cannot be identified from the file alone
    """
    kind = getattr(root.find("apparatus/kind"), "text", False)
    # Test for missing attribute or empty string
    if not kind:
        raise MissingElementError("apparatus/kind")

    kind = " ".join(kind.split()).lower()
    # ReSpecTh appends the vessel material, as in "flow reactor (quartz)", which ChemKED drops
    bare_kind = kind.split("(")[0].strip()

    if bare_kind in apparatus_kinds:
        return apparatus_kinds[bare_kind]

    corroborated = apparatus_kinds_by_experiment.get((bare_kind, experiment_type))
    if corroborated is not None:
        return corroborated

    modes = [
        " ".join(mode.text.split()).lower()
        for mode in root.iterfind("apparatus/mode")
        if mode.text and not mode.text.strip().endswith("?")
    ]
    matches = {flame_modes[mode] for mode in modes if mode in flame_modes}
    if len(matches) == 1:
        return matches.pop()
    if len(matches) > 1:
        raise NotImplementedError(
            f"{kind} apparatus has conflicting modes {sorted(modes)}, "
            f"which describe more than one apparatus kind: {sorted(matches)}"
        )

    raise NotImplementedError(
        f"{kind} apparatus with modes {sorted(modes)} does not identify a ChemKED apparatus "
        "kind; pass apparatus_kind to set it explicitly"
    )


def get_experiment_kind(root, apparatus_kind=None):
    """Read the experiment type and apparatus from the root of a ReSpecTh XML file.

    Args:
        root (`~xml.etree.ElementTree.Element`): Root of ReSpecTh XML file
        apparatus_kind (`str`, optional): ChemKED apparatus kind to use instead of the one
            derived from the file, for files whose apparatus is only known from the article

    Returns:
        properties (`dict`): Dictionary with experiment type and apparatus information.
    """
    properties: dict[str, Any] = {}
    experiment_type = getattr(root.find("experimentType"), "text", None)
    if experiment_type is None:
        raise MissingElementError("experimentType")

    # ReSpecTh 1.x capitalizes the type while 2.x does not
    experiment_type = " ".join(experiment_type.split())
    if experiment_type.lower() in experiment_types:
        properties["experiment-type"] = experiment_types[experiment_type.lower()]
    else:
        raise NotImplementedError(experiment_type + " not (yet) supported")

    properties["apparatus"] = {"kind": "", "institution": "", "facility": ""}
    if apparatus_kind is not None:
        # Still require the element to be present, so a malformed file is not silently accepted
        if not getattr(root.find("apparatus/kind"), "text", False):
            raise MissingElementError("apparatus/kind")
        properties["apparatus"]["kind"] = apparatus_kind
    else:
        properties["apparatus"]["kind"] = get_apparatus_kind(root, experiment_type.lower())

    return properties


def get_composition_amount(units, value, capitalize=False):
    """Convert a ReSpecTh composition amount to a ChemKED amount and kind.

    Args:
        units (`str`): Composition units as written in the ReSpecTh file
        value (`str`): Amount as written in the ReSpecTh file
        capitalize (`bool`, optional): Capitalize the units error message, matching the wording
            used for common properties

    Returns:
        `tuple`: The amount as a `float` and the ChemKED composition kind

    Raises:
        `KeywordError`: If the composition units are not supported
    """
    if units not in composition_units:
        message = (
            "omposition units need to be one of: mole fraction, "
            "mass fraction, mole percent, percent, ppm, or ppb."
        )
        raise KeywordError(("C" if capitalize else "c") + message)

    kind, factor, message = composition_units[units]
    if message is not None:
        warn(message)

    return float(value) * factor, kind


def reconcile_composition_kind(species, kinds):
    """Settle on one composition kind for a set of species amounts.

    ReSpecTh files sometimes state one species in mole percent and another in mole fraction. That
    pair converts exactly, so the amounts are put on a mole fraction basis; any other mixture is
    an error because ChemKED stores a single kind per composition.

    Args:
        species (`list`): ChemKED species dictionaries, modified in place
        kinds (`list`): The composition kind read for each species, in the same order

    Returns:
        `str`: The single ChemKED composition kind

    Raises:
        `KeywordError`: If the kinds cannot be reconciled
    """
    distinct = set(kinds)
    if len(distinct) <= 1:
        return kinds[0] if kinds else None

    if distinct <= {"mole fraction", "mole percent"}:
        warn("Composition mixes mole fraction and mole percent; converting to mole fraction")
        for spec, kind in zip(species, kinds):
            if kind == "mole percent":
                spec["amount"][0] *= 0.01
        return "mole fraction"

    inconsistent = next(kind for kind in kinds if kind != kinds[0])
    raise KeywordError("composition units " + inconsistent + " not consistent with " + kinds[0])


def get_composition(elem, capitalize=False):
    """Read a ReSpecTh ``initial composition`` property into a ChemKED composition.

    Args:
        elem (`~xml.etree.ElementTree.Element`): The ``initial composition`` property element
        capitalize (`bool`, optional): Capitalize the units error message

    Returns:
        `dict`: ChemKED composition with ``species`` and ``kind``

    Raises:
        `KeywordError`: If the composition units are unsupported or inconsistent
    """
    composition: dict[str, Any] = {"species": [], "kind": None}
    kinds = []

    for child in elem.iter("component"):
        spec = {}
        spec["species-name"] = child.find("speciesLink").attrib["preferredKey"]

        # use InChI for unique species identifier (if present)
        try:
            spec["InChI"] = child.find("speciesLink").attrib["InChI"]
        except KeyError:
            # TODO: add InChI validator/search
            warn("Missing InChI for species " + spec["species-name"])
            pass

        amount = child.find("amount")
        value, units = get_composition_amount(
            amount.attrib["units"], amount.text, capitalize=capitalize
        )
        spec["amount"] = [value]

        composition["species"].append(spec)
        kinds.append(units)

    composition["kind"] = reconcile_composition_kind(composition["species"], kinds)

    return composition


def get_common_properties(root):
    """Read common properties from root of ReSpecTh XML file.

    Uncertainty and evaluated standard deviation properties are skipped here because they are
    metadata about another quantity rather than quantities in their own right; `get_value_metadata`
    collects them so they can be attached to whatever they describe.

    Args:
        root (`~xml.etree.ElementTree.Element`): Root of ReSpecTh XML file

    Returns:
        properties (`dict`): Dictionary with common properties
    """
    properties: dict[str, Any] = {}

    for elem in root.iterfind("commonProperties/property"):
        name = " ".join(elem.attrib["name"].split())

        if name == "initial composition":
            properties["composition"] = get_composition(elem, capitalize=True)

        elif name in ["uncertainty", "evaluated standard deviation"]:
            continue

        elif name in common_property_fields:
            field = common_property_fields[name]
            units = elem.attrib["units"]
            check_units(name, field, units)
            properties[field] = [value_with_units(elem.find("value").text, units)]

        else:
            raise KeywordError("Property " + name + " not supported as common property")

    return properties


def get_value_metadata(root):
    """Read uncertainty and evaluated standard deviation common properties.

    ReSpecTh states these as properties in their own right, tied by the ``reference`` attribute
    (and a ``speciesLink`` when the reference is a composition) to the quantity they describe.
    ChemKED instead stores them alongside that quantity, so they are collected separately here
    and attached by `attach_value_metadata`.

    Args:
        root (`~xml.etree.ElementTree.Element`): Root of ReSpecTh XML file

    Returns:
        `list`: One `dict` per uncertainty or evaluated standard deviation property

    Raises:
        `KeywordError`: If a property is missing the ``reference`` or ``kind`` attribute
    """
    metadata = []

    for elem in root.iterfind("commonProperties/property"):
        name = " ".join(elem.attrib["name"].split())
        if name not in ["uncertainty", "evaluated standard deviation"]:
            continue

        if "reference" not in elem.attrib:
            raise MissingAttributeError("reference", name)
        if "kind" not in elem.attrib:
            raise MissingAttributeError("kind", name)

        species_link = elem.find("speciesLink")
        reference, species = resolve_reference(root, " ".join(elem.attrib["reference"].split()))
        metadata.append(
            {
                "name": name,
                "reference": reference,
                "kind": elem.attrib["kind"],
                "units": elem.attrib.get("units"),
                "sourcetype": elem.attrib.get("sourcetype"),
                "method": elem.attrib.get("method"),
                "value": elem.find("value").text,
                "species": (
                    species_link.attrib["preferredKey"] if species_link is not None else species
                ),
            }
        )

    return metadata


def resolve_reference(root, reference):
    """Work out which quantity a ReSpecTh uncertainty refers to.

    The ``reference`` attribute usually names a property, but part of the corpus points at a
    column by its ``label`` or its ``id`` instead, as in ``reference="Sl"`` for the column
    labelled ``Sl`` or ``reference="x1"`` for the first column.

    Args:
        root (`~xml.etree.ElementTree.Element`): Root of ReSpecTh XML file
        reference (`str`): The ``reference`` attribute as written

    Returns:
        `tuple`: The property name referred to, and the species it belongs to if the referenced
        property names one, otherwise `None`
    """
    known = [*common_property_fields, "composition", "initial composition"]
    if reference in known:
        return reference, None

    properties = chain(
        root.iterfind("commonProperties/property"), root.iterfind("dataGroup/property")
    )
    for prop in properties:
        if reference not in [prop.get("label"), prop.get("id")]:
            continue
        name = " ".join(prop.attrib["name"].split())
        if name in ["uncertainty", "evaluated standard deviation"]:
            # An uncertainty of an uncertainty is not something ChemKED records
            continue
        link = prop.find("speciesLink")
        return name, (link.attrib["preferredKey"] if link is not None else None)

    return reference, None


def format_value_metadata(item, factor=None, numeric=False):
    """Turn one ReSpecTh uncertainty descriptor into ChemKED metadata keys.

    Args:
        item (`dict`): Descriptor from `get_value_metadata` or a dataGroup metadata column
        factor (`float`, optional): Scale factor to apply, used when the described quantity is a
            composition whose units were converted, e.g. ppm to mole fraction
        numeric (`bool`, optional): Store the value as a number rather than as the text of the
            file. Composition amounts and profile values are plain numbers with the units stated
            elsewhere, so an uncertainty about one of them is a number too.

    Returns:
        `dict`: ChemKED uncertainty or evaluated standard deviation metadata

    Raises:
        `KeywordError`: If the ``kind`` attribute is neither absolute nor relative
    """
    if item["kind"] not in ["absolute", "relative"]:
        raise KeywordError(
            item["kind"] + " not a valid kind for " + item["name"] + "; use absolute or relative"
        )

    prefix = "uncertainty" if item["name"] == "uncertainty" else "evaluated-standard-deviation"
    metadata = {f"{prefix}-type": item["kind"]}

    # ReSpecTh states one-sided uncertainties with the bound attribute
    bounds = {"plusminus": prefix, "upper": "upper-uncertainty", "lower": "lower-uncertainty"}
    if prefix == "uncertainty":
        key = bounds.get(item.get("bound") or "plusminus", prefix)
    else:
        key = prefix

    value = item["value"].strip()
    if numeric:
        # A relative value is already a fraction, so only an absolute one is rescaled
        scale = factor if (factor is not None and item["kind"] == "absolute") else 1.0
        metadata[key] = float(value) * scale
    elif item["kind"] == "relative":
        # Relative values are fractions of the quantity, so they carry no units
        metadata[key] = value
    else:
        metadata[key] = value_with_units(value, item["units"])

    if item.get("sourcetype"):
        metadata[f"{prefix}-sourcetype"] = item["sourcetype"]

    # The ChemKED schema records a method for evaluated standard deviations only
    if item.get("method") and prefix == "evaluated-standard-deviation":
        metadata[f"{prefix}-method"] = item["method"]

    return metadata


def merge_value_metadata(value, metadata):
    """Add uncertainty metadata to a ChemKED value list, in place.

    Args:
        value (`list`): ChemKED value list, either ``[value]`` or ``[value, metadata]``
        metadata (`dict`): Metadata keys from `format_value_metadata`
    """
    if len(value) > 1:
        value[1].update(metadata)
    else:
        value.append(dict(metadata))


def attach_value_metadata(properties, metadata):
    """Attach uncertainty metadata to the quantities it describes.

    ReSpecTh states uncertainties as standalone properties that point at another quantity, so each
    one is attached to that quantity wherever it ended up: on every datapoint, on the shared
    common property, or on a species profile.

    Args:
        properties (`dict`): Partially built ChemKED dictionary, with datapoints
        metadata (`list`): Descriptors from `get_value_metadata`
    """
    for item in metadata:
        reference = item["reference"]
        datapoints = properties["datapoints"]

        if reference in ["composition", "initial composition"]:
            attached = False
            factor = composition_units.get(item["units"], (None, None, None))[1]

            if reference == "composition":
                # A speciation datapoint keeps its measured species in profiles
                for datapoint in datapoints:
                    for profile in datapoint.get("concentration-profiles", []):
                        if item["species"] in (None, profile["species-name"]):
                            profile.setdefault("uncertainty", [{}])
                            profile["uncertainty"][0].update(
                                format_value_metadata(item, factor=factor, numeric=True)
                            )
                            attached = True

            if not attached:
                # Otherwise it describes the amount of that species in the mixture, which may be
                # stated per datapoint or once for the whole file
                compositions = [dp["composition"] for dp in datapoints if "composition" in dp]
                shared = properties["common-properties"].get("composition")
                if shared is not None:
                    compositions.append(shared)

                for composition in compositions:
                    for species in composition["species"]:
                        if item["species"] == species["species-name"]:
                            merge_value_metadata(
                                species["amount"],
                                format_value_metadata(item, factor=factor, numeric=True),
                            )
                            attached = True
        else:
            field = common_property_fields.get(reference, reference.replace(" ", "-"))
            attached = False
            for datapoint in datapoints:
                if field in datapoint:
                    merge_value_metadata(datapoint[field], format_value_metadata(item))
                    attached = True

            if not attached and field in properties["common-properties"]:
                merge_value_metadata(
                    properties["common-properties"][field], format_value_metadata(item)
                )
                attached = True

        if not attached:
            warn(
                f"Dropping {item['name']} that refers to {reference}, "
                "which has no value in this file"
            )


def get_datagroup_columns(dataGroup, root=None):
    """Describe the columns of a ReSpecTh dataGroup.

    Args:
        dataGroup (`~xml.etree.ElementTree.Element`): A ``dataGroup`` element
        root (`~xml.etree.ElementTree.Element`, optional): Root of the file, used to resolve an
            uncertainty that points at a column by its label or id

    Returns:
        `list`: One `dict` per column, in file order, with the ReSpecTh name, units, id, the
        species it refers to if any, and the uncertainty attributes if it is a metadata column

    Raises:
        `MissingElementError`: If the dataGroup declares no properties
        `MissingAttributeError`: If a metadata column has no ``reference`` or ``kind``
    """
    columns = []
    for prop in dataGroup.findall("property"):
        name = " ".join(prop.attrib["name"].split())
        column = {
            "id": prop.attrib["id"],
            "name": name,
            "units": prop.attrib.get("units"),
            "species": None,
            "InChI": None,
        }

        species_link = prop.find("speciesLink")
        if species_link is not None:
            column["species"] = species_link.attrib["preferredKey"]
            column["InChI"] = species_link.attrib.get("InChI")
            if column["InChI"] is None and name == "composition":
                # TODO: add InChI validator/search
                warn("Missing InChI for species " + column["species"])

        if name in ["uncertainty", "evaluated standard deviation"]:
            if "reference" not in prop.attrib:
                raise MissingAttributeError("reference", name)
            if "kind" not in prop.attrib:
                raise MissingAttributeError("kind", name)
            reference, species = resolve_reference(
                root if root is not None else dataGroup,
                " ".join(prop.attrib["reference"].split()),
            )
            column["reference"] = reference
            if column["species"] is None:
                column["species"] = species
            column["kind"] = prop.attrib["kind"]
            column["bound"] = prop.attrib.get("bound")
            column["sourcetype"] = prop.attrib.get("sourcetype")
            column["method"] = prop.attrib.get("method")

        columns.append(column)

    if not columns:
        raise MissingElementError("property")

    return columns


def get_datagroup_rows(dataGroup, columns):
    """Read the dataPoint rows of a ReSpecTh dataGroup.

    Args:
        dataGroup (`~xml.etree.ElementTree.Element`): A ``dataGroup`` element
        columns (`list`): Column descriptors from `get_datagroup_columns`

    Returns:
        `list`: One `dict` per dataPoint, mapping column id to the text of the value

    Raises:
        `MissingElementError`: If the dataGroup has no dataPoints
        `KeywordError`: If a value refers to a column the dataGroup does not declare
    """
    ids = {column["id"] for column in columns}
    rows = []
    for datapoint in dataGroup.findall("dataPoint"):
        row = {}
        for value in datapoint:
            if value.tag not in ids:
                raise KeywordError("value missing from properties: " + value.tag)
            row[value.tag] = value.text
        rows.append(row)

    if not rows:
        raise MissingElementError("dataPoint")

    return rows


def get_lbv_datapoints(root):
    """Parse laminar burning velocity datapoints from a ReSpecTh file.

    Every dataPoint in the first dataGroup becomes one ChemKED datapoint, with the composition
    columns gathered into that datapoint's composition.

    Args:
        root (`~xml.etree.ElementTree.Element`): Root of ReSpecTh XML file

    Returns:
        `list`: ChemKED datapoints

    Raises:
        `KeyError`: If a column is not a valid property for this experiment type
    """
    dataGroups = root.findall("dataGroup")
    if not dataGroups:
        raise MissingElementError("dataGroup")
    if len(dataGroups) > 1:
        raise NotImplementedError(
            "Multiple dataGroups are not supported for laminar burning velocity measurements"
        )

    columns = get_datagroup_columns(dataGroups[0], root)
    for column in columns:
        if column["name"] in ["composition", "uncertainty", "evaluated standard deviation"]:
            continue
        if column["name"] not in common_property_fields:
            raise KeyError(column["name"] + " not valid dataPoint property")

    datapoints = []
    for row in get_datagroup_rows(dataGroups[0], columns):
        datapoint: dict[str, Any] = {}
        composition: dict[str, Any] = {"species": [], "kind": None}
        kinds = []

        for column in columns:
            if column["id"] not in row:
                continue
            name = column["name"]

            if name == "composition":
                amount, kind = get_composition_amount(column["units"], row[column["id"]])
                species = {"species-name": column["species"]}
                if column["InChI"] is not None:
                    species["InChI"] = column["InChI"]
                species["amount"] = [amount]
                composition["species"].append(species)
                kinds.append(kind)
            elif name in ["uncertainty", "evaluated standard deviation"]:
                continue
            else:
                field = common_property_fields[name]
                check_units(name, field, column["units"])
                datapoint[field] = [value_with_units(row[column["id"]], column["units"])]

        # Metadata columns are applied once the values they describe are in place
        for column in columns:
            if column["name"] not in ["uncertainty", "evaluated standard deviation"]:
                continue
            if column["id"] not in row:
                continue
            item = dict(column, value=row[column["id"]])
            attach_value_metadata(
                {"datapoints": [datapoint], "common-properties": {}},
                [dict(item, species=column["species"])],
            )

        if composition["species"]:
            composition["kind"] = reconcile_composition_kind(composition["species"], kinds)
            datapoint["composition"] = composition
        datapoints.append(datapoint)

    return datapoints


def get_speciation_datapoints(root):
    """Parse speciation datapoints from a ReSpecTh file.

    Each dataGroup becomes one ChemKED datapoint: the first column that is not a species is the
    swept axis, the species columns become concentration profiles, and any remaining measured
    quantity becomes an auxiliary profile.

    Args:
        root (`~xml.etree.ElementTree.Element`): Root of ReSpecTh XML file

    Returns:
        `list`: ChemKED datapoints

    Raises:
        `KeyError`: If a column is not a valid property for this experiment type
        `NotImplementedError`: If the file cannot be represented by the ChemKED speciation schema
    """
    dataGroups = root.findall("dataGroup")
    if not dataGroups:
        raise MissingElementError("dataGroup")

    datapoints = []
    for dataGroup in dataGroups:
        columns = get_datagroup_columns(dataGroup, root)
        rows = get_datagroup_rows(dataGroup, columns)

        independent = []
        species_columns = []
        auxiliary = []
        metadata_columns = []
        scalar_columns = []
        for column in columns:
            name = column["name"]
            constant = len({row.get(column["id"]) for row in rows}) == 1

            # ReSpecTh names a species column "concentration" when it holds a concentration
            if name in ["composition", "concentration"] and column["species"] is not None:
                species_columns.append(column)
            elif name in ["uncertainty", "evaluated standard deviation"]:
                metadata_columns.append(column)
            elif constant and name in common_property_fields and independent:
                # A column with one repeated value states a condition, not a profile
                scalar_columns.append(column)
            elif not independent:
                # ReSpecTh writes the swept axis as the first column
                if name not in independent_variables:
                    raise KeyError(name + " not valid dataPoint property")
                independent.append(column)
            elif (
                name in auxiliary_profile_types
                and independent_variables[independent[0]["name"]] in auxiliary_axes
            ):
                # A profile of this quantity along the reactor or the flame
                auxiliary.append(column)
            elif name in independent_variables:
                # Not a coordinate to profile against, so this varies point by point with the
                # swept axis: a co-variate of the sweep rather than a profile of its own
                independent.append(column)
            elif name in common_property_fields:
                raise NotImplementedError(
                    f"{name} varies across the dataGroup but ChemKED can hold it only as a "
                    "single value or as a profile against distance or time"
                )
            else:
                raise KeyError(name + " not valid dataPoint property")

        if not species_columns:
            raise NotImplementedError(
                "A dataGroup without composition columns cannot be a speciation datapoint; "
                "auxiliary profiles have to share the axis and the rows of their datapoint"
            )

        axis_names = [independent_variables[column["name"]] for column in independent]
        datapoint: dict[str, Any] = {
            "independent-variables": [
                {
                    "name": axis_names[idx],
                    "units": normalize_units(column["units"]),
                    "primary": idx == 0,
                }
                for idx, column in enumerate(independent)
            ]
        }
        for idx, column in enumerate(independent):
            if column["species"] is not None:
                datapoint["independent-variables"][idx]["species-name"] = column["species"]
                if column["InChI"] is not None:
                    datapoint["independent-variables"][idx]["InChI"] = column["InChI"]

        for column in scalar_columns:
            field = common_property_fields[column["name"]]
            check_units(column["name"], field, column["units"])
            datapoint[field] = [value_with_units(rows[0][column["id"]], column["units"])]

        # Gather the uncertainty columns by the quantity each one describes
        pointwise: dict[Any, list] = {}
        for column in metadata_columns:
            reference = column["reference"]
            if reference == "concentration":
                # A concentration column is still a species amount
                reference = "composition"
            pointwise.setdefault((reference, column["species"]), []).append(column)

        def split_metadata(key):
            """Separate the varying uncertainty column from any constant ones.

            A row can carry one trailing uncertainty, so only a column that varies down the
            dataGroup needs that slot; a column with one repeated value describes the whole
            profile and is stored as its metadata instead.
            """
            found = pointwise.pop(key, [])
            varying = [c for c in found if len({row.get(c["id"]) for row in rows}) > 1]
            if len(varying) > 1:
                raise NotImplementedError(
                    f"{key[0]} has more than one uncertainty column that varies across the "
                    "dataGroup, and a ChemKED profile row holds only one"
                )
            return (varying[0] if varying else None), [c for c in found if c not in varying]

        profiles = []
        for column in species_columns:
            _, kind = get_composition_amount(column["units"], "0")
            factor = composition_units[column["units"]][1]
            uncertainty_column, constant_columns = split_metadata(
                ("composition", column["species"])
            )

            values = []
            for row in rows:
                point = [float(row[axis["id"]]) for axis in independent]
                point.append(float(row[column["id"]]) * factor)
                if uncertainty_column is not None and uncertainty_column["id"] in row:
                    point.append(float(row[uncertainty_column["id"]]) * factor)
                values.append(point)

            profile = {"species-name": column["species"]}
            if column["InChI"] is not None:
                profile["InChI"] = column["InChI"]
            profile["quantity"] = {"units": kind}
            profile["values"] = values
            for constant_column in constant_columns:
                metadata = format_value_metadata(
                    dict(constant_column, value=rows[0][constant_column["id"]]),
                    factor=factor,
                    numeric=True,
                )
                profile.setdefault("uncertainty", [{}])[0].update(metadata)
            profiles.append(profile)

        datapoint["concentration-profiles"] = profiles

        if auxiliary:
            if axis_names[0] not in auxiliary_axes:
                raise NotImplementedError(
                    f"An auxiliary profile against {axis_names[0]} is not supported; "
                    "auxiliary-profiles.independent.name allows distance or time"
                )
            auxiliary_axis = auxiliary_axes[axis_names[0]]
            datapoint["auxiliary-profiles"] = []
            for column in auxiliary:
                uncertainty_column, _ = split_metadata((column["name"], None))
                values = []
                for row in rows:
                    point = [float(row[independent[0]["id"]]), float(row[column["id"]])]
                    if uncertainty_column is not None and uncertainty_column["id"] in row:
                        point.append(float(row[uncertainty_column["id"]]))
                    values.append(point)

                datapoint["auxiliary-profiles"].append(
                    {
                        "type": column["name"],
                        "independent": {
                            "name": auxiliary_axis,
                            "units": normalize_units(independent[0]["units"]),
                        },
                        "quantity": {"units": normalize_units(column["units"])},
                        "values": values,
                    }
                )

        for (reference, species), found in pointwise.items():
            warn(
                f"Dropping {found[0]['name']} column that refers to {reference}"
                + (f" of {species}" if species else "")
                + ", which has no profile in this dataGroup"
            )

        datapoints.append(datapoint)

    return datapoints


def get_ignition_type(root):
    """Gets ignition type and target.

    Args:
        root (`~xml.etree.ElementTree.Element`): Root of ReSpecTh XML file

    Returns:
        properties (`dict`): Dictionary with ignition type/target information
    """
    properties = {}
    elem = root.find("ignitionType")

    if elem is None:
        raise MissingElementError("ignitionType")
    elem = elem.attrib

    if "target" in elem:
        ign_target = elem["target"].rstrip(";").strip()
    else:
        raise MissingAttributeError("target", "ignitionType")

    if "type" in elem:
        ign_type = " ".join(elem["type"].split())
        ign_type = ignition_types.get(ign_type, ign_type)
    else:
        raise MissingAttributeError("type", "ignitionType")

    # ReSpecTh allows multiple ignition targets
    if len(ign_target.split(";")) > 1:
        raise NotImplementedError("Multiple ignition targets not supported.")

    # Acceptable ignition targets include pressure, temperature, and species
    # concentrations. ReSpecTh abbreviates the first two and names excited species differently.
    ign_target = ignition_targets.get(ign_target.upper(), ign_target)

    if ign_target not in ignition_target_values:
        raise KeywordError(ign_target + " not valid ignition target")

    if ign_type not in ignition_type_values:
        raise KeywordError(ign_type + " not valid ignition type")

    properties["type"] = ign_type
    properties["target"] = ign_target

    return properties


def get_datapoints(root):
    """Parse datapoints with ignition delay from file.

    Args:
        root (`~xml.etree.ElementTree.Element`): Root of ReSpecTh XML file

    Returns:
        properties (`dict`): Dictionary with ignition delay data
    """
    # Shock tube experiment will have one data group, while RCM may have one
    # or two (one for ignition delay, one for volume-history)
    dataGroups = root.findall("dataGroup")
    if not dataGroups:
        raise MissingElementError("dataGroup")

    # all situations will have main experimental data in first dataGroup
    dataGroup = dataGroups[0]
    property_id = {}
    unit_id = {}
    species_id = {}
    metadata_id = {}
    # get properties of dataGroup
    for column in get_datagroup_columns(dataGroup, root):
        unit_id[column["id"]] = column["units"]
        temp_prop = column["name"]

        # Uncertainties describe another column, and are applied once that column is read
        if temp_prop in ["uncertainty", "evaluated standard deviation"]:
            metadata_id[column["id"]] = column
            continue

        if temp_prop not in [*datagroup_properties, "composition"]:
            raise KeyError(temp_prop + " not valid dataPoint property")
        property_id[column["id"]] = temp_prop

        if temp_prop == "composition":
            spec = {"species-name": column["species"]}
            if column["InChI"] is not None:
                spec["InChI"] = column["InChI"]
            species_id[column["id"]] = spec

    if not property_id:
        raise MissingElementError("property")

    # now get data points
    datapoints = []
    for dp in dataGroup.findall("dataPoint"):
        datapoint: dict[str, Any] = {}
        kinds = []
        if "composition" in property_id.values():
            datapoint["composition"] = {"species": [], "kind": None}

        for val in dp:
            # handle "regular" properties differently than composition
            if property_id.get(val.tag) in datagroup_properties:
                units = unit_id[val.tag]
                datapoint[property_id[val.tag].replace(" ", "-")] = [
                    value_with_units(val.text, units)
                ]
            elif property_id.get(val.tag) == "composition":
                spec = {}
                spec["species-name"] = species_id[val.tag]["species-name"]
                spec["InChI"] = species_id[val.tag].get("InChI")

                amount, units = get_composition_amount(unit_id[val.tag], val.text)
                spec["amount"] = [amount]

                datapoint["composition"]["species"].append(spec)
                kinds.append(units)
            elif val.tag in metadata_id:
                continue
            else:
                raise KeywordError("value missing from properties: " + val.tag)

        if kinds:
            datapoint["composition"]["kind"] = reconcile_composition_kind(
                datapoint["composition"]["species"], kinds
            )

        # Uncertainty columns are applied now that the values they describe are in place
        for tag, column in metadata_id.items():
            value = dp.find(tag)
            if value is None:
                continue
            attach_value_metadata(
                {"datapoints": [datapoint], "common-properties": {}},
                [dict(column, value=value.text)],
            )

        datapoints.append(datapoint)

    if len(datapoints) == 0:
        raise MissingElementError("dataPoint")

    # ReSpecTh files can have other dataGroups with pressure, volume, or temperature histories
    if len(dataGroups) > 1:
        datapoints[0]["time-histories"] = []
        for dataGroup in dataGroups[1:]:
            time_tag = None
            quant_tags = []
            quant_dicts = []
            quant_types = []
            for prop in dataGroup.findall("property"):
                if prop.attrib["name"] == "time":
                    time_dict = {"units": prop.attrib["units"], "column": 0}
                    time_tag = prop.attrib["id"]
                elif prop.attrib["name"] in ["volume", "temperature", "pressure"]:
                    quant_types.append(prop.attrib["name"])
                    quant_dicts.append({"units": prop.attrib["units"], "column": 1})
                    quant_tags.append(prop.attrib["id"])
                else:
                    raise KeywordError(
                        "Only volume, temperature, pressure, and time are allowed "
                        "in a time-history dataGroup."
                    )

            if time_tag is None or len(quant_tags) == 0:
                raise KeywordError("Both time and quantity properties required for time-history.")

            time_histories = [
                {"time": time_dict, "quantity": q, "type": t, "values": []}
                for (q, t) in zip(quant_dicts, quant_types)
            ]
            # collect volume-time history
            for dp in dataGroup.findall("dataPoint"):
                time = None
                quants = {}
                for val in dp:
                    if val.tag == time_tag:
                        time = float(val.text)
                    elif val.tag in quant_tags:
                        quant = float(val.text)
                        tag_idx = quant_tags.index(val.tag)
                        quant_type = quant_types[tag_idx]
                        quants[quant_type] = quant
                    else:
                        raise KeywordError(
                            f"Value tag {val.tag} not found in dataGroup tags: {quant_tags}"
                        )
                if time is None or len(quants) == 0:
                    raise KeywordError(
                        "Both time and quantity values required in each time-history dataPoint."
                    )
                for t in time_histories:
                    t["values"].append([time, quants[t["type"]]])

            datapoints[0]["time-histories"].extend(time_histories)

    return datapoints


def ReSpecTh_to_ChemKED(
    filename_xml,
    file_author="",
    file_author_orcid="",
    *,
    validate=False,
    apparatus_kind=None,
):
    """Convert ReSpecTh XML file to ChemKED-compliant dictionary.

    Args:
        filename_xml (`str`): Name of ReSpecTh XML file to be converted.
        file_author (`str`, optional): Name to override original file author
        file_author_orcid (`str`, optional): ORCID of file author
        validate (`bool`, optional, keyword-only): Set to `True` to validate the resulting
            property dictionary with `ChemKED`. Set to `False` if the file is being loaded and will
            be validated at some other point before use.
        apparatus_kind (`str`, optional, keyword-only): ChemKED apparatus kind to use instead of
            the one derived from the file. ReSpecTh often records only the generic ``flame``
            apparatus, in which case the specific burner is known from the article rather than
            from the file.
    """
    # get all information from XML file
    tree = etree.parse(filename_xml)
    root = tree.getroot()

    # get file metadata
    properties = get_file_metadata(root)

    # get reference info
    properties["reference"] = get_reference(root)
    # Save name of original data filename
    properties["reference"]["detail"] = (
        properties["reference"].get("detail", "")
        + "Converted from ReSpecTh XML file "
        + Path(filename_xml).name
    )

    # Get the kind of experiment, which selects how the datapoints are read
    properties.update(get_experiment_kind(root, apparatus_kind=apparatus_kind))
    experiment_type = properties["experiment-type"]

    # Get properties shared across the file
    properties["common-properties"] = get_common_properties(root)

    if experiment_type == "ignition delay":
        # Determine definition of ignition delay
        properties["common-properties"]["ignition-type"] = get_ignition_type(root)
        properties["datapoints"] = get_datapoints(root)
    elif experiment_type == "laminar burning velocity measurement":
        properties["datapoints"] = get_lbv_datapoints(root)
    else:
        properties["datapoints"] = get_speciation_datapoints(root)

    # Attach the uncertainties that ReSpecTh states as separate common properties
    attach_value_metadata(properties, get_value_metadata(root))

    comments = [
        " ".join(comment.text.split()) for comment in root.findall("comment") if comment.text
    ]
    if comments:
        properties["comments"] = comments

    if experiment_type == "ignition delay":
        # Ensure inclusion of pressure rise or volume history matches apparatus.
        has_pres_rise = "pressure-rise" in properties["common-properties"] or any(
            True for dp in properties["datapoints"] if "pressure-rise" in dp
        )
        if has_pres_rise and properties["apparatus"]["kind"] == "rapid compression machine":
            raise KeywordError("Pressure rise cannot be defined for RCM.")

        has_vol_hist = any(
            t.get("type") == "volume"
            for dp in properties["datapoints"]
            for t in dp.get("time-histories", [{}])
        )
        if has_vol_hist and properties["apparatus"]["kind"] == "shock tube":
            raise KeywordError("Volume history cannot be defined for shock tube.")

    # add any additional file authors
    if file_author_orcid and not file_author:
        raise KeywordError("If file_author_orcid is specified, file_author must be as well")

    if file_author:
        temp_author = {"name": file_author}
        if file_author_orcid:
            temp_author["ORCID"] = file_author_orcid
        properties["file-authors"].append(temp_author)

    # Now go through datapoints and apply common properties
    for idx in range(len(properties["datapoints"])):
        for prop in properties["common-properties"]:
            properties["datapoints"][idx][prop] = properties["common-properties"][prop]

    if validate:
        chemked.ChemKED(dict_input=properties)

    return properties


def respth2ck(argv=None):
    """Command-line entry point for converting a ReSpecTh XML file to a ChemKED YAML file."""
    parser = ArgumentParser(description="Convert a ReSpecTh XML file to a ChemKED YAML file.")
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        required=True,
        help='Input filename (e.g., "file1.yaml")',
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        required=False,
        default="",
        help='Output filename (e.g., "file1.xml")',
    )
    parser.add_argument(
        "-fa",
        "--file-author",
        dest="file_author",
        type=str,
        required=False,
        default="",
        help="File author name to override original",
    )
    parser.add_argument(
        "-fo",
        "--file-author-orcid",
        dest="file_author_orcid",
        type=str,
        required=False,
        default="",
        help="File author ORCID",
    )
    parser.add_argument(
        "-ak",
        "--apparatus-kind",
        dest="apparatus_kind",
        type=str,
        required=False,
        default=None,
        help=(
            "ChemKED apparatus kind, for files whose apparatus is only stated in the article "
            '(e.g., "outwardly propagating spherical flame")'
        ),
    )

    args = parser.parse_args(argv)

    filename_ck = args.output
    filename_xml = args.input

    properties = ReSpecTh_to_ChemKED(
        filename_xml,
        args.file_author,
        args.file_author_orcid,
        validate=True,
        apparatus_kind=args.apparatus_kind,
    )

    # set output filename and path
    if not filename_ck:
        filename_ck = Path(filename_xml).with_suffix(".yaml")

    with open(filename_ck, "w") as outfile:
        yaml.dump(properties, outfile, default_flow_style=False)
    print(f"Converted to {filename_ck}")


def ck2respth(argv=None):
    """Command-line entry point for converting a ChemKED YAML file to a ReSpecTh XML file."""
    parser = ArgumentParser(description="Convert a ChemKED YAML file to a ReSpecTh XML file.")
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        required=True,
        help='Input filename (e.g., "file1.xml")',
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        required=False,
        default="",
        help='Output filename (e.g., "file1.yaml")',
    )

    args = parser.parse_args(argv)

    c = chemked.ChemKED(yaml_file=args.input)
    c.convert_to_ReSpecTh(args.output)


def main(argv=None):
    """General function for converting between ReSpecTh and ChemKED files based on extension."""
    parser = ArgumentParser(
        description="Convert between ReSpecTh XML file and ChemKED YAML file "
        "automatically based on file extension."
    )
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        required=True,
        help='Input filename (e.g., "file1.yaml" or "file2.xml")',
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        required=False,
        default="",
        help='Output filename (e.g., "file1.xml" or "file2.yaml")',
    )
    parser.add_argument(
        "-fa",
        "--file-author",
        dest="file_author",
        type=str,
        required=False,
        default="",
        help="File author name to override original",
    )
    parser.add_argument(
        "-fo",
        "--file-author-orcid",
        dest="file_author_orcid",
        type=str,
        required=False,
        default="",
        help="File author ORCID",
    )
    parser.add_argument(
        "-ak",
        "--apparatus-kind",
        dest="apparatus_kind",
        type=str,
        required=False,
        default=None,
        help=(
            "ChemKED apparatus kind, for files whose apparatus is only stated in the article "
            '(e.g., "outwardly propagating spherical flame")'
        ),
    )

    args = parser.parse_args(argv)

    in_suffix = Path(args.input).suffix
    out_suffix = Path(args.output).suffix

    if in_suffix == ".xml" and out_suffix == ".yaml":
        argv_respth2ck = [
            "-i",
            args.input,
            "-o",
            args.output,
            "-fa",
            args.file_author,
            "-fo",
            args.file_author_orcid,
        ]
        if args.apparatus_kind is not None:
            argv_respth2ck += ["-ak", args.apparatus_kind]
        respth2ck(argv_respth2ck)

    elif in_suffix == ".yaml" and out_suffix == ".xml":
        c = chemked.ChemKED(yaml_file=args.input)
        c.convert_to_ReSpecTh(args.output)

    elif in_suffix == ".xml" and out_suffix == ".xml":
        raise KeywordError("Cannot convert .xml to .xml")

    elif in_suffix == ".yaml" and out_suffix == ".yaml":
        raise KeywordError("Cannot convert .yaml to .yaml")

    else:
        raise KeywordError("Input/output args need to be .xml/.yaml")


if __name__ == "__main__":
    main()
