.. Tutorial on creating ChemKED files

Creating ChemKED files
======================

ChemKED Overview
----------------

ChemKED (**Chem**\ ical **K**\ inetics **E**\ xperimental **D**\ atabase) files use the YAML data
serialization format [yaml12]_. This format offers the advantages of being human readable, written
in plain text, and having parsers in most common programming languages, including Python, C++, Java,
Perl, MATLAB, and many others. The YAML syntax is quite simple: the basic file structure is made of
mappings, delimited by a colon. The key for the mapping is on the left of the colon, and the value
on the right can be a single value, a sequence of values, a nested mapping, or some combination of
these:

.. code-block:: yaml

    key1: value  # Single-value mapping
    key2:  # Sequence format
      - value
      - value
    key3:  # Nested mapping
      key4: 0
    key5:  # Sequence of mappings
      - key-s1: 0
        key-s2: value
      - key-s2: value
        key-s1: 0

The ``value`` can be a string, integer, or floating point number. The ChemKED format is designed to
include all of the information necessary to simulate a given experiment and can be thought of
conceptually in three main sections, a "meta" section that contains information about the ChemKED
file itself, a "reference" section that contains information about the type of experiment and the
article where the data is published, and a "data" section that contains the actual data for the
experiment. A full listing of the keys and their associated meanings can be found in the
:doc:`schema-docs`.

ChemKED files have the extension ``.yaml``. Within the file, indentation must be by spaces only, and
each level should be indented by two spaces relative to the previous level. Please set your text
editor to produce UNIX-style line endings (``\n``), not DOS style (``\r\n``). Note that all keys and
values are case-sensitive and should be written entirely in lower case (except author names, journal
names, and apparatus institution and facility, where standard case conventions may be used).

The Meta Section
----------------

ChemKED files require some information about the file itself to be stored in the file. This helps
ensure the integrity of the data encoded in the file. The meta information required for a ChemKED
format file includes:

    * the author of the file (which could be different from the author of the study where the
      experiment is published)
    * the version of the file
    * the version of the ChemKED database format targeted by the file

A typical meta section might look something like:

.. code-block:: yaml

    file-author:
      name: Kyle E Niemeyer
      ORCID: 0000-0003-4425-7097
    file-version: 0
    chemked-version: 0.1.6

The Reference Section
---------------------

In the reference section, information about the experimental facility and the article where the data
is published is collected. This information typically includes:

    * the type of experiment (for now, only autoignition experiments are supported)
    * the type and location of the experimental apparatus (rapid compression machine or shock tube)
    * the article authors and the journal, DOI, volume, and issue where the data was published
    * a note about where in the paper the data was collected from, if multiple data sets are
      presented in the same work

As an example, the following is the reference section from the work of Mittal et al. [Mittal2006]_:

.. code-block:: yaml

    reference:
      doi: 10.1002/kin.20180
      authors:
        - name: Gaurav Mittal
        - name: Chih-Jen Sung
          ORCID: 0000-0003-2046-8076
        - name: Richard A Yetter
      journal: International Journal of Chemical Kinetics
      year: 2006
      volume: 38
      pages: 516-529
      detail: Fig. 6, open circle
    experiment-type: ignition delay
    apparatus:
      kind: rapid compression machine
      institution: Case Western Reserve University
      facility: CWRU RCM

The Data Section
----------------

In the data section, the actual data from the reference is represented. The data section contains a
single top-level key, ``datapoints``, which contains a sequence whose elements represent the actual
data encoded in the file. The sequence can contain a single data point from the work, or it can
contain many data points. We have found that it is often convenient to represent only a single rapid
compression machine autoignition experiment in a single ChemKED file, but shock tube autoignition
experiments can often include multiple experiments in a file.

Each single data point in the sequence of ``datapoints`` has a number of required and optional
fields, depending on what type of data is being encoded. The typical information included will be:

    * temperature
    * pressure
    * initial composition
    * measured quantity (ignition delay, product composition, etc.)

