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
- Overhead: the five Overhead widgets load again. Their version is now
  `0.11.3+fork.1`; Tesserae refused `0.11.3.1`, so Photo, Plate, Cluster and
  Scene were missing from the widget picker.

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

[Unreleased]: https://github.com/Emacee/Tesserae-Paperlesspaper/compare/6c5e271...master
[0.1.1]: https://github.com/Emacee/Tesserae-Paperlesspaper/compare/ad7e2ba...6c5e271
[0.1.0]: https://github.com/Emacee/Tesserae-Paperlesspaper/tree/ad7e2ba26e101fa9fbb8248146d5efc8d31c096e
