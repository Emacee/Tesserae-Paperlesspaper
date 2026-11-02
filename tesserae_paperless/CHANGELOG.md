# Changelog

All notable changes to the **Tesserae + paperlesspaper** Home Assistant app
and the widgets, plugin and device kind it ships from this repository.
Home Assistant shows this file on the app's Changelog tab when an update is
offered. Versions follow `version` in [`config.yaml`](config.yaml).

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
New entries go under **Unreleased** with every change; a release moves them
under its version number.

## [Unreleased]

### Fixed
- paperlesspaper: setting up the frame's device from the setup endpoint
  stored its orientation on Tesserae 0.480 too (it stopped with an error
  after creating the device).
- Energy, Dynamic Price: when the home battery cannot be drawn, the widget
  data now says why instead of leaving it out silently.

## [0.2.1] - 2026-11-01

Built on Tesserae 0.480.0, from commit `b82a2b4`.

### Added
- The app connects Home Assistant Core to your Home Assistant by itself,
  through Supervisor: no URL or long-lived token to paste before the Home
  Assistant widgets work. A Home Assistant URL you set yourself is kept.
- paperlesspaper: the frame's device can be added (and its paper and
  orientation set) from the paperlesspaper page's setup endpoint, so a
  dashboard can be set up for you in one go.

## [0.2.0] - 2026-11-01

Built on Tesserae 0.480.0, from commit `37edbac`.

### Changed
- One typeface across the new widgets: Overhead: Map now defaults to the
  dashboard's own font, like Travel time, Weather, Today, Energy, Dynamic
  Price and Home batteries; text varies only in size and weight, with
  nothing thin at small sizes, for e-paper.
- Travel time: the people's names and sensors are kept as secrets: never
  in the page's markup, and left out of an exported template.

### Added
- **Overhead: Map**: the aircraft near your place on an OpenStreetMap map,
  quietened for e-paper. Each one's track over the last 10, 30 or 60
  minutes is coloured by its height or its speed (your choice), in the
  same green, ochre and red as the energy price chart; a numbered badge in
  a colour of its own marks where it is now and points the way it flies.
  Under the map a line for each: picture, registration, type, height,
  distance. Up to six (fewer when fewer are within reach), and the rest are
  counted. Home, the radius ring and a legend on the map.
- **Travel time**: travel time to work until 14:00 (or the hour you pick)
  and home after it, for up to three people, from travel-time sensors in
  Home Assistant (Waze Travel Time, Google Maps Travel Time). The sensors
  are picked from a list in the cell's options, so none of them is in the
  widget. When it takes longer than is normal for that weekday and time
  (the median of the sensor's own history), the page says **+x min**.
  Hidden at the weekend unless you want it.
- **Weather, Today**: today's weather as a column for a narrow portrait
  cell: the weather now, the day's high, low and rain, and below it every
  hour with its icon, temperature and a rain bar. Open-Meteo, no key.
- **Home batteries**: small rings for the home battery (a Deye inverter
  through the Solarman integration: state of charge, charging,
  discharging or resting, work mode, the target of the current
  time-of-use slot) and the car (state of charge, charge limit, range in
  km, charging or plugged in), with small icons drawn for e-paper.
- Energy, Dynamic Price: **the home battery over the prices**. Pick a Deye
  inverter and the chart shows its time-of-use targets as a dashed blue
  line on a 0–100% axis of its own, slots that charge from the grid drawn
  heavy with a pylon, the current slot outlined, and the battery's state
  of charge today as a pale blue line. The legend names the current and
  the next slot.
- Overhead: Map, **one row without the map**: the three nearest aircraft
  side by side, each with its registration over its picture, type and
  operator, height, speed in km/h, distance and a compass arrow pointing
  where it is from the place.
- A **Language** switch on Travel time, Weather, Today, Energy, Dynamic
  Price, Home batteries and Overhead: Map (Nederlands, English, Deutsch,
  or the dashboard's own), so a page can be one language throughout.
- Overhead: a **Paper** choice "The page's own", so a widget has no paper of
  its own and sits on the dashboard's background (the default for the map).

## [0.1.2] - 2026-11-01

Built on Tesserae 0.480.0, from commit `e786d19`.

### Fixed
- Overhead: the five Overhead widgets load again and are back in the widget
  picker. Tesserae refused their version `0.11.3.1` and skipped them with
  "manifest schema [version] does not match"; it is now `0.11.3+fork.1`.

## [0.1.1] - 2026-11-01

Built on Tesserae 0.480.0, from commit `6c5e271`.

### Added
- paperlesspaper: paste the API key on the paperlesspaper page itself
  (Settings › Widgets › paperlesspaper › Open admin), with a **Replace key**
  form once one is set. The key is stored encrypted, as before.
- Energy, Dynamic Price: a portrait layout for the paperlesspaper OpenPaper 7
  and OpenPaper L. Text follows the widget type scale, and day captions no
  longer clip.
- A logo and icon for the app in the Home Assistant store.

### Fixed
- paperlesspaper: the "add your API key" link led to the widget list, whose
  **Open admin** button led straight back: there was no way to the key
  field. It now links to the plugin's card under Settings › Widgets.
- Menu paths in messages and docs now read Settings › Widgets › … instead of
  Plugins › ….

## [0.1.0] - 2026-11-01

Built on Tesserae 0.480.0, from commit `ad7e2ba`.

### Added
- The Home Assistant app: the official Tesserae image with this repository's
  plugins and device kind added at build time.
- paperlesspaper Core: uploads every new frame of a paperlesspaper device to
  its paper in the paperlesspaper cloud, and manages your frames (which paper
  is shown, battery, last wake-up, Upload now).
- Device kind *paperlesspaper frame (stock firmware)*: 1600 × 1200, Spectra 6.
- Overhead (fork of `dmellok/tesserae-widget-overhead` 0.11.3) with a height
  ceiling beside the radius, and more helicopters recognised.
- Energy, Dynamic Price: EPEX and Tibber electricity prices for today and
  tomorrow.

[Unreleased]: https://github.com/Emacee/Tesserae-Paperlesspaper/compare/b82a2b4...master
[0.2.1]: https://github.com/Emacee/Tesserae-Paperlesspaper/compare/37edbac...b82a2b4
[0.2.0]: https://github.com/Emacee/Tesserae-Paperlesspaper/compare/e786d19...37edbac
[0.1.2]: https://github.com/Emacee/Tesserae-Paperlesspaper/compare/6c5e271...e786d19
[0.1.1]: https://github.com/Emacee/Tesserae-Paperlesspaper/compare/ad7e2ba...6c5e271
[0.1.0]: https://github.com/Emacee/Tesserae-Paperlesspaper/tree/ad7e2ba26e101fa9fbb8248146d5efc8d31c096e
