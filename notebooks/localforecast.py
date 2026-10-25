"""MeteoSwiss local forecasts (collection ch.meteoschweiz.ogd-local-forecasting)
for a few points, reduced to small per-screen payloads (home, boat, chalet, mountain).

Each parameter is one CSV per run covering all ~5,800 points (~33 MB), so
`fetch` streams it once and keeps only the rows of the requested points,
cached under data/local_forecast/<run>/. The `*_view` functions then build
plain dicts, small enough to serve as JSON to a microcontroller display.

Forecast data: MeteoSwiss OGD. Avalanche bulletin: WSL Institute for Snow and
Avalanche Research SLF (aws.slf.ch, CAAML JSON).
"""
import json
import os
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

STAC = "https://data.geo.admin.ch/api/stac/v1"
COLLECTION = "ch.meteoschweiz.ogd-local-forecasting"
POINTS_URL = f"https://data.geo.admin.ch/{COLLECTION}/ogd-local-forecasting_meta_point.csv"
SLF_URL = "https://aws.slf.ch/api/bulletin/caaml/{lang}/json"
ICONS_URL = ("https://raw.githubusercontent.com/MeteoSwiss/opendata-localforecast-demos/"
             "main/notebooks/icons/")

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "local_forecast")
TZ = ZoneInfo("Europe/Zurich")
KMH_TO_KT = 1 / 1.852

# parameters the views need (see the OGD parameter metadata for descriptions)
HOME_PARAMS = ["tre200h0", "jww003i0", "rre150h0", "rp0003i0", "zprfr0hs", "sre000h0",
               "gre000h0", "ods000h0", "jp2000d0", "tre200pn", "tre200px"]
BOAT_PARAMS = ["fu3010h0", "fu3010h1", "dkl010h0", "fu3q10h0", "fu3q90h0",
               "fu3q90h1", "tre200h0", "jww003i0"]
CHALET_PARAMS = ["tre200h0", "jww003i0", "rre150h0", "rp0003i0",
                 "zprfr0hs", "sre000h0", "jp2000d0", "tre200pn", "tre200px"]
MOUNTAIN_PARAMS = ["tre200h0", "jww003i0", "rre150h0", "zprfr0hs", "sre000h0",
                   "fu3010h0", "fu3010h1", "dkl010h0", "jp2000d0", "tre200pn", "tre200px"]
DAILY = {"jp2000d0", "tre200pn", "tre200px", "rka150p0", "rreq10p0", "rreq90p0"}


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def latest_run():
    """Return (run, {param: csv url}) for the newest run published.

    Items are named by production date (local), so look at today's item and
    fall back to yesterday's: just after midnight today's item exists but
    is still empty. A run's files arrive over a few minutes, so only runs
    with as many files as the fullest run of the item count."""
    today = datetime.now(TZ).date()
    for day in (today, today - timedelta(days=1)):
        r = requests.get(f"{STAC}/collections/{COLLECTION}/items/{day:%Y%m%d}-ch", timeout=30)
        if r.status_code == 404:
            continue
        r.raise_for_status()
        runs = {}
        # asset keys look like vnut12.lssw.<YYYYMMDDHHMM>.<param>.csv
        for k, a in r.json()["assets"].items():
            runs.setdefault(k.split(".")[2], {})[k.split(".")[3]] = a["href"]
        if not runs:
            continue
        full = max(len(u) for u in runs.values())
        run = max(k for k, u in runs.items() if len(u) == full)
        return run, runs[run]
    raise RuntimeError("no local-forecast run for today or yesterday")


def points():
    """All forecast points (stations, towns, postal codes) as a DataFrame."""
    path = os.path.join(OUT_DIR, "meta_point.csv")
    if not os.path.exists(path):
        os.makedirs(OUT_DIR, exist_ok=True)
        r = requests.get(POINTS_URL, timeout=60)
        r.raise_for_status()
        with open(path, "wb") as f:
            f.write(r.content)
    return pd.read_csv(path, sep=";", encoding="latin-1")


def _plain(text):
    """Lower case without accents, so "touno" finds "Le Toûno"."""
    return "".join(c for c in unicodedata.normalize("NFD", text.lower())
                   if unicodedata.category(c) != "Mn")