As an example, the following data is taken from the work of Stranic et al. [Stranic2012]_. This
example shows the inclusion of multiple experiments in the ``datapoints`` key.

.. code-block:: yaml

    datapoints:
      - temperature:
          - 1459 kelvin
        ignition-delay:
          - 347 us
        pressure:
          - 1.60 atm
        composition: *comp
        ignition-type: *ign
        equivalence-ratio: 0.5
      - temperature:
          - 1389 kelvin
        ignition-delay:
          - 756 us
        pressure:
          - 1.67 atm
        composition: *comp
        ignition-type: *ign
        equivalence-ratio: 0.5
      - temperature:
          - 1497 kelvin
        ignition-delay:
          - 212 us
        pressure:
          - 1.55 atm
        composition: *comp
        ignition-type: *ign
        equivalence-ratio: 0.5
      - temperature:
          - 1562 kelvin
        ignition-delay:
          - 105 us
        pressure:
          - 1.50 atm
        composition: *comp
        ignition-type: *ign
        equivalence-ratio: 0.5

Note that units are required for all quantities with units, and the units are validated to have the
appropriate dimensions for the particular quantity.

In cases where the same value should be specified multiple times, ChemKED files have a special key
called ``common-properties`` that stores any properties that are shared among multiple data points.
Properties are stored in the ``common-properties`` section as **anchors** and filled into a data
point with a **reference**. The reference syntax is shown in the example above in the
``composition`` and ``ignition-type`` keys, with the ``*comp`` and ``*ign`` as the values.
References are denoted by the ``*``. An example of the ``common-properties`` key is shown below:

.. code-block:: yaml

    common-properties:
      composition: &comp
        kind: mole fraction
        species:
          - species-name: t-butanol
            InChI: 1S/C4H10O/c1-4(2,3)5/h5H,1-3H3
            amount:
              - 0.003333333
          - species-name: O2
            InChI:  1S/O2/c1-2
            amount:
              - 0.04
          - species-name: Ar
            InChI:  1S/Ar
            amount:
              - 0.956666667
      ignition-type: &ign
        target: OH*
        type: 1/2 max

In the ``common-properties`` section, the **anchor** is created by the ``&`` followed by the name of
the anchor. This syntax stores the ``composition`` and ``ignition-type`` in the anchors ``comp`` and
``ign``, respectively, and in the ``datapoints`` section, these anchors are referenced by the ``*``.

Use of the ``common-properties`` key is strongly encouraged when there are multiple data points with
repeated values, to avoid typos and ensure consistency of the data. Note that if a field is required
in a data point, it must be included in the data point (by referencing) even if it has already been
included in the ``common-properties`` key. This is an intentional decision, and the user should use
the anchor and reference syntax to avoid having to write the same value multiple times.

Values in data points can also have an associated uncertainty. This uncertainty can be absolute or
relative, and is specified in the following way (the values in this example are arbitrary, and don't
represent actual experimental results):

.. code-block:: yaml

    datapoints:
      - temperature:
          - 1459 kelvin
          - uncertainty-type: absolute
            uncertainty: 10 kelvin
        ignition-delay:
          - 347 us
          - uncertainty-type: relative
            uncertainty: 0.01
        pressure:
          - 1.60 atm
        composition: *comp
        ignition-type: *ign
        equivalence-ratio: 0.5

Note that if the absolute uncertainty is specified, its units must have the same dimensions as the
quantity.

Examples
--------

The following are complete examples of ChemKED files for autoignition experiments.

Single Data Point with Volume History
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The following example encodes an experiment from the work of Mittal et al. [Mittal2006]_ in a rapid
compression machine.

