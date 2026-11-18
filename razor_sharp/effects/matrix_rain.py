"""Matrix rain: green code streams fall down the keyboard with bright heads and fading tails."""

import random

from razor_fx import Effect, mix, scale

CATEGORY = "Ambient"
# Which Lighting settings this effect uses: "full", "colors" (just the two colours), or "none".
LIGHTING = {"param": "use_base", "on": "full", "off": "none"}

PARAMS = {
    "color": {"type": "color", "label": "Rain colour", "default": "#00ff41", "show_if": {"param": "use_base", "is": False}},
    "use_base": {"type": "bool", "label": "Use lighting colours instead", "default": False},
    "density": {"type": "range", "label": "Drops per second", "min": 0.5, "max": 15, "default": 4, "step": 0.5},
    "speed": {"type": "range", "label": "Fall speed", "min": 1, "max": 20, "default": 6, "step": 0.5},
    "tail": {"type": "range", "label": "Tail length", "min": 1, "max": 6, "default": 3, "step": 0.5},
    "typing": {"type": "bool", "label": "Typing drops a stream", "default": True},
}

fx = Effect(PARAMS)
drops = []  # dicts: x, y (head), speed
last = None


def spawn(col, head=-0.5):
    drops.append({"x": col, "y": head, "v": float(fx.param("speed")) * random.uniform(0.6, 1.4)})


def frame(now):
    global last
    dt = 0.0 if last is None else min(0.1, now - last)
    last = now

    for r, c in fx.key_presses():
        if fx.param("typing"):
            spawn(c, r - 0.5)
    if random.random() < float(fx.param("density")) * dt:
        spawn(random.randrange(fx.cols))

    tail = float(fx.param("tail"))
    for d in drops:
        d["y"] += d["v"] * dt
    drops[:] = [d for d in drops if d["y"] - tail < fx.rows + 1]

    level = [[0.0] * fx.cols for _ in range(fx.rows)]
    head = [[0.0] * fx.cols for _ in range(fx.rows)]
    for d in drops:
        x = d["x"]
        for y in range(fx.rows):
            dist = d["y"] - y
            if 0 <= dist < tail:
                level[y][x] = max(level[y][x], (1.0 - dist / tail) ** 1.5)
            if -0.5 <= dist < 1.0:
                head[y][x] = max(head[y][x], 1.0 - abs(dist - 0.25))

    rain = fx.color("color")
    for y in range(fx.rows):
        for x in range(fx.cols):
            col = fx.base(y, x, now) if fx.param("use_base") else rain
            c = scale(col, level[y][x])
            fx.set(y, x, mix(c, fx.glow((220, 255, 220)), head[y][x] * 0.7))


fx.run(frame)
