# ReSpecTh schema fixtures

Each fixture consists of an original ReSpecTh XML file and the corresponding ChemKED YAML representation. The files were selected by schema-relevant structure rather than fuel or publication, so repeated datasets with the same shape are intentionally omitted.

| Pair | ReSpecTh measurement | Schema scenario |
| --- | --- | --- |
| `laminar-burning-velocity/x20014048` | Laminar burning velocity | Varying composition; shared relative ESD moved from `commonProperties` to every measured velocity |
| `laminar-burning-velocity/x20004235` | Laminar burning velocity | Common composition and temperature; pressure sweep; pointwise absolute ESD |
| `laminar-burning-velocity/x20100072` | Laminar burning velocity | Equivalence-ratio and composition sweep; combined pointwise uncertainty and ESD |
| `speciation/x30000017` | Concentration time profile | Time independent variable, profile-level absolute ESD, and time shift |
| `speciation/x00201001` | Jet-stirred reactor | Temperature sweep, multiple species profiles, common residence time and reactor volume, relative ESD |
| `speciation/x30400015` | Outlet concentration | Temperature and residence-time independent variables with ppm-to-mole-fraction conversion |
| `speciation/x60200017` | Burner-stabilized flame speciation | Distance profile with a separate auxiliary temperature profile |

The source XML files are from `ReSpecTh/indirect` experimental datasets. ReSpecTh's four speciation experiment labels are represented by the unified ChemKED `speciation measurement` type.