def find_point(text):
    """Points whose name, station abbreviation or postal code contains `text`
    (case and accents ignored)."""
    p = points()
    hay = (p["point_name"].astype(str) + " " + p["station_abbr"].fillna("").astype(str)
           + " " + p["postal_code"].fillna("").astype(str))
    cols = ["point_id", "point_type_id", "point_name", "station_abbr", "postal_code",
            "point_type_en", "point_height_masl"]
    return p.loc[hay.map(_plain).str.contains(_plain(text), regex=False), cols]


def point_info(key):
    """{name, lat, lon, alt} of point (point_id, point_type_id)."""
    p = points()
    r = p[(p["point_id"] == int(key[0])) & (p["point_type_id"] == int(key[1]))].iloc[0]
    return {"name": r["point_name"], "lat": float(r["point_coordinates_wgs84_lat"]),
            "lon": float(r["point_coordinates_wgs84_lon"]), "alt": float(r["point_height_masl"])}


def _download_filtered(url, keys, path):
    """Stream one parameter CSV, keeping the header and rows of `keys`."""
    prefixes = tuple(f"{pid};{ptype};".encode() for pid, ptype in keys)
    kept = []
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        for i, line in enumerate(r.iter_lines()):
            if i == 0 or line.startswith(prefixes):
                kept.append(line)
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(b"\n".join(kept) + b"\n")
    os.replace(tmp, path)


def fetch(keys, params, run=None):
    """Forecast of `params` for points `keys` [(point_id, point_type_id), …].

    Returns (run, {key: (hourly, daily)}), hourly indexed by local time and
    daily by calendar date. Downloads only what is not cached for this run."""
    keys = [(int(a), int(b)) for a, b in keys]
    latest, urls = latest_run()
    run = run or latest
    run_dir = os.path.join(OUT_DIR, run)
    os.makedirs(run_dir, exist_ok=True)

    # the cache is valid for a parameter if it holds every requested point
    manifest_path = os.path.join(run_dir, "points.json")
    cached = set()
    if os.path.exists(manifest_path):
        with open(manifest_path) as f:
            cached = {tuple(k) for k in json.load(f)}
    if not set(keys) <= cached:
        cached |= set(keys)
        for p in params:
            path = os.path.join(run_dir, f"{p}.csv")
            if os.path.exists(path):
                os.remove(path)
    todo = [p for p in params if not os.path.exists(os.path.join(run_dir, f"{p}.csv"))]
    if todo:
        if run != latest:
            urls = {p: u.replace(latest, run) for p, u in urls.items()}
        print(f"Downloading {len(todo)} parameters for run {run} (~33 MB each, filtered)…")
        with ThreadPoolExecutor(6) as pool:
            list(pool.map(lambda p: _download_filtered(urls[p], sorted(cached),
                                                       os.path.join(run_dir, f"{p}.csv")), todo))
        with open(manifest_path, "w") as f:
            json.dump(sorted(cached), f)

    frames = {k: ({}, {}) for k in keys}
    for p in params:
        df = pd.read_csv(os.path.join(run_dir, f"{p}.csv"), sep=";")
        t = pd.to_datetime(df["Date"].astype(str), format="%Y%m%d%H%M", utc=True)
        for k in keys:
            sel = (df["point_id"] == k[0]) & (df["point_type_id"] == k[1])
            if p in DAILY:
                # daily values are stamped 00:00 UTC of their (local) calendar date
                frames[k][1][p] = pd.Series(df.loc[sel, p].values, index=t[sel].dt.date.values)
            else:
                frames[k][0][p] = pd.Series(df.loc[sel, p].values,
                                            index=pd.DatetimeIndex(t[sel]).tz_convert(TZ))
    out = {k: (pd.DataFrame(h).sort_index(), pd.DataFrame(d).sort_index())
           for k, (h, d) in frames.items()}
    return run, out


def run_time(run):
    return datetime.strptime(run, "%Y%m%d%H%M").replace(tzinfo=timezone.utc).astimezone(TZ)


# ---------------------------------------------------------------------------
# Derived quantities
# ---------------------------------------------------------------------------