.. code-block:: yaml

    ---
    file-author:
      name: Kyle E Niemeyer
      ORCID: 0000-0003-4425-7097
    file-version: 0
    chemked-version: 0.0.1
    reference:
      doi: 10.1002/kin.20180
      authors:
        - name: Gaurav Mittal
        - name: Chih-Jen Sung
          ORCID: 0000-0003-2046-8076
        - name: Richard A Yetter
      journal: International Journal of Chemical Kinetics
      year: 2006
      volume: 38
      pages: 516-529
      detail: Fig. 6, open circle
    experiment-type: ignition delay
    apparatus:
      kind: rapid compression machine
      institution: Case Western Reserve University
      facility: CWRU RCM
    datapoints:
      - temperature:
          - 297.4 kelvin
        ignition-delay:
          - 1.0 ms
        pressure:
          - 958.0 torr
        composition:
          kind: mole fraction
          species:
            - species-name: H2
              InChI: 1S/H2/h1H
              amount:
                - 0.12500
            - species-name: O2
              InChI: 1S/O2/c1-2
              amount:
                - 0.06250
            - species-name: N2
              InChI: 1S/N2/c1-2
              amount:
                - 0.18125
            - species-name: Ar
              InChI: 1S/Ar
              amount:
                - 0.63125
        ignition-type:
          target: pressure
          type: d/dt max
        compression-time:
          - 38.0 ms
        volume-history:
          time:
            units: s
            column: 0
          volume:
            units: cm3
            column: 1
          values:
            - [0.00E+000, 5.47669375000E+002]
            - [1.00E-003, 5.46608789894E+002]
            - [2.00E-003, 5.43427034574E+002]
            - [3.00E-003, 5.38124109043E+002]
            - [4.00E-003, 5.30700013298E+002]
            - [5.00E-003, 5.21154747340E+002]
            - [6.00E-003, 5.09488311170E+002]
            - [7.00E-003, 4.95700704787E+002]
            - [8.00E-003, 4.79791928191E+002]
            - [9.00E-003, 4.61761981383E+002]
            - [1.00E-002, 4.41610864362E+002]
            - [1.10E-002, 4.20399162234E+002]
            - [1.20E-002, 3.99187460106E+002]
            - [1.30E-002, 3.77975757979E+002]
            - [1.40E-002, 3.56764055851E+002]
            - [1.50E-002, 3.35552353723E+002]
            - [1.60E-002, 3.14340651596E+002]
            - [1.70E-002, 2.93128949468E+002]
            - [1.80E-002, 2.71917247340E+002]
            - [1.90E-002, 2.50705545213E+002]
            - [2.00E-002, 2.29493843085E+002]
            - [2.10E-002, 2.08282140957E+002]
            - [2.20E-002, 1.87070438830E+002]
            - [2.30E-002, 1.65858736702E+002]
            - [2.40E-002, 1.44647034574E+002]
            - [2.50E-002, 1.23435332447E+002]
            - [2.60E-002, 1.02223630319E+002]
            - [2.70E-002, 8.10119281915E+001]
            - [2.80E-002, 6.33355097518E+001]
            - [2.90E-002, 5.27296586879E+001]
            - [3.00E-002, 4.91943750000E+001]
            - [3.10E-002, 4.97137623933E+001]
            - [3.20E-002, 5.02063762048E+001]
            - [3.30E-002, 5.06454851923E+001]
            - [3.40E-002, 5.10218564529E+001]
            - [3.50E-002, 5.13374097598E+001]
            - [3.60E-002, 5.16004693977E+001]
            - [3.70E-002, 5.18223244382E+001]
            - [3.80E-002, 5.20148449242E+001]
            - [3.90E-002, 5.21889350372E+001]
            - [4.00E-002, 5.23536351113E+001]
            - [4.10E-002, 5.25157124459E+001]
            - [4.20E-002, 5.26796063730E+001]
            - [4.30E-002, 5.28476160610E+001]
            - [4.40E-002, 5.30202402028E+001]
            - [4.50E-002, 5.31965961563E+001]
            - [4.60E-002, 5.33748623839E+001]
            - [4.70E-002, 5.35527022996E+001]
            - [4.80E-002, 5.37276399831E+001]
            - [4.90E-002, 5.38973687732E+001]
            - [5.00E-002, 5.40599826225E+001]
            - [5.10E-002, 5.42141273988E+001]
            - [5.20E-002, 5.43590751578E+001]
            - [5.30E-002, 5.44947289126E+001]
            - [5.40E-002, 5.46215686913E+001]
            - [5.50E-002, 5.47405518236E+001]
            - [5.60E-002, 5.48529815402E+001]
            - [5.70E-002, 5.49603582190E+001]
            - [5.80E-002, 5.50642270863E+001]
            - [5.90E-002, 5.51660349836E+001]
            - [6.00E-002, 5.52670070646E+001]
            - [6.10E-002, 5.53680520985E+001]
            - [6.20E-002, 5.54697025392E+001]
            - [6.30E-002, 5.55720927915E+001]
            - [6.40E-002, 5.56749762728E+001]
            - [6.50E-002, 5.57777790517E+001]
            - [6.60E-002, 5.58796851466E+001]
            - [6.70E-002, 5.59797461155E+001]
            - [6.80E-002, 5.60770054561E+001]
            - [6.90E-002, 5.61706266985E+001]
            - [7.00E-002, 5.62600130036E+001]
            - [7.10E-002, 5.63449057053E+001]
            - [7.20E-002, 5.64254496625E+001]
            - [7.30E-002, 5.65022146282E+001]
            - [7.40E-002, 5.65761642150E+001]
            - [7.50E-002, 5.66485675508E+001]
            - [7.60E-002, 5.67208534842E+001]
            - [7.70E-002, 5.67944133373E+001]
            - [7.80E-002, 5.68703658198E+001]
            - [7.90E-002, 5.69493069272E+001]
            - [8.00E-002, 5.70310785669E+001]
            - [8.10E-002, 5.71146023893E+001]
            - [8.20E-002, 5.71978399741E+001]
            - [8.30E-002, 5.72779572372E+001]
            - [8.40E-002, 5.73517897984E+001]
            - [8.50E-002, 5.74167271960E+001]
            - [8.60E-002, 5.74721573687E+001]
            - [8.70E-002, 5.75216388520E+001]
            - [8.80E-002, 5.75759967785E+001]
            - [8.90E-002, 5.76575701358E+001]
            - [9.00E-002, 5.78058719368E+001]
            - [9.10E-002, 5.80849611077E+001]
            - [9.20E-002, 5.85928651155E+001]
            - [9.30E-002, 5.94734357453E+001]
            - [9.40E-002, 6.09310671165E+001]
            - [9.50E-002, 6.32487551103E+001]
            - [9.60E-002, 6.68100309742E+001]
    ...

