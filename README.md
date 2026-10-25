# MeteoSwiss local forecast — home, boat, chalet, mountain

Three forecast views built on the MeteoSwiss local forecast
(`ch.meteoschweiz.ogd-local-forecasting`, OGD, updated hourly), prototyped as
notebooks before moving to a LilyGO T5 4.7" e-paper (ESP32-S3).

| notebook | shows |
|---|---|
| `notebooks/Home.ipynb` | forecast for now, estimated solar production today, 48 h temperature + rain/snow, daily outlook (min/max, precipitation, sunshine) |
| `notebooks/Boat.ipynb` | 48 h wind in knots: mean with 10–90 % range, gusts, direction |
| `notebooks/Chalet.ipynb` | estimated new snow and sunshine, daily outlook, SLF avalanche bulletin (level, problem, aspects, altitude) |
| `notebooks/Mountain.ipynb` | summit: the chalet's top panel (now, new snow, sunshine, avalanche bulletin), then wind every 3 h, sunshine with sunrise/sunset, snow, rain and temperature |

`notebooks/localforecast.py` does the work: it streams each parameter CSV
(~33 MB, all ~5,800 points), keeps only your points, caches them under
`data/local_forecast/<run>/`, and builds one small dict per view (~3 KB as JSON):
the payload a display would receive. `notebooks/screens.py` draws each screen
for a LilyGO T5 4.7" e-paper (960×540, 16 grey levels): `screens.render(screens.home, view)`
returns the image and `screens.epd_buffer(img)` packs it to the 259,200-byte
frame buffer the LilyGo-EPD47 driver draws.

## Setup (Windows)

    python -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt

Then open the notebooks in VS Code or Jupyter and edit the configuration cell
(point ids, PV system, SLF region; currently Renens, Lutry, Chandolin and Le Toûno).

## On the e-paper

    GitHub Actions (:12, :32, :52)        LilyGO T5 (wakes at :40, on reset, on button)
    render.py → site/*.raw, *.png  ──►  GitHub Pages  ──►  download all 3 to flash
                                                            show one, deep sleep

- `render.py` fetches the three points in one pass, renders the screens and
  writes `site/` (`<view>.raw` for the panel, `<view>.png` and `index.html` to
  check in a browser, `status.json` with the forecast run). Its configuration
  block repeats the notebooks' point ids.
- `.github/workflows/render.yml` runs it at :12, :32 and :52 (MeteoSwiss
  publishes 2–7 min past the hour; GitHub often drops scheduled runs, hence
  three an hour) and deploys `site/` to GitHub Pages. In the
  repository settings, set Pages → Source to "GitHub Actions".
- `firmware/` is a PlatformIO project (`src/main.cpp`). Each hourly wake
  (and power on / reset) downloads all four screens into flash and shows the
  current one; the button (GPIO21) wakes the board and shows the next screen
  from flash, without Wi-Fi, then stays awake 20 s after the last press so
  you can keep switching. Copy `include/secrets.h.example` to
  `include/secrets.h` (Wi-Fi and the Pages address), then open `firmware/` in
  VS Code with the PlatformIO extension, or run
  `pio run -t upload && pio device monitor` there. Board settings and the
  LilyGo-EPD47 library (pinned commit of branch `esp32s3`) are in
  `platformio.ini`.

GitHub Pages sites are public, so the screens (place names, forecasts) can be
seen by anyone with the address. GitHub can start scheduled jobs late under
load and pauses them in repositories with no activity for 60 days.

## Notes

- Snowfall is not published: it is estimated from forecast precipitation and the
  zero-degree level, at ~1 cm of snow per mm of water.
- Solar production uses a small built-in PV model (solar position, panel-plane
  irradiance, temperature derate), the same approach as the MeteoSwiss
  SolarProduction demo but without pvlib.
- The SLF bulletin (`aws.slf.ch`) is empty outside the winter season; set
  `SLF_ACTIVE_AT` to a past winter time to try the layout.
- Weather icons are drawn as vectors by `notebooks/icons.py` (bold outlines
  for e-paper, the same shapes in colour for the notebooks), one per
  MeteoSwiss pictogram code; the code descriptions come from
  [MeteoSwiss/opendata-localforecast-demos](https://github.com/MeteoSwiss/opendata-localforecast-demos)
  (BSD-3-Clause).
