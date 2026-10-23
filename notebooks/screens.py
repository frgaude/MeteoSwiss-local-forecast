"""Screens for the home, boat and chalet views on a LilyGO T5 4.7" e-paper
(V2.3: ESP32-S3, ED047TC1 panel, 960×540, 16 grey levels), drawn with
matplotlib from the dicts built by localforecast.py.

The panel is small (~104×58 mm, ~234 dpi), so text is never below 11 pt
here (15 px, ~1.6 mm) and the main values are large.

    img = render(home, view)       # 960×540 greyscale PIL image, 16 levels
    buf = epd_buffer(img)          # 259,200 bytes for the LilyGo-EPD47 driver
"""
from datetime import datetime

import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.dates import DateFormatter, HourLocator
from matplotlib.patches import Rectangle, Wedge
from PIL import Image

import localforecast as lf

W, H = 960, 540
# greys only; each lands on one of the panel's 16 levels (multiples of 0x11)
INK, MUTED, GRID, NIGHT = "#000000", "#444444", "#bbbbbb", "#eeeeee"
RAIN, SNOW, SUN, BAND = "#000000", "#999999", "#555555", "#cccccc"
# EAWS danger levels 1–5 as greys, light to dark; white text from level 3
DANGER_GREYS = {1: "#eeeeee", 2: "#bbbbbb", 3: "#777777", 4: "#333333", 5: "#000000"}
ASPECTS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12, "axes.edgecolor": MUTED,
                     "axes.labelcolor": MUTED, "xtick.color": INK, "ytick.color": MUTED,
                     "xtick.labelsize": 12, "ytick.labelsize": 11})


def _screen():
    return plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor="white")


def _axes(fig, x, y, w, h, **kw):
    """Axes at figure px: lower-left corner (x, y), size w×h."""
    return fig.add_axes([x / W, y / H, w / W, h / H], **kw)


def _icon(fig, code, x, y, w):
    """Place pictogram `code` with its lower-left corner at figure px (x, y)."""
    if code is None:
        return
    ax = _axes(fig, x, y, w, w)
    ax.imshow(_grey_icon(code, round(w)), cmap="gray", vmin=0, vmax=255)
    ax.axis("off")


def _grey_icon(code, size):
    """Pictogram flattened on white and darkened, so pale colours (yellow sun,
    light clouds) still stand out in grey."""
    im = Image.open(lf.icon_path(code)).convert("RGBA")
    flat = Image.new("RGBA", im.size, "white")
    flat.alpha_composite(im)
    grey = flat.convert("L").resize((size, size), Image.LANCZOS)
    return np.asarray(grey.point(lambda v: 255 if v > 245 else int(255 * (v / 255) ** 1.8)))


def _text(fig, x, y, s, size=12, color=INK, weight="normal", ha="left", va="baseline"):
    fig.text(x / W, y / H, s, fontsize=size, color=color, weight=weight, ha=ha, va=va)


def _times(hourly):
    return [datetime.fromisoformat(t) for t in hourly["time"]]


def _time_axis(ax, times):
    ax.xaxis.set_major_locator(HourLocator(byhour=[0, 12], tz=lf.TZ))
    ax.xaxis.set_major_formatter(DateFormatter("%a %Hh", tz=lf.TZ))
    ax.xaxis.set_minor_locator(HourLocator(byhour=[6, 18], tz=lf.TZ))
    ax.set_xlim(times[0], times[-1])
    ax.grid(axis="x", which="both", color=GRID, lw=1)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(length=0, which="both")


def _shade_nights(ax, times):
    for t in times:
        if t.hour < 7 or t.hour >= 19:
            ax.axvspan(t - np.timedelta64(30, "m"), t + np.timedelta64(30, "m"),
                       color=NIGHT, lw=0, zorder=0)


