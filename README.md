# Tesserae Paperlesspaper

Eigen widgets voor [Tesserae](https://docs.tesserae.ink), plus een Home
Assistant-app die Tesserae draait en de pagina's naar een
[paperlesspaper](https://paperlesspaper.de)-frame stuurt, op de standaard
firmware van het frame (niets flashen).

| Onderdeel | Map |
|---|---|
| Home Assistant-app: Tesserae met deze widgets en de paperlesspaper-brug | [`tesserae_paperless/`](tesserae_paperless/) ([DOCS](tesserae_paperless/DOCS.md)) |
| paperlesspaper Core: uploadt elke render naar het paper van het frame en beheert de frames (welk paper, batterij, laatste wake) | [`paperlesspaper_core/`](paperlesspaper_core/) |
| Device-type *paperlesspaper frame (stock firmware)*, 1600×1200 Spectra 6, push | [`devices/paperlesspaper/`](devices/paperlesspaper/) |
| Overhead (fork): vliegtuigen en helikopters boven een plek, met straal én hoogteplafond | [`overhead_core/`](overhead_core/) + `overhead_cluster/`, `overhead_photo/`, `overhead_plate/`, `overhead_scene/` |
| Energy, Dynamic Price: EPEX- en Tibber-stroomprijzen voor vandaag en morgen | [`energy_dynamic_price/`](energy_dynamic_price/) |

Widgetmappen zijn op zichzelf staande Tesserae-plugins (`plugin.json` +
`server.py`, widgets ook `client.js`).

## Home Assistant-app

Settings › Apps › App store › ⋮ › Repositories:
`https://github.com/Emacee/Tesserae-Paperlesspaper`, installeer
**Tesserae + paperlesspaper**. De stappen staan in
[`tesserae_paperless/DOCS.md`](tesserae_paperless/DOCS.md).

Hoe het werkt: Home Assistant bouwt het image zelf, vanaf het officiële
`ghcr.io/dmellok/tesserae` (versie in
[`tesserae_paperless/build.yaml`](tesserae_paperless/build.yaml)), en zet de
plugins en het device-type uit deze repo erin, van de tag `WIDGETS_REF`. Voor
een nieuwe versie van de app: tag deze repo (`v0.1.1`, …), zet die tag in
`build.yaml` en dezelfde versie in `config.yaml`.

Het frame wordt wakker op de update-periodes uit de paperlesspaper-app en
haalt dan het plaatje op dat Tesserae naar zijn paper heeft geüpload; een
upload maakt het frame niet wakker (de knop of schudden wel).

Tests (offline):

```sh
python -m pytest paperlesspaper_core/tests -q
```

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

**Installeren**: zit in de Home Assistant-app hierboven. Los: kopieer de vijf
mappen `overhead_core`, `overhead_photo`, `overhead_plate`, `overhead_cluster`
en `overhead_scene` samen naar de plugins-map van Tesserae, in plaats van de
Overhead-bundel uit de catalogus (dezelfde widget-id's, dus bestaande cellen
blijven werken). Het
versienummer is `0.11.3.1`: een catalogus-update naar 0.11.4 of later zou de
fork weer overschrijven.

Tests (offline, met een checkout van de Tesserae-server ernaast of via
`TESSERAE_REPO`):

```sh
PYTHONPATH=../tesserae python -m pytest overhead_core/tests -q
```
