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
from matplotlib.patches import Polygon, Rectangle
from PIL import Image

import icons
import localforecast as lf

W, H = 960, 540
# greys each land on one of the panel's 16 levels (multiples of 0x11)
GREY = {"INK": "#000000", "MUTED": "#444444", "GRID": "#bbbbbb", "NIGHT": "#eeeeee",
        "TEMP": "#000000", "RAIN": "#888888", "SNOW": "#cccccc",
        "SUN": "#555555", "WIND": "#000000", "BAND": "#cccccc", "GUST": "#000000",
        "SLF": "#333333", "ICONS": icons.GREY,
        # EAWS danger levels 1–5, light to dark; white text from level 3
        "DANGER": {1: "#eeeeee", 2: "#bbbbbb", 3: "#777777", 4: "#333333", 5: "#000000"},
        "DANGER_WHITE_FROM": 3}
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


def _temp_axis(ax, t, temp, lo=None, ls="-"):
    """Temperature line on a right-hand axis, with a white halo over bars."""
    ax2 = ax.twinx()
    ax2.plot(t, temp, color=P["TEMP"], lw=3, ls=ls, label="temperature",
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


def chalet(view):
    fig = _screen()
    _header(fig, view, f" · {view['alt']:.0f} m")
    now, h = view["now"], view["hourly"]

    _icon(fig, now["icon"], 8, 368, 105)
    _text(fig, 118, 412, _deg(now['temp']), 50, weight="bold")
    _text(fig, 121, 380, f"0° level {now['freezing_m']} m", 13, P["MUTED"])

    _label(fig, 330, 462, "new snow 48 h (est.)")
    snow = f"{view['snow_next_cm']:.0f}"
    _text(fig, 330, 412, snow, 42, weight="bold")
    _text(fig, 336 + 32 * len(snow), 412, "cm", 15, P["MUTED"])
    _text(fig, 330, 380, f"sunshine 48 h: {view['sun_next_h']:.0f} h", 13, P["MUTED"])

    # avalanche bulletin, drawn like the SLF: level with its sub-level (- = +),
    # exposure star and altitude mountain of the main avalanche problem
    av = view.get("avalanche")
    _label(fig, 590, 462, "avalanche danger")
    if av:
        fill = P["DANGER"][av["level"]]
        fig.patches.append(Rectangle((590 / W, 372 / H), 66 / W, 72 / H, transform=fig.transFigure,
                                     fc=fill, ec=P["INK"], lw=1.5))
        _text(fig, 623, 408, f"{av['level']}{av['sub']}", 30,
              "white" if av["level"] >= P["DANGER_WHITE_FROM"] else P["INK"], weight="bold",
              ha="center", va="center")
        _text(fig, 666, 428, DANGER_NAMES[av["level"]], 14, weight="bold")
        main = max(av["problems"], key=lambda p: p["level"] or 0) if av["problems"] else None
        if main:
            _text(fig, 666, 405, PROBLEM_NAMES.get(main["type"], main["type"].replace("_", " ")), 13)
            _aspect_rose(fig, 780, 366, 88, main["aspects"])
            _altitude_mountain(fig, 870, 398, 76, 52, main["above_m"], main["below_m"])
            if main["above_m"] or main["below_m"]:
                _text(fig, 908, 378, f"{main['above_m'] or main['below_m']} m", 12, weight="bold",
                      ha="center")
        until = datetime.fromisoformat(av["valid_to"].replace("Z", "+00:00")).astimezone(lf.TZ)
        _text(fig, 666, 380, f"until {until:%a %H:%M}", 11, P["MUTED"])
    else:
        _text(fig, 590, 412, "no bulletin", 15)
        _text(fig, 590, 388, "outside the season", 13, P["MUTED"])

    # 48 h: sunshine strip on top, then snowfall bars and temperature line
    t = _times(h)
    sx = _axes(fig, 62, 318, 830, 26)
    tb = _hour_starts(t)
    sx.bar(tb, h["sun_min"], width=0.9 / 24, align="edge", color=P["SUN"])
    sx.set_ylim(0, 60)
    sx.set_xlim(datetime.fromisoformat(view["chart"]["start"]), datetime.fromisoformat(view["chart"]["end"]))
    sx.axis("off")
    _text(fig, 18, 324, "sun", 11, P["MUTED"], weight="bold")
    ax = _axes(fig, 62, 165, 830, 145)
    _shade_nights(ax, t)
    ax.bar(tb, h["snow_cm"], width=0.9 / 24, align="edge", color=P["SNOW"],
           label="snow cm" if any(h["snow_cm"]) else None)
    ax.bar(tb, h["rain_mm"], bottom=h["snow_cm"], width=0.9 / 24, align="edge", color=P["RAIN"],
           label="rain mm")
    _precip_scale(ax, [s + r for s, r in zip(h["snow_cm"], h["rain_mm"])])
    ax.legend(loc="upper left", fontsize=11, frameon=False, ncol=2, handlelength=1)
    _time_axis(ax, view["chart"])
    ax2 = _temp_axis(ax, t, h["temp"], lo=0)
    ax2.axhline(0, color=P["TEMP"], lw=1, ls=":")

    # daily outlook
    _daily(fig, view["days"], "snow")
    return fig


# ---------------------------------------------------------------------------

def mountain(view):
    fig = _screen()
    _header(fig, view, f" · {view['alt']:.0f} m")
    now, h = view["now"], view["hourly"]

    # now: icon, temperature and felt temperature
    _icon(fig, now["icon"], 8, 368, 105)
    _text(fig, 118, 412, _deg(now["temp"]), 50, weight="bold")
    _text(fig, 121, 380, f"feels like {_deg(now['feels'])}", 13, P["MUTED"])

    # wind in km/h, as MeteoSwiss gives it for mountains
    _label(fig, 300, 462, "wind")
    _text(fig, 300, 412, f"{now['wind_kmh']:.0f}", 42, weight="bold")
    _text(fig, 308 + 36 * len(f"{now['wind_kmh']:.0f}"), 412, "km/h", 15, P["MUTED"])
    _text(fig, 300, 380, f"gusts {now['gust_kmh']:.0f} km/h", 13, P["MUTED"])
    _compass(fig, 480, 362, 110, now["dir"])

    # zero-degree level against the summit
    _label(fig, 650, 462, "0° level")
    _text(fig, 650, 415, f"{now['freezing_m']} m", 26, weight="bold")
    gap = now["freezing_m"] - view["alt"]
    _text(fig, 650, 385, f"{abs(gap):.0f} m {'above' if gap >= 0 else 'below'} the summit", 13,
          P["MUTED"])

    # 48 h: wind with range, gusts and direction; temperature (dashed) on the right
    t = _times(h)
    ax = _axes(fig, 62, 165, 830, 180)
    # headroom above the data for the legend and the direction arrows
    top = max(max(h["gust_kmh"]), max(h["wind_q90_kmh"]), 30) * 1.5
    _wind_chart(ax, view["chart"], t, h["wind_kmh"], h["wind_q10_kmh"], h["wind_q90_kmh"], h["gust_kmh"], h["dir"],
                "km/h", top=top, step=20 if top > 60 else 10, arrows_at=0.76)
    ax2 = _temp_axis(ax, t, h["temp"], ls="--")
    ax2.axhline(0, color=P["TEMP"], lw=1, ls=":")
    handles = ax.get_legend_handles_labels()[0] + ax2.get_legend_handles_labels()[0]
    ax.legend(handles=handles, loc="upper left", fontsize=11, frameon=False, ncol=4, handlelength=1.5)

    # daily outlook
    _daily(fig, view["days"], "snow")
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
