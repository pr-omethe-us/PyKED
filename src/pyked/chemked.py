"""Main ChemKED module"""

# Standard libraries
import xml.dom.minidom as minidom
import xml.etree.ElementTree as etree
from copy import deepcopy
from itertools import chain, count
from pathlib import Path
from typing import Any, ClassVar, NamedTuple
from warnings import warn

import numpy as np
import pint

from .converters import (
    ReSpecTh_to_ChemKED,
    auxiliary_axes,
    common_property_fields,
    composition_units,
    datagroup_properties,
    independent_variables,
)

# Local imports
from .validation import Q_, OurValidator, _normalize_unit_str, schema, yaml

respecth_property_names = {field: name for name, field in common_property_fields.items()}
"""`dict`: ChemKED field name mapped to the ReSpecTh property name, the inverse of
`~pyked.converters.common_property_fields`"""

respecth_axis_names = {axis: name for name, axis in independent_variables.items()}
"""`dict`: Speciation independent-variable name mapped to the ReSpecTh dataGroup property name,
the inverse of `~pyked.converters.independent_variables`"""

respecth_speciation_apparatus = {
    "jet stirred reactor": ("jet stirred reactor", []),
    "flow reactor": ("flow reactor", []),
    "shock tube": ("shock tube", []),
    # ReSpecTh names a flame generically and the burner in a mode
    "burner stabilized flame": ("flame", ["burner-stabilized"]),
}
"""`dict`: ChemKED ``apparatus.kind`` of a speciation measurement mapped to the ReSpecTh
``apparatus/kind`` and ``apparatus/mode`` elements"""

respecth_labels = {
    "temperature": "T",
    "pressure": "P",
    "time": "t",
    "residence time": "tau",
    "distance": "x",
    "volume": "V",
    "equivalence ratio": "phi",
}
"""`dict`: ReSpecTh property name mapped to the column label ReSpecTh files give it"""

concentration_kinds = {kind for kind, _, _ in composition_units.values() if "/" in kind}
"""`set`: Composition kinds that are concentrations, which ReSpecTh names ``concentration``
rather than ``composition``"""

speciation_profile_keys = [
    "independent-variables",
    "concentration-profiles",
    "auxiliary-profiles",
    "time-shift",
]
"""`list`: Speciation datapoint fields that are written as dataGroup columns or elements of their
own rather than as properties"""


def _respecth_units(units):
    """Spell units as ReSpecTh does, which writes a dimensionless quantity as ``unitless``."""
    if units is None or units.strip() in ["", "dimensionless"]:
        return "unitless"
    return units.strip()


def _split_value(value):
    """Split a ChemKED value into the value text and the units ReSpecTh states it in.

    The value text is kept as written, so its significant figures survive the conversion.
    """
    number, _, units = str(value).strip().partition(" ")
    return number, _respecth_units(units)


def _metadata_items(metadata):
    """Turn ChemKED uncertainty metadata into ReSpecTh uncertainty descriptors.

    The inverse of `~pyked.converters.format_value_metadata`: an uncertainty, each bound of an
    asymmetric one, and an evaluated standard deviation each become a property of their own.

    Args:
        metadata (`dict`): The metadata mapping of a ChemKED quantity or profile

    Returns:
        `list`: One `dict` per ReSpecTh uncertainty or evaluated standard deviation property
    """
    items = []
    bounds = {
        "uncertainty": "plusminus",
        "upper-uncertainty": "upper",
        "lower-uncertainty": "lower",
    }
    for key, bound in bounds.items():
        if key in metadata:
            items.append(
                {
                    "name": "uncertainty",
                    "kind": metadata.get("uncertainty-type"),
                    "bound": bound,
                    "sourcetype": metadata.get("uncertainty-sourcetype"),
                    "value": metadata[key],
                }
            )

    if "evaluated-standard-deviation" in metadata:
        items.append(
            {
                "name": "evaluated standard deviation",
                "kind": metadata.get("evaluated-standard-deviation-type"),
                "sourcetype": metadata.get("evaluated-standard-deviation-sourcetype"),
                "method": metadata.get("evaluated-standard-deviation-method"),
                "value": metadata["evaluated-standard-deviation"],
            }
        )

    return items


row_uncertainty = {"name": "uncertainty", "kind": "absolute", "bound": "plusminus", "value": ""}
"""`dict`: Descriptor of the uncertainty a ChemKED profile row may end with, which is an
absolute uncertainty in the units of the profile. Its values are in the rows, so it has none of
its own."""


def _metadata_value(item, units):
    """The value text of an uncertainty descriptor and the units ReSpecTh states it in.

    Args:
        item (`dict`): Descriptor from `_metadata_items`
        units (`str`): Units of the quantity the uncertainty is about, which an absolute value
            without units of its own is stated in

    Returns:
        `tuple`: The value text and its units
    """
    value, own_units = _split_value(item["value"])
    if item["kind"] == "relative":
        # A relative value is a fraction of the quantity
        return value, "unitless"
    if own_units == "unitless":
        return value, _respecth_units(units)
    return value, own_units


def _set_metadata_attributes(prop, item, reference, units, column_id=None):
    """Describe a ReSpecTh uncertainty property and return its value text.

    Args:
        prop (`~xml.etree.ElementTree.Element`): The ReSpecTh property to describe
        item (`dict`): Descriptor from `_metadata_items`
        reference (`str`): ReSpecTh name of the quantity the uncertainty is about
        units (`str`): Units of that quantity
        column_id (`str`, optional): The id of the property, when it is a dataGroup column

    Returns:
        `str`: The value text
    """
    value, units = _metadata_value(item, units)
    prop.set("name", item["name"])
    if column_id is not None:
        prop.set("id", column_id)
    prop.set("units", units)
    prop.set("reference", reference)
    for attribute in ["kind", "bound", "sourcetype", "method"]:
        if item.get(attribute) is not None:
            prop.set(attribute, item[attribute])

    return value


def _add_species_link(parent, species):
    """Add a ReSpecTh speciesLink for a ChemKED species, profile, or swept inlet species."""
    link = etree.SubElement(parent, "speciesLink")
    link.set("preferredKey", species["species-name"])
    for key in ["InChI", "SMILES"]:
        if species.get(key) is not None:
            link.set(key, species[key])


def _add_metadata_property(parent, item, reference, units, species=None):
    """Add an uncertainty that applies to every value of a quantity as a common property."""
    prop = etree.SubElement(parent, "property")
    value = _set_metadata_attributes(prop, item, reference, units)
    if species is not None:
        _add_species_link(prop, species)
    etree.SubElement(prop, "value").text = value


def _shared_value(values):
    """The value every entry has, or `None` when they differ or the value is missing."""
    if not values or values[0] is None:
        return None
    if all(value == values[0] for value in values):
        return values[0]
    return None


def _speciation_experiment_type(apparatus_kind, datapoints):
    """Pick the ReSpecTh experiment type for a ChemKED speciation measurement.

    ReSpecTh keeps four speciation types where ChemKED has one. The apparatus says which, and for a
    shock tube or flow reactor so does the swept axis: profiles against time are concentration
    time profiles, while sweeps of temperature or residence time sample the outlet.

    Args:
        apparatus_kind (`str`): The ChemKED ``apparatus.kind``
        datapoints (`list`): The ChemKED datapoints

    Returns:
        `str`: The ReSpecTh ``experimentType``

    Raises:
        `NotImplementedError`: If the apparatus has no ReSpecTh speciation type, or the datapoints
            would need more than one
    """
    if apparatus_kind == "jet stirred reactor":
        return "jet stirred reactor measurement"
    if apparatus_kind == "burner stabilized flame":
        return "burner stabilized flame speciation measurement"
    if apparatus_kind not in ["shock tube", "flow reactor"]:
        raise NotImplementedError(
            f"ReSpecTh has no speciation measurement type for a {apparatus_kind}."
        )

    against_time = {dp["independent-variables"][0]["name"] == "time" for dp in datapoints}
    if len(against_time) > 1:
        raise NotImplementedError(
            "ReSpecTh gives one experiment type per file, but some datapoints are profiles "
            "against time and others are outlet concentrations."
        )
    if against_time.pop():
        return "concentration time profile measurement"
    return "outlet concentration measurement"


