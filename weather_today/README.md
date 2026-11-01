# Weather, Today (`weather_today`)

Today's weather as a column, made for a narrow portrait cell (about 290 px
wide on a 1200 × 1600 paperlesspaper L):

- On top: the date, the weather now (icon, temperature, what it is like),
  the day's high and low and its rain in mm. On a day with rain the
  headline is the day's weather (*Showers, sunny spells*), otherwise what it
  is now.
- Below: one row per hour from the hour you pick (07:00 by default) to
  midnight: icon, temperature and a blue bar for the rain in that hour. The
  hours gone by are faded; the current hour is marked. When the rows do not
  fit, the earliest past hours go first.

The icons are drawn by the widget in the few inks of a colour e-paper panel:
a yellow sun, white clouds with a dark outline, blue rain.

Data from [Open-Meteo](https://open-meteo.com) (no key), cached for ten
minutes per place.

```sh
python -m pytest weather_today/tests -q
```
