"""Fire: flickering flames rise from the bottom row; typing feeds the flames and makes them flare up."""

import random

from razor_fx import Effect, gradient, scale

CATEGORY = "Ambient"
# Whether the "Effect brightness" slider applies (this effect only uses the lighting colours otherwise).
EFFECT_BRIGHTNESS = {"param": "use_base", "is": False}
# Which Lighting settings this effect uses: "full", "colors" (just the two colours), or "none".
LIGHTING = {"param": "use_base", "on": "full", "off": "none"}

PARAMS = {
    "height": {"type": "range", "label": "Flame height", "min": 1, "max": 10, "default": 6, "step": 0.5},
    "intensity": {"type": "range", "label": "Intensity (%)", "min": 30, "max": 100, "default": 90, "step": 1},
    "flare": {"type": "bool", "label": "Typing makes flames flare", "default": True},
    "use_base": {"type": "bool", "label": "Flames in lighting colours", "default": False},
}

FLAME = [(0.0, (0, 0, 0)), (0.2, (120, 0, 0)), (0.45, (255, 40, 0)),
         (0.7, (255, 140, 0)), (0.88, (255, 220, 40)), (1.0, (255, 255, 200))]

fx = Effect(PARAMS)
H = fx.rows + 2                       # two hidden rows below the keyboard feed the fire
heat = [[0.0] * fx.cols for _ in range(H)]
fuel = [0.0] * fx.cols
acc = 0.0
last = None
STEP = 1.0 / 24                       # simulation rate


def simulate():
    inten = float(fx.param("intensity")) / 100.0
    cooling = (11.0 - float(fx.param("height"))) * 0.022
    for x in range(fx.cols):
        for y in (H - 1, H - 2):
            heat[y][x] = min(1.0, random.uniform(0.45, 1.0) * inten + fuel[x])
        fuel[x] *= 0.85
    for y in range(H - 2):
        below = heat[y + 1]
        below2 = heat[min(H - 1, y + 2)]
        new = []
        for x in range(fx.cols):
            l, r = below[max(0, x - 1)], below[min(fx.cols - 1, x + 1)]
            v = (l + below[x] * 2 + r + below2[x]) / 5.0
            new.append(max(0.0, v - random.uniform(0.0, cooling * 1.6)))
        heat[y] = new


def frame(now):
    global acc, last
    dt = 0.0 if last is None else min(0.2, now - last)
    last = now
    for r, c in fx.key_presses():
        if fx.param("flare"):
            for x in range(max(0, c - 1), min(fx.cols, c + 2)):
                fuel[x] = min(0.8, fuel[x] + (0.6 if x == c else 0.3))
    acc += dt
    while acc >= STEP:
        simulate()
        acc -= STEP

    use_base = fx.param("use_base")
    for y in range(fx.rows):
        for x in range(fx.cols):
            h = min(1.0, heat[y][x] * 1.15)
            c = scale(fx.base(y, x, now), h ** 0.8) if use_base else fx.glow(gradient(FLAME, h))
            fx.set(y, x, c)


fx.run(frame)
