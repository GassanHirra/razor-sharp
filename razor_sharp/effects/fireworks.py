"""Fireworks: presses launch rockets that climb the keyboard and burst into coloured sparks."""

import math
import random

from razor_fx import Effect, add, hsv, scale

CATEGORY = "Reactive"
# Which Lighting settings this effect uses: "full", "colors" (just the two colours), or "none".
LIGHTING = {"param": "background", "on": "full", "off": "none"}

PARAMS = {
    "auto": {"type": "bool", "label": "Launch on their own too", "default": True},
    "rate": {"type": "range", "label": "Auto launches per second", "min": 0.1, "max": 3, "default": 0.7, "step": 0.1},
    "particles": {"type": "range", "label": "Sparks per burst", "min": 6, "max": 40, "default": 18, "step": 1},
    "gravity": {"type": "range", "label": "Gravity", "min": 0, "max": 10, "default": 4, "step": 0.5},
    "spark_life": {"type": "range", "label": "Spark life (s)", "min": 0.3, "max": 2, "default": 0.9, "step": 0.1},
    "background": {"type": "range", "label": "Base colours (%)", "min": 0, "max": 100, "default": 12, "step": 1},
}

fx = Effect(PARAMS)
rockets = []    # dicts: x, y, vy, target, color
sparks = []     # dicts: x, y, vx, vy, color, born, life
last = None


def launch(col):
    rockets.append({"x": float(col), "y": fx.rows - 0.5, "vy": -random.uniform(8, 11),
                    "target": random.uniform(0.2, 2.2), "color": hsv(random.random(), 0.85)})


def splat(buf, x, y, color, k):
    """Spread a point of light over the four nearest keys."""
    x0, y0 = math.floor(x), math.floor(y)
    fx_, fy = x - x0, y - y0
    for yy, xx, w in ((y0, x0, (1 - fx_) * (1 - fy)), (y0, x0 + 1, fx_ * (1 - fy)),
                      (y0 + 1, x0, (1 - fx_) * fy), (y0 + 1, x0 + 1, fx_ * fy)):
        if 0 <= yy < fx.rows and 0 <= xx < fx.cols and w > 0:
            buf[yy][xx] = add(buf[yy][xx], color, k * w * 1.6)


def frame(now):
    global last
    dt = 0.0 if last is None else min(0.1, now - last)
    last = now

    for r, c in fx.key_presses():
        launch(c)
    if fx.param("auto") and random.random() < float(fx.param("rate")) * dt:
        launch(random.randrange(fx.cols))

    g = float(fx.param("gravity"))
    for rk in rockets[:]:
        rk["y"] += rk["vy"] * dt
        if rk["y"] <= rk["target"]:
            rockets.remove(rk)
            for _ in range(int(fx.param("particles"))):
                a = random.uniform(0, 2 * math.pi)
                sp = random.uniform(2, 7)
                col = rk["color"] if random.random() < 0.8 else (255, 255, 255)
                sparks.append({"x": rk["x"], "y": rk["y"], "vx": math.cos(a) * sp * 1.4,
                               "vy": math.sin(a) * sp * 0.8, "color": col, "born": now,
                               "life": float(fx.param("spark_life")) * random.uniform(0.6, 1.2)})
    for s in sparks:
        s["vy"] += g * dt
        s["vx"] *= 0.97
        s["x"] += s["vx"] * dt
        s["y"] += s["vy"] * dt
    sparks[:] = [s for s in sparks if now - s["born"] < s["life"]]

    buf = [[(0.0, 0.0, 0.0)] * fx.cols for _ in range(fx.rows)]
    for rk in rockets:
        splat(buf, rk["x"], rk["y"], (255, 230, 180), 1.0)
        splat(buf, rk["x"], rk["y"] + 0.8, (255, 120, 40), 0.4)
    for s in sparks:
        k = 1.0 - (now - s["born"]) / s["life"]
        splat(buf, s["x"], s["y"], s["color"], k * k)

    bg = float(fx.param("background")) / 100.0
    for y in range(fx.rows):
        for x in range(fx.cols):
            fx.set(y, x, add(scale(fx.base(y, x, now), bg), fx.glow(buf[y][x])))


fx.run(frame)
