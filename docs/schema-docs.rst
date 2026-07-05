.. Complete documentation for the schema

Schema Documentation
====================

This document contains the complete specification for the ChemKED schema. The schema is broken into
several files for ease of maintenance. These files are combined with the custom ``!include``
directive that has been added for this purpose. Note that ``!include`` should only be used in the
main schema file (``chemked_schema.yaml``) and must appear at the top of the file. The ``!include``
directive is **not** supported in any actual ChemKED files.

Examples of constructing a ChemKED format file, as well as examples of files themselves, are located
in :doc:`ck-tutorial`. The sections laid out in this file roughly correspond to the sections
discussed in the tutorial.

.. contents::
    :local:

.. _meta-keys:

Meta Keys
---------

The keys in this section encode the "meta" information about the ChemKED file. All of the keys in
this section are required in every ChemKED file.

.. _meta-chemked-version:

* ``chemked-version``: string, required
    A string with the version of the ChemKED schema that this file targets.

.. _meta-datapoints:

* ``datapoints``: sequence, required
    A sequence of mappings representing the data encoded in the file. Each element of the sequence
    must conform to the schema described in :ref:`ignition-delay-keys` (for now).

.. _meta-file-version:

* ``file-version``: integer, required
    An integer that represents the version of the file. Should be incremented every time a change is
    committed to a file in the database.

.. _meta-file-authors:

* ``file-authors``: sequence, required
    The author(s) of the ChemKED file, which may be different from the authors of the referenced
    work. Elements of the sequence must be mappings that conform to the
    :ref:`author <schema-author>` schema.

.. _reference-keys:

Reference Keys
--------------

The keys in this section are related to the reference for the experiment, the article where the data
is published, and the apparatus used to conduct the experiment. All the top-level keys in this
section are required, although some of the sub-keys are optional.

.. _reference-apparatus:

* ``apparatus``: mapping, required
    This mapping provides information about the apparatus used to conduct the experiments. Fields:

    - ``kind``: string, required
        Must be one of ``shock tube``, ``rapid compression machine``, ``stirred reactor``, ``jet stirred reactor``, ``tubular reactor``, ``flow reactor``, ``burner stabilized flame``, ``counterflow flame``, ``heat flux burner``, ``bunsen burner``, or ``outwardly propagating spherical flame``. Values are case-sensitive.

    - ``institution``: string, optional
        The institution where the experimental apparatus is located

    - ``facility``: string, optional
        A unique name or identifier for the apparatus, if the institution has several that are
        similar

.. _reference-experiment-type:

* ``experiment-type``: string, required
    The type of experiment encoded in this file. Must be one of the following case-sensitive
    values:

        * ``ignition delay``
        * ``laminar burning velocity measurement``
        * ``speciation measurement``

.. _reference-reference:

* ``reference``: mapping, required
    The reference contains the information about the article where the data in the file are
    published. Fields:

    - ``journal``: string, optional
        The journal where the data are published

    - ``year``: integer, required
        The year of publication. Must be greater than 1600.

    - ``authors``: sequence, required
        A sequence of all the authors of the article, where the elements of the sequence are
        mappings that must conform to the :ref:`author <schema-author>` type.

    - ``volume``: integer, optional
        The volume of the publication. Must be greater than 0.

    - ``doi``: string, optional
        A DOI, if available.

    - ``detail``: string, optional
        A description of where in the article the data in this file are from, for instance, a figure
        or table number.

    - ``pages``: string, optional
        The pages in the journal where the article is published (not the pages where the data are
        located, that would go in the ``detail`` field.)

.. _common-property-keys:

Common Property Keys
--------------------

The keys in this section can be specified as sub-keys of the the ``common-properties`` top-level
key, and reused in many different data points within a single ChemKED file. All of the keys in the
``common-properties`` section are optional, although some of their values may be required in a
particular experiment type.

.. _common-pressure-rise:

* ``pressure-rise``: sequence, optional
    Has the same format as :ref:`pressure-rise <ignition-pressure-rise>`

.. _common-pressure:

