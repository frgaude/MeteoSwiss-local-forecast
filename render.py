"""Render the home, boat, chalet and mountain screens for the LilyGO T5 4.7" e-paper.

Writes into site/ (published by GitHub Pages, see .github/workflows/render.yml):

    <view>.raw    259,200-byte 4-bit frame buffer the T5 downloads and shows
    <view>.png    the same screen, for checking in a browser
    <view>.json   the view payload
    status.json   forecast run and render time
    index.html    previews

Usage: python render.py [out_dir]
"""
import json
import os
import sys
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "notebooks"))
import localforecast as lf  # noqa: E402
import screens  # noqa: E402

# ── Configuration (same as the notebooks' configuration cells) ──────────────
HOME = (102000, 2)        # Renens VD
BOAT = (109500, 2)        # Lutry, lake shore
WIND_STATION = "CHVD19"   # WindSpots: Lutry - Port du Vieux-Stand, measured wind
CHALET = (396123, 2)      # Chandolin, 1900 m
MOUNTAIN = (1119, 3)      # Le Toûno, 3018 m (point of interest)
SLF_REGION = "CH-4124"    # Val d'Anniviers
SLF_STATION = "ANV2"      # Orzival, 2640 m: measured snow depth
PV = {"kwp": 7.905, "tilt": 29, "azimuth": 212, "derate": 0.88}   # azimuth 180 = south
# ─────────────────────────────────────────────────────────────────────────────


def _optional(fetch, *args):
    """`fetch(*args)`, or None (logged) if it fails in any way."""
    try:
        return fetch(*args)
    except Exception as e:
        print(f"{fetch.__name__}{args}: unavailable ({e!r})")
        return None


def main(out):
    os.makedirs(out, exist_ok=True)
    # one pass over each parameter CSV for all points
    params = sorted(set(lf.HOME_PARAMS) | set(lf.BOAT_PARAMS) | set(lf.CHALET_PARAMS)
                    | set(lf.MOUNTAIN_PARAMS))
    run, data = lf.fetch([HOME, BOAT, CHALET, MOUNTAIN], params)
    try:
        # a past time (ISO, UTC) shows the bulletin valid then, for testing the layout
        bulletin = lf.slf_bulletin(SLF_REGION, active_at=os.environ.get("SLF_ACTIVE_AT") or None)
    except Exception as e:  # the screen still works without it
        print(f"SLF bulletin unavailable: {e}")
        bulletin = None
    # measurements: an unreachable or broken source leaves its block empty,
    # it must never stop the screens from being rendered
    station = _optional(lf.slf_station, SLF_STATION)
    measured = _optional(lf.windspots_station, WIND_STATION)
    views = {
        "home": (screens.home, lf.home_view(run, *data[HOME], lf.point_info(HOME), PV)),
        "boat": (screens.boat, lf.boat_view(run, data[BOAT][0], lf.point_info(BOAT), measured)),
        "chalet": (screens.chalet, lf.chalet_view(run, *data[CHALET], lf.point_info(CHALET), bulletin, station)),
        "mountain": (screens.mountain, lf.mountain_view(run, data[MOUNTAIN][0], lf.point_info(MOUNTAIN), bulletin, station)),
    }
    for name, (draw, view) in views.items():
        img = screens.render(draw, view)
        img.save(os.path.join(out, f"{name}.png"), optimize=True)
        with open(os.path.join(out, f"{name}.raw"), "wb") as f:
            f.write(screens.epd_buffer(img))
        with open(os.path.join(out, f"{name}.json"), "w", encoding="utf-8") as f:
            json.dump(view, f, ensure_ascii=False, separators=(",", ":"))

    rendered = datetime.now(lf.TZ)
    with open(os.path.join(out, "status.json"), "w") as f:
        json.dump({"run": lf.run_time(run).isoformat(), "rendered": rendered.isoformat(timespec="seconds")}, f)
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(f"""<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Local forecast screens</title>
<style>body{{font-family:system-ui,sans-serif;margin:16px;background:#fff;color:#111}}
img{{max-width:100%;border:1px solid #ccc;margin:8px 0 24px}}</style>
<h1>Local forecast screens</h1>
<p>Forecast run {lf.run_time(run):%a %d %b %H:%M}, rendered {rendered:%H:%M}.
Data: MeteoSwiss (OGD) and SLF.</p>
""" + "".join(f'<h2>{n}</h2><img src="{n}.png" alt="{n} screen">\n' for n in views))
    print(f"run {run}: wrote {', '.join(views)} to {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "site")
