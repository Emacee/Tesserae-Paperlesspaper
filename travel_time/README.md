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

## Your sensors stay yours

The sensors are picked from a dropdown in the cell's options: travel-time
sensors only, Waze first, each with its current value. They are stored with
the page in Tesserae, not in this widget. A page exported as a template
leaves them out and asks the new user for their own. The names you type are
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
