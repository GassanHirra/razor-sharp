"""Comet trail: the keys you type are joined by a glowing streak that fades from the tail."""

import math

from razor_fx import Effect, hsv, mix, scale

CATEGORY = "Reactive"
# Which Lighting settings this effect uses: "full", "colors" (just the two colours), or "none".
LIGHTING = {"param": "background", "on": "full", "off": "none"}

PARAMS = {
    "color": {"type": "color", "label": "Comet colour", "default": "#00e5ff", "show_if": {"param": "rainbow", "is": False}},
    "rainbow": {"type": "bool", "label": "Rainbow tail", "default": True},
    "trail_time": {"type": "range", "label": "Tail length (s)", "min": 0.3, "max": 5, "default": 1.5, "step": 0.1},
    "points": {"type": "range", "label": "Keys in the tail", "min": 2, "max": 30, "default": 10, "step": 1},
    "background": {"type": "range", "label": "Base colours (%)", "min": 0, "max": 100, "default": 30, "step": 1},
}

fx = Effect(PARAMS)
history = []  # (time, row, col)


def frame(now):
    for r, c in fx.key_presses():
        history.append((now, r, c))
    trail = float(fx.param("trail_time"))
    del history[:-int(fx.param("points"))]
    history[:] = [h for h in history if now - h[0] < trail]

    level = [[0.0] * fx.cols for _ in range(fx.rows)]
    hue = [[0.0] * fx.cols for _ in range(fx.rows)]

    def light(y, x, k, h):
        y, x = round(y), round(x)
        if 0 <= y < fx.rows and 0 <= x < fx.cols and k > level[y][x]:
            level[y][x], hue[y][x] = k, h

    n = len(history)
    for i in range(n - 1):
        (t0, y0, x0), (t1, y1, x1) = history[i], history[i + 1]
        steps = max(1, int(math.hypot(y1 - y0, x1 - x0) * 4))
        for s in range(steps + 1):
            f = s / steps
            age = now - (t0 + (t1 - t0) * f)
            light(y0 + (y1 - y0) * f, x0 + (x1 - x0) * f, max(0.0, 1.0 - age / trail), (i + f) / max(1, n))
    if history:  # glowing head
        t, y, x = history[-1]
        k = max(0.0, 1.0 - (now - t) / trail)
        for dy, dx in ((0, 0), (0, 1), (0, -1), (1, 0), (-1, 0)):
            light(y + dy, x + dx, k * (1.0 if dy == dx == 0 else 0.4), 1.0)

    bg = float(fx.param("background")) / 100.0
    base_col = fx.color("color")
    for y in range(fx.rows):
        for x in range(fx.cols):
            k = level[y][x]
            col = fx.glow(hsv(hue[y][x] * 0.8 + now * 0.05)) if fx.param("rainbow") else base_col
            fx.set(y, x, mix(scale(fx.base(y, x, now), bg), col, k))


fx.run(frame)
