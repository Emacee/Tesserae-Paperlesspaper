# Mijn Afvalwijzer (`afvalwijzer_core`)

The collection dates of your household waste, for the waste widgets. It has no
cell of its own: give your **postcode** and **house number** (and an addition,
if you have one) once under **Settings › Widgets › Mijn Afvalwijzer**, and

- **Waste, next collection** (`waste_next`) shows the next bin, as a round tile
  or a short list, and
- **Agenda, with travel time** shows the collections on their days when you
  switch on *Waste collection* in its cell.

## How it works

The dates come from the web service behind
[mijnafvalwijzer.nl](https://www.mijnafvalwijzer.nl), which covers the
municipalities that use Mijn Afvalwijzer. It is asked once every twelve hours
and the answer is kept in memory and on disk; when the service is down for a
while, the last answer is used. Your address is a secret setting and is only
sent to mijnafvalwijzer.nl.

The service is **unofficial**: it is what the Mijn Afvalwijzer app and website
use, with the key they use (public, found in many open-source projects, and a
setting here in case it changes). If your address is not known to it, the
widgets say so instead of staying empty.

The types are those of your municipality's calendar, usually `gft`,
`restafval`, `pmd`, `papier`, and sometimes `glas`, `textiel`, `kerstbomen`.
