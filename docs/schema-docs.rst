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
        Must be one of ``shock tube`` or ``rapid compression machine``. Values are case-sensitive.

    - ``institution``: string, optional
        The institution where the experimental apparatus is located

    - ``facility``: string, optional
        A unique name or identifier for the apparatus, if the institution has several that are
        similar

.. _reference-experiment-type:

* ``experiment-type``: string, required
    The type of experiment encoded in this file. Currently, the only allowed value is
    ``ignition delay``, which is case sensitive.

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

.. _common-ignition-type:

* ``ignition-type``: mapping, optional
    Has the same schema as :ref:`ignition-type <ignition-ignition-type>`

.. _common-composition:

* ``composition``: mapping, optional
    This mapping provides the specification of the initial composition of the mixture. Fields:

    - ``kind``: string, required
        The ``kind`` can be ``mole fraction``, ``mass fraction``, or ``mole percent``

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
            A sequence representing the amount of the species. Must conform to either
            :ref:`value-with-uncertainty <schema-value-with-uncertainty>` or
            :ref:`value-without-uncertainty <schema-value-without-uncertainty>`.

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
        Describes the target measurement to define ignition. Can be one of:

            * ``temperature``
            * ``pressure``
            * ``OH``
            * ``OH*``
            * ``CH``
            * ``CH*``

    - ``type``: string, required
        Describes the type of ignition delay measurement. Can be one of:

            * ``d/dt max``: maximum of the time derivative of the ``target``
            * ``max``: maximum of the ``target``
            * ``1/2 max``: half-maximum of the ``target``
            * ``min``: minimum of the ``target``
            * ``d/dt max extrapolated``: maximum slope of the target extrapolated to the baseline

.. _ignition-ignition-delay:

* ``ignition-delay``: sequence, required
    The ignition delay measurement, with dimensions of time. Must conform to
    :ref:`value-unit-required <schema-value-unit-required>`

.. _ignition-pressure-rise:

* ``pressure-rise``: sequence, optional
    The pressure rise after the passage of the reflected shock, with dimensions of inverse time.
    Must conform to :ref:`value-unit-optional <schema-value-unit-optional>`

.. _ignition-compression-time:

* ``compression-time``: sequence, optional
    The time taken during the compression stroke of a rapid compression machine experiment, with
    dimensions of time. Must conform to :ref:`value-unit-optional <schema-value-unit-optional>`

.. _ignition-first-stage-ignition-delay:

* ``first-stage-ignition-delay``: sequence, optional
    If two stages of ignition are present, this is the value of the first stage of ignition, with
    dimensions of time. Must conform to :ref:`value-unit-optional <schema-value-unit-optional>`

.. _ignition-compressed-pressure:

* ``compressed-pressure``: sequence, optional
    The pressure at the end of the compression stroke for a rapid compression machine experiment,
    with dimensions of mass per length per time squared. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`

.. _ignition-compressed-temperature:

* ``compressed-temperature``: sequence, optional
    The temperature at the end of the compression stroke for a rapid compression machine experiment,
    with dimensions of temperature. Must conform to
    :ref:`value-unit-optional <schema-value-unit-optional>`

.. _ignition-equivalence-ratio:

* ``equivalence-ratio``: float, optional
    The equivalence ratio of the experiment, dimensionless. Minimum value is 0.0.

.. _ignition-volume-history:

* ``volume-history``: mapping, optional
    Specify the volume history of the reaction chamber in a rapid compression machine experiment,
    for use in simulating the complete experiment. Fields:

    - ``volume``: mapping, required
        A mapping describing the volume in the history. Fields:

        * ``units``: string, required
            The units of the volume, with dimensions of length cubed

        * ``column``: integer, required
            The 0-based index of the column containing the volume information in the ``values``
            array. Must be 0 or 1

    - ``time``: mapping, required
        A mapping describing the time in the history. Fields:

        * ``units``: string, required
            The units of the time, with dimensions of time

        * ``column``: integer, required
            The 0-based index of the column containing the time information in the ``values``
            array. Must be 0 or 1

    - ``values``: sequence, required
        A sequence of sequences describing the values of the volume at the time points. Can be
        entered in any supported syntax, including:

        .. code-block:: yaml

            - [0.0, 0.0]
            - [1.0, 1.0]
            - - 2.0
              - 2.0
            - - 3.0
              - 3.0

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
    A combination of a value and unit with uncertainty. Sequence elements:

    - 0: string, required
        The first element of the sequence should be the value and its associated
        units. The units are validated to have appropriate dimensions for the particular quantity
        under consideration

    - 1: mapping, optional
        The second element of the sequence should be a mapping representing the uncertainty. Fields:

        * ``uncertainty-type``: string, required
            The type of uncertainty. Options are ``absolute`` or ``relative``.

        * ``uncertainty``: string, required, excludes ``upper-uncertainty`` and ``lower-uncertainty``
            The value of the uncertainty. If ``uncertainty-type`` is ``absolute``, must include
            units whose dimensions match the units of the value in the first element of the
            sequence.

        * ``upper-uncertainty``: string, required, excludes ``uncertainty``, requires ``lower-uncertainty``
            The upper value of an asymmetrical uncertainty. Due to limitations in the Python
            library, asymmetrical uncertainties aren't supported in PyKED, so the larger of
            ``upper-uncertainty`` and ``lower-uncertainty`` is used.

        * ``lower-uncertainty``: string, required, excludes ``uncertainty``, requires ``upper-uncertainty``
            The lower value of an asymmetrical uncertainty. Due to limitations in the Python
            library, asymmetrical uncertainties aren't supported in PyKED, so the larger of
            ``upper-uncertainty`` and ``lower-uncertainty`` is used.

.. _schema-value-without-uncertainty:

* ``value-without-uncertainty``: sequence
    A combination of a value and unit without uncertainty. Sequence elements:

    - 0: string, required
        The first element of the sequence should be the value and its associated
        units. The units are validated to have appropriate dimensions for the particular quantity
        under consideration

.. _schema-value-unit-required:

* ``value-unit-required``: sequence, required
    A sequence conforming to either :ref:`value-with-uncertainty <schema-value-with-uncertainty>` or
    :ref:`value-without-uncertainty <schema-value-without-uncertainty>`. Must be included in the
    ChemKED file.

.. _schema-value-unit-optional:

* ``value-unit-optional``: sequence, optional
    A sequence conforming to either :ref:`value-with-uncertainty <schema-value-with-uncertainty>` or
    :ref:`value-without-uncertainty <schema-value-without-uncertainty>`. May or may not be included
    in the ChemKED file.
