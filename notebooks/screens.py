"""Screens for the home, boat and chalet views on a LilyGO T5 4.7" e-paper
(V2.3: ESP32-S3, ED047TC1 panel, 960×540, 16 grey levels), drawn with
matplotlib from the dicts built by localforecast.py.

The panel is small (~104×58 mm, ~234 dpi), so text is never below 11 pt
here (15 px, ~1.6 mm) and the main values are large. The same layout can be
drawn in colour for the notebooks.

    img = render(home, view)                # 960×540 greyscale, 16 levels
    buf = epd_buffer(img)                   # 259,200 bytes for LilyGo-EPD47
    img = render(home, view, colour=True)   # colour preview
"""
import math
import textwrap
from datetime import datetime, timedelta

import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.dates import HourLocator, num2date
from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle
from PIL import Image

import icons
import localforecast as lf

W, H = 960, 540
# greys each land on one of the panel's 16 levels (multiples of 0x11)
GREY = {"INK": "#000000", "MUTED": "#444444", "GRID": "#bbbbbb", "NIGHT": "#eeeeee",
        "TEMP": "#000000", "RAIN": "#888888", "SNOW": "#cccccc",
        "SUN": "#aaaaaa", "WIND": "#000000", "BAND": "#cccccc", "GUST": "#000000",
        "SLF": "#333333", "ICONS": icons.GREY,
        # EAWS danger levels 1–5, light to mid grey so the black figure stays
        # readable on the T5
        "DANGER": {1: "#eeeeee", 2: "#dddddd", 3: "#bbbbbb", 4: "#999999", 5: "#777777"},
        "DANGER_WHITE_FROM": 6}
COLOUR = {"INK": "#1d1d1f", "MUTED": "#6e6e73", "GRID": "#dee2e6", "NIGHT": "#f1f3f5",
          "TEMP": "#d9480f", "RAIN": "#1c7ed6", "SNOW": "#74c0fc",
          "SUN": "#f59f00", "WIND": "#0b7285", "BAND": "#99e9f2", "GUST": "#c92a2a",
          "SLF": "#1f5c88", "ICONS": icons.COLOUR,
          # official EAWS danger level colours
          "DANGER": {1: "#ccff66", 2: "#ffff00", 3: "#ff9900", 4: "#ff0000", 5: "#9e1313"},
          "DANGER_WHITE_FROM": 4}
P = GREY   # palette in use, set by `render`
ASPECTS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12,
                     "xtick.labelsize": 12, "ytick.labelsize": 11})


def _screen():
    return plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor="white")


def _axes(fig, x, y, w, h, **kw):
    """Axes at figure px: lower-left corner (x, y), size w×h."""
    return fig.add_axes([x / W, y / H, w / W, h / H], **kw)


def _icon(fig, code, x, y, w):
    """Place pictogram `code` with its lower-left corner at figure px (x, y)."""
    icons.draw(_axes(fig, x, y, w, w), code, P["ICONS"])


def _text(fig, x, y, s, size=12, color=None, weight="normal", ha="left", va="baseline"):
    fig.text(x / W, y / H, s, fontsize=size, color=color or P["INK"], weight=weight, ha=ha, va=va)


def _deg(v):
    """Whole degrees, without the "-0" that rounding -0.4 gives."""
    return f"{round(v) + 0}°"


def _times(hourly):
    return [datetime.fromisoformat(t) for t in hourly["time"]]


def _hour_starts(times):
    """Values are stamped at the end of their hour: bars start an hour earlier."""
    return [t - timedelta(hours=1) for t in times]


