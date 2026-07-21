"""Main ChemKED module"""

# Standard libraries
import xml.dom.minidom as minidom
import xml.etree.ElementTree as etree
from copy import deepcopy
from itertools import chain
from pathlib import Path
from typing import Any, ClassVar, NamedTuple
from warnings import warn

import numpy as np
import pint

from .converters import ReSpecTh_to_ChemKED, datagroup_properties

# Local imports
from .validation import Q_, OurValidator, _normalize_unit_str, schema, yaml


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
            with open(yaml_file) as f:
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

        with open(filename, "w") as yaml_file:
            yaml.dump(self._properties, yaml_file)

    def convert_to_ReSpecTh(self, filename):
        """Convert ChemKED record to ReSpecTh XML file.

        This converter uses common information in a ChemKED file to generate a
        ReSpecTh XML file. Note that some information may be lost, as ChemKED stores
        some additional attributes.

        Arguments:
            filename (`str`): Filename for output ReSpecTh XML file.

        Example:
            >>> dataset = ChemKED(yaml_file)
            >>> dataset.convert_to_ReSpecTh(xml_file)
        """
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

        # Only ignition delay currently supported
        exp = etree.SubElement(root, "experimentType")
        if self.experiment_type == "ignition delay":
            exp.text = "Ignition delay measurement"
        else:
            raise NotImplementedError("Only ignition delay type supported for conversion.")

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
        with open(filename, "w") as f:
            f.write(xml_string)

        print("Converted to " + str(filename))


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