def _temp_axis(ax, t, temp, lo=None):
    """Temperature line on a right-hand axis, with a white halo over bars."""
    ax2 = ax.twinx()
    ax2.plot(t, temp, color=INK, lw=3,
             path_effects=[pe.Stroke(linewidth=7, foreground="white"), pe.Normal()])
    ax2.set_ylim((min(temp) if lo is None else min(min(temp), lo)) - 2, max(temp) + 2)
    ax2.yaxis.set_major_locator(plt.MaxNLocator(4, integer=True))
    ax2.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}°")
    ax2.tick_params(length=0, labelsize=12, labelcolor=INK)
    for s in ("top", "left", "right"):
        ax2.spines[s].set_visible(False)
    return ax2


def _header(fig, view, extra=""):
    run = datetime.fromisoformat(view["run"])
    _text(fig, 16, H - 36, view["name"], 22, weight="bold")
    _text(fig, W - 16, H - 32, f"forecast run {run:%a %H:%M}{extra}", 12, MUTED, ha="right")


def _label(fig, x, y, s):
    _text(fig, x, y, s.upper(), 11, MUTED, weight="bold")


# ---------------------------------------------------------------------------

def home(view):
    fig = _screen()
    _header(fig, view)
    now, solar = view["now"], view["solar"]

    # now: icon + forecast temperature for this hour
    _icon(fig, now["icon"], 10, 360, 120)
    _text(fig, 140, 410, f"{now['temp']:.0f}°", 60, weight="bold")
    _text(fig, 144, 378, lf.icon_text(now["icon"]), 13, MUTED)

    # solar: today's estimated energy + hourly profile
    _label(fig, 470, 462, "solar today (est.)")
    _text(fig, 470, 412, f"{solar['today_kwh']:.1f}", 40, weight="bold")
    _text(fig, 475 + 30 * len(f"{solar['today_kwh']:.1f}"), 412, "kWh", 15, MUTED)
    _text(fig, 470, 380, f"tomorrow {solar['tomorrow_kwh']:.1f} kWh", 13, MUTED)
    ax = _axes(fig, 735, 382, 210, 85)
    hours = solar["hours"]
    ax.bar(hours, solar["hourly_kw"], width=0.85, color=SUN)
    ax.axvline(datetime.now(lf.TZ).hour, color=INK, lw=1.5, ls=":")
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
    ax.bar(t, h["rain_mm"], width=1 / 26, color=RAIN, label="rain")
    ax.bar(t, h["snow_mm"], bottom=h["rain_mm"], width=1 / 26, color=SNOW, label="snow")
    ax.set_ylim(0, max(2, max(r + s for r, s in zip(h["rain_mm"], h["snow_mm"])) * 1.2))
    ax.yaxis.set_major_locator(plt.MaxNLocator(3))
    ax.set_ylabel("mm/h", fontsize=11)
    ax.legend(loc="upper left", fontsize=11, frameon=False, ncol=2, handlelength=1)
    _time_axis(ax, t)
    _temp_axis(ax, t, h["temp"])

    # outlook: half-day steps
    steps = view["outlook"]
    w = (W - 32) / max(len(steps), 1)
    for i, s in enumerate(steps):
        x = 16 + i * w
        start = datetime.fromisoformat(s["start"])
        label = f"{start:%a}" + ("" if s["day"] else " night")
        _text(fig, x + w / 2, 115, label, 13, INK if s["day"] else MUTED, ha="center")
        _icon(fig, s["icon"], x + 4, 18, 80)
        _text(fig, x + 90, 45, f"{s['temp']:.0f}°", 24, INK if s["day"] else MUTED, weight="bold")
    return fig


# ---------------------------------------------------------------------------

def _beaufort(kt):
    return int(np.searchsorted([1, 4, 7, 11, 17, 22, 28, 34, 41, 48, 56, 64], kt, side="right"))