def _time_axis(ax, chart):
    """Chart window from the view (last 00:00 / 12:00 + 39 h): a tick every
    3 h labelled "15h" (the weekday at midnight), gridlines at 00:00 and
    12:00, and a line at the time the screen was drawn."""
    start, end = datetime.fromisoformat(chart["start"]), datetime.fromisoformat(chart["end"])
    ax.set_xlim(start, end)
    ax.xaxis.set_major_locator(HourLocator(byhour=range(0, 24, 3), tz=lf.TZ))
    ax.xaxis.set_major_formatter(
        lambda x, _: f"{d:%a}" if (d := num2date(x, tz=lf.TZ)).hour == 0 else f"{d:%H}h")
    t = start
    while t <= end:
        if t.astimezone(lf.TZ).hour in (0, 12):
            ax.axvline(t, color=P["GRID"], lw=1, zorder=0)
        t += timedelta(hours=1)
    ax.axvline(datetime.fromisoformat(chart["now"]), color=P["INK"], lw=2, zorder=6)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(axis="x", length=4, labelsize=11)
    ax.tick_params(axis="y", length=0)


def _shade_nights(ax, times):
    for t in _hour_starts(times):
        if t.hour < 7 or t.hour >= 19:
            ax.axvspan(t, t + timedelta(hours=1), color=P["NIGHT"], lw=0, zorder=0)