def _respecth_bibliography(reference):
    """Write a ChemKED reference as a ReSpecTh 2 ``bibliographyLink``.

    The reference is stated in full in ``details``, which `~pyked.converters.get_reference_details`
    reads back without a DOI look-up. Author names are written as ChemKED has them, given name
    first, which BibTeX accepts as well as the family-name-first form.

    Args:
        reference (`Reference`): The ChemKED reference

    Returns:
        `~xml.etree.ElementTree.Element`: The ``bibliographyLink`` element
    """
    names = [author["name"] for author in reference.authors]
    citation = ", ".join(names)
    for part in [reference.journal, reference.volume, reference.pages, reference.year]:
        if part is not None:
            citation += f", {part}"
    citation += "."
    if reference.detail:
        citation += f" {reference.detail}"

    link = etree.Element("bibliographyLink")
    etree.SubElement(link, "description").text = citation
    if reference.doi is not None:
        etree.SubElement(link, "referenceDOI").text = reference.doi

    details = etree.SubElement(link, "details")
    etree.SubElement(details, "author").text = " and ".join(names)
    for field in ["journal", "pages", "volume", "year"]:
        value = getattr(reference, field)
        if value is not None:
            etree.SubElement(details, field).text = str(value)

    return link


def _respecth_property_name(field):
    """The ReSpecTh property name of a ChemKED condition.

    Raises:
        `NotImplementedError`: If ReSpecTh has no property for the condition
    """
    if field not in respecth_property_names:
        raise NotImplementedError(f"ReSpecTh has no property for {field}.")
    return respecth_property_names[field]


def _speciation_common_properties(properties):
    """The conditions of a speciation measurement that ReSpecTh can state once for the file.

    ReSpecTh applies a common property to every dataGroup, so only a condition every datapoint
    states with the same value can be common. The candidates are the file's own
    common-properties, so that the file reads back the same, or what the first datapoint states
    when the file has none.

    Args:
        properties (`dict`): The ChemKED file

    Returns:
        `dict`: ChemKED field mapped to the value every datapoint shares

    Raises:
        `NotImplementedError`: If the datapoints have different initial compositions
    """
    datapoints = properties["datapoints"]
    candidates = properties.get("common-properties")
    if candidates is None:
        candidates = {
            field: value
            for field, value in datapoints[0].items()
            if field not in speciation_profile_keys
        }

    common = {
        field: value
        for field, value in candidates.items()
        if all(field in dp and dp[field] == value for dp in datapoints)
    }
    if "composition" not in common:
        raise NotImplementedError(
            "ReSpecTh states one initial composition for the whole file, but the datapoints "
            "have different compositions."
        )
    return common


def _datapoint_conditions(datapoint, common):
    """The conditions a datapoint states with a value of its own rather than a common one."""
    return [
        field for field in datapoint if field not in common and field not in speciation_profile_keys
    ]


def _shared_uncertainties(datapoints, common):
    """Find the uncertainties that ReSpecTh can state as common properties.

    The converter attaches a common uncertainty about a species to every profile of that species,
    and one about a condition to every datapoint that states the condition. Such an uncertainty
    can therefore be common when every profile of the species, or every datapoint stating the
    condition, carries the same one.

    Args:
        datapoints (`list`): The ChemKED datapoints
        common (`dict`): The common conditions, from `_speciation_common_properties`

    Returns:
        `tuple`: Species name mapped to a profile of it and the uncertainty mapping they share,
        and ChemKED field mapped to the uncertainty mapping the datapoints share
    """
    profiles: dict[str, list] = {}
    conditions: dict[str, list] = {}
    for dp in datapoints:
        for profile in dp["concentration-profiles"]:
            profiles.setdefault(profile["species-name"], []).append(profile)
        for field in _datapoint_conditions(dp, common):
            conditions.setdefault(field, []).append(dp[field][1] if len(dp[field]) > 1 else None)

    shared_profiles = {}
    for species, found in profiles.items():
        # The units are shared too, as an absolute uncertainty is stated in them
        shared = _shared_value([(p["quantity"]["units"], p.get("uncertainty")) for p in found])
        if shared is not None and shared[1] is not None:
            shared_profiles[species] = (found[0], shared[1][0])

    shared_conditions = {}
    for field, found in conditions.items():
        shared = _shared_value(found)
        if shared is not None:
            shared_conditions[field] = shared

    return shared_profiles, shared_conditions


def _add_speciation_common_properties(root, datapoints, common, shared_profiles, shared_conditions):
    """Write the common properties of a speciation measurement.

    The uncertainties follow the values they describe, as in ReSpecTh files, and each names the
    quantity it is about: an amount in the inlet mixture is referred to as the ``initial
    composition`` and a measured profile as the ``composition``, with the species linked.

    Args:
        root (`~xml.etree.ElementTree.Element`): The ReSpecTh ``experiment`` element
        datapoints (`list`): The ChemKED datapoints
        common (`dict`): The common conditions, from `_speciation_common_properties`
        shared_profiles (`dict`): Profile uncertainties to state once, from `_shared_uncertainties`
        shared_conditions (`dict`): Condition uncertainties to state once, likewise
    """
    common_properties = etree.SubElement(root, "commonProperties")

    # (reference, units of the quantity, species, descriptor) of each uncertainty
    metadata = []
    for field, value in common.items():
        prop = etree.SubElement(common_properties, "property")
        if field == "composition":
            prop.set("name", "initial composition")
            for species in value["species"]:
                component = etree.SubElement(prop, "component")
                _add_species_link(component, species)
                amount = etree.SubElement(component, "amount")
                amount.set("units", value["kind"])
                amount.text = str(species["amount"][0])
                if len(species["amount"]) > 1:
                    metadata.extend(
                        ("initial composition", value["kind"], species, item)
                        for item in _metadata_items(species["amount"][1])
                    )
            continue

        name = _respecth_property_name(field)
        number, units = _split_value(value[0])
        prop.set("name", name)
        if name in respecth_labels:
            prop.set("label", respecth_labels[name])
        prop.set("units", units)
        etree.SubElement(prop, "value").text = number
        if len(value) > 1:
            metadata.extend((name, units, None, item) for item in _metadata_items(value[1]))

    for profile, uncertainty in shared_profiles.values():
        metadata.extend(
            ("composition", profile["quantity"]["units"], profile, item)
            for item in _metadata_items(uncertainty)
        )

    for field, uncertainty in shared_conditions.items():
        value = next(dp[field] for dp in datapoints if field in dp)
        metadata.extend(
            (_respecth_property_name(field), _split_value(value[0])[1], None, item)
            for item in _metadata_items(uncertainty)
        )

    for reference, units, species, item in metadata:
        _add_metadata_property(common_properties, item, reference, units, species)


