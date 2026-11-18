"""Starfield: fly through space as stars stream out from the centre of the keyboard; typing jumps to warp speed."""

import math
import random

from razor_fx import Effect, add, hsv, scale

CATEGORY = "Ambient"
LIGHTING = {"param": "background", "on": "full", "off": "none"}

PARAMS = {
    "star_color": {"type": "color", "label": "Star colour", "default": "#ffffff",
                   "show_if": {"param": "tinted", "is": False}},
    "tinted": {"type": "bool", "label": "Coloured stars", "default": False},
    "speed": {"type": "range", "label": "Speed", "min": 0.2, "max": 3, "default": 1.0, "step": 0.1},
    "density": {"type": "range", "label": "Stars", "min": 5, "max": 60, "default": 22, "step": 1},
    "warp": {"type": "bool", "label": "Typing jumps to warp", "default": True},
    "background": {"type": "range", "label": "Lighting colours behind (%)", "min": 0, "max": 100, "default": 0, "step": 1},
}

fx = Effect(PARAMS)
R0, R1, C0, C1 = fx.bounds
CY, CX = (R0 + R1) / 2.0, (C0 + C1) / 2.0
stars = []
state = {"last": None, "boost": 0.0}


def new_star(far=False):
    a = random.uniform(0, 2 * math.pi)
    d = random.uniform(0.3, 6.0) if far else random.uniform(0.0, 0.8)
    col = hsv(random.random(), 0.45) if fx.param("tinted") else None
    return {"a": a, "d": d, "v": random.uniform(0.6, 1.4), "col": col}


def frame(now):
    dt = 0.0 if state["last"] is None else min(0.1, now - state["last"])
    if state["last"] is None:
        stars.extend(new_star(far=True) for _ in range(int(fx.param("density"))))
    state["last"] = now
    if fx.key_presses() and fx.param("warp"):
        state["boost"] = 1.0
    state["boost"] = max(0.0, state["boost"] - dt * 0.8)
    speed = float(fx.param("speed")) * (1.0 + 5.0 * state["boost"])

    want = int(fx.param("density"))
    while len(stars) < want:
        stars.append(new_star())
    del stars[want:]

    buf = {}
    plain = fx.color("star_color")
    for s in stars:
        s["d"] += dt * speed * s["v"] * (0.6 + s["d"] * 0.9)
        if s["d"] > 12:
            s.update(new_star())
            continue
        bright = min(1.0, 0.15 + s["d"] / 5.0)
        col = fx.glow(s["col"]) if s["col"] else plain
        trail = 1 + int(min(3, s["d"] / 3 * (1 + state["boost"] * 2)))
        for i in range(trail):
            dd = s["d"] - i * 0.7
            if dd < 0:
                break
            y = round(CY + math.sin(s["a"]) * dd * 0.45)
            x = round(CX + math.cos(s["a"]) * dd * 1.3)
            if R0 <= y <= R1 and C0 <= x <= C1:
                k = bright * (1.0 - i / (trail + 0.5))
                buf[(y, x)] = add(buf.get((y, x), (0, 0, 0)), col, k)

    bg = float(fx.param("background")) / 100.0
    for y in range(fx.rows):
        for x in range(fx.cols):
            base = scale(fx.base(y, x, now), bg) if bg else (0, 0, 0)
            fx.set(y, x, add(base, buf.get((y, x), (0, 0, 0))))


fx.run(frame)