def solar_position(times, lat, lon):
    """Solar zenith and azimuth (degrees) — NOAA approximation, ~0.5° accurate."""
    t = pd.DatetimeIndex(times).tz_convert("UTC")
    doy = t.dayofyear.values
    hour = t.hour.values + t.minute.values / 60
    g = 2 * np.pi / 365 * (doy - 1 + (hour - 12) / 24)
    eqtime = 229.18 * (0.000075 + 0.001868 * np.cos(g) - 0.032077 * np.sin(g)
                       - 0.014615 * np.cos(2 * g) - 0.040849 * np.sin(2 * g))
    decl = (0.006918 - 0.399912 * np.cos(g) + 0.070257 * np.sin(g) - 0.006758 * np.cos(2 * g)
            + 0.000907 * np.sin(2 * g) - 0.002697 * np.cos(3 * g) + 0.00148 * np.sin(3 * g))
    ha = np.radians((hour * 60 + eqtime + 4 * lon) / 4 - 180)
    phi = np.radians(lat)
    cos_z = np.sin(phi) * np.sin(decl) + np.cos(phi) * np.cos(decl) * np.cos(ha)
    zenith = np.degrees(np.arccos(np.clip(cos_z, -1, 1)))
    az = np.degrees(np.arctan2(np.sin(ha), np.cos(ha) * np.sin(phi) - np.tan(decl) * np.cos(phi))) + 180
    return zenith, az % 360


def pv_power(hourly, lat, lon, kwp, tilt=30, azimuth=180, derate=0.85, gamma=-0.0043):
    """Estimated PV output (kW) per hour from forecast global/diffuse radiation.

    Same chain as the MeteoSwiss SolarProduction demo, without pvlib: direct
    beam from GHI − DHI, isotropic-sky transposition onto the panel plane,
    PVWatts with a simple cell-temperature rise. Radiation values are hourly
    means ending at the timestamp, so the sun is taken at mid-hour."""
    mid = hourly.index - pd.Timedelta(minutes=30)
    zen, az = solar_position(mid, lat, lon)
    ghi = hourly["gre000h0"].clip(lower=0).values
    dhi = np.minimum(hourly["ods000h0"].clip(lower=0).values, ghi)
    cos_z = np.cos(np.radians(zen))
    beam_h = np.where(cos_z > 0.05, ghi - dhi, 0)          # direct on horizontal
    dni = np.where(cos_z > 0.05, beam_h / np.maximum(cos_z, 0.05), 0)
    b, za = np.radians(tilt), np.radians(zen)
    cos_aoi = (np.cos(za) * np.cos(b)
               + np.sin(za) * np.sin(b) * np.cos(np.radians(az - azimuth)))
    poa = (dni * np.clip(cos_aoi, 0, None) + dhi * (1 + np.cos(b)) / 2
           + ghi * 0.2 * (1 - np.cos(b)) / 2)              # albedo 0.2
    cell = hourly["tre200h0"].values + poa * 0.03           # ~+30 °C at 1000 W/m²
    kw = kwp * poa / 1000 * (1 + gamma * (cell - 25)) * derate
    return pd.Series(np.clip(kw, 0, kwp), index=hourly.index)


def snow_fraction(hourly, altitude):
    """Share (0–1) of precipitation estimated to fall as snow at `altitude`.

    The snowfall limit is typically ~300 m below the zero-degree level; we
    ramp from rain to snow between 100 and 500 m below it. Rough estimate."""
    gap = hourly["zprfr0hs"] - altitude                     # m above the point
    return ((500 - gap) / 400).clip(0, 1)


def _days(hourly, daily, n, snow_cm=None):
    """Daily outlook for today and the next `n` - 1 days: icon, min/max,
    precipitation, sunshine, and estimated new snow if `snow_cm` is given."""
    today = datetime.now(TZ).date()
    out = []
    for i in range(n):
        d = today + timedelta(days=i)
        on = hourly.index.date == d
        if not on.any():
            break
        day = {
            "date": d.isoformat(),
            "icon": int(daily.at[d, "jp2000d0"]) if d in daily.index else None,
            "tmin": _r(daily.at[d, "tre200pn"]) if d in daily.index else None,
            "tmax": _r(daily.at[d, "tre200px"]) if d in daily.index else None,
            "precip_mm": _r(hourly.loc[on, "rre150h0"].sum()),
            "sun_h": _r(hourly.loc[on, "sre000h0"].sum() / 60),
        }
        if snow_cm is not None:
            day.update(snow_cm=_r(snow_cm[on].sum()),
                       freezing_m=int(hourly.loc[on, "zprfr0hs"].median()))
        out.append(day)
    return out


