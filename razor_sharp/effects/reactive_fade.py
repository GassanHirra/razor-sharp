"""Reactive: pressed keys flash a colour and fade back to the base lighting.

Turn up "Glow radius" to light the neighbouring keys too.
"""

import math

from razor_fx import Effect, hsv, mix

CATEGORY = "Reactive"

PARAMS = {
    "flash_color": {"type": "color", "label": "Flash colour", "default": "#ffffff", "show_if": {"param": "rainbow_flash", "is": False}},
    "rainbow_flash": {"type": "bool", "label": "Random colour per press", "default": False},
    "fade": {"type": "range", "label": "Fade (s)", "min": 0.1, "max": 4, "default": 0.8, "step": 0.1},
    "radius": {"type": "range", "label": "Glow radius", "min": 0, "max": 4, "default": 0, "step": 0.5},
}

fx = Effect(PARAMS)
presses = []  # (time, row, col, colour)
hue = 0.0


def frame(now):
    global hue
    for r, c in fx.key_presses():
        if fx.param("rainbow_flash"):
            hue = (hue + 0.17) % 1.0
            col = fx.glow(hsv(hue))
        else:
            col = fx.color("flash_color", "#ffffff")
        presses.append((now, r, c, col))

    fade = max(0.05, float(fx.param("fade")))
    radius = float(fx.param("radius"))
    presses[:] = [p for p in presses if now - p[0] < fade]

    for y in range(fx.rows):
        for x in range(fx.cols):
            color = fx.base(y, x, now)
            for start, py, px, pcol in presses:
                d = math.hypot(y - py, x - px)
                if d > radius + 0.01:
                    continue
                k = (1.0 - (now - start) / fade) * (1.0 - d / (radius + 1.0))
                color = mix(color, pcol, k)
            fx.set(y, x, color)


fx.run(frame)
