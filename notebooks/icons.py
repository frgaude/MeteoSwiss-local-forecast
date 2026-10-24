"""Vector weather icons for the MeteoSwiss pictogram codes (1–42 day,
101–142 night), drawn with matplotlib patches so they stay sharp at any size.

Bold outlines and few shapes, so they read well on a 16-grey e-paper panel;
the same shapes are drawn in colour for the notebooks. Each code is split
into a sky (sun, moon, clouds, fog), a precipitation type and amount, and
thunder.

    draw(ax, code, palette)     # palette: COLOUR or GREY
"""
import numpy as np
from matplotlib.patches import Circle, FancyBboxPatch, Polygon

COLOUR = {"line": "#343a40", "sun": "#ffc21a", "sun_edge": "#f59f00", "ray": "#f59f00", "moon": "#ffe066",
          "cloud": "#f8f9fa", "dark": "#ced4da", "rain": "#1c7ed6", "snow": "#4dabf7",
          "bolt": "#fcc419", "fog": "#868e96", "bg": "white"}
GREY = {"line": "#000000", "sun": "#ffffff", "sun_edge": "#000000", "ray": "#000000", "moon": "#ffffff",
        "cloud": "#ffffff", "dark": "#cccccc", "rain": "#000000", "snow": "#000000",
        "bolt": "#000000", "fog": "#000000", "bg": "white"}

# code (day, 1–42) → (sky, precipitation, amount 1–3, thunder)
# sky: sun, few (sun + small cloud), part (sun behind cloud), cloud (overcast),
# heavy (two clouds, dark), high (high clouds), stratus, fog
SYMBOLS = {
    1: ("sun", None, 0, False), 2: ("few", None, 0, False), 3: ("part", None, 0, False),
    4: ("cloud", None, 0, False), 5: ("heavy", None, 0, False),
    6: ("part", "rain", 1, False), 7: ("part", "sleet", 1, False), 8: ("part", "snow", 1, False),
    9: ("cloud", "rain", 1, False), 10: ("cloud", "sleet", 1, False), 11: ("cloud", "snow", 1, False),
    12: ("part", None, 0, True), 13: ("part", "rain", 1, True),
    14: ("heavy", "rain", 1, False), 15: ("heavy", "sleet", 1, False), 16: ("heavy", "snow", 1, False),
    17: ("heavy", "rain", 2, False), 18: ("heavy", "sleet", 2, False), 19: ("heavy", "snow", 2, False),
    20: ("heavy", "rain", 3, False), 21: ("heavy", "sleet", 3, False), 22: ("heavy", "snow", 3, False),
    23: ("heavy", None, 0, True), 24: ("heavy", "rain", 2, True), 25: ("heavy", "rain", 3, True),
    26: ("high", None, 0, False), 27: ("stratus", None, 0, False), 28: ("fog", None, 0, False),
    29: ("part", "rain", 2, False), 30: ("part", "snow", 2, False), 31: ("part", "sleet", 2, False),
    32: ("part", "rain", 1, False), 33: ("part", "rain", 3, False), 34: ("part", "snow", 3, False),
    35: ("cloud", None, 0, False), 36: ("part", "rain", 1, True), 37: ("part", "snow", 1, True),
    38: ("cloud", "rain", 2, True), 39: ("cloud", "snow", 2, True), 40: ("heavy", None, 0, True),
    41: ("cloud", None, 0, True), 42: ("heavy", "snow", 2, True),
}


def draw(ax, code, p=COLOUR):
    """Draw pictogram `code` filling `ax` (turned into a unit box)."""
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.axis("off")
    if code is None:
        return
    night = code > 100
    sky, precip, amount, thunder = SYMBOLS.get(code % 100, ("cloud", None, 0, False))
    # line width in points from the axes size, so icons look the same at any size
    lw = ax.bbox.width / ax.figure.dpi * 72 * 0.045
    low = 0.13 if (precip or thunder) else 0.0   # lift the sky to make room below

    def body(x, y, r):                            # sun or moon
        if night:
            _moon(ax, x, y, r * 1.3, p, lw)
        else:
            _sun(ax, x, y, r, p, lw)

    if sky == "sun":
        body(0.5, 0.5 + low, 0.2 if not night else 0.24)
    elif sky == "few":
        body(0.43, 0.6 + low / 2, 0.17)
        _cloud(ax, 0.62, 0.33 + low, 0.55, p["cloud"], p, lw)
    elif sky == "part":
        body(0.32, 0.7 + low / 4, 0.16)
        _cloud(ax, 0.57, 0.42 + low, 0.82, p["cloud"], p, lw)
    elif sky == "cloud":
        _cloud(ax, 0.5, 0.48 + low, 0.95, p["cloud"], p, lw)
    elif sky == "heavy":
        _cloud(ax, 0.62, 0.62 + low * 0.7, 0.62, p["dark"], p, lw)
        _cloud(ax, 0.45, 0.45 + low, 0.92, p["dark"] if precip or thunder else p["cloud"], p, lw)
    elif sky == "high":
        body(0.5, 0.58, 0.18)
        for y, x0, x1 in ((0.32, 0.12, 0.7), (0.2, 0.3, 0.88)):
            ax.plot([x0, x1], [y, y], color=p["fog"], lw=lw, solid_capstyle="round", zorder=5)
    elif sky == "stratus":
        ax.add_patch(FancyBboxPatch((0.1, 0.42), 0.8, 0.2, boxstyle="round,pad=0,rounding_size=0.1",
                                    fc=p["dark"], ec=p["line"], lw=lw, zorder=3))
        for y, x0, x1 in ((0.3, 0.16, 0.84), (0.18, 0.26, 0.74)):
            ax.plot([x0, x1], [y, y], color=p["fog"], lw=lw, solid_capstyle="round", zorder=5)
    elif sky == "fog":
        _cloud(ax, 0.5, 0.62, 0.7, p["cloud"], p, lw)
        for y, x0, x1 in ((0.38, 0.12, 0.88), (0.26, 0.2, 0.8), (0.14, 0.12, 0.88)):
            ax.plot([x0, x1], [y, y], color=p["fog"], lw=lw, solid_capstyle="round", zorder=5)

    if thunder:
        _bolt(ax, 0.5 if precip else 0.47, 0.03, p, lw)
    if precip:
        _precip(ax, precip, amount, thunder, p, lw)