def _add_speciation_datagroup(
    root, datapoint, datagroup_id, column_ids, common, shared_profiles, shared_conditions
):
    """Write a speciation datapoint as a ReSpecTh dataGroup.

    The columns are, in order, the independent variables with the swept axis first, one column
    per concentration profile, any condition the datapoint states with a value of its own, the
    auxiliary profiles, and then the uncertainties. That is the order in which
    `~pyked.converters.get_speciation_datapoints` tells the columns apart. An uncertainty that
    could not be common is written as a column with one repeated value, which describes the whole
    profile.

    Args:
        root (`~xml.etree.ElementTree.Element`): The ReSpecTh ``experiment`` element
        datapoint (`dict`): The ChemKED datapoint
        datagroup_id (`str`): The id of the dataGroup
        column_ids (`~collections.abc.Iterator`): Column numbers, which ReSpecTh counts across the
            whole file
        common (`dict`): The common conditions, from `_speciation_common_properties`
        shared_profiles (`dict`): Profile uncertainties stated once, from `_shared_uncertainties`
        shared_conditions (`dict`): Condition uncertainties stated once, likewise

    Raises:
        `NotImplementedError`: If the concentration and auxiliary profiles are not all sampled at
            the same points
    """
    axes = datapoint["independent-variables"]
    n_axes = len(axes)
    profiles = datapoint["concentration-profiles"]
    auxiliary = datapoint.get("auxiliary-profiles", [])

    grid = [row[:n_axes] for row in profiles[0]["values"]]
    for profile in profiles[1:]:
        if [row[:n_axes] for row in profile["values"]] != grid:
            raise NotImplementedError(
                f"The profile of {profile['species-name']} is sampled at other points than that "
                f"of {profiles[0]['species-name']}, but a ReSpecTh dataGroup holds every profile "
                "on one set of rows."
            )
    for aux in auxiliary:
        if (
            aux["independent"]["name"] != auxiliary_axes.get(axes[0]["name"])
            or aux["independent"]["units"] != axes[0]["units"]
            or [row[0] for row in aux["values"]] != [point[0] for point in grid]
        ):
            raise NotImplementedError(
                f"The auxiliary {aux['type']} profile is not sampled at the points of the "
                "concentration profiles, but a ReSpecTh dataGroup holds both on one set of rows."
            )

    datagroup = etree.SubElement(root, "dataGroup")
    datagroup.set("id", datagroup_id)
    columns = []

    def add_column(values, name, units, species=None, metadata=None):
        """Declare a column whose text in each row is in ``values``, `None` where it is blank.

        An uncertainty column is described by ``metadata``, its descriptor and the name of the
        quantity it is about, instead of by ``name``.
        """
        prop = etree.SubElement(datagroup, "property")
        column_id = f"x{next(column_ids)}"
        if metadata is not None:
            item, reference = metadata
            _set_metadata_attributes(prop, item, reference, units, column_id)
        else:
            prop.set("name", name)
            prop.set("id", column_id)
            if species is not None:
                prop.set("label", f"[{species['species-name']}]")
            elif name in respecth_labels:
                prop.set("label", respecth_labels[name])
            prop.set("units", _respecth_units(units))
        if species is not None:
            _add_species_link(prop, species)
        columns.append((column_id, values))

    for idx, axis in enumerate(axes):
        add_column(
            [str(point[idx]) for point in grid],
            respecth_axis_names[axis["name"]],
            axis["units"],
            species=axis if "species-name" in axis else None,
        )

    for profile in profiles:
        units = profile["quantity"]["units"]
        add_column(
            [str(row[n_axes]) for row in profile["values"]],
            "concentration" if units in concentration_kinds else "composition",
            units,
            species=profile,
        )

    conditions = _datapoint_conditions(datapoint, common)
    for field in conditions:
        number, units = _split_value(datapoint[field][0])
        add_column([number] * len(grid), _respecth_property_name(field), units)

    for aux in auxiliary:
        add_column([str(row[1]) for row in aux["values"]], aux["type"], aux["quantity"]["units"])

    # A row may end with the uncertainty of its value
    for profile in profiles:
        if any(len(row) > n_axes + 1 for row in profile["values"]):
            add_column(
                [
                    str(row[n_axes + 1]) if len(row) > n_axes + 1 else None
                    for row in profile["values"]
                ],
                None,
                profile["quantity"]["units"],
                species=profile,
                metadata=(row_uncertainty, "composition"),
            )
    for aux in auxiliary:
        if any(len(row) > 2 for row in aux["values"]):
            add_column(
                [str(row[2]) if len(row) > 2 else None for row in aux["values"]],
                None,
                aux["quantity"]["units"],
                metadata=(row_uncertainty, aux["type"]),
            )

    for profile in profiles:
        if profile["species-name"] in shared_profiles or "uncertainty" not in profile:
            continue
        units = profile["quantity"]["units"]
        for item in _metadata_items(profile["uncertainty"][0]):
            add_column(
                [_metadata_value(item, units)[0]] * len(grid),
                None,
                units,
                species=profile,
                metadata=(item, "composition"),
            )
    for field in conditions:
        if field in shared_conditions or len(datapoint[field]) < 2:
            continue
        units = _split_value(datapoint[field][0])[1]
        for item in _metadata_items(datapoint[field][1]):
            add_column(
                [_metadata_value(item, units)[0]] * len(grid),
                None,
                units,
                metadata=(item, _respecth_property_name(field)),
            )

    for row in range(len(grid)):
        point = etree.SubElement(datagroup, "dataPoint")
        for column_id, values in columns:
            if values[row] is not None:
                etree.SubElement(point, column_id).text = values[row]


class VolumeHistory(NamedTuple):
    """Time history of the volume in an RCM experiment. Deprecated, to be removed after PyKED 0.4"""

    time: pint.Quantity
    """(`~pint.Quantity`): the time during the experiment"""
    volume: pint.Quantity
    """(`~pint.Quantity`): the volume during the experiment"""


class TimeHistory(NamedTuple):
    """Time history of the quantity in an RCM experiment"""

    time: pint.Quantity
    """(`~pint.Quantity`): the time during the experiment"""
    quantity: pint.Quantity
    """(`~pint.Quantity`): the quantity of interest during the experiment"""
    type: str
    """(`str`): the type of time history represented. Possible options are:

    * volume
    * temperature
    * pressure
    * piston position
    * light emission
    * OH emission
    * absorption
    """


class RCMData(NamedTuple):
    """Data fields specific to rapid compression machine experiments"""

    compressed_pressure: pint.Quantity | None
    """(`~pint.Quantity`) The pressure at the end of compression"""
    compressed_temperature: pint.Quantity | None
    """(`~pint.Quantity`) The temperature at the end of compression"""
    compression_time: pint.Quantity | None
    """(`~pint.Quantity`) The duration of the compression stroke"""
    stroke: pint.Quantity | None
    """(`~pint.Quantity`) The length of the stroke"""
    clearance: pint.Quantity | None
    """(`~pint.Quantity`) The clearance between piston face and end wall at the end of compression"""
    compression_ratio: pint.Quantity | None
    """(`~pint.Quantity`) The volumetric compression ratio"""


class Reference(NamedTuple):
    """Information about the article or report where the data can be found"""

    volume: str | None
    """(`str`) The journal volume"""
    journal: str | None
    """(`str`) The name of the journal"""
    doi: str | None
    """(`str`) The Digital Object Identifier of the article"""
    authors: list | None
    """(`list`) The list of authors of the article"""
    detail: str | None
    """(`str`) Detail about where the data can be found in the article"""
    year: int | None
    """(`int`) The year the article was published"""
    pages: str | None
    """(`str`) The pages in the journal where the article was published"""


class Apparatus(NamedTuple):
    """Information about the experimental apparatus used to generate the data"""

    kind: str | None
    """(`str`) The kind of experimental apparatus"""
    institution: str | None
    """(`str`) The institution where the experiment is located"""
    facility: str | None
    """(`str`) The particular experimental facility at the location"""


class EvaluatedStandardDeviation(NamedTuple):
    """Evaluated standard deviation metadata attached to a quantity"""

    value: pint.Quantity | float
    """(`~pint.Quantity` or `float`) The evaluated standard deviation. Absolute values are
    stored as a `~pint.Quantity` with the units given in the file; relative values are stored
    as a plain `float` fraction"""
    type: str | None
    """(`str`) Whether the value is ``absolute`` or ``relative``"""
    sourcetype: str | None
    """(`str`) How the value was obtained, e.g. ``reported``, ``estimated``, ``calculated``,
    or ``digitized``"""
    method: str | None
    """(`str`) The method used to compute the value, e.g. ``statistical scatter``"""


class Composition(NamedTuple):
    """Detail of the initial composition of the mixture for the experiment"""

    species_name: str
    """(`str`) The name of the species"""
    InChI: str | None
    """(`str`) The InChI identifier for the species"""
    SMILES: str | None
    """(`str`) The SMILES identifier for the species"""
    atomic_composition: dict | None
    """(`dict`) The atomic composition of the species"""
    amount: pint.Quantity
    """(`~pint.Quantity`) The amount of this species"""
    amount_esd: EvaluatedStandardDeviation | None = None
    """(`EvaluatedStandardDeviation`) The evaluated standard deviation of the amount,
    if specified"""


