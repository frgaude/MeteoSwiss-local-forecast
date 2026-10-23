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
from datetime import datetime

import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.dates import DateFormatter, HourLocator
from matplotlib.patches import Rectangle, Wedge
from PIL import Image

import icons
import localforecast as lf

W, H = 960, 540
# greys each land on one of the panel's 16 levels (multiples of 0x11)
GREY = {"INK": "#000000", "MUTED": "#444444", "GRID": "#bbbbbb", "NIGHT": "#eeeeee",
        "TEMP": "#000000", "COLD": "#444444", "RAIN": "#000000", "SNOW": "#999999",
        "SUN": "#555555", "WIND": "#000000", "BAND": "#cccccc", "GUST": "#000000",
        "ROSE": "#444444", "SNOW_TEXT": "#000000", "SUN_TEXT": "#000000", "ICONS": icons.GREY,
        # EAWS danger levels 1–5, light to dark; white text from level 3
        "DANGER": {1: "#eeeeee", 2: "#bbbbbb", 3: "#777777", 4: "#333333", 5: "#000000"},
        "DANGER_WHITE_FROM": 3}
COLOUR = {"INK": "#1d1d1f", "MUTED": "#6e6e73", "GRID": "#dee2e6", "NIGHT": "#f1f3f5",
          "TEMP": "#d9480f", "COLD": "#1c7ed6", "RAIN": "#1c7ed6", "SNOW": "#74c0fc",
          "SUN": "#f59f00", "WIND": "#0b7285", "BAND": "#99e9f2", "GUST": "#c92a2a",
          "ROSE": None, "SNOW_TEXT": "#1c7ed6", "SUN_TEXT": "#e8590c", "ICONS": icons.COLOUR,
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


def _times(hourly):
    return [datetime.fromisoformat(t) for t in hourly["time"]]


def _time_axis(ax, times):
    ax.xaxis.set_major_locator(HourLocator(byhour=[0, 12], tz=lf.TZ))
    ax.xaxis.set_major_formatter(DateFormatter("%a %Hh", tz=lf.TZ))
    ax.xaxis.set_minor_locator(HourLocator(byhour=[6, 18], tz=lf.TZ))
    ax.set_xlim(times[0], times[-1])
    ax.grid(axis="x", which="both", color=P["GRID"], lw=1)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(length=0, which="both")


def _shade_nights(ax, times):
    for t in times:
        if t.hour < 7 or t.hour >= 19:
            ax.axvspan(t - np.timedelta64(30, "m"), t + np.timedelta64(30, "m"),
                       color=P["NIGHT"], lw=0, zorder=0)


def _temp_axis(ax, t, temp, lo=None):
    """Temperature line on a right-hand axis, with a white halo over bars."""
    ax2 = ax.twinx()
    ax2.plot(t, temp, color=P["TEMP"], lw=3,
             path_effects=[pe.Stroke(linewidth=7, foreground="white"), pe.Normal()])
    ax2.set_ylim((min(temp) if lo is None else min(min(temp), lo)) - 2, max(temp) + 2)
    ax2.yaxis.set_major_locator(plt.MaxNLocator(4, integer=True))
    ax2.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}°")
    ax2.tick_params(length=0, labelsize=12, labelcolor=P["TEMP"])
    for s in ("top", "left", "right"):
        ax2.spines[s].set_visible(False)
    return ax2


def _header(fig, view, extra=""):
    run = datetime.fromisoformat(view["run"])
    _text(fig, 16, H - 36, view["name"], 22, weight="bold")
    _text(fig, W - 16, H - 32, f"forecast run {run:%a %H:%M}{extra}", 12, P["MUTED"], ha="right")


def _label(fig, x, y, s):
    _text(fig, x, y, s.upper(), 11, P["MUTED"], weight="bold")


# ---------------------------------------------------------------------------

def home(view):
    fig = _screen()
    _header(fig, view)
    now, solar = view["now"], view["solar"]

    # now: icon + forecast temperature for this hour
    _icon(fig, now["icon"], 10, 360, 120)
    _text(fig, 140, 410, f"{now['temp']:.0f}°", 60, weight="bold")
    _text(fig, 144, 378, lf.icon_text(now["icon"]), 13, P["MUTED"])

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
    ax.bar(t, h["rain_mm"], width=1 / 26, color=P["RAIN"], label="rain")
    ax.bar(t, h["snow_mm"], bottom=h["rain_mm"], width=1 / 26, color=P["SNOW"], label="snow")
    ax.set_ylim(0, max(2, max(r + s for r, s in zip(h["rain_mm"], h["snow_mm"])) * 1.2))
    ax.yaxis.set_major_locator(plt.MaxNLocator(3))
    ax.set_ylabel("mm/h", fontsize=11)
    ax.legend(loc="upper left", fontsize=11, frameon=False, ncol=2, handlelength=1)
    _time_axis(ax, t)
    _temp_axis(ax, t, h["temp"])

    # outlook: half-day steps, day max / night min
    steps = view["outlook"]
    w = (W - 32) / max(len(steps), 1)
    for i, s in enumerate(steps):
        x = 16 + i * w
        start = datetime.fromisoformat(s["start"])
        label = f"{start:%a}" + ("" if s["day"] else " night")
        _text(fig, x + w / 2, 115, label, 13, None if s["day"] else P["MUTED"], ha="center")
        _icon(fig, s["icon"], x + 4, 18, 80)
        _text(fig, x + 90, 45, f"{s['temp']:.0f}°", 24, P["TEMP"] if s["day"] else P["COLD"],
              weight="bold")
    return fig


