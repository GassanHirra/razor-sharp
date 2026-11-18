"""Shockwave: each press fires a bright ring outward that bends the colours as it passes, like a ripple on water."""

import math
import random

from razor_fx import Effect, add, hsv

CATEGORY = "Reactive"

PARAMS = {
    "wave_color": {"type": "color", "label": "Ring colour", "default": "#ffffff", "show_if": {"param": "rainbow", "is": False}},
    "rainbow": {"type": "bool", "label": "Random colour per ring", "default": False},
    "speed": {"type": "range", "label": "Ring speed", "min": 4, "max": 30, "default": 12, "step": 1},
    "thickness": {"type": "range", "label": "Ring thickness", "min": 0.5, "max": 3, "default": 1.0, "step": 0.25},
    "warp": {"type": "range", "label": "Colour bending", "min": 0, "max": 4, "default": 1.5, "step": 0.25},
    "life": {"type": "range", "label": "Ring lifetime (s)", "min": 0.4, "max": 4, "default": 1.6, "step": 0.1},
}

fx = Effect(PARAMS)
waves = []  # (start, row, col, colour)


def frame(now):
    for r, c in fx.key_presses():
        col = fx.glow(hsv(random.random())) if fx.param("rainbow") else fx.color("wave_color")
        waves.append((now, r, c, col))

    speed = float(fx.param("speed"))
    thick = float(fx.param("thickness"))
    warp = float(fx.param("warp"))
    life = float(fx.param("life"))
    waves[:] = [w for w in waves if now - w[0] < life]

    for y in range(fx.rows):
        for x in range(fx.cols):
            glow = (0.0, 0.0, 0.0)
            sy = sx = 0.0
            for start, wy, wx, wcol in waves:
                age = now - start
                dy, dx = y - wy, x - wx
                d = math.hypot(dy, dx)
                k = math.exp(-((d - age * speed) / thick) ** 2) * (1.0 - age / life)
                if k < 0.01:
                    continue
                glow = add(glow, wcol, k)
                if d > 0.01:  # push the colours outward where the ring is
                    sy += dy / d * k * warp
                    sx += dx / d * k * warp
            fx.set(y, x, add(fx.base(y - sy, x - sx, now), glow))


fx.run(frame)
