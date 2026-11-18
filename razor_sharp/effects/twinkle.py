"""Twinkle: random keys sparkle softly like stars on top of your lighting colours."""

import math
import random

from razor_fx import Effect, hsv, mix, scale

CATEGORY = "Ambient"
# Which Lighting settings this effect uses: "full", "colors" (just the two colours), or "none".
LIGHTING = {"param": "background", "on": "full", "off": "none"}

PARAMS = {
    "star_color": {"type": "color", "label": "Star colour", "default": "#ffffff", "show_if": {"param": "random_colors", "is": False}},
    "random_colors": {"type": "bool", "label": "Random star colours", "default": False},
    "rate": {"type": "range", "label": "Stars per second", "min": 1, "max": 40, "default": 8, "step": 1},
    "duration": {"type": "range", "label": "Twinkle time (s)", "min": 0.2, "max": 3, "default": 1.2, "step": 0.1},
    "background": {"type": "range", "label": "Base colours (%)", "min": 0, "max": 100, "default": 35, "step": 1},
    "typing": {"type": "bool", "label": "Pressed keys sparkle", "default": True},
}

fx = Effect(PARAMS)
cells = [(y, x) for y in range(fx.rows) for x in range(fx.cols) if fx.is_key(y, x)] or \
        [(y, x) for y in range(fx.rows) for x in range(fx.cols)]
stars = []  # (start, y, x, colour, duration)
last = None


def add_star(now, y, x):
    col = fx.glow(hsv(random.random(), 0.7)) if fx.param("random_colors") else fx.color("star_color")
    dur = float(fx.param("duration")) * random.uniform(0.7, 1.3)
    stars.append((now, y, x, col, dur))


def frame(now):
    global last
    dt = 0.0 if last is None else min(0.1, now - last)
    last = now
    expected = float(fx.param("rate")) * dt
    while expected > 0:
        if random.random() < min(1.0, expected):
            add_star(now, *random.choice(cells))
        expected -= 1.0
    for r, c in fx.key_presses():
        if fx.param("typing"):
            add_star(now, r, c)
    stars[:] = [s for s in stars if now - s[0] < s[4]]

    glow = {}
    for start, y, x, col, dur in stars:
        k = math.sin(math.pi * (now - start) / dur) ** 2
        if k > glow.get((y, x), (0, None))[0]:
            glow[(y, x)] = (k, col)

    bg = float(fx.param("background")) / 100.0
    for y in range(fx.rows):
        for x in range(fx.cols):
            c = scale(fx.base(y, x, now), bg)
            k, col = glow.get((y, x), (0.0, None))
            fx.set(y, x, mix(c, col, k) if col else c)


fx.run(frame)