# Hours are rounded in UTC: in local time the repeated hour when summer time
# ends (02:00–03:00) is ambiguous and pandas refuses to round it. Swiss time
# is a whole number of hours from UTC, so the hour boundaries are the same.

def _now_row(hourly):
    now = pd.Timestamp.now("UTC").ceil("h")
    return hourly.loc[hourly.index >= now].iloc[0]


def _upcoming(hourly, hours):
    now = pd.Timestamp.now("UTC").floor("h")
    return hourly[(hourly.index > now) & (hourly.index <= now + pd.Timedelta(hours=hours))]


def _chart_window(hourly, hours):
    """Hours shown in the charts: `hours` hours from the last 00:00 or 12:00
    local time, so the chart also shows the past few hours. Returns the rows
    (stamped at the end of their hour) and {start, end, now} for the axis."""
    now = datetime.now(TZ)
    start = pd.Timestamp(now.replace(hour=0 if now.hour < 12 else 12, minute=0, second=0,
                                     microsecond=0)).tz_convert("UTC")
    end = start + pd.Timedelta(hours=hours)   # absolute hours, right across a DST change
    rows = hourly[(hourly.index > start) & (hourly.index <= end)]
    return rows, {"start": start.tz_convert(TZ).isoformat(), "end": end.tz_convert(TZ).isoformat(),
                  "now": now.isoformat(timespec="minutes")}


def _r(x, nd=1):
    return None if pd.isna(x) else round(float(x), nd)


# ---------------------------------------------------------------------------
# Views — plain dicts, the payload a display would receive
# ---------------------------------------------------------------------------

def home_view(run, hourly, daily, point, pv, hours=39, days=5):
    """Now (temperature, icon), today's PV estimate, `hours` of temperature
    and rain/snow from the last 00:00 / 12:00, and a `days` daily outlook."""
    pv_kw = pv_power(hourly, point["lat"], point["lon"], **pv)
    today = datetime.now(TZ).date()
    on_today = pv_kw.index.date == today
    now = _now_row(hourly)
    nxt, chart = _chart_window(hourly, hours)
    snow = snow_fraction(nxt, point["alt"])
    return {
        "view": "home", "name": point["name"], "run": run_time(run).isoformat(),
        "now": {"time": now.name.isoformat(), "temp": _r(now["tre200h0"]), "icon": int(now["jww003i0"])},
        "solar": {
            "kwp": pv["kwp"],
            "today_kwh": _r(pv_kw[on_today].sum()),
            "remaining_kwh": _r(pv_kw[on_today & (pv_kw.index > pd.Timestamp.now(TZ))].sum()),
            "peak_kw": _r(pv_kw[on_today].max(), 2),
            "tomorrow_kwh": _r(pv_kw[pv_kw.index.date == today + timedelta(days=1)].sum()),
            "hourly_kw": [_r(v, 2) for v in pv_kw[on_today].values],
            "hours": [t.hour for t in pv_kw[on_today].index],
        },
        "hourly": {
            "time": [t.isoformat() for t in nxt.index],
            "temp": [_r(v) for v in nxt["tre200h0"]],
            "rain_mm": [_r(v) for v in nxt["rre150h0"] * (1 - snow)],
            "snow_mm": [_r(v) for v in nxt["rre150h0"] * snow],
            "prob": [int(v) for v in nxt["rp0003i0"]],
        },
        "chart": chart,
        "days": _days(hourly, daily, days),
    }


