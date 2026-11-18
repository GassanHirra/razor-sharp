"""Ocean waves: layered waves roll across the keyboard with white foam on the crests; typing makes splashes."""

import math

from razor_fx import Effect, mix, scale

CATEGORY = "Ambient"
# Which Lighting settings this effect uses: "full", "colors" (just the two colours), or "none".
LIGHTING = {"param": "sky_base", "on": "full", "off": "none"}

PARAMS = {
    "deep": {"type": "color", "label": "Deep water", "default": "#001a66"},
    "shallow": {"type": "color", "label": "Shallow water", "default": "#00b4d8"},
    "foam": {"type": "color", "label": "Foam", "default": "#ffffff"},
    "sky_base": {"type": "bool", "label": "Lighting colours above the water", "default": True},
    "level": {"type": "range", "label": "Water level (rows from top)", "min": 0, "max": 5, "default": 2.0, "step": 0.1},
    "wave_height": {"type": "range", "label": "Wave height", "min": 0, "max": 3, "default": 1.0, "step": 0.1},
    "speed": {"type": "range", "label": "Speed", "min": 0.2, "max": 3, "default": 1.0, "step": 0.1},
}

fx = Effect(PARAMS)
splashes = []  # (time, col)


def surface(x, t, now):
    sp = float(fx.param("speed"))
    h = float(fx.param("wave_height"))
    s = (float(fx.param("level"))
         + h * (0.6 * math.sin(0.55 * x - 1.4 * t * sp)
                + 0.3 * math.sin(1.3 * x + 0.9 * t * sp)
                + 0.15 * math.sin(2.1 * x - 2.3 * t * sp)))
    for start, c in splashes:
        age = now - start
        d = abs(x - c)
        s -= 1.4 * math.exp(-age * 1.8) * math.cos(d * 1.3 - age * 7) * math.exp(-d * 0.25)
    return s


def frame(now):
    for r, c in fx.key_presses():
        splashes.append((now, c))
    splashes[:] = [s for s in splashes if now - s[0] < 3.0]

    deep, shallow, foam = fx.color("deep"), fx.color("shallow"), fx.color("foam")
    sky_base = fx.param("sky_base")
    for x in range(fx.cols):
        surf = surface(x, now, now)
        for y in range(fx.rows):
            d = y - surf
            if d < -0.5:
                c = scale(fx.base(y, x, now), 0.35) if sky_base else (0, 0, 0)
            elif d < 0.5:
                c = mix(shallow, foam, (1.0 - abs(d) * 2) * 0.9)
            else:
                c = mix(shallow, deep, min(1.0, (d - 0.5) / 3.0))
                c = scale(c, 1.0 + 0.12 * math.sin(x * 1.7 + y * 1.1 + now * 3))
            fx.set(y, x, c)


fx.run(frame)
