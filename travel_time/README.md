# Travel time (`travel_time`)

Travel time to work in the morning and home in the afternoon, for up to
three people, from travel-time sensors in Home Assistant: **Waze Travel
Time**, **Google Maps Travel Time**, or any sensor in minutes. Requires the
**Home Assistant Core** plugin (URL and token under Settings › Widgets).

## What you see

- **Travel time to work** until the hour under *Home from* (14:00 by
  default), **Travel time home** from then on.
- A row per person: their initial, name and roads (`via A12 · A2`, from the
  Waze route), the minutes large on the right.
- **+8 min** in red when the trip takes longer than normal for that weekday
  and time of day; a quiet **normal** otherwise. The threshold is a cell
  option (+2 min by default).
- At the weekend the cell is empty (or shown, if you choose).

## The strip, with the car

*Layout: A strip* puts the blocks side by side for a wide, low cell (about 900
by 150): first the car, with its range in km and whether it is plugged in or
charging (pick the range, plug and charging sensors in the cell; all are kept as
secrets), then each person with the minutes large and, when a sensor knows what
is normal, **+4**. At the weekend the commutes rest and the car stays.

## When Waze is down: OSRM

If a sensor has no value (Waze Travel Time cannot reach Waze, or the sensor was
never set up), the drive can still be worked out from the person's **work
address** (a cell option) with the free **OSRM** routing service. The places
are found with OpenStreetMap's Nominatim, once each (kept on disk). OSRM knows
no traffic, so 15% is added (a cell option), the minutes show with a **≈**, no
delay against normal is given, and a line at the bottom says so. Only your home
position (the Home Assistant zone `zone.home` unless the cell says otherwise)
and the work address are sent to those two services, under a generic client
name. *Drive time from* in the cell chooses: the sensor and OSRM when it has no
value (the default), the sensor only, or OSRM only.

## Your sensors stay yours

The sensors are picked from a dropdown in the cell's options: travel-time
sensors only, Waze first, each with its current value. They are stored with
the page in Tesserae, not in this widget. A page exported as a template
leaves them out and asks the new user for their own. The work addresses and the names you type are
stored with the page as well; leave a name blank to use the sensor's name.

## "Normal"

The median of the same sensor on the same weekday at the same quarter of an
hour, over the last 4, 6 or 8 weeks (a cell option), from Home Assistant's
history. It is worked out once a day per sensor, in the background, and kept
in the widget's data folder (named by a hash, not by the sensor). Until
there is enough history the delay is left out.

Home Assistant's recorder keeps 10 days by default; for a baseline over
weeks, raise `purge_keep_days` in the recorder settings.

## Tests

```sh
python -m pytest travel_time/tests -q
```