def boat(view):
    fig = _screen()
    _header(fig, view)
    now, h = view["now"], view["hourly"]

    # now: wind, gust, direction compass
    _text(fig, 16, 405, f"{now['wind_kt']:.0f}", 66, weight="bold")
    _text(fig, 22 + 50 * len(f"{now['wind_kt']:.0f}"), 405, "kt", 18, MUTED)
    _text(fig, 18, 372, f"gusts {now['gust_kt']:.0f} kt · Bft {_beaufort(now['wind_kt'])}", 14, MUTED)
    ax = _axes(fig, 205, 362, 110, 110, projection="polar")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_yticks([])
    ax.set_xticks(np.radians(range(0, 360, 90)), ["N", "E", "S", "W"], fontsize=11)
    ax.tick_params(pad=-2)
    ax.annotate("", xy=(np.radians(now["dir"] + 180), 0.9), xytext=(np.radians(now["dir"]), 0.9),
                arrowprops=dict(arrowstyle="-|>,head_width=0.5,head_length=0.8", color=INK, lw=3.5))
    ax.set_ylim(0, 1)

    # summary for the next 12 h
    t = _times(h)
    nxt12 = slice(0, 12)
    _label(fig, 370, 462, "next 12 h")
    _text(fig, 370, 428, f"mean {min(h['wind_kt'][nxt12]):.0f}–{max(h['wind_kt'][nxt12]):.0f} kt", 20,
          weight="bold")
    _text(fig, 370, 400, f"max gust {max(h['gust_kt'][nxt12]):.0f} kt", 15)
    _text(fig, 370, 375, f"up to {max(h['gust_q90_kt'][nxt12]):.0f} kt at 90 %", 13, MUTED)
    _icon(fig, now["icon"], W - 115, 365, 100)
    _text(fig, W - 120, 395, f"{now['temp']:.0f}°", 26, weight="bold", ha="right")

    # 48 h wind: mean with 10–90 % band, gusts, direction
    ax = _axes(fig, 52, 42, 893, 300)
    _shade_nights(ax, t)
    ax.fill_between(t, h["wind_q10_kt"], h["wind_q90_kt"], color=BAND, lw=0, label="10–90 %")
    ax.plot(t, h["wind_kt"], color=INK, lw=3, label="mean wind")
    ax.plot(t, h["gust_kt"], color=INK, lw=0, marker="o", ms=4, mfc="white", mew=1.5, label="gusts")
    top = max(max(h["gust_q90_kt"]), 15) * 1.18
    ax.set_ylim(0, top)
    for lvl in (10, 20, 30, 40):
        if lvl < top:
            ax.axhline(lvl, color=GRID, lw=1, zorder=0)
    ax.set_yticks([v for v in (10, 20, 30, 40) if v < top])
    ax.set_ylabel("kt", fontsize=12)
    _time_axis(ax, t)
    ax.legend(loc="upper left", fontsize=11, frameon=False, ncol=3, handlelength=1.5)
    for ti, d in list(zip(t, h["dir"]))[1::3]:
        ax.text(ti, top * 0.83, "↓", rotation=-d, ha="center", va="center", fontsize=18,
                weight="bold", color=INK)
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
                           fc=color if a in aspects else "white", ec=INK, lw=1))
    ax.text(0, 1.2, "N", ha="center", va="center", fontsize=11, weight="bold")