# ---------------------------------------------------------------------------

def _beaufort(kt):
    return int(np.searchsorted([1, 4, 7, 11, 17, 22, 28, 34, 41, 48, 56, 64], kt, side="right"))


def boat(view):
    fig = _screen()
    _header(fig, view)
    now, h = view["now"], view["hourly"]

    # now: wind, gust, direction compass
    _text(fig, 16, 405, f"{now['wind_kt']:.0f}", 66, P["WIND"], weight="bold")
    _text(fig, 22 + 50 * len(f"{now['wind_kt']:.0f}"), 405, "kt", 18, P["MUTED"])
    _text(fig, 18, 372, f"gusts {now['gust_kt']:.0f} kt · Bft {_beaufort(now['wind_kt'])}", 14,
          P["MUTED"])
    ax = _axes(fig, 205, 362, 110, 110, projection="polar")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_yticks([])
    ax.set_xticks(np.radians(range(0, 360, 90)), ["N", "E", "S", "W"], fontsize=11)
    ax.tick_params(pad=-2)
    ax.annotate("", xy=(np.radians(now["dir"] + 180), 0.9), xytext=(np.radians(now["dir"]), 0.9),
                arrowprops=dict(arrowstyle="-|>,head_width=0.5,head_length=0.8", color=P["WIND"], lw=3.5))
    ax.set_ylim(0, 1)

    # summary for the next 12 h
    t = _times(h)
    nxt12 = slice(0, 12)
    _label(fig, 370, 462, "next 12 h")
    _text(fig, 370, 428, f"mean {min(h['wind_kt'][nxt12]):.0f}–{max(h['wind_kt'][nxt12]):.0f} kt", 20,
          weight="bold")
    _text(fig, 370, 400, f"max gust {max(h['gust_kt'][nxt12]):.0f} kt", 15)
    _text(fig, 370, 375, f"up to {max(h['gust_q90_kt'][nxt12]):.0f} kt at 90 %", 13, P["MUTED"])
    _icon(fig, now["icon"], W - 115, 365, 100)
    _text(fig, W - 120, 395, f"{now['temp']:.0f}°", 26, weight="bold", ha="right")

    # 48 h wind: mean with 10–90 % band, gusts, direction
    ax = _axes(fig, 52, 42, 893, 300)
    _shade_nights(ax, t)
    ax.fill_between(t, h["wind_q10_kt"], h["wind_q90_kt"], color=P["BAND"], lw=0, label="10–90 %")
    ax.plot(t, h["wind_kt"], color=P["WIND"], lw=3, label="mean wind")
    ax.plot(t, h["gust_kt"], color=P["GUST"], lw=0, marker="o", ms=4, mfc="white", mew=1.5,
            label="gusts")
    top = max(max(h["gust_q90_kt"]), 15) * 1.18
    ax.set_ylim(0, top)
    for lvl in (10, 20, 30, 40):
        if lvl < top:
            ax.axhline(lvl, color=P["GRID"], lw=1, zorder=0)
    ax.set_yticks([v for v in (10, 20, 30, 40) if v < top])
    ax.set_ylabel("kt", fontsize=12)
    _time_axis(ax, t)
    ax.legend(loc="upper left", fontsize=11, frameon=False, ncol=3, handlelength=1.5)
    for ti, d in list(zip(t, h["dir"]))[1::3]:
        ax.text(ti, top * 0.83, "↓", rotation=-d, ha="center", va="center", fontsize=18,
                weight="bold", color=P["INK"])
    return fig


# ---------------------------------------------------------------------------

def _aspect_rose(fig, x, y, size, aspects, color):
    """Exposure compass: highlighted sectors are the critical aspects."""
    ax = _axes(fig, x, y, size, size)
    ax.set_xlim(-1.3, 1.3)
    ax.set_ylim(-1.3, 1.3)
    ax.set_aspect("equal")
    ax.axis("off")
    for i, a in enumerate(ASPECTS):
        # compass bearing → matplotlib angle (counter-clockwise from east)
        mid = 90 - i * 45
        ax.add_patch(Wedge((0, 0), 1, mid - 22.5, mid + 22.5, width=0.55,
                           fc=color if a in aspects else "white", ec=P["INK"], lw=1))
    ax.text(0, 1.2, "N", ha="center", va="center", fontsize=11, weight="bold", color=P["INK"])


