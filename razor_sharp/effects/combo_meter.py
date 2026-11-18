"""Combo meter: the faster you type, the hotter and more intense the keyboard gets; pause and it cools down."""

import math

from razor_fx import Effect, add, mix, scale

CATEGORY = "Reactive"

PARAMS = {
    "hot_color": {"type": "color", "label": "Full-power colour", "default": "#ff2a00"},
    "max_speed": {"type": "range", "label": "Keys/s for full power", "min": 2, "max": 15, "default": 7, "step": 0.5},
    "cool": {"type": "range", "label": "Cool-down speed", "min": 0.2, "max": 5, "default": 1.2, "step": 0.1},
    "pulse": {"type": "bool", "label": "Pulse at high speed", "default": True},
    "show_bar": {"type": "bool", "label": "Show level on F-keys", "default": True},
}

fx = Effect(PARAMS)
presses = []   # times
flashes = {}   # (y, x) -> time
level = 0.0
last = None
F_KEYS = fx.positions([f"F{i}" for i in range(1, 13)]) or fx.positions(["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "MINUS", "EQUAL"])  # number row if no F-keys


def frame(now):
    global level, last
    dt = 0.0 if last is None else now - last
    last = now
    for r, c in fx.key_presses():
        presses.append(now)
        flashes[(r, c)] = now
    presses[:] = [t for t in presses if now - t < 2.0]

    target = min(1.0, (len(presses) / 2.0) / float(fx.param("max_speed")))
    rate = 5.0 if target > level else float(fx.param("cool")) * 0.6
    level += (target - level) * min(1.0, dt * rate)

    hot = fx.color("hot_color")
    pulse = 1.0
    if fx.param("pulse") and level > 0.5:
        pulse = 1.0 - (level - 0.5) * 0.6 * (0.5 + 0.5 * math.sin(now * (6 + 14 * level)))

    bar = fx.param("show_bar")
    lit = level * len(F_KEYS)
    for y in range(fx.rows):
        for x in range(fx.cols):
            c = scale(mix(fx.base(y, x, now), hot, level), pulse)
            t = flashes.get((y, x))
            if t is not None:
                k = 1.0 - (now - t) / 0.3
                if k > 0:
                    c = add(c, fx.glow((255, 255, 255)), k * (0.4 + 0.6 * level))
            if bar and (y, x) in F_KEYS:
                i = F_KEYS.index((y, x))
                fill = max(0.0, min(1.0, lit - i))
                seg = mix((0, 255, 80), (255, 0, 0), i / (len(F_KEYS) - 1))
                c = fx.glow(mix((12, 12, 12), seg, fill))
            fx.set(y, x, c)
    for key, t in list(flashes.items()):
        if now - t > 0.3:
            del flashes[key]


fx.run(frame)