Multiple Experiments
^^^^^^^^^^^^^^^^^^^^

The following example encodes some of the data from the work of Stranic et al. [Stranic2012]_ in the
shock tube at Stanford.

.. code-block:: yaml

    ---
    file-author:
      name: Morgan Mayer
      ORCID: 0000-0001-7137-5721
    file-version: 0
    chemked-version: 0.0.1
    reference:
      doi: 10.1016/j.combustflame.2011.08.014
      authors:
        - name: Ivo Stranic
        - name: Deanna P. Chase
        - name: Joseph T. Harmon
        - name: Sheng Yang
        - name: David F. Davidson
        - name: Ronald K. Hanson
      journal: Combustion and Flame
      year: 2012
      volume: 159
      pages: 516-527
    experiment-type: ignition delay
    apparatus:
      kind: shock tube
      institution: High Temperature Gasdynamics Laboratory, Stanford University
      facility: stainless steel shock tube
    common-properties:
      composition: &comp
        kind: mole fraction
        species:
          - species-name: t-butanol
            InChI: 1S/C4H10O/c1-4(2,3)5/h5H,1-3H3
            amount:
              - 0.003333333
          - species-name: O2
            InChI:  1S/O2/c1-2
            amount:
              - 0.04
          - species-name: Ar
            InChI:  1S/Ar
            amount:
              - 0.956666667
      ignition-type:  &ign
        target: OH*
        type: 1/2 max
    datapoints:
      - temperature:
          - 1459 kelvin
        ignition-delay:
          - 347 us
        pressure:
          - 1.60 atm
        composition: *comp
        ignition-type: *ign
        equivalence-ratio: 0.5
      - temperature:
          - 1389 kelvin
        ignition-delay:
          - 756 us
        pressure:
          - 1.67 atm
        composition: *comp
        ignition-type: *ign
        equivalence-ratio: 0.5
      - temperature:
          - 1497 kelvin
        ignition-delay:
          - 212 us
        pressure:
          - 1.55 atm
        composition: *comp
        ignition-type: *ign
        equivalence-ratio: 0.5
      - temperature:
          - 1562 kelvin
        ignition-delay:
          - 105 us
        pressure:
          - 1.50 atm
        composition: *comp
        ignition-type: *ign
        equivalence-ratio: 0.5
    ...