def _sun(ax, x, y, r, p, lw):
    for a in np.radians(np.arange(0, 360, 45) + 22.5):
        ax.plot([x + 1.4 * r * np.cos(a), x + 1.85 * r * np.cos(a)],
                [y + 1.4 * r * np.sin(a), y + 1.85 * r * np.sin(a)],
                color=p["ray"], lw=lw, solid_capstyle="round", zorder=1)
    ax.add_patch(Circle((x, y), r, fc=p["sun"], ec=p["sun_edge"], lw=lw, zorder=1))


def _moon(ax, x, y, r, p, lw):
    """Crescent opening to the upper right: the disc minus an offset disc."""
    d, phi, r2 = 0.55 * r, np.pi / 4, 0.85 * r
    c2 = np.array([x + d * np.cos(phi), y + d * np.sin(phi)])
    a = np.arccos((d * d + r * r - r2 * r2) / (2 * d * r))
    t = np.linspace(phi + a, phi + 2 * np.pi - a, 48)
    outer = np.column_stack([x + r * np.cos(t), y + r * np.sin(t)])
    b0 = np.arctan2(*(outer[-1] - c2)[::-1])
    b1 = np.arctan2(*(outer[0] - c2)[::-1])
    # of the two ways round the inner circle, keep the one inside the disc
    for arc in (np.linspace(b0, b1 + 2 * np.pi * (b1 < b0), 48),
                np.linspace(b0, b1 - 2 * np.pi * (b1 > b0), 48)):
        mid = c2 + r2 * np.array([np.cos(arc[24]), np.sin(arc[24])])
        if np.hypot(mid[0] - x, mid[1] - y) < r:
            break
    inner = np.column_stack([c2[0] + r2 * np.cos(arc), c2[1] + r2 * np.sin(arc)])
    ax.add_patch(Polygon(np.vstack([outer, inner]), closed=True, fc=p["moon"], ec=p["line"],
                         lw=lw, joinstyle="round", zorder=1))


def _cloud(ax, x, y, s, fill, p, lw):
    """Cloud centred at (x, y), `s` = width / 0.85. Drawn twice: outlined
    shapes, then the same shapes without outline on top, so only the outer
    contour shows."""
    parts = [(Circle, (x - 0.22 * s, y - 0.01 * s), 0.16 * s),
             (Circle, (x - 0.02 * s, y + 0.09 * s), 0.24 * s),
             (Circle, (x + 0.2 * s, y + 0.0 * s), 0.18 * s)]
    base = ((x - 0.38 * s, y - 0.17 * s), 0.76 * s, 0.2 * s)
    z = ax.patches[-1].get_zorder() + 1 if ax.patches else 2
    for ec, zz in ((p["line"], z), ("none", z + 0.5)):
        for cls, c, r in parts:
            ax.add_patch(cls(c, r, fc=fill, ec=ec, lw=lw * 2 if ec != "none" else 0, zorder=zz))
        ax.add_patch(FancyBboxPatch(*base, boxstyle=f"round,pad=0,rounding_size={0.1 * s}",
                                    fc=fill, ec=ec, lw=lw * 2 if ec != "none" else 0, zorder=zz))


def _bolt(ax, x, y, p, lw):
    pts = np.array([[0.06, 0.34], [-0.06, 0.14], [0.02, 0.14], [-0.04, -0.02],
                    [0.12, 0.2], [0.04, 0.2], [0.12, 0.34]]) + [x - 0.03, y]
    ax.add_patch(Polygon(pts, closed=True, fc=p["bolt"], ec=p["line"], lw=lw * 0.6,
                         joinstyle="round", zorder=20))


def _precip(ax, kind, amount, thunder, p, lw):
    """Drops (rain), flakes (snow) or both (sleet) under the cloud."""
    n = amount + 1
    xs = np.linspace(0.32 - 0.04 * n, 0.68 + 0.04 * n, n) if n > 1 else np.array([0.5])
    if thunder:   # leave the middle to the bolt
        xs = np.array([0.24, 0.76]) if n <= 3 else np.array([0.2, 0.32, 0.68, 0.8])
    for i, cx in enumerate(xs):
        kind_i = kind if kind != "sleet" else ("rain", "snow")[i % 2]
        cy = 0.15 if i % 2 == 0 else 0.1
        if kind_i == "rain":
            ax.plot([cx + 0.035, cx - 0.035], [cy + 0.08, cy - 0.06], color=p["rain"], lw=lw,
                    solid_capstyle="round", zorder=15)
        else:
            r = 0.065
            for a in np.radians([90, 30, 150]):
                ax.plot([cx - r * np.cos(a), cx + r * np.cos(a)], [cy - r * np.sin(a), cy + r * np.sin(a)],
                        color=p["snow"], lw=lw * 0.75, solid_capstyle="round", zorder=15)
