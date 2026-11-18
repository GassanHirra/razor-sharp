"""Reverse ripple: all keys lit, and each press sends out a ring that switches keys off before they fade back.

Base colours come from the app; the ring colour, speed, width and fade are effect options.
"""

import math

from razor_fx import Effect, mix

CATEGORY = "Reactive"

PARAMS = {
    "ring_color": {"type": "color", "label": "Ring colour", "default": "#000000"},
    "speed": {"type": "range", "label": "Ring speed", "min": 4, "max": 40, "default": 18, "step": 1},
    "width": {"type": "range", "label": "Ring width", "min": 0.5, "max": 6, "default": 1.5, "step": 0.5},
    "fade": {"type": "range", "label": "Fade back (s)", "min": 0.1, "max": 3, "default": 0.6, "step": 0.1},
}

fx = Effect(PARAMS)
ripples = []  # (start_time, row, col)


def frame(now):
    for r, c in fx.key_presses():
        ripples.append((now, r, c))

    speed = float(fx.param("speed"))
    width = float(fx.param("width"))
    fade = max(0.05, float(fx.param("fade")))
    ring = fx.color("ring_color", "#000000")
    life = math.hypot(fx.rows, fx.cols) / speed + width / speed + fade
    ripples[:] = [rp for rp in ripples if now - rp[0] < life]

    for y in range(fx.rows):
        for x in range(fx.cols):
            k = 0.0
            for start, ry, rx in ripples:
                age = now - start
                reach = math.hypot(y - ry, x - rx) / speed
                if age < reach:
                    continue
                leave = reach + width / speed
                k = 1.0 if age < leave else max(k, 1.0 - (age - leave) / fade)
                if k >= 1.0:
                    break
            fx.set(y, x, mix(fx.base(y, x, now), ring, k))


fx.run(frame)
