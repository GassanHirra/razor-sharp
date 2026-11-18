"""Plasma: smooth, slowly morphing blobs of colour, like a lava lamp."""

import math

from razor_fx import Effect, hsv, mix

CATEGORY = "Ambient"
# Whether the "Effect brightness" slider applies (this effect only uses the lighting colours otherwise).
EFFECT_BRIGHTNESS = {"param": "use_base", "is": False}
# Which Lighting settings this effect uses: "full", "colors" (just the two colours), or "none".
LIGHTING = {"param": "use_base", "on": "colors", "off": "none"}

PARAMS = {
    "use_base": {"type": "bool", "label": "Use the two lighting colours", "default": False},
    "speed": {"type": "range", "label": "Speed", "min": 0.1, "max": 3, "default": 0.8, "step": 0.1},
    "zoom": {"type": "range", "label": "Blob size", "min": 0.3, "max": 3, "default": 1.2, "step": 0.1},
    "saturation": {"type": "range", "label": "Saturation (%)", "min": 0, "max": 100, "default": 100, "step": 1, "show_if": {"param": "use_base", "is": False}},
}

fx = Effect(PARAMS)


def frame(now):
    t = now * float(fx.param("speed"))
    s = 0.6 / float(fx.param("zoom"))
    sat = float(fx.param("saturation")) / 100.0
    use_base = fx.param("use_base")
    a, b = fx.light_colors()
    cx, cy = 8 + math.sin(t / 5) * 6, 2.5 + math.cos(t / 3) * 2.5
    for y in range(fx.rows):
        for x in range(fx.cols):
            yy = y * 1.6
            v = (math.sin(x * s + t)
                 + math.sin((yy * s + t) / 2)
                 + math.sin((x * s + yy * s + t) / 2)
                 + math.sin(math.hypot(x - cx, yy - cy * 1.6) * s + t))
            u = (v + 4) / 8  # 0..1
            if use_base:
                c = mix(a, b, 0.5 + 0.5 * math.sin(u * math.pi * 3 + t * 0.3))
            else:
                c = fx.glow(hsv(u + t * 0.03, sat))
            fx.set(y, x, c)


fx.run(frame)
