# Home batteries (`home_batteries`)

Small rings for the batteries in the house, side by side:

- **Home battery**: a Deye hybrid inverter through the
  [Solarman integration](https://github.com/davidrapan/ha-solarman). Its
  state of charge, whether it charges, discharges or rests (an arrow and a
  word: the power itself changes too often for e-paper), its work mode
  (Export First, Zero Export to CT, Zero Export to Load), and the target of
  the time-of-use slot it is in, as a tick on the ring.
- **Car**: any integration (Tibber's for a Volkswagen, for example): state
  of charge, charge limit as a tick, range in km (from m, km or mi), and
  whether it charges or is plugged in.

The ring fills red under 20%, ochre under 40%, green above. Icons are drawn
by the widget in 2 px strokes, sharp on e-paper.

## Settings

Pick the inverter (the device of its *Work Mode* select; the widget reads
`sensor.<device>_battery`, `sensor.<device>_battery_state`,
`select.<device>_work_mode` and the six `program_N` time, SOC and charging
entities) and the car's sensors. All are kept as secrets: never in the
page's markup, left out of an exported template, and none in this widget.

A slot set to charge from the grid with a target of 10% or less charges
nothing and is not counted as grid charging (*Grid charging counts from*).

**Language**: Nederlands, English, Deutsch, or the dashboard's own.

`deye.py` is shared with Energy, Dynamic Price, which draws the same
schedule over the prices.

```sh
python -m pytest home_batteries/tests -q
```