* ``pressure``: sequence, optional
    The pressure of the experiment, with dimensions of mass per length per time squared. Must
    conform to :ref:`value-unit-optional <schema-value-unit-optional>`

.. _common-temperature:

* ``temperature``: sequence, optional
    The temperature of the experiment, with dimensions of temperature. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`

.. _common-ignition-type:

* ``ignition-type``: mapping, optional
    Has the same schema as :ref:`ignition-type <ignition-ignition-type>`

.. _common-ignition-delay:

* ``ignition-delay``: sequence, optional
    The ignition delay measurement, with dimensions of time. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`

.. _common-equivalence-ratio:

* ``equivalence-ratio``: sequence, optional
    The equivalence ratio of the experiment, dimensionless. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`

.. _common-laminar-burning-velocity:

* ``laminar-burning-velocity``: sequence, optional
    The laminar burning velocity measurement, with dimensions of length per time. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`

.. _common-residence-time:

* ``residence-time``: sequence, optional
    The residence time in a flow/jet-stirred reactor experiment, with dimensions of time. Must
    conform to :ref:`value-unit-optional <schema-value-unit-optional>`

.. _common-reactor-volume:

* ``reactor-volume``: sequence, optional
    The volume of the reactor, with dimensions of length cubed. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`

.. _common-reactor-length:

* ``reactor-length``: sequence, optional
    The length of the reactor, with dimensions of length. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`

.. _common-reactor-diameter:

* ``reactor-diameter``: sequence, optional
    The diameter of the reactor, with dimensions of length. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`

.. _common-flow-rate:

* ``flow-rate``: sequence, optional
    The flow rate through the reactor. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`

.. _common-environment-temperature:

* ``environment-temperature``: sequence, optional
    The temperature of the environment surrounding the reactor, with dimensions of temperature.
    Must conform to :ref:`value-unit-optional <schema-value-unit-optional>`

.. _common-global-heat-exchange-coefficient:

* ``global-heat-exchange-coefficient``: sequence, optional
    The global heat exchange coefficient between the reactor and its environment. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`

.. _common-exchange-area:

* ``exchange-area``: sequence, optional
    The heat exchange area between the reactor and its environment, with dimensions of length
    squared. Must conform to :ref:`value-unit-optional <schema-value-unit-optional>`

.. _common-pressure-in-reference-state:

* ``pressure-in-reference-state``: sequence, optional
    The pressure used to define the reference state for reported quantities, with dimensions of
    mass per length per time squared. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`

.. _common-temperature-in-reference-state:

* ``temperature-in-reference-state``: sequence, optional
    The temperature used to define the reference state for reported quantities, with dimensions of
    temperature. Must conform to :ref:`value-unit-optional <schema-value-unit-optional>`

.. _common-composition:

* ``composition``: mapping, optional
    This mapping provides the specification of the initial composition of the mixture. Fields:

    - ``kind``: string, required
        The ``kind`` can be ``mole fraction``, ``mass fraction``, ``mole percent``,
        ``mol/cm3``, ``mol/m3``, ``mol/L``, or ``mol/dm3``. Fraction kinds must be
        nonnegative, no greater than 1, and sum to 1. ``mole percent`` values must be
        nonnegative, no greater than 100, and sum to 100. Concentration-style kinds must be
        nonnegative and are not required to sum to a fixed total.

    - ``species``: sequence, required
        The elements of this sequence specify the species and their amounts in the mixture. Each
        element of the sequence is a mapping with the following keys:

        * ``species-name``: string, required
            The name of the species

        * ``InChI``: string, required, excludes ``SMILES``, ``atomic-composition``
            The InChI string for the species

        * ``SMILES``: string, required, excludes ``InChI``, ``atomic-composition``
            The SMILES string for the species

        * ``atomic-composition``: sequence, required, excludes ``InChI``, ``SMILES``
            A sequence of mappings representing the atoms that make up the species. Useful for
            species without SMILES or InChI representations, such as real hydrocarbon fuels. Each
            element of the sequence is a mapping with the following keys:

            - ``element``: string, required
                The name of the element

            - ``amount``: float, required, must be greater than 0.0
                The amount of the element

        * ``amount``: sequence, required
            A sequence conforming to either
            :ref:`value-with-uncertainty <schema-value-with-uncertainty>` or
            :ref:`value-without-uncertainty <schema-value-without-uncertainty>`, where the first
            element is a float representing the species amount (interpreted according to the
            parent ``kind``, e.g., mole fraction, mass fraction, or concentration units). The
            optional metadata mapping may additionally include the
            :ref:`evaluated-standard-deviation <schema-evaluated-standard-deviation>` fields.
            Because species amounts are unitless numbers, all uncertainty and
            evaluated-standard-deviation values must be plain floats (not strings with units).

