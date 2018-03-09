.. Examples of using PyKED

Usage examples
==============

The following usage examples provide a guide to the use of PyKED. They are by no means an exhaustive
treatment, and are meant to demonstrate the basic capabilities of the software.

RCM modeling with varying reactor volume
----------------------------------------

The ChemKED file that will be used in this example can be found in the ``tests`` directory of the
PyKED repository. [1]_ Examining that file, we find the first section specifies the information
about the ChemKED file itself:

.. code-block:: yaml

    file-author:
      name: Kyle E Niemeyer
      ORCID: 0000-0003-4425-7097
    file-version: 0
    chemked-version: 0.1.6

Then, we find the information regarding the article in the literature from which this data was
taken. In this case, the dataset comes from the work of Mittal et al. [Mittal2006]_:

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

Finally, there is just a single datapoint in this file, which describes the ignition delay for the
experiment, the mixture composition, the initial temperature, pressure, compression time, ignition
type, and the volume history that specifies how the volume of the reactor varies with time, for
simulating the compression stroke and post-compression processes.

.. code-block:: yaml

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

The values for the ``volume-history`` are truncated here to save space. A user might want to load
the information from this file to perform a simulation using Cantera to calculate the ignition
delay. All of the information required to perform this simulation is present in the ChemKED file,
with the exception of a chemical kinetic model for H2/CO combustion.

.. code-block:: python

    import cantera as ct
    from pyked import ChemKED

    # Load the ChemKED file and retrieve the first element of the
    # datapoints list, which is an instance of the DataPoint class
    ck = ChemKED('testfile_rcm.yaml')
    dp = ck.datapoints[0]

The initial temperature, pressure, and mixture composition can be read from the instance of the
``DataPoint`` class. PyKED uses Pint ``Quantities`` to store values with units, while Cantera
expects a floating point value in SI units as input. Therefore, we use the built-in capabilities of
Pint to convert the units from those specified in the ChemKED file to SI units:

.. code-block:: python

    T_initial = dp.temperature.to('K').magnitude
    P_initial = dp.pressure.to('Pa').magnitude
    X_initial = dp.get_cantera_mole_fraction()

    # Load the mechanism and set the initial state of the mixture
    gas = ct.Solution('h2-co-mechanism.cti')
    gas.TPX = T_initial, P_initial, X_initial

    # Create the reactor and the outside environment
    reac = ct.IdealGasReactor(gas)
    env = ct.Reservoir(ct.Solution('air.xml'))

To apply the effect of the volume trace to the ``IdealGasReactor``, a ``Wall`` is installed between
the reactor and the environment and assigned a velocity. Although we do not show the details here, a
reference implementation of a class that computes a wall velocity given the volume history of the
reactor is available in CanSen [CanSen2015]_, in the ``cansen.profile.VolumeProfile``
class. Then, a Cantera ``ReactorNet`` can be used to advance the state through autoignition, in this
case to an end time of 50 ms:

.. code-block:: python

    time = dp.volume_history.time
    volume = dp.volume_history.volume
    ct.Wall(reac, env, velocity=VolumeProfile(time=time, volume=volume))

    netw = ct.ReactorNet([reac])

    # Integrate for 50 ms
    while netw.time < 0.05:
        netw.step()


Although not shown in this example, the user would typically store
information about the ``IdealGasReactor`` (e.g., temperature, pressure,
mass fractions) at each time step of the integration for
post-processing.

Shock tube modeling with constant volume
----------------------------------------

The ChemKED file used in this example can be found in the ``tests`` directory of the PyKED
repository. [2]_ The data in this file comes from Stranic et al. [Stranic2012]_, describing
shock-tube ignition delays for *tert*-butanol. We have omitted the file meta information below for
space. This ChemKED file specifies multiple data points with some common conditions, including a
common mixture composition and common definition of ignition delay. Therefore, a
``common-properties`` section is specified.

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
      ignition-type:  &ign
        target: OH*
        type: 1/2 max

This block uses the ability of YAML files to define an anchor with the
``&`` symbol and refer to that section later with the ``\*`` symbol, as
can be seen in the definition of the ``datapoints`` section:

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

The ``common-properties`` section is not required, but can save space
and help avoid errors when all data points share some common values.

In this example, we would like to run constant-volume simulations at
each of the pressure and temperature conditions in the ``datapoints``
list. Once again, the ChemKED file specifies all the information
required for the simulations except for the chemical kinetic model, and
Cantera can be used to simulate autoignition:

.. code-block:: python

    import cantera as ct
    from pyked import ChemKED

    ck = ChemKED('Stranic2012-tbuoh.yaml')

    gas = ct.Solution('tbuoh-mechanism.cti')

    # Since the composition is specified by the common-properties,
    # just take the composition of the first DataPoint
    X_initial = ck.datapoints[0].get_cantera_mole_fraction()

    # Loop through each of the DataPoints
    for dp in ck.datapoints:
        T_initial = dp.temperature.to('K').magnitude
        P_initial = dp.pressure.to('Pa').magnitude
        gas.TPX = T_initial, P_initial, X_initial
        reac = ct.IdealGasReactor(gas)
        netw = ct.ReactorNet([reac])
        # Define ignition delay as T_initial + 400 K
        while reac.T < T_initial + 400:
            netw.step()

        print('The ignition delay for T_initial={}, P_initial={} is: '
              '{} seconds'.format(T_initial, P_initial, netw.time)
              )

The ignition delay in this example is defined as equal to the above the
initial temperature, a simplified definition used for this example. In
general, the user could post-process the concentration information from
the simulation to determine one-half the maximum concentration to match
the experimental definition of ignition delay.

.. [Mittal2006] Mittal, Gaurav, Chih-Jen Sung, and Richard A. Yetter. 2006.
                "Autoignition of H2/CO at Elevated Pressures in a Rapid Compression
                Machine." *International Journal of Chemical Kinetics* 38 (8): 516–29.
                doi:\ `10.1002/kin.20180 <https://doi.org/10.1002/kin.20180>`__.

.. [Stranic2012] Stranic, Ivo, Deanna P. Chase, Joseph T. Harmon, Sheng Yang, David F.
                 Davidson, and Ronald K. Hanson. 2012. "Shock Tube Measurements of
                 Ignition Delay Times for the Butanol Isomers." *Combustion and Flame*
                 159 (2): 516–27.
                 doi:\ `10.1016/j.combustflame.2011.08.014 <https://doi.org/10.1016/j.combustflame.2011.08.014>`__.

.. [CanSen2015]  Weber, Bryan William. 2015. "CanSen." https://github.com/bryanwweber/CanSen.

.. [1] https://github.com/pr-omethe-us/PyKED/blob/master/pyked/tests/testfile_rcm.yaml

.. [2] https://github.com/pr-omethe-us/PyKED/blob/master/pyked/tests/testfile_st_p5.yaml
