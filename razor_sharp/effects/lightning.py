"""Lightning: each press shoots a jagged, branching bolt across nearby keys that flickers and fades."""

import math
import random

from razor_fx import Effect, mix

CATEGORY = "Reactive"

PARAMS = {
    "bolt_color": {"type": "color", "label": "Bolt colour", "default": "#a8dcff"},
    "length": {"type": "range", "label": "Bolt length", "min": 3, "max": 20, "default": 9, "step": 1},
    "branches": {"type": "range", "label": "Branching (%)", "min": 0, "max": 80, "default": 35, "step": 1},
    "fade": {"type": "range", "label": "Fade (s)", "min": 0.1, "max": 2, "default": 0.5, "step": 0.05},
    "flash": {"type": "bool", "label": "Flash the whole keyboard", "default": True},
}

fx = Effect(PARAMS)
bolts = []  # (start, {(y, x): strength})
FLICKER = 0.14


def make_bolt(r, c):
    cells = {(r, c): 1.0}
    length = int(fx.param("length"))
    branch = float(fx.param("branches")) / 100.0
    walkers = [(float(r), float(c), random.uniform(0, 2 * math.pi), length, 1.0)]
    while walkers:
        y, x, ang, left, strength = walkers.pop()
        for i in range(left):
            ang += random.uniform(-0.9, 0.9)
            y += math.sin(ang) * 0.7
            x += math.cos(ang)
            cy, cx = round(y), round(x)
            if not (0 <= cy < fx.rows and 0 <= cx < fx.cols):
                break
            s = strength * (1.0 - i / (left + 1) * 0.6)
            cells[(cy, cx)] = max(cells.get((cy, cx), 0.0), s)
            if random.random() < branch * 0.3 and left - i > 2:
                walkers.append((y, x, ang + random.choice((-1, 1)) * random.uniform(0.6, 1.2),
                                (left - i) // 2, s * 0.7))
    return cells


def frame(now):
    for r, c in fx.key_presses():
        bolts.append((now, make_bolt(r, c)))

    fade = float(fx.param("fade"))
    bolts[:] = [b for b in bolts if now - b[0] < FLICKER + fade]
    color = fx.color("bolt_color")

    light = {}
    flash = 0.0
    for start, cells in bolts:
        age = now - start
        if age < FLICKER:
            k = random.choice((1.0, 0.25, 1.0, 0.6, 0.9))
            flash = max(flash, 0.35 * k)
        else:
            k = 1.0 - (age - FLICKER) / fade
        for cell, s in cells.items():
            light[cell] = max(light.get(cell, 0.0), s * k)
    if not fx.param("flash"):
        flash = 0.0

    for y in range(fx.rows):
        for x in range(fx.cols):
            k = max(light.get((y, x), 0.0), flash)
            fx.set(y, x, mix(fx.base(y, x, now), color, k))


fx.run(frame)