def boat_view(run, hourly, point, hours=39):
    """Hourly wind (knots) with 10–90 % range, gusts, direction for `hours`
    from the last 00:00 / 12:00, and a summary of the next 12 hours."""
    nxt, chart = _chart_window(hourly, hours)
    kt = lambda col: [_r(v * KMH_TO_KT) for v in nxt[col]]
    now = _now_row(hourly)
    n12 = _upcoming(hourly, 12) * KMH_TO_KT
    return {
        "view": "boat", "name": point["name"], "run": run_time(run).isoformat(),
        "now": {"time": now.name.isoformat(), "wind_kt": _r(now["fu3010h0"] * KMH_TO_KT),
                "gust_kt": _r(now["fu3010h1"] * KMH_TO_KT), "dir": int(now["dkl010h0"]),
                "temp": _r(now["tre200h0"]), "icon": int(now["jww003i0"])},
        "hourly": {
            "time": [t.isoformat() for t in nxt.index],
            "wind_kt": kt("fu3010h0"), "wind_q10_kt": kt("fu3q10h0"), "wind_q90_kt": kt("fu3q90h0"),
            "gust_kt": kt("fu3010h1"), "gust_q90_kt": kt("fu3q90h1"),
            "dir": [int(v) for v in nxt["dkl010h0"]],
            "icon": [int(v) for v in nxt["jww003i0"]],
        },
        "chart": chart,
        "next_12h": {"wind_min_kt": _r(n12["fu3010h0"].min()), "wind_max_kt": _r(n12["fu3010h0"].max()),
                     "gust_max_kt": _r(n12["fu3010h1"].max()), "gust_q90_max_kt": _r(n12["fu3q90h1"].max())},
    }


def chalet_view(run, hourly, daily, point, bulletin=None, hours=39, days=5):
    """Now, new snow and sunshine over the next 48 h, `hours` of snow, rain,
    sunshine and temperature from the last 00:00 / 12:00, daily snow/sun/
    min/max for `days`, plus the avalanche bulletin summary if given."""
    snow = snow_fraction(hourly, point["alt"])
    snow_cm = hourly["rre150h0"] * snow          # ~1 cm fresh snow per mm water
    nxt, chart = _chart_window(hourly, hours)
    next48 = _upcoming(hourly, 48)
    now = _now_row(hourly)
    return {
        "view": "chalet", "name": point["name"], "alt": point["alt"], "run": run_time(run).isoformat(),
        "now": {"time": now.name.isoformat(), "temp": _r(now["tre200h0"]), "icon": int(now["jww003i0"]),
                "freezing_m": int(now["zprfr0hs"])},
        "snow_next_cm": _r(snow_cm[next48.index].sum()),
        "sun_next_h": _r(next48["sre000h0"].sum() / 60),
        "hourly": {
            "time": [t.isoformat() for t in nxt.index],
            "temp": [_r(v) for v in nxt["tre200h0"]],
            "snow_cm": [_r(v) for v in snow_cm[nxt.index]],
            "rain_mm": [_r(v) for v in nxt["rre150h0"] * (1 - snow[nxt.index])],
            "sun_min": [int(v) for v in nxt["sre000h0"]],
            "freezing_m": [int(v) for v in nxt["zprfr0hs"]],
        },
        "chart": chart,
        "days": _days(hourly, daily, days, snow_cm),
        "avalanche": bulletin,
    }


def wind_chill(temp, kmh):
    """Felt temperature (°C) from air temperature and wind (km/h), the
    North American / UK wind chill index; equal to `temp` above 10 °C or in
    light wind, where it does not apply."""
    v = np.power(np.maximum(kmh, 0), 0.16)
    wc = 13.12 + 0.6215 * temp - 11.37 * v + 0.3965 * temp * v
    return np.where((temp <= 10) & (kmh > 4.8), np.minimum(wc, temp), temp)


