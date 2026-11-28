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

Two sources, chosen in the cell (*Drive time from*), **Waze, and OSRM when
Waze does not answer** by default.

- **Waze**, through Home Assistant's `waze_travel_time.get_travel_times`
  service: live traffic, but it needs the **Waze Travel Time** integration in
  Home Assistant (no account) and the **Home Assistant Core** plugin
  (Settings › Widgets).
- **OSRM**, a free routing service with no account or key. It knows no
  traffic, so a surcharge (15% by default, a cell option) is added and the
  drive shows with **≈**, with a line at the bottom saying so. The places are
  found with OpenStreetMap's Nominatim, once each (kept on disk), at most four
  new ones per refresh. Only your home position and the event locations are
  sent to those two services, under a generic client name.

For both:

- *Time to leave* = start − drive (rounded up) − the margin (5 minutes by
  default, a cell option).
- *Home* is the Home Assistant zone `zone.home`; change it in the cell's
  options to an address, a device or `latitude,longitude`. It is kept with
  the page and left out of an exported template.
- A Waze answer for an event less than three hours away has live traffic and
  is kept for ten minutes; further away it is kept for six hours. After Waze
  fails, OSRM is used straight away for ten minutes before Waze is tried again.
- A location nobody can find is tried again after a while, and the event shows
  without a drive.
- At most twelve locations are worked out per refresh, and only for events in
  the first *Work out the drive for* days (7 by default).
- No locations, no services, no problem: the list simply shows no drive.

## Options

Days, calendars, feed symbol before titles (off by default), drive time on or
off, source, home, Waze region, surcharge without traffic, margin, language.

## Waste collections, with icons

*Waste collection* shows the collections on their days with a bin icon in the colour
of the stream, once each. They come from two places, either is enough:

- **Mijn Afvalwijzer** (the plugin of that name: postcode and house number under
  Settings › Widgets), and
- **waste events in your calendars**: an all-day event whose title names one stream
  (*GFT*, *GFTE*, *Restafval*, *PMD*, *Papier*, *Glas* …, with or without an emoji), for
  instance the Mijn Afvalwijzer iCal subscription added under **Calendar Feeds**. A
  title that says anything else (*Restaurant*, *GFT en restafval*) stays an ordinary
  event.

An iCal feed carries no icon of its own; the icon is chosen from the title.
