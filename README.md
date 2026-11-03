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

    NAS container (:12, :32, :52)         LilyGO T5 (wakes at :40, on reset, on button)
    render.py → site/*.raw, *.png  ──►  GitHub Pages  ──►  download all 4 to flash
    push to gh-pages                                        show one, deep sleep

- `render.py` fetches the three points in one pass, renders the screens and
  writes `site/` (`<view>.raw` for the panel, `<view>.png` and `index.html` to
  check in a browser, `status.json` with the forecast run). Its configuration
  block repeats the notebooks' point ids.
- `nas/publish.py` runs it on the NAS at :12, :32 and :52 (MeteoSwiss
  publishes 2–7 min past the hour; the T5 fetches at :40) and force-pushes
  `site/` as a single commit to the `gh-pages` branch, which Pages serves
  (Settings → Pages → Source: "Deploy from a branch", `gh-pages`, `/ (root)`).
  See "On the NAS" below. It replaced a scheduled GitHub Actions workflow,
  because GitHub dropped most of its scheduled runs.
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
seen by anyone with the address.

## On the NAS (TrueNAS SCALE 24.10+)

A Custom App (one Docker container, `nas/compose.yaml`) renders and publishes:

1. **Dataset**: create one, e.g. `tank/apps/forecast` (Datasets → Add, preset
   Apps). It holds a clone of this repository, the Python venv and the
   forecast cache (runs older than 7 days are deleted). The container runs
   as the `apps` user (568), so the dataset and everything in it must belong
   to `apps`: the Apps preset does that for a new dataset; for one used
   before, set the owner to `apps` with "Apply recursively" (Datasets → Edit
   Permissions), or empty it.
2. **Token**: on GitHub, Settings → Developer settings → Fine-grained tokens →
   Generate: repository access "Only select repositories" → this one,
   permission Contents: Read and write. Note the expiry date and renew it
   before then (the push fails once it has expired).
3. **App**: Apps → Discover Apps → ⋮ → Install via YAML, name it `forecast`,
   paste `nas/compose.yaml`, then set the token and the dataset path
   (`/mnt/<pool>/<dataset>`).

On start the container clones the repository into the dataset (first time
only), pulls `main`, installs `requirements.txt` into `.venv-nas/`, renders
once, then again at :12, :32 and :52. Each round pulls `main` first, so code
pushed to GitHub is used from the next round; restart the app after changing
`requirements.txt`. Logs: Apps → forecast → Workloads → logs (one
"published" or "failed" line per round, plus the render output).

To try it on a PC: `python nas/publish.py --once` (pushes with git's own
credentials when `GITHUB_TOKEN` is not set).

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
