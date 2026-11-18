"""Typing heatmap: keys you use most glow hotter (blue, yellow, red, white) and slowly cool down."""

from razor_fx import Effect, gradient, mix, scale

CATEGORY = "Reactive"
# Which Lighting settings this effect uses: "full", "colors" (just the two colours), or "none".
LIGHTING = {"param": "background", "on": "full", "off": "none"}

PARAMS = {
    "cool_time": {"type": "range", "label": "Cool-down half-life (s)", "min": 2, "max": 300, "default": 30, "step": 1},
    "sensitivity": {"type": "range", "label": "Presses for full heat", "min": 1, "max": 40, "default": 8, "step": 1},
    "spread": {"type": "bool", "label": "Warm neighbouring keys", "default": True},
    "background": {"type": "range", "label": "Base colours when cold (%)", "min": 0, "max": 100, "default": 20, "step": 1},
}

HEAT = [(0.0, (0, 0, 60)), (0.25, (0, 60, 255)), (0.5, (0, 230, 255)),
        (0.7, (255, 230, 0)), (0.87, (255, 60, 0)), (1.0, (255, 255, 255))]

fx = Effect(PARAMS)
heat = [[0.0] * fx.cols for _ in range(fx.rows)]
last = None


def frame(now):
    global last
    dt = 0.0 if last is None else now - last
    last = now
    decay = 0.5 ** (dt / max(0.5, float(fx.param("cool_time"))))
    step = 1.0 / max(1.0, float(fx.param("sensitivity")))

    for r, c in fx.key_presses():
        heat[r][c] += step
        if fx.param("spread"):
            for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                y, x = r + dy, c + dx
                if 0 <= y < fx.rows and 0 <= x < fx.cols:
                    heat[y][x] += step * 0.3

    bg = float(fx.param("background")) / 100.0
    for y in range(fx.rows):
        for x in range(fx.cols):
            heat[y][x] = min(1.5, heat[y][x] * decay)
            h = min(1.0, heat[y][x])
            cold = scale(fx.base(y, x, now), bg)
            fx.set(y, x, mix(cold, fx.glow(gradient(HEAT, h)), min(1.0, h * 5.0)))


fx.run(frame)
