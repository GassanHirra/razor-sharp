"""Rain: drops fall down the keyboard and splash across the bottom row; turn on Thunderstorm for lightning."""

import math
import random

from razor_fx import Effect, add, mix, scale

CATEGORY = "Ambient"
LIGHTING = {"param": "background", "on": "full", "off": "none"}

PARAMS = {
    "drop_color": {"type": "color", "label": "Rain colour", "default": "#3aa0ff"},
    "intensity": {"type": "range", "label": "Rain (drops per second)", "min": 1, "max": 30, "default": 9, "step": 1},
    "speed": {"type": "range", "label": "Fall speed", "min": 2, "max": 20, "default": 9, "step": 0.5},
    "storm": {"type": "bool", "label": "Thunderstorm", "default": False},
    "typing": {"type": "bool", "label": "Typing makes drops", "default": True},
    "background": {"type": "range", "label": "Lighting colours behind (%)", "min": 0, "max": 100, "default": 12, "step": 1},
}

fx = Effect(PARAMS)
R0, R1, C0, C1 = fx.bounds
drops, splashes = [], []
state = {"last": None, "flash": -99.0, "next_storm": 0.0}


def frame(now):
    dt = 0.0 if state["last"] is None else min(0.1, now - state["last"])
    state["last"] = now
    rate = float(fx.param("intensity")) * (1.8 if fx.param("storm") else 1.0)
    n = rate * dt
    while n > 0:
        if random.random() < min(1.0, n):
            drops.append({"x": random.randint(C0, C1), "y": R0 - random.random(), "v": random.uniform(0.8, 1.2)})
        n -= 1
    for r, c in fx.key_presses():
        if fx.param("typing"):
            drops.append({"x": c, "y": float(r), "v": 1.0})
    speed = float(fx.param("speed"))
    for d in drops[:]:
        d["y"] += d["v"] * speed * dt
        if d["y"] >= R1 + 0.5:
            drops.remove(d)
            splashes.append((now, d["x"]))
    splashes[:] = [s for s in splashes if now - s[0] < 0.6]

    if fx.param("storm") and now >= state["next_storm"]:
        if state["next_storm"]:
            state["flash"] = now
        state["next_storm"] = now + random.uniform(4, 12)
    since = now - state["flash"]
    flash = 0.0
    if since < 0.6:
        flash = max(0.0, 1.0 - since / 0.6) * (0.4 + 0.6 * (math.sin(since * 40) > 0))

    rain = fx.color("drop_color")
    bg = float(fx.param("background")) / 100.0
    for y in range(fx.rows):
        for x in range(fx.cols):
            c = scale(fx.base(y, x, now), bg)
            for d in drops:
                if d["x"] == x:
                    dist = d["y"] - y
                    if -0.5 <= dist < 2.0:
                        c = add(c, rain, max(0.0, 1.0 - abs(dist - 0.2) / 1.4))
            if y == R1:
                for t, sx in splashes:
                    age = now - t
                    ring = abs(abs(x - sx) - age * 6)
                    if ring < 0.8 and abs(x - sx) <= 3:
                        c = add(c, rain, (1.0 - ring / 0.8) * (1.0 - age / 0.6))
            if flash:
                c = mix(c, fx.glow((220, 225, 255)), flash * (0.9 if y < R0 + 2 else 0.6))
            fx.set(y, x, c)


fx.run(frame)