class ChemKED:
    """Main ChemKED class.

    The ChemKED class stores information about the contents of a ChemKED database
    file. It stores each datapoint associated with the database and provides access
    the the reference information, versions, and file author.

    Arguments:
        yaml_file (`str`, optional): The filename of the YAML database in ChemKED format.
        dict_input (`dict`, optional): A dictionary with the parsed ouput of YAML file in ChemKED
            format.
        skip_validation (`bool`, optional): Whether validation of the ChemKED should be done. Must
            be supplied as a keyword-argument.

    Attributes:
        datapoints (`list`): List of `DataPoint` objects storing each datapoint in the database.
        reference (`~collections.namedtuple`): Attributes include ``volume``, ``journal``, ``doi``,
            ``authors``, ``detail``, ``year``, and ``pages`` describing the reference from which the
            datapoints are derived.
        apparatus (`~collections.namedtuple`): Attributes include ``kind`` of experimental
            apparatus, and the ``institution`` and ``facility`` where the experimental apparatus is
            located.
        chemked_version (`str`): Version of the ChemKED database schema used in this file.
        experiment_type (`str`): Type of exeperimental data contained in this database.
        file_author (`dict`): Information about the author of the ChemKED database file.
        file_version (`str`): Version of the ChemKED database file.
        _properties (`dict`): Original dictionary read from ChemKED database file, meant for
            internal use.
    """

    chemked_version: Any
    experiment_type: Any
    file_authors: Any
    file_version: Any

    def __init__(self, yaml_file=None, dict_input=None, *, skip_validation=False):
        if yaml_file is not None:
            with open(yaml_file, encoding="utf-8") as f:
                self._properties = yaml.safe_load(f)
        elif dict_input is not None:
            self._properties = dict_input
        else:
            raise NameError("ChemKED needs either a YAML filename or dictionary as input.")

        if not skip_validation:
            self.validate_yaml(self._properties)

        self.datapoints = []
        for point in self._properties["datapoints"]:
            self.datapoints.append(DataPoint(point))

        self.reference = Reference(
            volume=self._properties["reference"].get("volume"),
            journal=self._properties["reference"].get("journal"),
            doi=self._properties["reference"].get("doi"),
            authors=self._properties["reference"].get("authors"),
            detail=self._properties["reference"].get("detail"),
            year=self._properties["reference"].get("year"),
            pages=self._properties["reference"].get("pages"),
        )

        self.apparatus = Apparatus(
            kind=self._properties["apparatus"].get("kind"),
            institution=self._properties["apparatus"].get("institution"),
            facility=self._properties["apparatus"].get("facility"),
        )

        for prop in [
            "chemked-version",
            "experiment-type",
            "file-authors",
            "file-version",
        ]:
            setattr(self, prop.replace("-", "_"), self._properties[prop])

    @classmethod
    def from_respecth(cls, filename_xml, file_author="", file_author_orcid=""):
        """Construct a ChemKED instance directly from a ReSpecTh file.

        Arguments:
            filename_xml (`str`): Filename of the ReSpecTh-formatted XML file to be imported
            file_author (`str`, optional): File author to be added to the list generated from the
                XML file
            file_author_orcid (`str`, optional): ORCID for the file author being added to the list
                of file authors

        Returns:
            `ChemKED`: Instance of the `ChemKED` class containing the data in ``filename_xml``.

        Examples:
            >>> ck = ChemKED.from_respecth('respecth_file.xml')
            >>> ck = ChemKED.from_respecth('respecth_file.xml', file_author='Bryan W. Weber')
            >>> ck = ChemKED.from_respecth('respecth_file.xml', file_author='Bryan W. Weber',
                                           file_author_orcid='0000-0000-0000-0000')
        """
        properties = ReSpecTh_to_ChemKED(
            filename_xml, file_author, file_author_orcid, validate=False
        )
        return cls(dict_input=properties)

    def validate_yaml(self, properties):
        """Validate the parsed YAML file for adherance to the ChemKED format.

        Arguments:
            properties (`dict`): Dictionary created from the parsed YAML file

        Raises:
            `ValueError`: If the YAML file cannot be validated, a `ValueError` is raised whose
                string contains the errors that are present.
        """
        validator = OurValidator(schema)
        if not validator.validate(properties):
            for key, value in validator.errors.items():
                if any("unallowed value" in v for v in value):
                    print(
                        (
                            "{key} has an illegal value. Allowed values are {values} and are case "
                            "sensitive."
                        ).format(key=key, values=schema[key]["allowed"])
                    )

            raise ValueError(validator.errors)

    def get_dataframe(self, output_columns=None):
        """Get a Pandas DataFrame of the datapoints in this instance.

        Arguments:
            output_columns (`list`, optional): List of strings specifying the columns to include
                in the output DataFrame. The default is `None`, which outputs all of the
                columns. Options include (not case sensitive):

                    * ``Temperature``
                    * ``Pressure``
                    * ``Ignition Delay``
                    * ``Composition``
                    * ``Equivalence Ratio``
                    * ``Reference``
                    * ``Apparatus``
                    * ``Experiment Type``
                    * ``File Author``
                    * ``File Version``
                    * ``ChemKED Version``

                In addition, specific fields from the ``Reference`` and ``Apparatus`` attributes can
                be included by specifying the name after a colon. These options are:

                    * ``Reference:Volume``
                    * ``Reference:Journal``
                    * ``Reference:DOI``
                    * ``Reference:Authors``
                    * ``Reference:Detail``
                    * ``Reference:Year``
                    * ``Reference:Pages``
                    * ``Apparatus:Kind``
                    * ``Apparatus:Facility``
                    * ``Apparatus:Institution``

                Only the first author is printed when ``Reference`` or ``Reference:Authors`` is
                selected because the whole author list may be quite long.

        Note:
            If the Composition is selected as an output type, the composition specified in the
            `DataPoint` is used. No attempt is made to convert to a consistent basis; mole fractions
            will remain mole fractions, mass fractions will remain mass fractions, and mole percent
            will remain mole percent. Therefore, it is possible to end up with more than one type of
            composition specification in a given column. However, if the composition is included
            in the resulting dataframe, the type of each composition will be specified by the "Kind"
            field in each row.

        Examples:
            >>> df = ChemKED(yaml_file).get_dataframe()
            >>> df = ChemKED(yaml_file).get_dataframe(['Temperature', 'Ignition Delay'])

        Returns:
            `~pandas.DataFrame`: Contains the information regarding each point in the ``datapoints``
                attribute
        """
        import pandas as pd

        valid_labels = [
            a.replace("_", " ")
            for a in self.__dict__
            if not (a.startswith("__") or a.startswith("_"))
        ]
        valid_labels.remove("datapoints")
        valid_labels.extend(
            [
                "composition",
                "ignition delay",
                "temperature",
                "pressure",
                "equivalence ratio",
            ]
        )
        ref_index = valid_labels.index("reference")
        valid_labels[ref_index : ref_index + 1] = ["reference:" + a for a in Reference._fields]
        app_index = valid_labels.index("apparatus")
        valid_labels[app_index : app_index + 1] = ["apparatus:" + a for a in Apparatus._fields]
        species_list = list(set(chain(*[list(d.composition.keys()) for d in self.datapoints])))

        if output_columns is None or len(output_columns) == 0:
            col_labels = valid_labels
            comp_index = col_labels.index("composition")
            col_labels[comp_index : comp_index + 1] = [*species_list, "Composition:Kind"]
        else:
            output_columns = [a.lower() for a in output_columns]
            col_labels = []
            for col in output_columns:
                if col in valid_labels or col in ["reference", "apparatus"]:
                    col_labels.append(col)
                else:
                    raise ValueError(f"{col} is not a valid output column choice")

            if "composition" in col_labels:
                comp_index = col_labels.index("composition")
                col_labels[comp_index : comp_index + 1] = [*species_list, "Composition:Kind"]
            if "reference" in col_labels:
                ref_index = col_labels.index("reference")
                col_labels[ref_index : ref_index + 1] = [
                    "reference:" + a for a in Reference._fields
                ]
            if "apparatus" in col_labels:
                app_index = col_labels.index("apparatus")
                col_labels[app_index : app_index + 1] = [
                    "apparatus:" + a for a in Apparatus._fields
                ]

        data = []
        for d in self.datapoints:
            row = []
            d_species = list(d.composition.keys())
            for col in col_labels:
                if col in species_list:
                    if col in d_species:
                        row.append(d.composition[col].amount)
                    else:
                        row.append(Q_(0.0, "dimensionless"))
                elif "reference" in col or "apparatus" in col:
                    split_col = col.split(":")
                    if split_col[1] == "authors":
                        row.append(getattr(getattr(self, split_col[0]), split_col[1])[0]["name"])
                    else:
                        row.append(getattr(getattr(self, split_col[0]), split_col[1]))
                elif col in [
                    "temperature",
                    "pressure",
                    "ignition delay",
                    "equivalence ratio",
                ]:
                    row.append(getattr(d, col.replace(" ", "_")))
                elif col == "file authors":
                    row.append(getattr(self, col.replace(" ", "_"))[0]["name"])
                elif col == "Composition:Kind":
                    row.append(d.composition_type)
                else:
                    row.append(getattr(self, col.replace(" ", "_")))
            data.append(row)

        col_labels = [a.title() for a in col_labels]
        columns = pd.Index(col_labels)
        return pd.DataFrame(data=data, columns=columns)

    def write_file(self, filename, *, overwrite=False):
        """Write new ChemKED YAML file based on object.

        Arguments:
            filename (`str`): Filename for target YAML file
            overwrite (`bool`, optional): Whether to overwrite file with given name if present.
                Must be supplied as a keyword-argument.

        Raises:
            `NameError`: If ``filename`` is already present, and ``overwrite`` is not ``True``.

        Example:
            >>> dataset = ChemKED(yaml_file)
            >>> dataset.write_file(new_yaml_file)
        """
        # Ensure file isn't already present
        if Path(filename).exists() and not overwrite:
            raise OSError(
                str(filename)
                + ' already present. Specify "overwrite=True" to overwrite, or rename.'
            )

        with open(filename, "w", encoding="utf-8") as yaml_file:
            yaml.dump(self._properties, yaml_file)

    def convert_to_ReSpecTh(self, filename):
        """Convert ChemKED record to ReSpecTh XML file.

        This converter uses common information in a ChemKED file to generate a
        ReSpecTh XML file. Note that some information may be lost, as ChemKED stores
        some additional attributes.

        Ignition delay and speciation measurement files can be converted. A speciation
        measurement is written as whichever of the four ReSpecTh speciation types fits its
        apparatus and swept axis; see `_speciation_to_ReSpecTh`.

        Arguments:
            filename (`str`): Filename for output ReSpecTh XML file.

        Example:
            >>> dataset = ChemKED(yaml_file)
            >>> dataset.convert_to_ReSpecTh(xml_file)
        """
        if self.experiment_type == "speciation measurement":
            root = self._speciation_to_ReSpecTh()
            # Indent for reading, but keep each dataPoint on one line as ReSpecTh files do, since
            # a profile can run to hundreds of rows
            etree.indent(root, space="    ")
            for point in root.iter("dataPoint"):
                point.text = None
                for value in point:
                    value.tail = None
            etree.ElementTree(root).write(filename, encoding="utf-8", xml_declaration=True)
            print("Converted to " + str(filename))
            return

        root = etree.Element("experiment")

        file_author = etree.SubElement(root, "fileAuthor")
        file_author.text = self.file_authors[0]["name"]

        # right now ChemKED just uses an integer file version
        file_version = etree.SubElement(root, "fileVersion")
        major_version = etree.SubElement(file_version, "major")
        major_version.text = str(self.file_version)
        minor_version = etree.SubElement(file_version, "minor")
        minor_version.text = "0"

        respecth_version = etree.SubElement(root, "ReSpecThVersion")
        major_version = etree.SubElement(respecth_version, "major")
        major_version.text = "1"
        minor_version = etree.SubElement(respecth_version, "minor")
        minor_version.text = "0"

        # Speciation measurements were handled above
        exp = etree.SubElement(root, "experimentType")
        if self.experiment_type == "ignition delay":
            exp.text = "Ignition delay measurement"
        else:
            raise NotImplementedError(
                "Only ignition delay and speciation measurement types supported for conversion."
            )

        reference = etree.SubElement(root, "bibliographyLink")
        citation = (
            f"{', '.join(a['name'] for a in self.reference.authors)}, "
            f"{self.reference.journal} ({self.reference.year}) "
            f"{self.reference.volume}:{self.reference.pages}. {self.reference.detail}"
        )
        reference.set("preferredKey", citation)
        reference.set("doi", self.reference.doi)

        apparatus = etree.SubElement(root, "apparatus")
        kind = etree.SubElement(apparatus, "kind")
        kind.text = self.apparatus.kind

        common_properties = etree.SubElement(root, "commonProperties")
        # ChemKED objects have no common properties once loaded. Check for properties
        # among datapoints that tend to be common
        common = []
        composition = self.datapoints[0].composition

        # Composition type *has* to be the same
        composition_type = self.datapoints[0].composition_type
        if not all(dp.composition_type == composition_type for dp in self.datapoints):
            raise NotImplementedError(
                "Error: ReSpecTh does not support varying composition type among datapoints."
            )

        if all(composition == dp.composition for dp in self.datapoints):
            # initial composition is common
            common.append("composition")
            prop = etree.SubElement(common_properties, "property")
            prop.set("name", "initial composition")

            for species_name, species in composition.items():
                component = etree.SubElement(prop, "component")
                species_link = etree.SubElement(component, "speciesLink")
                species_link.set("preferredKey", species_name)
                if species.InChI is not None:
                    species_link.set("InChI", species.InChI)

                amount = etree.SubElement(component, "amount")
                amount.set("units", composition_type)
                amount.text = str(species.amount.magnitude)

        # If multiple datapoints present, then find any common properties. If only
        # one datapoint, then composition should be the only "common" property.
        if len(self.datapoints) > 1:
            for prop_name in datagroup_properties:
                attribute = prop_name.replace(" ", "_")
                quantities = [getattr(dp, attribute, False) for dp in self.datapoints]

                # All quantities must have the property in question and all the
                # values must be equal
                if all(quantities) and quantities.count(quantities[0]) == len(quantities):
                    common.append(prop_name)
                    prop = etree.SubElement(common_properties, "property")
                    prop.set("description", "")
                    prop.set("name", prop_name)
                    prop.set("units", str(quantities[0].units))  # type: ignore[union-attr]

                    value = etree.SubElement(prop, "value")
                    value.text = str(quantities[0].magnitude)  # type: ignore[union-attr]

        # Ignition delay can't be common, unless only a single datapoint.

        datagroup = etree.SubElement(root, "dataGroup")
        datagroup.set("id", "dg1")
        datagroup_link = etree.SubElement(datagroup, "dataGroupLink")
        datagroup_link.set("dataGroupID", "")
        datagroup_link.set("dataPointID", "")

        property_idx: dict[str, Any] = {}
        labels = {
            "temperature": "T",
            "pressure": "P",
            "ignition delay": "tau",
            "pressure rise": "dP/dt",
        }

        for prop_name in datagroup_properties:
            attribute = prop_name.replace(" ", "_")
            # This can't be hasattr because properties are set to the value None
            # if no value is specified in the file, so the attribute always exists
            prop_indices = [
                i for i, dp in enumerate(self.datapoints) if getattr(dp, attribute) is not None
            ]
            if prop_name in common or not prop_indices:
                continue

            prop = etree.SubElement(datagroup, "property")
            prop.set("description", "")
            prop.set("name", prop_name)
            units = str(getattr(self.datapoints[prop_indices[0]], attribute).units)
            prop.set("units", units)
            idx = f"x{len(property_idx) + 1}"
            property_idx[idx] = {"name": prop_name, "units": units}
            prop.set("id", idx)
            prop.set("label", labels[prop_name])

        # Need to handle datapoints with possibly different species in the initial composition
        if "composition" not in common:
            for dp in self.datapoints:
                for species in dp.composition.values():
                    # Only add new property for species not already considered
                    has_spec = any(
                        species.species_name in d.values() for d in property_idx.values()
                    )
                    if not has_spec:
                        prop = etree.SubElement(datagroup, "property")
                        prop.set("description", "")

                        idx = f"x{len(property_idx) + 1}"
                        property_idx[idx] = {"name": species.species_name}
                        prop.set("id", idx)
                        prop.set("label", "[" + species.species_name + "]")
                        prop.set("name", "composition")
                        prop.set("units", self.datapoints[0].composition_type)

                        species_link = etree.SubElement(prop, "speciesLink")
                        species_link.set("preferredKey", species.species_name)
                        if species.InChI is not None:
                            species_link.set("InChI", species.InChI)

        for dp in self.datapoints:
            datapoint = etree.SubElement(datagroup, "dataPoint")
            for idx, val in property_idx.items():
                # handle regular properties a bit differently than composition
                if val["name"] in datagroup_properties:
                    value = etree.SubElement(datapoint, idx)
                    quantity = getattr(dp, val["name"].replace(" ", "_")).to(val["units"])
                    value.text = str(quantity.magnitude)
                else:
                    # composition
                    for item in dp.composition.values():
                        if item.species_name == val["name"]:
                            value = etree.SubElement(datapoint, idx)
                            value.text = str(item.amount.magnitude)

        # See https://stackoverflow.com/a/16097112 for the None.__ne__
        history_types = [
            "volume_history",
            "temperature_history",
            "pressure_history",
            "piston_position_history",
            "light_emission_history",
            "OH_emission_history",
            "absorption_history",
        ]
        time_histories = [getattr(dp, p) for dp in self.datapoints for p in history_types]
        time_histories = [th for th in time_histories if th is not None]

        if len(self.datapoints) > 1 and len(time_histories) > 1:
            raise NotImplementedError(
                "Error: ReSpecTh files do not support multiple datapoints with a time history."
            )
        elif len(time_histories) > 0:
            for dg_idx, hist in enumerate(time_histories):
                if hist.type not in ["volume", "temperature", "pressure"]:
                    warn(
                        f"The time-history type {hist.type} is not supported by ReSpecTh for "
                        "ignition delay experiments"
                    )
                    continue

                datagroup = etree.SubElement(root, "dataGroup")
                datagroup.set("id", f"dg{dg_idx}")
                datagroup_link = etree.SubElement(datagroup, "dataGroupLink")
                datagroup_link.set("dataGroupID", "")
                datagroup_link.set("dataPointID", "")

                # Time history has two properties: time and quantity.
                prop = etree.SubElement(datagroup, "property")
                prop.set("description", "")
                prop.set("name", "time")
                prop.set("units", str(hist.time.units))
                time_idx = f"x{len(property_idx) + 1}"
                property_idx[time_idx] = {"name": "time"}
                prop.set("id", time_idx)
                prop.set("label", "t")

                prop = etree.SubElement(datagroup, "property")
                prop.set("description", "")
                prop.set("name", hist.type)
                prop.set("units", str(hist.quantity.units))
                quant_idx = f"x{len(property_idx) + 1}"
                property_idx[quant_idx] = {"name": hist.type}
                prop.set("id", quant_idx)
                prop.set("label", "V")

                for time, quantity in zip(hist.time, hist.quantity):
                    datapoint = etree.SubElement(datagroup, "dataPoint")
                    value = etree.SubElement(datapoint, time_idx)
                    value.text = str(time.magnitude)
                    value = etree.SubElement(datapoint, quant_idx)
                    value.text = str(quantity.magnitude)

        ign_types = [getattr(dp, "ignition_type", False) for dp in self.datapoints]
        # All datapoints must have the same ignition target and type
        if all(ign_types) and ign_types.count(ign_types[0]) == len(ign_types):
            # In ReSpecTh files all datapoints must share ignition type
            ignition = etree.SubElement(root, "ignitionType")
            if ign_types[0]["target"] in ["pressure", "temperature"]:  # type: ignore[index]
                ignition.set("target", ign_types[0]["target"][0].upper())  # type: ignore[index]
            else:
                # options left are species
                ignition.set("target", self.datapoints[0].ignition_type["target"])
            if ign_types[0]["type"] == "d/dt max extrapolated":  # type: ignore[index]
                ignition.set("type", "baseline max intercept from d/dt")
            else:
                ignition.set("type", self.datapoints[0].ignition_type["type"])
        else:
            raise NotImplementedError(
                "Different ignition targets or types for multiple datapoints "
                "are not supported in ReSpecTh."
            )

        et = etree.ElementTree(root)
        et.write(filename, encoding="utf-8", xml_declaration=True)

        # now do a "pretty" rewrite
        xml = minidom.parse(str(filename))
        xml_string = xml.toprettyxml(indent="    ")
        with open(filename, "w", encoding="utf-8") as f:
            f.write(xml_string)

        print("Converted to " + str(filename))

    def _speciation_to_ReSpecTh(self):
        """Build the ReSpecTh experiment for a speciation measurement.

        The inverse of `~pyked.converters.get_speciation_datapoints`: each datapoint becomes a
        dataGroup, with the independent variables, the concentration and auxiliary profiles, and
        the per-row uncertainties as its columns. A per-row uncertainty is written as an absolute
        uncertainty in the units of its profile, which is how a ChemKED row states it. Conditions
        every datapoint shares, the initial composition, and the uncertainties that describe a
        whole profile or quantity become common properties.

        `DataPoint` does not model profiles, so they are read from the mapping the instance was
        built from.

        Note:
            ReSpecTh has no place for the ORCID of an author, for more than one file author
            (their names are joined into one), for the apparatus institution and facility, or for
            the atomic composition and thermo of a species.

        Returns:
            `~xml.etree.ElementTree.Element`: The ReSpecTh ``experiment`` element

        Raises:
            `NotImplementedError`: If the measurement cannot be stated in one ReSpecTh file, as
                for datapoints with different initial compositions or time shifts, or profiles
                of one datapoint that are sampled at different points
        """
        datapoints = self._properties["datapoints"]
        experiment_type = _speciation_experiment_type(self.apparatus.kind, datapoints)
        common = _speciation_common_properties(self._properties)
        shared_profiles, shared_conditions = _shared_uncertainties(datapoints, common)

        root = etree.Element("experiment")
        etree.SubElement(root, "fileAuthor").text = "; ".join(
            author["name"] for author in self.file_authors
        )

        # right now ChemKED just uses an integer file version
        file_version = etree.SubElement(root, "fileVersion")
        etree.SubElement(file_version, "major").text = str(self.file_version)
        etree.SubElement(file_version, "minor").text = "0"

        # The speciation types and the bibliographic details are ReSpecTh 2 elements
        respecth_version = etree.SubElement(root, "ReSpecThVersion")
        etree.SubElement(respecth_version, "major").text = "2"
        etree.SubElement(respecth_version, "minor").text = "3"

        root.append(_respecth_bibliography(self.reference))
        etree.SubElement(root, "experimentType").text = experiment_type

        apparatus = etree.SubElement(root, "apparatus")
        kind, modes = respecth_speciation_apparatus[self.apparatus.kind]
        etree.SubElement(apparatus, "kind").text = kind
        for mode in modes:
            etree.SubElement(apparatus, "mode").text = mode

        _add_speciation_common_properties(
            root, datapoints, common, shared_profiles, shared_conditions
        )

        # ReSpecTh numbers columns across the whole file
        column_ids = count(1)
        for index, dp in enumerate(datapoints):
            _add_speciation_datagroup(
                root, dp, f"dg{index + 1}", column_ids, common, shared_profiles, shared_conditions
            )

        # ReSpecTh states the zero of a time axis once for the whole file
        shifts = [dp.get("time-shift") for dp in datapoints]
        if any(shift is not None for shift in shifts):
            shift = _shared_value(shifts)
            if shift is None:
                raise NotImplementedError(
                    "ReSpecTh states one time shift for the whole file, but the datapoints "
                    "have different ones."
                )
            timeshift = etree.SubElement(root, "timeshift")
            timeshift.set("target", shift["target"])
            timeshift.set("type", shift["type"])
            if shift.get("amount"):
                timeshift.set("amount", _split_value(shift["amount"][0])[0])

        for comment in self._properties.get("comments", []):
            etree.SubElement(root, "comment").text = comment

        return root