.. _ignition-delay-keys:

Ignition Delay Keys
-------------------

This section details the schema for an autoignition delay measurement. This is one of the options
for the :ref:`datapoints <meta-datapoints>` schema.

.. _ignition-temperature:

* ``temperature``: sequence, required
    The temperature of the experiment, with dimensions of temperature. Must conform to
    :ref:`value-unit-required <schema-value-unit-required>`

.. _ignition-composition:

* ``composition``: mapping, required
    The composition of the experiment. Must conform to :ref:`composition <common-composition>`

.. _ignition-pressure:

* ``pressure``: sequence, required
    The pressure of the experiment, with dimensions of mass per length per time squared. Must
    conform to :ref:`value-unit-required <schema-value-unit-required>`

.. _ignition-ignition-type:

* ``ignition-type``: mapping, required
    A mapping describing how the ignition delay is defined in the experiments. Fields:

    - ``target``: string, required
        Describes the target measurement (species or physical quantity) used to define ignition.
        Must be one of: ``temperature``, ``pressure``, ``OH``, ``OH*``, ``CH``, ``CH*``, ``NH3``,
        ``CO2``, ``N2O``, ``CH4``, ``CO``, ``H2O``, ``C2``, ``O``,
        ``CH3OH``, ``CH3``, ``O2``, ``soot``.

    - ``type``: string, required
        Describes the type of ignition delay measurement. Can be one of:

            * ``d/dt max``: maximum of the time derivative of the ``target``
            * ``d/dt min extrapolated``: minimum slope of the ``target`` extrapolated to the
              baseline
            * ``d/dt max extrapolated``: maximum slope of the ``target`` extrapolated to the
              baseline
            * ``d/dt second max``: second maximum of the time derivative of the ``target``
            * ``max``: maximum of the ``target``
            * ``1/2 max``: half-maximum of the ``target``
            * ``min``: minimum of the ``target``
            * ``concentration``: the ``target`` reaches a specified concentration
            * ``relative concentration``: the ``target`` reaches a specified fraction of a
              reference concentration
            * ``relative increase``: the ``target`` increases by a specified amount relative to
              its initial value

    - ``amount``: float, optional
        A numeric threshold associated with the ignition ``type`` (for example, the concentration
        or relative-increase value used when ``type`` is ``concentration``, ``relative
        concentration``, or ``relative increase``).

.. _ignition-ignition-delay:

* ``ignition-delay``: sequence, required
    The ignition delay measurement, with dimensions of time. Must conform to
    :ref:`value-unit-required <schema-value-unit-required>`

.. _ignition-first-stage-ignition-delay:

* ``first-stage-ignition-delay``: sequence, optional
    If two stages of ignition are present, this is the value of the first stage of ignition, with
    dimensions of time. Must conform to :ref:`value-unit-optional <schema-value-unit-optional>`

.. _ignition-pressure-rise:

* ``pressure-rise``: sequence, optional
    The pressure rise after the passage of the reflected shock, with dimensions of inverse time.
    Must conform to :ref:`value-unit-optional <schema-value-unit-optional>`

.. _ignition-equivalence-ratio:

* ``equivalence-ratio``: sequence, optional
    The equivalence ratio of the experiment, dimensionless. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`.

.. _ignition-rcm-data:

* ``rcm-data``: mapping, optional
    Data related to rapid compression machine (RCM) experiments. The keys of the mapping are
    detailed in the :ref:`Rapid Compression Machine Data Keys <rcm-data-keys>` section.

.. _ignition-time-histories:

* ``time-histories``: sequence, optional
    A sequence of mappings conforming to the :ref:`time-history <ignition-time-history>`
    schema. Used to specify a time-varying history of one or more quantities during an experiment.

.. _ignition-volume-history:

* ``volume-history``: mapping, optional
    A legacy key for specifying a volume time-history for RCM experiments. New files should use
    :ref:`time-histories <ignition-time-histories>` with ``type: volume`` instead. Fields:

    - ``volume``: mapping, required
        Describes the volume column in the ``values`` array. Must contain ``units`` (string with
        dimensions of length cubed) and ``column`` (integer, 0 or 1).

    - ``time``: mapping, required
        Describes the time column in the ``values`` array. Must contain ``units`` (string with
        dimensions of time) and ``column`` (integer, 0 or 1).

    - ``values``: sequence, required
        A sequence of ``[time, volume]`` pairs of floats.

.. _rcm-data-keys:

Rapid Compression Machine Data Keys
-----------------------------------

This section details the keys specific to rapid compression machine (RCM) experiments, which are
subkeys of the :ref:`rcm-data <ignition-rcm-data>` key.

.. _rcm-data-compression-time:

* ``compression-time``: sequence, optional
    The time taken during the compression stroke of a rapid compression machine experiment, with
    dimensions of time. Must conform to :ref:`value-unit-optional <schema-value-unit-optional>`

.. _rcm-data-compressed-pressure:

* ``compressed-pressure``: sequence, optional
    The pressure at the end of the compression stroke for a rapid compression machine experiment,
    with dimensions of mass per length per time squared. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`

.. _rcm-data-compressed-temperature:

* ``compressed-temperature``: sequence, optional
    The temperature at the end of the compression stroke for a rapid compression machine experiment,
    with dimensions of temperature. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`

.. _rcm-data-compression-ratio:

* ``compression-ratio``: sequence, optional
    The dimensionless volumetric compression ratio for a rapid compression machine experiment. Must
    conform to :ref:`value-unit-optional <schema-value-unit-optional>`

.. _rcm-data-stroke:

* ``stroke``: sequence, optional
    The length of the stroke in a rapid compression machine experiment, with dimensions of length.
    Must conform to :ref:`value-unit-optional <schema-value-unit-optional>`

.. _rcm-data-clearance:

* ``clearance``: sequence, optional
    The clearance from the piston face to the end wall of the reaction chamber at the end of
    compression, with dimensions of length. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`

.. _laminar-burning-velocity-keys:

Laminar Burning Velocity Measurement Keys
-----------------------------------------

This section details the schema for a laminar burning velocity measurement datapoint, selected
when :ref:`experiment-type <reference-experiment-type>` is ``laminar burning velocity measurement``.

* ``temperature``: sequence, required
    Unburnt-mixture temperature, with dimensions of temperature. Must conform to
    :ref:`value-unit-required <schema-value-unit-required>`.

* ``pressure``: sequence, required
    Unburnt-mixture pressure, with dimensions of mass per length per time squared. Must conform
    to :ref:`value-unit-required <schema-value-unit-required>`.

* ``laminar-burning-velocity``: sequence, required
    The measured laminar burning velocity, with dimensions of length per time. Must conform to
    :ref:`value-unit-required <schema-value-unit-required>`.

* ``composition``: mapping, required
    The composition of the unburnt mixture. Must conform to
    :ref:`composition <common-composition>`.

* ``pressure-rise``: sequence, optional
    Rate of pressure rise during the measurement, with dimensions of inverse time. Must conform
    to :ref:`value-unit-optional <schema-value-unit-optional>`.

* ``equivalence-ratio``: sequence, optional
    The equivalence ratio of the experiment, dimensionless. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`.

.. _speciation-measurement-keys:

Speciation Measurement Keys
---------------------------

This section details the schema for a speciation measurement datapoint, selected when
:ref:`experiment-type <reference-experiment-type>` is ``speciation measurement``.

* ``pressure``: sequence, required
    The pressure of the experiment, with dimensions of mass per length per time squared. Must
    conform to :ref:`value-unit-required <schema-value-unit-required>`.

* ``temperature``: sequence, optional
    The inlet, initial, or local temperature, with dimensions of temperature. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`.