def chalet(view):
    fig = _screen()
    _header(fig, view, f" · {view['alt']:.0f} m")
    now, h = view["now"], view["hourly"]

    _icon(fig, now["icon"], 8, 368, 105)
    _text(fig, 118, 412, f"{now['temp']:.0f}°", 50, weight="bold")
    _text(fig, 121, 380, f"0° level {now['freezing_m']} m", 13, MUTED)

    _label(fig, 330, 462, "new snow 48 h (est.)")
    snow = f"{view['snow_next_cm']:.0f}"
    _text(fig, 330, 412, snow, 42, weight="bold")
    _text(fig, 336 + 32 * len(snow), 412, "cm", 15, MUTED)
    _text(fig, 330, 380, f"sunshine 48 h: {sum(h['sun_min']) / 60:.0f} h", 13, MUTED)

    # avalanche bulletin
    av = view.get("avalanche")
    _label(fig, 590, 462, "avalanche danger")
    if av:
        fill = DANGER_GREYS[av["level"]]
        fig.patches.append(Rectangle((590 / W, 372 / H), 66 / W, 72 / H, transform=fig.transFigure,
                                     fc=fill, ec=INK, lw=1.5))
        _text(fig, 623, 408, f"{av['level']}{av['sub'] if av['sub'] != '=' else ''}", 30,
              "white" if av["level"] >= 3 else INK, weight="bold", ha="center", va="center")
        main = max(av["problems"], key=lambda p: p["level"] or 0) if av["problems"] else None
        if main:
            elev = (f"above {main['above_m']} m" if main["above_m"] else
                    f"below {main['below_m']} m" if main["below_m"] else "all altitudes")
            _text(fig, 668, 428, main["type"].replace("_", " "), 14, weight="bold")
            _text(fig, 668, 405, elev, 13)
            _aspect_rose(fig, 845, 365, 100, main["aspects"], MUTED)
        _text(fig, 668, 380, f"{av['region']} · {datetime.fromisoformat(av['valid_from']):%d.%m}",
              11, MUTED)
    else:
        _text(fig, 590, 412, "no bulletin", 15)
        _text(fig, 590, 388, "outside the season", 13, MUTED)

    # 48 h: sunshine strip on top, then snowfall bars and temperature line
    t = _times(h)
    sx = _axes(fig, 62, 318, 830, 26)
    sx.bar(t, h["sun_min"], width=1 / 26, color=SUN)
    sx.set_ylim(0, 60)
    sx.set_xlim(t[0], t[-1])
    sx.axis("off")
    _text(fig, 18, 324, "sun", 11, MUTED, weight="bold")
    ax = _axes(fig, 62, 165, 830, 145)
    _shade_nights(ax, t)
    ax.bar(t, h["snow_cm"], width=1 / 26, color=SNOW, label="snow cm")
    ax.bar(t, h["rain_mm"], bottom=h["snow_cm"], width=1 / 26, color=RAIN, label="rain mm")
    ax.set_ylim(0, max(1, max(s + r for s, r in zip(h["snow_cm"], h["rain_mm"])) * 1.25))
    ax.yaxis.set_major_locator(plt.MaxNLocator(3))
    ax.legend(loc="upper left", fontsize=11, frameon=False, ncol=2, handlelength=1)
    _time_axis(ax, t)
    ax2 = _temp_axis(ax, t, h["temp"], lo=0)
    ax2.axhline(0, color=INK, lw=1, ls=":")

    # daily outlook
    days = view["days"]
    w = (W - 32) / max(len(days), 1)
    for i, d in enumerate(days):
        x = 16 + i * w
        day = datetime.fromisoformat(d["date"])
        _text(fig, x + 4, 112, f"{day:%a %d}", 13, weight="bold")
        _icon(fig, d["icon"], x, 18, 78)
        _text(fig, x + 82, 78, f"{d['tmin']:.0f}/{d['tmax']:.0f}°", 15, weight="bold")
        _text(fig, x + 82, 54, f"❄ {d['snow_cm']:.0f} cm", 13, INK if d["snow_cm"] >= 1 else MUTED)
        _text(fig, x + 82, 30, f"☀ {d['sun_h']:.0f} h", 13, INK if d["sun_h"] >= 1 else MUTED)
    return fig


# ---------------------------------------------------------------------------
# Output for the panel
# ---------------------------------------------------------------------------

def render(draw, view):
    """Draw `view` with `draw` (home, boat or chalet) and return it as a
    960×540 greyscale image snapped to the panel's 16 levels."""
    fig = draw(view)
    fig.canvas.draw()
    rgba = np.asarray(fig.canvas.buffer_rgba())
    plt.close(fig)
    return Image.fromarray(rgba).convert("L").point(lambda v: (v // 16) * 17)


def epd_buffer(img):
    """Frame buffer for the LilyGo-EPD47 driver (`epd_draw_grayscale_image`):
    4 bits per pixel, 0 = black, 15 = white, rows top to bottom, two pixels
    per byte with the left (even x) pixel in the low nibble. 259,200 bytes."""
    a = np.asarray(img.convert("L"), dtype=np.uint8) >> 4
    return (a[:, 0::2] | (a[:, 1::2] << 4)).astype(np.uint8).tobytes()
