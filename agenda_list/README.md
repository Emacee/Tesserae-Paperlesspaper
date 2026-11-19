# Agenda, with travel time (`agenda_list`)

The next days as a list, one row per day, with the drive from home to each
event's location and the time to leave. Events come from **Settings ›
Widgets › Calendar Feeds** (the Calendar Core plugin).

## What you see

- A row per day: the weekday and date in fixed columns, so they line up
  whatever the day holds. Today is in the accent colour.
- **All day** events as a chip in their calendar's colour. One that runs for
  several days shows once, on its first day, with *through Sat*.
- Timed events: the start time, the title, *until 15:30*, and the location on
  a line below with a pin.
- On the right, for events with a location that have not started yet: the
  drive by car (**34 min**) and **leave 09:21**.

## The drive

The widget asks Home Assistant's `waze_travel_time.get_travel_times` service
for the drive from home to the event's location, so the **Waze Travel Time**
integration must be set up in Home Assistant (it needs no account), and the
**Home Assistant Core** plugin must be configured (Settings › Widgets).

- *Time to leave* = start − drive (rounded up) − the margin (5 minutes by
  default, a cell option).
- *Home* is the Home Assistant zone `zone.home`; change it in the cell's
  options to an address, a device or `latitude,longitude`. It is kept with
  the page and left out of an exported template.
- An event less than three hours away gets a live answer with traffic, kept
  for ten minutes. Further away, the answer is kept for six hours. A location
  Waze cannot find is tried again after half an hour, and shown without a
  drive meanwhile.
- At most twelve locations are sent per refresh, and only for events in the
  first *Work out the drive for* days (7 by default).
- No locations, no Waze, no problem: the list simply shows no drive.

## Options

Days, calendars, feed symbol before titles (off by default), drive time on or
off, home, Waze region, margin, language.
