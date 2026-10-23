# Project context

Three forecast views (home, boat, chalet) from the MeteoSwiss local forecast
(OGD, `ch.meteoschweiz.ogd-local-forecasting`), inspired by
https://github.com/MeteoSwiss/opendata-localforecast-demos. Plan: prototype in
notebooks first, later an ESP32 app with a display. The ESP32 should receive
the small per-view JSON built by `notebooks/localforecast.py`, not raw CSVs
(each parameter CSV is ~33 MB for all points).

- Home: forecast for now (temp + pictogram), solar production estimate for
  today, 48 h temperature + rain/snow, 5-day outlook (same pane as chalet,
  with precipitation instead of new snow).
- Boat: wind in knots: mean with 10–90 % range, gusts, direction (Lake Geneva).
- Chalet: like home without solar; estimated new snow, sunshine, daily outlook,
  SLF avalanche bulletin (danger level, problem, aspect compass, altitude).

Describe all data as forecasts (e.g. "forecast for now", not "current").

## Decisions so far

- No pvlib: it needs h5py, which has no wheel for Python 3.15. The PV model
  in `localforecast.pv_power` is self-contained, so it could be ported.
- Snowfall is not a published parameter: estimated from `rre150h0` and the
  zero-degree level `zprfr0hs` (rain→snow ramp 500–100 m below it), 1 mm ≈ 1 cm.
- SLF bulletin: `https://aws.slf.ch/api/bulletin/caaml/en/json`, empty outside
  the season; `?activeAt=<ISO time>` returns past bulletins for testing.
- Locations: home Renens VD 102000/2, boat Lutry 109500/2 (lake shore,
  392 m), chalet St-Luc 396122/2 (1658 m), SLF region CH-4124 Val d'Anniviers.
- PV: the placeholder (10 kWp, 30°, south) stays until the user says otherwise.
- Outlook: home and chalet share the daily pane (`lf._days`,
  `screens._daily`); the 6 half-day outlook was dropped on 23 Oct 2026.
- Colour (notebooks) is for charts and icons only: numbers stay in the text
  colour on all screens.
- Display: LilyGO T5 4.7" e-paper V2.3 (ESP32-S3-WROOM-1 N16R8: 16 MB flash,
  8 MB PSRAM; ED047TC1 panel 960×540, 16 greys; driver LilyGo-EPD47,
  branch esp32s3). Panel is ~104×58 mm (~234 dpi), so screen text is never
  below 11 pt (15 px). Full refreshes only: LilyGO warns long partial-refresh
  use leaves ghosting / damage.
- `screens.render(draw, view)` draws a screen at 960×540 snapped to 16 greys;
  `screens.epd_buffer(img)` packs it to 259,200 bytes for
  `epd_draw_grayscale_image` (4 bpp, 0 = black, even x in the low nibble).
- Icons: own vector set in `notebooks/icons.py` (code → sky, precipitation,
  amount, thunder), bold outlines for e-ink, same shapes in colour. Style
  inspired by LilyGo-EPD-4-7-OWM-Weather-Display, but its code is
  "Copyright David Bird, all rights reserved" with no license: do not copy it.
- `render(draw, view, colour=True)` gives the colour version (notebooks
  show both); palettes are `screens.COLOUR` / `screens.GREY`.
- Refresh: every 60 min, plus once on boot/reset. Full refresh each time.
  Runs are named by the hour and published 2–7 min past it (checked 22 Oct
  2026): the workflow renders at :10, the T5 fetches at :40 because GitHub
  often starts scheduled jobs late.
- Rendering is server-side: `render.py` → `site/` → GitHub Pages via
  `.github/workflows/render.yml`. One T5: the PlatformIO project `firmware/` (`src/main.cpp`)
  downloads all three `<view>.raw` into LittleFS each hour; the button
  (BUTTON_1 = GPIO21, ext0 wake) cycles home → boat → chalet from flash with
  no Wi-Fi. Current view is kept in NVS (Preferences). After a button wake or power
  on / reset it stays awake 20 s after the last press (`AWAKE_MS`, presses
  counted by interrupt, also during a refresh); hourly timer wakes sleep at
  once. `epd_poweroff()` between draws, `epd_poweroff_all()` only before
  deep sleep (it zeroes the driver's config register).
  Pages is public (and needs a public repo on a free plan).
- Repo: https://github.com/frgaude/MeteoSwiss-local-forecast (public), Pages
  https://frgaude.github.io/MeteoSwiss-local-forecast/ (Source: GitHub
  Actions). First workflow run succeeded on 23 Oct 2026 in ~1 min.

- Firmware builds with PlatformIO (`~/.platformio/penv/Scripts/pio.exe run`
  in `firmware/`): espressif32@6.12.0 (Arduino core 2.0.x), LilyGO's
  `T5-ePaper-S3` board file copied to `firmware/boards/`, LilyGo-EPD47 pinned
  to commit 5022422 of branch esp32s3. `include/secrets.h` is gitignored.

- Firmware runs on the T5 (flashed 23 Oct 2026 over native USB, COM14):
  downloads, display and button all work. Wakes at HH:40 (sleeps ≥ 5 min
  after a fetch), retries after 10 min on failure.