def chalet(view):
    fig = _screen()
    _header(fig, view, f" · {view['alt']:.0f} m")
    now, h = view["now"], view["hourly"]

    _icon(fig, now["icon"], 8, 368, 105)
    _text(fig, 118, 412, f"{now['temp']:.0f}°", 50, weight="bold")
    _text(fig, 121, 380, f"0° level {now['freezing_m']} m", 13, P["MUTED"])

    _label(fig, 330, 462, "new snow 48 h (est.)")
    snow = f"{view['snow_next_cm']:.0f}"
    _text(fig, 330, 412, snow, 42, weight="bold")
    _text(fig, 336 + 32 * len(snow), 412, "cm", 15, P["MUTED"])
    _text(fig, 330, 380, f"sunshine 48 h: {sum(h['sun_min']) / 60:.0f} h", 13, P["MUTED"])

    # avalanche bulletin
    av = view.get("avalanche")
    _label(fig, 590, 462, "avalanche danger")
    if av:
        fill = P["DANGER"][av["level"]]
        fig.patches.append(Rectangle((590 / W, 372 / H), 66 / W, 72 / H, transform=fig.transFigure,
                                     fc=fill, ec=P["INK"], lw=1.5))
        _text(fig, 623, 408, f"{av['level']}{av['sub'] if av['sub'] != '=' else ''}", 30,
              "white" if av["level"] >= P["DANGER_WHITE_FROM"] else P["INK"], weight="bold",
              ha="center", va="center")
        main = max(av["problems"], key=lambda p: p["level"] or 0) if av["problems"] else None
        if main:
            elev = (f"above {main['above_m']} m" if main["above_m"] else
                    f"below {main['below_m']} m" if main["below_m"] else "all altitudes")
            _text(fig, 668, 428, main["type"].replace("_", " "), 14, weight="bold")
            _text(fig, 668, 405, elev, 13)
            _aspect_rose(fig, 845, 365, 100, main["aspects"], P["ROSE"] or fill)
        _text(fig, 668, 380, f"{av['region']} · {datetime.fromisoformat(av['valid_from']):%d.%m}",
              11, P["MUTED"])
    else:
        _text(fig, 590, 412, "no bulletin", 15)
        _text(fig, 590, 388, "outside the season", 13, P["MUTED"])

    # 48 h: sunshine strip on top, then snowfall bars and temperature line
    t = _times(h)
    sx = _axes(fig, 62, 318, 830, 26)
    sx.bar(t, h["sun_min"], width=1 / 26, color=P["SUN"])
    sx.set_ylim(0, 60)
    sx.set_xlim(t[0], t[-1])
    sx.axis("off")
    _text(fig, 18, 324, "sun", 11, P["MUTED"], weight="bold")
    ax = _axes(fig, 62, 165, 830, 145)
    _shade_nights(ax, t)
    ax.bar(t, h["snow_cm"], width=1 / 26, color=P["SNOW"], label="snow cm")
    ax.bar(t, h["rain_mm"], bottom=h["snow_cm"], width=1 / 26, color=P["RAIN"], label="rain mm")
    ax.set_ylim(0, max(1, max(s + r for s, r in zip(h["snow_cm"], h["rain_mm"])) * 1.25))
    ax.yaxis.set_major_locator(plt.MaxNLocator(3))
    ax.legend(loc="upper left", fontsize=11, frameon=False, ncol=2, handlelength=1)
    _time_axis(ax, t)
    ax2 = _temp_axis(ax, t, h["temp"], lo=0)
    ax2.axhline(0, color=P["TEMP"], lw=1, ls=":")

    # daily outlook
    days = view["days"]
    w = (W - 32) / max(len(days), 1)
    for i, d in enumerate(days):
        x = 16 + i * w
        day = datetime.fromisoformat(d["date"])
        _text(fig, x + 4, 112, f"{day:%a %d}", 13, weight="bold")
        _icon(fig, d["icon"], x, 18, 78)
        _text(fig, x + 82, 78, f"{d['tmin']:.0f}/{d['tmax']:.0f}°", 15, weight="bold")
        _text(fig, x + 82, 54, f"❄ {d['snow_cm']:.0f} cm", 13,
              P["SNOW_TEXT"] if d["snow_cm"] >= 1 else P["MUTED"])
        _text(fig, x + 82, 30, f"☀ {d['sun_h']:.0f} h", 13, P["SUN_TEXT"] if d["sun_h"] >= 1 else P["MUTED"])
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