* ``composition``: mapping, optional
    The inlet or initial composition. Must conform to
    :ref:`composition <common-composition>`.

* ``equivalence-ratio``: sequence, optional
    The equivalence ratio of the experiment, dimensionless. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`.

* ``environment-temperature``: sequence, optional
    Temperature of the environment surrounding the reactor or burner. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`.

* ``residence-time``: sequence, optional
    Residence time in the reactor, with dimensions of time. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`.

* ``reactor-volume``: sequence, optional
    Reactor volume, with dimensions of length cubed. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`.

* ``reactor-length``: sequence, optional
    Reactor length, with dimensions of length. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`.

* ``reactor-diameter``: sequence, optional
    Reactor diameter, with dimensions of length. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`.

* ``flow-rate``: sequence, optional
    Flow rate through the reactor or burner. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`.

* ``volumetric-flow-in-reference-state``: sequence, optional
    Volumetric flow rate expressed in a defined reference state, with dimensions of length cubed
    per time. Must conform to :ref:`value-unit-optional <schema-value-unit-optional>`.

* ``pressure-in-reference-state``: sequence, optional
    Reference-state pressure for a volumetric flow measurement. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`.

* ``temperature-in-reference-state``: sequence, optional
    Reference-state temperature for a volumetric flow measurement. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`.

* ``global-heat-exchange-coefficient``: sequence, optional
    Global heat exchange coefficient, with dimensions of heat flux per temperature. Must conform
    to :ref:`value-unit-optional <schema-value-unit-optional>`.

* ``exchange-area``: sequence, optional
    Heat exchange area, with dimensions of area. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`.

* ``independent-variables``: sequence, required
    A sequence of mappings describing the independent variable columns. Each element has the
    following fields:

    - ``name``: string, required
        Must be one of ``temperature``, ``residence-time``, ``distance``, ``time``,
        ``equivalence-ratio``, ``initial-composition``, or ``pressure``.

    - ``units``: string, required
        Units for the independent variable values.

    - ``primary``: boolean, optional
        Indicates the primary swept variable.

    - ``species-name``: string, optional
        Identifies the swept inlet species when ``name`` is ``initial-composition``.

    - ``InChI``: string, optional
        The InChI string for the swept inlet species.

    - ``SMILES``: string, optional
        The SMILES string for the swept inlet species.

* ``concentration-profiles``: sequence, required
    A sequence of mappings, each describing measured values for a single species. Each element
    has the following fields:

    - ``species-name``: string, required
        The name of the measured species.

    - ``InChI``: string, optional
        The InChI string for the species.

    - ``SMILES``: string, optional
        The SMILES string for the species.

    - ``quantity``: mapping, required
        A mapping with a required ``units`` string describing the measured quantity.

    - ``values``: sequence, required
        A sequence of at least two rows. Each row contains one value for each
        ``independent-variables`` entry, followed by the measured amount, and optionally an
        uncertainty value.

    - ``uncertainty``: sequence, optional
        Metadata describing uncertainty for the profile values. Must conform to
        :ref:`value-metadata-only <schema-value-metadata-only>`.

* ``auxiliary-profiles``: sequence, optional
    A sequence of auxiliary measured profiles, such as temperature, pressure, volume, or
    velocity. Each profile includes an ``independent`` mapping, a ``quantity`` mapping, and
    ``values`` rows.

.. _schema-only-keys:

Schema-Only Keys
----------------

The schema files contain several keys that are used purely as references within the schema and
should not be used in actual ChemKED files. These keys are documented in this section.

.. _schema-author:

* ``author``: mapping
    Information about a single author, used in several contexts. Fields:

    - ``name``: string, required
        The author's full name

    - ``ORCID``: string, optional
        The author's ORCID identifier. Validated to be a valid ORCID and that the ``name`` matches

.. _schema-value-with-uncertainty:

* ``value-with-uncertainty``: sequence
    A combination of a value and unit with an associated uncertainty and/or evaluated standard
    deviation. Sequence elements:

    - 0: string or float, required
        The first element of the sequence is the value and its associated units (as a single
        string, e.g., ``"1000.0 K"``) or a bare float. The units are validated to have appropriate
        dimensions for the particular quantity under consideration.

    - 1: mapping, optional
        The second element of the sequence is a mapping containing uncertainty and/or
        evaluated-standard-deviation metadata. Metadata labels such as ``uncertainty-type``,
        ``uncertainty-sourcetype``, ``evaluated-standard-deviation-type``,
        ``evaluated-standard-deviation-sourcetype``, and
        ``evaluated-standard-deviation-method`` must be accompanied by an actual
        ``uncertainty``, ``upper-uncertainty``/``lower-uncertainty``, or
        ``evaluated-standard-deviation`` value.

        - Uncertainty fields:

            * ``uncertainty-type``: string
                The type of uncertainty. Must be ``absolute`` or ``relative``. Required when
                ``uncertainty``, ``upper-uncertainty``, or ``lower-uncertainty`` is specified.

            * ``uncertainty``: string or float, excludes ``upper-uncertainty`` and ``lower-uncertainty``, requires ``uncertainty-type``
                The symmetric uncertainty of the value. If ``uncertainty-type`` is ``absolute``
                and a string is given, it must include units whose dimensions match the units of
                the value in the first element of the sequence.

            * ``upper-uncertainty``: string or float, excludes ``uncertainty``, requires ``lower-uncertainty`` and ``uncertainty-type``
                The upper value of an asymmetrical uncertainty. Due to limitations in the Python
                library, asymmetrical uncertainties aren't supported in PyKED, so the larger of
                ``upper-uncertainty`` and ``lower-uncertainty`` is used.

            * ``lower-uncertainty``: string or float, excludes ``uncertainty``, requires ``upper-uncertainty`` and ``uncertainty-type``
                The lower value of an asymmetrical uncertainty. Due to limitations in the Python
                library, asymmetrical uncertainties aren't supported in PyKED, so the larger of
                ``upper-uncertainty`` and ``lower-uncertainty`` is used.

            * ``uncertainty-sourcetype``: string, optional
                A label describing how the ``uncertainty`` value was obtained. Typical values
                include ``reported``, ``estimated``, ``calculated``, and ``digitized``. Must be
                accompanied by an uncertainty value.

        The mapping may also include the
        :ref:`evaluated-standard-deviation <schema-evaluated-standard-deviation>` fields, which
        may be combined with, or used independently of, the uncertainty fields above.

.. _schema-evaluated-standard-deviation:

* ``evaluated-standard-deviation``: mapping fields
    A group of optional fields describing a statistically evaluated standard deviation for a
    value (e.g., from a dataset-wide re-evaluation). These fields appear inside the metadata
    mapping of a :ref:`value-with-uncertainty <schema-value-with-uncertainty>` entry or a
    composition :ref:`amount <common-composition>` metadata mapping, and may be used with or
    without the uncertainty fields:

    * ``evaluated-standard-deviation``: string or float, optional
        The evaluated standard deviation value. If ``evaluated-standard-deviation-type`` is
        ``absolute`` for a unitful quantity, the value must include units whose dimensions match
        the quantity being described. Relative values and dimensionless absolute values may be
        plain floats.

    * ``evaluated-standard-deviation-type``: string, optional
        Must be ``absolute`` or ``relative``. Must be accompanied by an
        ``evaluated-standard-deviation`` value.

    * ``evaluated-standard-deviation-sourcetype``: string, optional
        A label describing how the evaluated standard deviation was obtained. Typical values
        include ``reported``, ``estimated``, ``calculated``, and ``digitized``. Must be
        accompanied by an ``evaluated-standard-deviation`` value.

    * ``evaluated-standard-deviation-method``: string, optional
        The method used to compute the evaluated standard deviation. Typical values include
        ``generic uncertainty``, ``combined from scatter and reported uncertainty``, and
        ``statistical scatter``. Must be accompanied by an ``evaluated-standard-deviation``
        value.