def mountain_view(run, hourly, daily, point, hours=39, days=5):
    """Summit forecast: now (temperature, felt temperature, wind in km/h,
    0° level), `hours` of snow, rain, temperature and wind from the last
    00:00 / 12:00, and a daily outlook with new snow."""
    snow = snow_fraction(hourly, point["alt"])
    snow_cm = hourly["rre150h0"] * snow
    nxt, chart = _chart_window(hourly, hours)
    next48 = _upcoming(hourly, 48)
    now = _now_row(hourly)
    return {
        "view": "mountain", "name": point["name"], "alt": point["alt"],
        "run": run_time(run).isoformat(),
        "now": {"time": now.name.isoformat(), "temp": _r(now["tre200h0"]), "icon": int(now["jww003i0"]),
                "feels": _r(float(wind_chill(now["tre200h0"], now["fu3010h0"]))),
                "wind_kmh": _r(now["fu3010h0"], 0), "gust_kmh": _r(now["fu3010h1"], 0),
                "dir": int(now["dkl010h0"]), "freezing_m": int(now["zprfr0hs"])},
        "snow_next_cm": _r(snow_cm[next48.index].sum()),
        "hourly": {
            "time": [t.isoformat() for t in nxt.index],
            "temp": [_r(v) for v in nxt["tre200h0"]],
            "snow_cm": [_r(v) for v in snow_cm[nxt.index]],
            "rain_mm": [_r(v) for v in nxt["rre150h0"] * (1 - snow[nxt.index])],
            "wind_kmh": [_r(v) for v in nxt["fu3010h0"]],
            "dir": [int(v) for v in nxt["dkl010h0"]],
            "freezing_m": [int(v) for v in nxt["zprfr0hs"]],
        },
        "chart": chart,
        "days": _days(hourly, daily, days, snow_cm),
    }


# ---------------------------------------------------------------------------
# Avalanche bulletin (SLF)
# ---------------------------------------------------------------------------

DANGER = {"low": 1, "moderate": 2, "considerable": 3, "high": 4, "very_high": 5}
SUBDIVISION = {"minus": "-", "neutral": "=", "plus": "+"}


def slf_bulletin(region_id, lang="en", active_at=None):
    """Summary of the SLF bulletin for one warning region (e.g. "CH-4121"),
    or None when no bulletin covers it (outside the winter season).

    `active_at` (ISO time) fetches a past bulletin, handy for testing in summer."""
    params = {"activeAt": active_at} if active_at else None
    r = requests.get(SLF_URL.format(lang=lang), params=params, timeout=30)
    r.raise_for_status()
    for b in r.json()["bulletins"]:
        region = next((g for g in b["regions"] if g["regionID"] == region_id), None)
        if region is None:
            continue
        top = max(b["dangerRatings"], key=lambda d: DANGER.get(d["mainValue"], 0))
        problems = []
        for p in b.get("avalancheProblems", []):
            elev = p.get("elevation") or {}
            problems.append({"type": p["problemType"], "level": DANGER.get(p.get("dangerRatingValue")),
                             "aspects": p.get("aspects", []),
                             "above_m": elev.get("lowerBound"), "below_m": elev.get("upperBound")})
        return {
            "region": region["name"], "region_id": region_id,
            "valid_from": b["validTime"]["startTime"], "valid_to": b["validTime"]["endTime"],
            "level": DANGER.get(top["mainValue"]),
            "sub": SUBDIVISION.get(top.get("customData", {}).get("CH", {}).get("subdivision"), ""),
            "problems": problems,
        }
    return None


def slf_regions(lang="en", active_at="2026-02-15T10:00:00Z"):
    """All warning regions {id: name} from one (winter) bulletin."""
    r = requests.get(SLF_URL.format(lang=lang), params={"activeAt": active_at}, timeout=30)
    r.raise_for_status()
    return dict(sorted({g["regionID"]: g["name"] for b in r.json()["bulletins"]
                        for g in b["regions"]}.items()))


# ---------------------------------------------------------------------------
# Pictogram descriptions (from the MeteoSwiss demo repo, BSD-3-Clause)
# ---------------------------------------------------------------------------

def icon_text(code, lang="en"):
    """Description of MeteoSwiss pictogram `code`, e.g. "very cloudy, light rain"."""
    path = os.path.join(OUT_DIR, "icons", "symbols.json")
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        r = requests.get(f"{ICONS_URL}symbols.json", timeout=30)
        r.raise_for_status()
        with open(path, "wb") as f:
            f.write(r.content)
    with open(path, encoding="utf-8") as f:
        symbols = json.load(f)
    entry = symbols.get(str(code), {})
    return entry.get(f"description_{lang}", entry.get("description_en", ""))