Converting from ReSpecTh
------------------------

PyKED provides converter functions from (and to) the ReSpecTh XML format
[Varga2015a]_, [Varga2015b]_, though ChemKED files created in this manner may
require manual edits to fully satisfy our schema.

Given a ReSpecTh XML file ``file.xml``, a corresponding ChemKED file can be created
either from the command line

.. code-block:: bash

    python converter -i file.xml -o file.yaml

or via Python:

.. code-block:: Python

    from pyked.converters import ReSpecTh_to_ChemKED
    ReSpecTh_to_ChemKED('file.xml', 'file.yaml')

Information about the person creating this new ChemKED file (e.g., file author name
and their ORCID) may also be added via the ``file_author`` and ``file_author_orcid``
arguments in Python or the corresponding command-line options `-fa` and `-fo`. More
details can be found via ``python converter --help`` or
``help(pyked.converters.ReSpecTh_to_ChemKED)``, respectively.

PyKED also provides a converter to generate ReSpecTh files based on ChemKED records.
Given a ChemKED file ``file.yaml``, a corresponding ReSpecTh file can be created
from the command line via

.. code-block:: bash

    python converter -i file.yaml -o file.xml

or from inside Python with

.. code-block:: Python

    from pyked import ChemKED
    c = ChemKED('file.yaml')
    c.convert_to_ReSpecTh('file.xml')

Note that some information, or granularity of details, may be lost in this conversion.


Works Cited
-----------

.. [yaml12] Ben-Kiki, Oren, Clark Evans, and Ingy döt Net. 2009. "YAML Ain't Markup
            Language (Yaml™) Version 1.2." http://www.yaml.org/spec/1.2/spec.html.

.. [Mittal2006] Mittal, Gaurav, Chih-Jen Sung, and Richard A. Yetter. 2006.
                "Autoignition of H2/CO at Elevated Pressures in a Rapid Compression
                Machine." *International Journal of Chemical Kinetics* 38 (8): 516–29.
                doi:\ `10.1002/kin.20180 <https://doi.org/10.1002/kin.20180>`__.

.. [Stranic2012] Stranic, Ivo, Deanna P. Chase, Joseph T. Harmon, Sheng Yang, David F.
                 Davidson, and Ronald K. Hanson. 2012. "Shock Tube Measurements of
                 Ignition Delay Times for the Butanol Isomers." *Combustion and Flame*
                 159 (2): 516–27.
                 doi:\ `10.1016/j.combustflame.2011.08.014 <https://doi.org/10.1016/j.combustflame.2011.08.014>`__.

.. [Varga2015a] Varga, Tamás, Tamás Turányi, Eszter Czinki, Tibor Furtenbacher, Attila G. Császár,
                "ReSpecTh: a joint reaction kinetics, spectroscopy, and thermochemistry information
                system." 2015. Proceedings of the 7th European Combustion Meeting,
                Budapest, Hungary.

.. [Varga2015b] Varga, Tamás. "ReSpecTh Kinetics Data Format Specification v1.0." 2015.
                http://respecth.hu/
