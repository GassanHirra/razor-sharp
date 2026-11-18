"""Game of Life: Conway's cellular automaton lives on your keys; typing seeds new life where you press.

Newborn cells flash bright, dying ones fade. The board reseeds itself if life dies out or stops changing.
"""

import random

from razor_fx import Effect, add, hsv, mix, scale

CATEGORY = "Ambient"
# Which Lighting settings this effect uses: "full", "colors" (just the two colours), or "none".
LIGHTING = {"param": "use_base", "on": "full", "off": "none"}

PARAMS = {
    "use_base": {"type": "bool", "label": "Cells in lighting colours", "default": False},
    "cell_color": {"type": "color", "label": "Cell colour", "default": "#00ff9c",
                   "show_if": {"param": "use_base", "is": False}},
    "rainbow": {"type": "bool", "label": "Colour by age", "default": True,
                "show_if": {"param": "use_base", "is": False}},
    "speed": {"type": "range", "label": "Generations per second", "min": 1, "max": 15, "default": 5, "step": 1},
    "fade": {"type": "range", "label": "Fade (s)", "min": 0.1, "max": 2, "default": 0.5, "step": 0.1},
    "density": {"type": "range", "label": "Starting life (%)", "min": 10, "max": 60, "default": 35, "step": 5},
}

fx = Effect(PARAMS)
R0, R1, C0, C1 = fx.bounds
cells = [(y, x) for y in range(R0, R1 + 1) for x in range(C0, C1 + 1)]
alive, age, born_at, died_at = set(), {}, {}, {}
state = {"next": 0.0, "history": [], "last": None}


def seed(now, density=None):
    d = (float(fx.param("density")) if density is None else density) / 100.0
    for c in cells:
        if random.random() < d and c not in alive:
            alive.add(c)
            age[c] = 0
            born_at[c] = now


def step(now):
    h, w = R1 - R0 + 1, C1 - C0 + 1
    counts = {}
    for (y, x) in alive:
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy or dx:
                    n = (R0 + (y - R0 + dy) % h, C0 + (x - C0 + dx) % w)
                    counts[n] = counts.get(n, 0) + 1
    new = {c for c, n in counts.items() if n == 3 or (n == 2 and c in alive)}
    for c in alive - new:
        died_at[c] = now
        age.pop(c, None)
    for c in new - alive:
        born_at[c] = now
        age[c] = 0
    for c in new & alive:
        age[c] = age.get(c, 0) + 1
    alive.clear()
    alive.update(new)
    key = frozenset(alive)
    hist = state["history"]
    hist.append(key)
    del hist[:-6]
    if len(alive) < 3 or hist.count(key) > 2:      # died out or stuck in a loop
        seed(now, 30)
        hist.clear()


def frame(now):
    if state["last"] is None:
        seed(now)
    state["last"] = now
    for r, c in fx.key_presses():
        for dy, dx in random.choice([[(0, 0), (0, 1), (0, -1)], [(0, 0), (1, 0), (-1, 0), (0, 1)],
                                     [(-1, 0), (0, 1), (1, -1), (1, 0), (1, 1)]]):
            cell = (min(R1, max(R0, r + dy)), min(C1, max(C0, c + dx)))
            if cell not in alive:
                alive.add(cell)
                age[cell] = 0
                born_at[cell] = now
    if now >= state["next"]:
        state["next"] = now + 1.0 / float(fx.param("speed"))
        step(now)

    fade = max(0.05, float(fx.param("fade")))
    use_base, rainbow = fx.param("use_base"), fx.param("rainbow")
    own = fx.color("cell_color")
    for y in range(fx.rows):
        for x in range(fx.cols):
            c = (y, x)
            if c in alive:
                if use_base:
                    col = fx.base(y, x, now)
                elif rainbow:
                    col = fx.glow(hsv(0.45 - min(age.get(c, 0), 20) * 0.02, 0.9))
                else:
                    col = own
                flash = max(0.0, 1.0 - (now - born_at.get(c, -9)) / 0.25)
                col = add(col, fx.glow((255, 255, 255)), flash * 0.6)
            else:
                k = max(0.0, 1.0 - (now - died_at.get(c, -99)) / fade)
                col = scale(fx.base(y, x, now) if use_base else own, k * 0.5)
            fx.set(y, x, col)


fx.run(frame)