class DataPoint:
    """Class for a single datapoint.

    The `DataPoint` class stores the information associated with a single data point in the dataset
    parsed from the `ChemKED` YAML input.

    Arguments:
        properties (`dict`): Dictionary adhering to the ChemKED format for ``datapoints``

    Attributes:
        composition (`list`): List of dictionaries representing the species and their quantities
        ignition_delay (pint.Quantity): The ignition delay of the experiment
        temperature (pint.Quantity): The temperature of the experiment
        pressure (pint.Quantity): The pressure of the experiment
        pressure_rise (pint.Quantity, optional): The amount of pressure rise during the induction
            period of a shock tube experiment.
        compression_time (pint.Quantity, optional): The compression time for an RCM experiment.
        compressed_pressure (pint.Quantity, optional): The pressure at the end of compression for
            an RCM experiment.
        compressed_temperature (pint.Quantity, optional): The temperature at the end of compression
            for an RCM experiment.
        first_stage_ignition_delay (pint.Quantity, optional): The first stage ignition delay of the
            experiment.
        laminar_burning_velocity (pint.Quantity, optional): The laminar burning velocity of the
            experiment.
        ignition_type (`dict`): Dictionary with the ignition target and type.
        volume_history (`~collections.namedtuple`, optional): The volume history of the reactor
            during an RCM experiment.
        pressure_history (`~collections.namedtuple`, optional): The pressure history of the reactor
            during an experiment.
        temperature_history (`~collections.namedtuple`, optional): The temperature history of the
            reactor during an experiment.
        piston_position_history (`~collections.namedtuple`, optional): The piston position history
            of the reactor during an RCM experiment.
        light_emission_history (`~collections.namedtuple`, optional): The light emission history
            of the reactor during an experiment.
        OH_emission_history (`~collections.namedtuple`, optional): The OH emission history of the
            reactor during an experiment.
        absorption_history (`~collections.namedtuple`, optional): The absorption history of the
            reactor during an experiment.
        evaluated_standard_deviation (`dict`): Mapping of property name (with underscores,
            e.g. ``ignition_delay``) to the `EvaluatedStandardDeviation` given in the file
            for that property, for properties that specify one.
    """

    value_unit_props: ClassVar[list[str]] = [
        "ignition-delay",
        "first-stage-ignition-delay",
        "temperature",
        "pressure",
        "pressure-rise",
        "laminar-burning-velocity",
    ]

    rcm_data_props: ClassVar[list[str]] = [
        "compressed-pressure",
        "compressed-temperature",
        "compression-time",
        "stroke",
        "clearance",
        "compression-ratio",
    ]

    def __init__(self, properties):
        self.evaluated_standard_deviation: dict[str, EvaluatedStandardDeviation] = {}

        for prop in self.value_unit_props:
            if prop in properties:
                self._store_evaluated_standard_deviation(prop, properties[prop])
            if prop in properties:
                quant = self.process_quantity(properties[prop])
                setattr(self, prop.replace("-", "_"), quant)
            else:
                setattr(self, prop.replace("-", "_"), None)

        if "rcm-data" in properties:
            orig_rcm_data = properties["rcm-data"]
            rcm_props = {}
            for prop in self.rcm_data_props:
                if prop in orig_rcm_data:
                    self._store_evaluated_standard_deviation(prop, orig_rcm_data[prop])
                if prop in orig_rcm_data:
                    quant = self.process_quantity(orig_rcm_data[prop])
                    rcm_props[prop.replace("-", "_")] = quant
                else:
                    rcm_props[prop.replace("-", "_")] = None
            self.rcm_data: RCMData | None = RCMData(**rcm_props)
        else:
            self.rcm_data = None

        self.composition_type = properties["composition"]["kind"]
        composition = {}
        for species in properties["composition"]["species"]:
            species_name = species["species-name"]
            amount = self.process_quantity(species["amount"])
            InChI = species.get("InChI")
            SMILES = species.get("SMILES")
            atomic_composition = species.get("atomic-composition")
            composition[species_name] = Composition(
                species_name=species_name,
                InChI=InChI,
                SMILES=SMILES,
                atomic_composition=atomic_composition,
                amount=amount,
                amount_esd=self.process_evaluated_standard_deviation(species["amount"]),
            )

        self.composition = composition

        if "equivalence-ratio" in properties:
            self._store_evaluated_standard_deviation(
                "equivalence-ratio", properties["equivalence-ratio"]
            )
        self.equivalence_ratio = self.process_equivalence_ratio(
            properties.get("equivalence-ratio")
        )
        self.ignition_type = deepcopy(properties.get("ignition-type"))

        if "time-histories" in properties and "volume-history" in properties:
            raise TypeError("time-histories and volume-history are mutually exclusive")

        if "time-histories" in properties:
            for hist in properties["time-histories"]:
                if hasattr(self, "{}_history".format(hist["type"].replace(" ", "_"))):
                    raise ValueError(
                        "Each history type may only be specified once. {} was "
                        "specified multiple times".format(hist["type"])
                    )
                time_col = hist["time"]["column"]
                time_units = hist["time"]["units"]
                quant_col = hist["quantity"]["column"]
                quant_units = hist["quantity"]["units"]
                if isinstance(hist["values"], list):
                    values = np.array(hist["values"])
                else:
                    # Load the values from a file
                    values = np.genfromtxt(hist["values"]["filename"], delimiter=",")

                time_history = TimeHistory(
                    time=Q_(values[:, time_col], time_units),
                    quantity=Q_(values[:, quant_col], quant_units),
                    type=hist["type"],
                )

                setattr(
                    self,
                    "{}_history".format(hist["type"].replace(" ", "_")),
                    time_history,
                )

        if "volume-history" in properties:
            warn(
                "The volume-history field should be replaced by time-histories. "
                "volume-history will be removed after PyKED 0.4",
                DeprecationWarning,
            )
            time_col = properties["volume-history"]["time"]["column"]
            time_units = properties["volume-history"]["time"]["units"]
            volume_col = properties["volume-history"]["volume"]["column"]
            volume_units = properties["volume-history"]["volume"]["units"]
            values = np.array(properties["volume-history"]["values"])
            self.volume_history = VolumeHistory(
                time=Q_(values[:, time_col], time_units),
                volume=Q_(values[:, volume_col], volume_units),
            )

        history_types = [
            "volume",
            "temperature",
            "pressure",
            "piston_position",
            "light_emission",
            "OH_emission",
            "absorption",
        ]
        for h in history_types:
            if not hasattr(self, f"{h}_history"):
                setattr(self, f"{h}_history", None)

    def process_evaluated_standard_deviation(self, properties):
        """Extract evaluated-standard-deviation metadata from a quantity list.

        Arguments:
            properties (`list`): List in the value-unit format, whose metadata
                mapping (if any) may contain evaluated-standard-deviation fields.

        Returns:
            `EvaluatedStandardDeviation` or `None`: The evaluated standard
            deviation, or `None` when the metadata does not include one.
        """
        if not isinstance(properties, list):
            return None

        if len(properties) > 1 and isinstance(properties[1], dict):
            metadata = properties[1]
        else:
            return None

        esd = metadata.get("evaluated-standard-deviation")
        if esd is None:
            return None

        esd_type = metadata.get("evaluated-standard-deviation-type")
        if esd_type == "absolute":
            value = Q_(_normalize_unit_str(esd))
        else:
            value = float(Q_(_normalize_unit_str(esd)).magnitude)

        return EvaluatedStandardDeviation(
            value=value,
            type=esd_type,
            sourcetype=metadata.get("evaluated-standard-deviation-sourcetype"),
            method=metadata.get("evaluated-standard-deviation-method"),
        )

    def _store_evaluated_standard_deviation(self, prop, properties):
        """Store the evaluated standard deviation of a property, if one is given."""
        esd = self.process_evaluated_standard_deviation(properties)
        if esd is not None:
            self.evaluated_standard_deviation[prop.replace("-", "_")] = esd

    def process_quantity(self, properties):
        """Process the uncertainty information from a given quantity and return it"""
        quant = Q_(_normalize_unit_str(properties[0]))
        if len(properties) > 1:
            unc = properties[1]
            uncertainty = unc.get("uncertainty")
            upper_uncertainty = unc.get("upper-uncertainty")
            lower_uncertainty = unc.get("lower-uncertainty")
            uncertainty_type = unc.get("uncertainty-type")

            has_uncertainty_value = (
                uncertainty is not None
                or upper_uncertainty is not None
                or lower_uncertainty is not None
            )

            if uncertainty_type is None:
                if has_uncertainty_value:
                    raise ValueError('uncertainty-type must be one of "absolute" or "relative"')
                return quant

            if not has_uncertainty_value:
                if unc.get("evaluated-standard-deviation") is not None:
                    # Only evaluated-standard-deviation metadata accompanies the
                    # uncertainty-type label; there is no uncertainty to attach
                    # to the quantity.
                    return quant
                raise ValueError(
                    'Either "uncertainty" or "upper-uncertainty" and '
                    '"lower-uncertainty" need to be specified.'
                )

            if uncertainty_type == "relative":
                if uncertainty is not None:
                    quant = quant.plus_minus(float(uncertainty), relative=True)
                elif upper_uncertainty is not None and lower_uncertainty is not None:
                    warn(
                        "Asymmetric uncertainties are not supported. The "
                        "maximum of lower-uncertainty and upper-uncertainty "
                        "has been used as the symmetric uncertainty."
                    )
                    uncertainty = max(float(upper_uncertainty), float(lower_uncertainty))
                    quant = quant.plus_minus(uncertainty, relative=True)
                else:
                    raise ValueError(
                        'Either "uncertainty" or "upper-uncertainty" and '
                        '"lower-uncertainty" need to be specified.'
                    )
            elif uncertainty_type == "absolute":
                if uncertainty is not None:
                    uncertainty = Q_(_normalize_unit_str(uncertainty))
                    quant = quant.plus_minus(uncertainty.to(quant.units).magnitude)
                elif upper_uncertainty is not None and lower_uncertainty is not None:
                    warn(
                        "Asymmetric uncertainties are not supported. The "
                        "maximum of lower-uncertainty and upper-uncertainty "
                        "has been used as the symmetric uncertainty."
                    )
                    uncertainty = max(
                        Q_(_normalize_unit_str(upper_uncertainty)),
                        Q_(_normalize_unit_str(lower_uncertainty)),
                    )
                    quant = quant.plus_minus(uncertainty.to(quant.units).magnitude)
                else:
                    raise ValueError(
                        'Either "uncertainty" or "upper-uncertainty" and '
                        '"lower-uncertainty" need to be specified.'
                    )
            else:
                raise ValueError('uncertainty-type must be one of "absolute" or "relative"')

        return quant

    def process_equivalence_ratio(self, properties):
        """Process equivalence ratio while preserving the historic scalar API."""
        if properties is None:
            return None

        if isinstance(properties, list):
            if len(properties) == 0:
                return None
            quant = self.process_quantity(properties)
        else:
            quant = Q_(_normalize_unit_str(properties))

        return quant.to("dimensionless").magnitude

    def get_cantera_composition_string(self, species_conversion=None):
        """Get the composition in a string format suitable for input to Cantera.

        Returns a formatted string no matter the type of composition. As such, this method
        is not recommended for end users; instead, prefer the `get_cantera_mole_fraction`
        or `get_cantera_mass_fraction` methods.

        Arguments:
            species_conversion (`dict`, optional): Mapping of species identifier to a
                species name. This argument should be supplied when the name of the
                species in the ChemKED YAML file does not match the name of the same
                species in a chemical kinetic mechanism. The species identifier (the key
                of the mapping) can be the name, InChI, or SMILES provided in the ChemKED
                file, while the value associated with a key should be the desired name in
                the Cantera format output string.

        Returns:
            `str`: String in the ``SPEC:AMT, SPEC:AMT`` format

        Raises:
            `ValueError`: If the composition type of the `DataPoint` is not one of
                ``'mass fraction'``, ``'mole fraction'``, or ``'mole percent'``
        """
        if self.composition_type in ["mole fraction", "mass fraction"]:
            factor = 1.0
        elif self.composition_type == "mole percent":
            factor = 100.0
        else:
            raise ValueError(f"Unknown composition type: {self.composition_type}")

        if species_conversion is None:
            comps = [
                f"{c.species_name!s}:{c.amount.magnitude / factor:.4e}"
                for c in self.composition.values()
            ]
        else:
            comps = []
            for c in self.composition.values():
                amount = c.amount.magnitude / factor
                idents = [getattr(c, s, False) for s in ["species_name", "InChI", "SMILES"]]
                present = [i in species_conversion for i in idents]
                if not any(present):
                    comps.append(f"{c.species_name!s}:{amount:.4e}")
                else:
                    if len([i for i in present if i]) > 1:
                        raise ValueError(
                            f"More than one conversion present for species {c.species_name}"
                        )

                    ident = idents[present.index(True)]
                    species_replacement_name = species_conversion.pop(ident)
                    comps.append(f"{species_replacement_name!s}:{amount:.4e}")

            if len(species_conversion) > 0:
                raise ValueError(f"Unknown species in conversion: {species_conversion}")

        return ", ".join(comps)

    def get_cantera_mole_fraction(self, species_conversion=None):
        """Get the mole fractions in a string format suitable for input to Cantera.

        Arguments:
            species_conversion (`dict`, optional): Mapping of species identifier to a
                species name. This argument should be supplied when the name of the
                species in the ChemKED YAML file does not match the name of the same
                species in a chemical kinetic mechanism. The species identifier (the key
                of the mapping) can be the name, InChI, or SMILES provided in the ChemKED
                file, while the value associated with a key should be the desired name in
                the Cantera format output string.

        Returns:
            `str`: String of mole fractions in the ``SPEC:AMT, SPEC:AMT`` format

        Raises:
            `ValueError`: If the composition type is ``'mass fraction'``, the conversion cannot
                be done because no molecular weight information is known

        Examples:
            >>> dp = DataPoint(properties)
            >>> dp.get_cantera_mole_fraction()
            'H2:4.4400e-03, O2:5.5600e-03, Ar:9.9000e-01'
            >>> species_conversion = {'H2': 'h2', 'O2': 'o2'}
            >>> dp.get_cantera_mole_fraction(species_conversion)
            'h2:4.4400e-03, o2:5.5600e-03, Ar:9.9000e-01'
            >>> species_conversion = {'1S/H2/h1H': 'h2', '1S/O2/c1-2': 'o2'}
            >>> dp.get_cantera_mole_fraction(species_conversion)
            'h2:4.4400e-03, o2:5.5600e-03, Ar:9.9000e-01'
        """
        if self.composition_type == "mass fraction":
            raise ValueError(
                f"Cannot get mole fractions from the given composition.\n{self.composition}"
            )
        else:
            return self.get_cantera_composition_string(species_conversion)

    def get_cantera_mass_fraction(self, species_conversion=None):
        """Get the mass fractions in a string format suitable for input to Cantera.

        Arguments:
            species_conversion (`dict`, optional): Mapping of species identifier to a
                species name. This argument should be supplied when the name of the
                species in the ChemKED YAML file does not match the name of the same
                species in a chemical kinetic mechanism. The species identifier (the key
                of the mapping) can be the name, InChI, or SMILES provided in the ChemKED
                file, while the value associated with a key should be the desired name in
                the Cantera format output string.

        Returns:
            `str`: String of mass fractions in the ``SPEC:AMT, SPEC:AMT`` format

        Raises:
            `ValueError`: If the composition type is ``'mole fraction'`` or
                ``'mole percent'``, the conversion cannot be done because no molecular
                weight information is known

        Examples:
            >>> dp = DataPoint(properties)
            >>> dp.get_cantera_mass_fraction()
            'H2:2.2525e-04, O2:4.4775e-03, Ar:9.9530e-01'
            >>> species_conversion = {'H2': 'h2', 'O2': 'o2'}
            >>> dp.get_cantera_mass_fraction(species_conversion)
            'h2:2.2525e-04, o2:4.4775e-03, Ar:9.9530e-01'
            >>> species_conversion = {'1S/H2/h1H': 'h2', '1S/O2/c1-2': 'o2'}
            >>> dp.get_cantera_mass_fraction(species_conversion)
            'h2:2.2525e-04, o2:4.4775e-03, Ar:9.9530e-01'
        """
        if self.composition_type in ["mole fraction", "mole percent"]:
            raise ValueError(
                f"Cannot get mass fractions from the given composition.\n{self.composition}"
            )
        else:
            return self.get_cantera_composition_string(species_conversion)
