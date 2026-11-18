"""Lighting only: shows the colours chosen in the app (solid, gradient, rainbow, breathing) with no key reaction."""

from razor_fx import Effect

CATEGORY = "Ambient"
# Whether the "Effect brightness" slider applies (this effect only uses the lighting colours otherwise).
EFFECT_BRIGHTNESS = False

fx = Effect()


def frame(now):
    for y in range(fx.rows):
        for x in range(fx.cols):
            fx.set(y, x, fx.base(y, x, now))


fx.run(frame)