def _precip_scale(ax, totals):
    """Precipitation axis like the MeteoSwiss app: at least 0–8 per hour,
    extended in steps of 2 for heavier forecasts, ticks every quarter."""
    top = max(8, 2 * math.ceil(max(totals, default=0) / 2))
    ax.set_ylim(0, top)
    ax.set_yticks(range(0, top + 1, top // 4))


def _temp_axis(ax, t, temp, lo=None):
    """Temperature line on a right-hand axis, with a white halo over bars."""
    ax2 = ax.twinx()
    ax2.plot(t, temp, color=P["TEMP"], lw=3,
             path_effects=[pe.Stroke(linewidth=7, foreground="white"), pe.Normal()])
    ax2.set_ylim((min(temp) if lo is None else min(min(temp), lo)) - 2, max(temp) + 2)
    ax2.yaxis.set_major_locator(plt.MaxNLocator(4, integer=True))
    ax2.yaxis.set_major_formatter(lambda v, _: _deg(v))
    ax2.tick_params(length=0, labelsize=12, labelcolor=P["INK"])
    for s in ("top", "left", "right"):
        ax2.spines[s].set_visible(False)
    return ax2


def _header(fig, view, extra=""):
    run = datetime.fromisoformat(view["run"])
    _text(fig, 16, H - 36, view["name"], 22, weight="bold")
    _text(fig, W - 16, H - 32, f"forecast run {run:%a %H:%M}{extra}", 12, P["MUTED"], ha="right")


def _value_unit(fig, x, y, value, unit, size):
    """Big bold value with its unit right after it, placed from the drawn width."""
    t = fig.text(x / W, y / H, value, fontsize=size, color=P["INK"], weight="bold")
    right = t.get_window_extent(renderer=fig.canvas.get_renderer()).x1
    _text(fig, right + 5, y, unit, 15, P["MUTED"])


def _label(fig, x, y, s):
    _text(fig, x, y, s.upper(), 11, P["MUTED"], weight="bold")


def _daily(fig, days, extra):
    """Bottom pane: one column per day with icon, min/max, sunshine and
    either precipitation (`extra="precip"`) or estimated new snow ("snow")."""
    w = (W - 32) / max(len(days), 1)
    for i, d in enumerate(days):
        x = 16 + i * w
        day = datetime.fromisoformat(d["date"])
        _text(fig, x + 4, 112, f"{day:%a %d}", 13, weight="bold")
        _icon(fig, d["icon"], x, 18, 78)
        _text(fig, x + 82, 78, f"{round(d['tmin']) + 0}/{_deg(d['tmax'])}", 15, weight="bold")
        if extra == "snow":
            _text(fig, x + 82, 54, f"❄ {d['snow_cm']:.0f} cm", 13)
        else:
            mm = d["precip_mm"]
            _text(fig, x + 82, 54, f"☂ {mm:.0f} mm" if mm >= 10 or mm == 0 else f"☂ {mm:.1f} mm", 13)
        _text(fig, x + 82, 30, f"☀ {d['sun_h']:.0f} h", 13)


# ---------------------------------------------------------------------------

def home(view):
    fig = _screen()
    _header(fig, view)
    now, solar = view["now"], view["solar"]

    # now: icon + forecast temperature for this hour
    _icon(fig, now["icon"], 10, 360, 120)
    _text(fig, 140, 410, _deg(now['temp']), 60, weight="bold")
    # description on up to two lines, so it stays clear of the solar block
    for i, line in enumerate(textwrap.wrap(lf.icon_text(now["icon"]), 34)[:2]):
        _text(fig, 144, 378 - 18 * i, line, 13, P["MUTED"])

    # solar: today's estimated energy + hourly profile
    _label(fig, 470, 462, "solar today (est.)")
    _text(fig, 470, 412, f"{solar['today_kwh']:.1f}", 40, weight="bold")
    _text(fig, 475 + 30 * len(f"{solar['today_kwh']:.1f}"), 412, "kWh", 15, P["MUTED"])
    _text(fig, 470, 380, f"tomorrow {solar['tomorrow_kwh']:.1f} kWh", 13, P["MUTED"])
    ax = _axes(fig, 735, 382, 210, 85)
    hours = solar["hours"]
    ax.bar(hours, solar["hourly_kw"], width=0.85, color=P["SUN"])
    ax.axvline(datetime.now(lf.TZ).hour, color=P["INK"], lw=1.5, ls=":")
    ax.set_xlim(5.5, 20.5)
    ax.set_ylim(0, max(0.1, max(solar["hourly_kw"]) * 1.1))
    ax.set_xticks([6, 12, 18])
    ax.set_yticks([])
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(length=0, labelsize=11)

    # next hours: temperature line over rain/snow bars
    h = view["hourly"]
    t = _times(h)
    ax = _axes(fig, 62, 175, 830, 170)
    _shade_nights(ax, t)
    tb = _hour_starts(t)
    ax.bar(tb, h["rain_mm"], width=0.9 / 24, align="edge", color=P["RAIN"], label="rain")
    ax.bar(tb, h["snow_mm"], bottom=h["rain_mm"], width=0.9 / 24, align="edge", color=P["SNOW"],
           label="snow" if any(h["snow_mm"]) else None)
    _precip_scale(ax, [r + s for r, s in zip(h["rain_mm"], h["snow_mm"])])
    ax.set_ylabel("mm/h", fontsize=11)
    ax.legend(loc="upper left", fontsize=11, frameon=False, ncol=2, handlelength=1)
    _time_axis(ax, view["chart"])
    _temp_axis(ax, t, h["temp"])

    # daily outlook
    _daily(fig, view["days"], "precip")
    return fig


# ---------------------------------------------------------------------------

def _beaufort(kt):
    return int(np.searchsorted([1, 4, 7, 11, 17, 22, 28, 34, 41, 48, 56, 64], kt, side="right"))


def _compass(fig, x, y, size, direction):
    """Compass with an arrow blowing from `direction` (degrees)."""
    ax = _axes(fig, x, y, size, size, projection="polar")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_yticks([])
    ax.set_xticks(np.radians(range(0, 360, 90)), ["N", "E", "S", "W"], fontsize=11)
    ax.tick_params(pad=-2)
    ax.annotate("", xy=(np.radians(direction + 180), 0.9), xytext=(np.radians(direction), 0.9),
                arrowprops=dict(arrowstyle="-|>,head_width=0.5,head_length=0.8", color=P["WIND"], lw=3.5))
    ax.set_ylim(0, 1)


def _wind_chart(ax, chart, t, mean, q10, q90, gust, dirs, unit, top, step, arrows_at=0.83):
    """Mean wind with its 10–90 % band, gusts, and direction arrows on the
    3-hour ticks at `arrows_at` of the axis height."""
    _shade_nights(ax, t)
    ax.fill_between(t, q10, q90, color=P["BAND"], lw=0, label="10–90 %")
    ax.plot(t, mean, color=P["WIND"], lw=3, label="mean wind")
    ax.plot(t, gust, color=P["GUST"], lw=0, marker="o", ms=4, mfc="white", mew=1.5, label="gusts")
    ax.set_ylim(0, top)
    levels = [v for v in range(step, int(top), step)][:4]
    for lvl in levels:
        ax.axhline(lvl, color=P["GRID"], lw=1, zorder=0)
    ax.set_yticks(levels)
    ax.set_ylabel(unit, fontsize=12)
    _time_axis(ax, chart)
    for ti, d in [(ti, d) for ti, d in zip(t, dirs) if ti.hour % 3 == 0]:
        ax.text(ti, top * arrows_at, "↓", rotation=-d, ha="center", va="center", fontsize=18,
                weight="bold", color=P["INK"])


def boat(view):
    fig = _screen()
    _header(fig, view)
    now, h = view["now"], view["hourly"]

    # now: wind, gust, direction compass
    _text(fig, 16, 405, f"{now['wind_kt']:.0f}", 66, weight="bold")
    _text(fig, 22 + 50 * len(f"{now['wind_kt']:.0f}"), 405, "kt", 18, P["MUTED"])
    _text(fig, 18, 372, f"gusts {now['gust_kt']:.0f} kt · Bft {_beaufort(now['wind_kt'])}", 14,
          P["MUTED"])
    _compass(fig, 205, 362, 110, now["dir"])

    # summary for the next 12 h
    t = _times(h)
    n12 = view["next_12h"]
    _label(fig, 370, 462, "next 12 h")
    _text(fig, 370, 428, f"mean {n12['wind_min_kt']:.0f}–{n12['wind_max_kt']:.0f} kt", 20, weight="bold")
    _text(fig, 370, 400, f"max gust {n12['gust_max_kt']:.0f} kt", 15)
    _text(fig, 370, 375, f"up to {n12['gust_q90_max_kt']:.0f} kt at 90 %", 13, P["MUTED"])
    _icon(fig, now["icon"], W - 115, 365, 100)
    _text(fig, W - 120, 395, _deg(now['temp']), 26, weight="bold", ha="right")

    # 48 h wind: mean with 10–90 % band, gusts, direction
    ax = _axes(fig, 52, 42, 893, 300)
    _wind_chart(ax, view["chart"], t, h["wind_kt"], h["wind_q10_kt"], h["wind_q90_kt"], h["gust_kt"], h["dir"],
                "kt", top=max(max(h["gust_q90_kt"]), 15) * 1.18, step=10)
    ax.legend(loc="upper left", fontsize=11, frameon=False, ncol=3, handlelength=1.5)
    return fig


# ---------------------------------------------------------------------------

DANGER_NAMES = {1: "Low", 2: "Moderate", 3: "Considerable", 4: "High", 5: "Very high"}
PROBLEM_NAMES = {"new_snow": "new snow", "wind_slab": "wind slab", "persistent_weak_layers": "weak layers",
                 "wet_snow": "wet snow", "gliding_snow": "gliding snow", "cornices": "cornices",
                 "favourable_situation": "favourable", "no_distinct_avalanche_problem": "no clear problem"}


def _danger_badge(fig, x, baseline, level, text, size=40):
    """Danger level figure ("2=") on a rounded fill in the level's colour, no
    frame, at the size and on the baseline of the other blocks' big figures.
    Returns the badge's right edge (px)."""
    probe = fig.text(0, 0, text, fontsize=size, weight="bold")
    w = probe.get_window_extent(renderer=fig.canvas.get_renderer()).width + 10
    probe.remove()
    h, below = 66, 10                         # px; the fill reaches `below` under the baseline
    ax = _axes(fig, x, baseline - below, w, h)
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis("off")
    ax.add_patch(FancyBboxPatch((0, 0), w, h, boxstyle="round,pad=0,rounding_size=10",
                                fc=P["DANGER"][level], ec="none"))
    ax.text(w / 2, below, text, ha="center", va="baseline", fontsize=size, weight="bold",
            color="white" if level >= P["DANGER_WHITE_FROM"] else P["INK"])
    return x + w


def _aspect_rose(fig, x, y, size, aspects):
    """SLF exposure star: 8 kite-shaped petals, the critical aspects filled,
    N E S W written on their petals."""
    ax = _axes(fig, x, y, size, size)
    ax.set_xlim(-1.05, 1.05)
    ax.set_ylim(-1.05, 1.05)
    ax.set_aspect("equal")
    ax.axis("off")
    for i, a in enumerate(ASPECTS):
        b = np.radians(90 - i * 45)          # compass bearing → maths angle
        side = 0.72
        kite = [(0, 0), (side * np.cos(b - np.pi / 8), side * np.sin(b - np.pi / 8)),
                (np.cos(b), np.sin(b)), (side * np.cos(b + np.pi / 8), side * np.sin(b + np.pi / 8))]
        on = a in aspects
        ax.add_patch(Polygon(kite, closed=True, fc=P["SLF"] if on else "white", ec=P["INK"], lw=1.2,
                             joinstyle="round"))
        if len(a) == 1:
            ax.text(0.6 * np.cos(b), 0.6 * np.sin(b), a, ha="center", va="center", fontsize=10,
                    weight="bold", color="white" if on else P["INK"])


def _altitude_mountain(fig, x, y, w, h, above, below):
    """SLF altitude pictogram: a mountain filled above `above` m (or below
    `below` m, or entirely), with the altitude written beside the line."""
    ax = _axes(fig, x, y, w, h)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    level = 0.5                              # the threshold line, half way up
    outline = [(0.02, 0.0), (0.98, 0.0), (0.84, level), (0.66, 0.96), (0.53, 0.72), (0.42, 0.82),
               (0.16, level)]
    clip = (Rectangle((0, level), 1, 1) if above else Rectangle((0, 0), 1, level) if below
            else Rectangle((0, 0), 1, 1))
    ax.add_patch(Polygon(outline, closed=True, fc="white", ec="none"))
    filled = Polygon(outline, closed=True, fc=P["SLF"], ec="none")
    ax.add_patch(filled)
    clip.set_transform(ax.transData)
    filled.set_clip_path(clip)
    ax.add_patch(Polygon(outline, closed=True, fc="none", ec=P["INK"], lw=1.2, joinstyle="round"))
    if above or below:
        ax.plot([0.16, 0.84], [level, level], color=P["INK"], lw=1.2)


def _snow_rain_temp(ax, view):
    """Snow and rain bars (0–8 per hour or more) under the temperature line."""
    h = view["hourly"]
    t = _times(h)
    tb = _hour_starts(t)
    _shade_nights(ax, t)
    ax.bar(tb, h["snow_cm"], width=0.9 / 24, align="edge", color=P["SNOW"],
           label="snow cm" if any(h["snow_cm"]) else None)
    ax.bar(tb, h["rain_mm"], bottom=h["snow_cm"], width=0.9 / 24, align="edge", color=P["RAIN"],
           label="rain mm" if any(h["rain_mm"]) else None)
    _precip_scale(ax, [s + r for s, r in zip(h["snow_cm"], h["rain_mm"])])
    if ax.get_legend_handles_labels()[0]:     # only what is forecast
        ax.legend(loc="upper left", fontsize=11, frameon=False, ncol=2, handlelength=1)
    _time_axis(ax, view["chart"])
    ax2 = _temp_axis(ax, t, h["temp"], lo=0)
    ax2.axhline(0, color=P["TEMP"], lw=1, ls=":")


def _sunshine(ax, view):
    """Sunshine minutes per hour (0–60) on the chart's time scale, with
    sunrise ("07:01 ↑") and sunset ("↓ 17:26") marked on the baseline."""
    h = view["hourly"]
    t = _times(h)
    ax.bar(_hour_starts(t), h["sun_min"], width=0.9 / 24, align="edge", color=P["SUN"])
    ax.set_ylim(0, 60)
    ax.set_yticks([0, 30, 60])
    ax.axhline(30, color=P["GRID"], lw=1, zorder=0)
    ax.axhline(60, color=P["GRID"], lw=1, zorder=0)
    _time_axis(ax, view["chart"])
    ax.tick_params(axis="x", labelbottom=False, length=0)
    ax.tick_params(axis="y", labelsize=10)
    ax.text(0.01, 0.97, "sunshine min/h", transform=ax.transAxes, ha="left", va="top", fontsize=11,
            color=P["MUTED"])
    for e in view["sun_events"]:
        te = datetime.fromisoformat(e["time"])
        label = f"{te:%H:%M} ↑" if e["rise"] else f"↓ {te:%H:%M}"
        ax.text(te, 8, label, ha="right" if e["rise"] else "left", va="bottom", fontsize=11,
                weight="bold", color=P["INK"])


def _wind_row(ax, view, key):
    """Wind every 3 h on the chart's time scale: an arrow blowing with the
    wind, and the mean speed under it."""
    h, chart = view["hourly"], view["chart"]
    ax.set_xlim(datetime.fromisoformat(chart["start"]), datetime.fromisoformat(chart["end"]))
    ax.set_ylim(0, 1)
    ax.axis("off")
    for ti, d, v in zip(_times(h), h["dir"], h[key]):
        if ti.hour % 3 == 0 and v is not None:
            ax.text(ti, 0.72, "↓", rotation=-d, ha="center", va="center", fontsize=16, weight="bold",
                    color=P["INK"])
            ax.text(ti, 0.12, f"{v:.0f}", ha="center", va="center", fontsize=12, color=P["INK"])


def _snow_avalanche_panel(fig, view):
    """Top panel of chalet and mountain: forecast for now with the 0° level,
    measured snow at the SLF station, and the avalanche bulletin."""
    now = view["now"]
    if "feels" in now:                        # mountain: wind chill above the temperature
        _text(fig, 121, 470, f"feels like {_deg(now['feels'])}", 13, P["MUTED"])
    _icon(fig, now["icon"], 8, 368, 105)
    _text(fig, 118, 412, _deg(now['temp']), 50, weight="bold")
    _text(fig, 121, 380, f"0° level {now['freezing_m']} m", 13, P["MUTED"])

    # measured, not forecast: SLF new snow over 24 h / 3 days, and snow depth
    st = view.get("station")
    _label(fig, 280, 468, "snow 24 h / 3 days (SLF)")
    if st:
        _value_unit(fig, 280, 412, f"{st['new_24h_cm']:.0f} / {st['new_3d_cm']:.0f}", "cm", 40)
        _text(fig, 280, 380, f"depth {st['depth_cm']:.0f} cm · {st['name']} {st['alt']:.0f} m", 12,
              P["MUTED"])
    else:
        _text(fig, 280, 412, "no data", 15)

    # avalanche bulletin, drawn like the SLF: level with its sub-level (- = +),
    # exposure star and altitude mountain of the main avalanche problem
    # Rows as in the first two blocks: label at 468, big figures on the 412
    # baseline (pictograms centred on them), small text at 380.
    av = view.get("avalanche")
    _label(fig, 548, 468, "avalanche danger")
    if av:
        right = _danger_badge(fig, 548, 412, av["level"], f"{av['level']}{av['sub']}")
        _text(fig, right + 8, 433, DANGER_NAMES[av["level"]], 13, weight="bold")
        main = max(av["problems"], key=lambda p: p["level"] or 0) if av["problems"] else None
        if main:
            _text(fig, right + 8, 412, PROBLEM_NAMES.get(main["type"], main["type"].replace("_", " ")),
                  13)
            # pictograms centred on the big figures; the mountain and its
            # altitude form one pictogram
            _aspect_rose(fig, 800, 399, 64, main["aspects"])
            _altitude_mountain(fig, 872, 414, 54, 42, main["above_m"], main["below_m"])
            if main["above_m"] or main["below_m"]:
                _text(fig, 899, 400, f"{main['above_m'] or main['below_m']} m", 12, weight="bold",
                      ha="center")
        until = datetime.fromisoformat(av["valid_to"].replace("Z", "+00:00")).astimezone(lf.TZ)
        _text(fig, 548, 380, f"until {until:%a %H:%M}", 12, P["MUTED"])
    else:
        _text(fig, 548, 412, "no bulletin", 15)
        _text(fig, 548, 380, "none published now", 12, P["MUTED"])


def chalet(view):
    fig = _screen()
    _header(fig, view, f" · {view['alt']:.0f} m")
    h = view["hourly"]

    _snow_avalanche_panel(fig, view)

    # 48 h: sunshine strip on top, then snowfall bars and temperature line
    t = _times(h)
    sx = _axes(fig, 62, 318, 830, 26)
    tb = _hour_starts(t)
    sx.bar(tb, h["sun_min"], width=0.9 / 24, align="edge", color=P["SUN"])
    sx.set_ylim(0, 60)
    sx.set_xlim(datetime.fromisoformat(view["chart"]["start"]), datetime.fromisoformat(view["chart"]["end"]))
    sx.axis("off")
    _text(fig, 18, 324, "sun", 11, P["MUTED"], weight="bold")
    _snow_rain_temp(_axes(fig, 62, 165, 830, 145), view)

    # daily outlook
    _daily(fig, view["days"], "snow")
    return fig


# ---------------------------------------------------------------------------

def mountain(view):
    fig = _screen()
    _header(fig, view, f" · {view['alt']:.0f} m")

    _snow_avalanche_panel(fig, view)

    # as in the MeteoSwiss app: wind every 3 h (arrow + km/h), sunshine with
    # sunrise and sunset, then snow, rain and temperature
    _wind_row(_axes(fig, 62, 303, 830, 44), view, "wind_kmh")
    _text(fig, 18, 312, "km/h", 11, P["MUTED"], weight="bold")
    _sunshine(_axes(fig, 62, 224, 830, 72), view)
    _snow_rain_temp(_axes(fig, 62, 40, 830, 160), view)
    return fig


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def render(draw, view, colour=False):
    """Draw `view` with `draw` (home, boat or chalet) as a 960×540 image:
    greyscale snapped to the panel's 16 levels, or RGB with `colour`."""
    global P
    P = COLOUR if colour else GREY
    rc = {"axes.edgecolor": P["MUTED"], "axes.labelcolor": P["MUTED"],
          "xtick.color": P["INK"], "ytick.color": P["MUTED"]}
    try:
        with plt.rc_context(rc):
            fig = draw(view)
            fig.canvas.draw()
            rgba = np.asarray(fig.canvas.buffer_rgba())
            plt.close(fig)
    finally:
        P = GREY
    img = Image.fromarray(rgba).convert("RGB")
    return img if colour else img.convert("L").point(lambda v: (v // 16) * 17)


def epd_buffer(img):
    """Frame buffer for the LilyGo-EPD47 driver (`epd_draw_grayscale_image`):
    4 bits per pixel, 0 = black, 15 = white, rows top to bottom, two pixels
    per byte with the left (even x) pixel in the low nibble. 259,200 bytes."""
    a = np.asarray(img.convert("L"), dtype=np.uint8) >> 4
    return (a[:, 0::2] | (a[:, 1::2] << 4)).astype(np.uint8).tobytes()
