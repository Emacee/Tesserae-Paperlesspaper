# Tesserae widgets

Eigen widgets voor [Tesserae](https://docs.tesserae.ink). Elke map is een
op zichzelf staande widget (`plugin.json` + `client.js` + `server.py`).

| Widget | Map |
|---|---|
| Energy, Dynamic Price: EPEX- en Tibber-stroomprijzen voor vandaag en morgen | [`energy_dynamic_price/`](energy_dynamic_price/) |
| Overhead (fork): vliegtuigen en helikopters boven een plek, met straal én hoogteplafond | [`overhead_core/`](overhead_core/) + `overhead_cluster/`, `overhead_photo/`, `overhead_plate/`, `overhead_scene/` |

## Overhead (fork van `dmellok/tesserae-widget-overhead`)

Een fork van de officiële Overhead-bundel (v0.11.3, AGPL-3.0-or-later), met:

- **Below** (`max_alt_ft`): een vlieghoogte-plafond, direct onder **Within**
  (de straal vanaf de **Place**). Alleen toestellen op of onder die hoogte
  (barometrisch, in voet) komen op de pagina; de rest valt af vóór er geteld
  wordt. Keuzes: geen plafond, 500, 1.000, 1.500, 2.000, 3.000, 5.000 of
  10.000 ft. De kop van de pagina zegt dan bijvoorbeeld *within 10 km, below
  1,500 ft*.
- **Helikopters beter herkend**: zo'n 50 extra helikoptertypes in de tabel
  (o.a. politie H135/EC35, traumaheli H145/EC45, kustwacht AW189, AS365
  Dauphin, NH90, Chinook, Apache, Alouette III, Cabri G2, MD 500/600), en een
  type dat niet in de tabel staat telt als helikopter wanneer de ADS-B-
  emittercategorie A7 (rotorcraft) is, of de typebeschrijving *heli*,
  *copter*, *rotor* of *gyro* zegt. Helikopters gebruiken dezelfde
  systematiek als de rest: de soort **Helicopters** onder *Kinds of aircraft*,
  een eigen silhouet, en een schilderij met de ski's/wielen zoals het type ze
  heeft.

Alleen laagvliegers en helikopters, bijvoorbeeld:

| Optie | Waarde |
|---|---|
| Place | je eigen adres |
| Within | 5 of 10 km |
| Below | 1,500 ft (450 m) |
| Kinds of aircraft (More options) | Light aircraft + Helicopters (of alleen Helicopters) |
| Order (More options) | Lowest first |

**Installeren**: kopieer de vijf mappen `overhead_core`, `overhead_photo`,
`overhead_plate`, `overhead_cluster` en `overhead_scene` samen naar de
plugins-map van Tesserae, in plaats van de Overhead-bundel uit de catalogus
(dezelfde widget-id's, dus bestaande cellen blijven werken). Het
versienummer is `0.11.3+fork.1` (Tesserae eist drie getallen, met eventueel
een `-`/`+`-achtervoegsel; `0.11.3.1` werd geweigerd en de widgets laadden
niet). Een catalogus-update naar 0.11.4 of later zou de fork weer
overschrijven.

Tests (offline, met een checkout van de Tesserae-server ernaast of via
`TESSERAE_REPO`):

```sh
PYTHONPATH=../tesserae python -m pytest overhead_core/tests -q
```
