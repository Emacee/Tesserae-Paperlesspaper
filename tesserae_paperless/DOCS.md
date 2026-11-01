# Tesserae + paperlesspaper

[Tesserae](https://docs.tesserae.ink) composes and renders e-ink dashboards.
This app is the official Tesserae image with three things added from
[Tesserae-Paperlesspaper](https://github.com/Emacee/Tesserae-Paperlesspaper):

- **paperlesspaper Core** (Settings › Widgets › paperlesspaper › Open
  admin): uploads each new frame
  of a paperlesspaper device to its paper in the paperlesspaper cloud, and
  manages your frames: which paper each shows (the Tesserae one, or one of
  paperlesspaper's own integrations), battery, last wake-up, Upload now.
- **paperlesspaper frame (stock firmware)**: a device kind of 1600 × 1200
  (13.3", Spectra 6) that Tesserae renders for without anything polling it.
- **Overhead** (fork) with a height ceiling, and **Energy, Dynamic Price**.

The frame keeps its paperlesspaper firmware. It wakes on the update periods
set in the paperlesspaper app, fetches its paper's image from the
paperlesspaper cloud, and sleeps. Tesserae puts the image there.

## Setup

1. **Install.** Settings › Apps › App store › ⋮ › Repositories, add
   `https://github.com/Emacee/Tesserae-Paperlesspaper`, install
   **Tesserae + paperlesspaper** and start it. Open it from the sidebar.
2. **API key.** Create one at
   [web.paperlesspaper.de/account](https://web.paperlesspaper.de/account).
   In Tesserae: Settings › Widgets › paperlesspaper › **Open admin**,
   paste it under **Add your API key** and press **Save key**.
3. **An image paper for Tesserae.** In the paperlesspaper app, add an image
   paper to your frame (any picture will do; Tesserae replaces it). Keep
   your integrations (XKCD, calendar, …) as their own papers.
4. **A Tesserae device.** Settings › Devices › Add device, kind
   **paperlesspaper frame (stock firmware)**. For a portrait frame, set the
   device's panel to portrait (1200 × 1600) and the device's orientation to
   portrait.
5. **Link.** The paperlesspaper page (Settings › Widgets › paperlesspaper ›
   Open admin) lists your frames and their papers.
   Press **Link** on the Tesserae image paper (with your new device chosen):
   the device uploads to it from now on, and the current frame goes up at
   once. Press **Show** on that paper so the frame displays it.
6. **A page.** Give the device a page (for example Overhead, Cluster) and a
   schedule. Every render is uploaded; nothing is uploaded when the frame did
   not change.
7. **Wake-ups.** In the paperlesspaper app, set the frame's update periods to
   match the page's schedule. A new image shows at the next wake-up; press
   the frame's button or shake it to fetch it now.

To show one of paperlesspaper's own integrations instead, press **Show** on
its paper. Tesserae keeps uploading to its own paper meanwhile, so switching
back is instant.

## Good to know

- Frames reach the panel through the paperlesspaper cloud: a render is
  uploaded to `api.paperlesspaper.de` and paperlesspaper dithers it for the
  panel. An upload never wakes a sleeping frame.
- The API allows 300 requests a minute; a render costs one upload.
- Port 8765 is closed by default. Open it on the Network tab only for panels
  that fetch frames from Tesserae itself (ESP32, Kindle, TRMNL).
- The Configuration tab's MQTT settings are only for MQTT panels and Home
  Assistant discovery; a paperlesspaper frame needs none.
- Your data (pages, settings, paintings) lives in the app's `/data` and is in
  Home Assistant backups.