.. _schema-value-without-uncertainty:

* ``value-without-uncertainty``: sequence
    A combination of a value and unit without any uncertainty metadata. Sequence elements:

    - 0: string or float, required
        The first element of the sequence is the value and its associated units (as a single
        string, e.g., ``"1.0 atm"``) or a bare float. The units are validated to have appropriate
        dimensions for the particular quantity under consideration.

.. _schema-value-metadata-only:

* ``value-metadata-only``: sequence
    A metadata-only entry containing uncertainty and/or evaluated-standard-deviation fields but
    no measured value. Used in ``common-properties`` when the uncertainty metadata is shared
    across datapoints but the property value varies per datapoint. The metadata mapping must
    include an actual ``uncertainty``, ``upper-uncertainty``/``lower-uncertainty``, or
    ``evaluated-standard-deviation`` value. Sequence elements:

    - 0: mapping, required
        A mapping containing uncertainty and/or evaluated-standard-deviation fields listed in
        :ref:`value-with-uncertainty <schema-value-with-uncertainty>` (element ``1``). No
        measured value element is included.

.. _schema-value-unit-required:

* ``value-unit-required``: sequence, required
    A sequence conforming to either :ref:`value-with-uncertainty <schema-value-with-uncertainty>` or
    :ref:`value-without-uncertainty <schema-value-without-uncertainty>`. Must be included in the
    ChemKED file.

.. _schema-value-unit-optional:

* ``value-unit-optional``: sequence, optional
    A sequence conforming to one of
    :ref:`value-with-uncertainty <schema-value-with-uncertainty>`,
    :ref:`value-without-uncertainty <schema-value-without-uncertainty>`, or
    :ref:`value-metadata-only <schema-value-metadata-only>`. May or may not be included in the
    ChemKED file.

.. _ignition-time-history:

* ``time-history``: mapping, optional
    Specify the time history of a quantity during an experiment. Fields:

    - ``type``: string, required
        The kind of quantity being recorded. Must be one of ``volume``, ``temperature``,
        ``pressure``, ``piston position``, ``light emission``, ``OH emission``, or
        ``absorption``.

    - ``quantity``: mapping, required
        A mapping describing the recorded quantity. Fields:

        * ``units``: string, required
            The units of the quantity, with dimensions appropriate for ``type`` (e.g., length
            cubed for ``volume``, temperature for ``temperature``).

        * ``column``: integer, required
            The 0-based index of the column containing the quantity in the ``values`` array.

    - ``time``: mapping, required
        A mapping describing the time in the history. Fields:

        * ``units``: string, required
            The units of the time, with dimensions of time

        * ``column``: integer, required
            The 0-based index of the column containing the time information in the ``values``
            array.

    - ``uncertainty``: mapping, optional
        The uncertainty of the values in the ``quantity`` column. Can be specified either globally
        by a single value in the sequence or by specifying a column that must be present in the
        values array. Mapping keys:

        * ``type``: string, required
            Either ``absolute`` or ``relative`` to indicate the type of uncertainty

        * ``value``: string, optional
            A global value for the uncertainty applied to all points in the ``values`` array,
            specified as a string with units. Either this key must be present, or the ``column`` and
            ``units`` keys must be present

        * ``column``: integer, optional
            The column in the ``values`` array containing the uncertainty of each point. Either this
            key and the ``units`` key must be specified, or the ``value`` key must be specified.

        * ``units``: string, optional
            The units of the uncertainty in the ``column`` array. IF the ``type`` is relative, this
            should be ``dimensionless``. Either this key and the ``column`` key must be specified,
            or the ``value`` key must be specified.

    - ``values``: sequence or mapping, required
        Must be a sequence or mapping. If a mapping, the only key should be ``filename`` whose value
        should be the filename of a comma-separated value file containing the values for the
        history. If a sequence, should be a sequence of sequences describing the values of the
        volume at the time points. Can be entered in any supported syntax, including:

        .. code-block:: yaml

            - [0.0, 0.0]
            - [1.0, 1.0]
            - - 2.0
              - 2.0
            - - 3.0
              - 3.0
