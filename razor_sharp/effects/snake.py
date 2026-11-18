"""Snake: a playable game on your keyboard lights. Steer with the arrow keys (or WASD).

Tip: click on the desktop first so your key presses don't type into another window.
The F-row shows your score. After a crash, press any key to play again.
"""

import random

from razor_fx import Effect, mix, scale

CATEGORY = "Games"
# Which Lighting settings this effect uses: "full", "colors" (just the two colours), or "none".
LIGHTING = {"param": "background", "on": "full", "off": "none"}

PARAMS = {
    "speed": {"type": "range", "label": "Speed (moves/s)", "min": 2, "max": 15, "default": 5, "step": 0.5},
    "snake_color": {"type": "color", "label": "Snake colour", "default": "#44d62c"},
    "food_color": {"type": "color", "label": "Food colour", "default": "#ff2d55"},
    "wrap": {"type": "bool", "label": "Wrap around the edges", "default": True},
    "background": {"type": "range", "label": "Background (%)", "min": 0, "max": 100, "default": 8, "step": 1},
}

fx = Effect(PARAMS)
# play field: the main block of keys, from the number row to the Shift row
_tl = fx.pos("GRAVE") or fx.pos("1") or (1, 0)
_br = fx.pos("BACKSPACE") or fx.pos("EQUAL") or (1, min(13, fx.cols - 1))
_bottom = fx.pos("Z") or fx.pos("LEFTSHIFT") or (4, 0)
TOP, BOTTOM = _tl[0], max(_tl[0] + 1, _bottom[0])
LEFT, RIGHT = _tl[1], max(_tl[1] + 3, _br[1])
FIELD = [(y, x) for y in range(TOP, BOTTOM + 1) for x in range(LEFT, RIGHT + 1)]
FOOD_CELLS = [c for c in FIELD if fx.is_key(*c)] or FIELD
F_KEYS = fx.positions([f"F{i}" for i in range(1, 13)])
DIRS = {"UP": (-1, 0), "W": (-1, 0), "DOWN": (1, 0), "S": (1, 0),
        "LEFT": (0, -1), "A": (0, -1), "RIGHT": (0, 1), "D": (0, 1)}

g = {}


def new_game(now):
    g.update(snake=[(2, 5), (2, 4), (2, 3)], dir=(0, 1), queue=[], alive=True,
             next_move=now + 0.5, died=None, score=0)
    place_food()
    print("New game. Arrow keys / WASD to steer.", flush=True)


def place_food():
    free = [c for c in FOOD_CELLS if c not in g["snake"]]
    g["food"] = random.choice(free) if free else None


def step():
    dy, dx = g["dir"]
    hy, hx = g["snake"][0]
    ny, nx = hy + dy, hx + dx
    if fx.param("wrap"):
        ny = TOP + (ny - TOP) % (BOTTOM - TOP + 1)
        nx = LEFT + (nx - LEFT) % (RIGHT - LEFT + 1)
    elif not (TOP <= ny <= BOTTOM and LEFT <= nx <= RIGHT):
        return False
    if (ny, nx) in g["snake"][:-1]:
        return False
    g["snake"].insert(0, (ny, nx))
    if (ny, nx) == g["food"]:
        g["score"] += 1
        place_food()
    else:
        g["snake"].pop()
    return True


def frame(now):
    if not g:
        new_game(now)
    for name, _r, _c in fx.key_events():
        if not g["alive"]:
            if now - g["died"] > 0.8:
                new_game(now)
            continue
        if name in DIRS:
            last = g["queue"][-1] if g["queue"] else g["dir"]
            d = DIRS[name]
            if d != last and d != (-last[0], -last[1]) and len(g["queue"]) < 2:
                g["queue"].append(d)

    if g["alive"] and now >= g["next_move"]:
        g["next_move"] = now + 1.0 / float(fx.param("speed"))
        if g["queue"]:
            g["dir"] = g["queue"].pop(0)
        if not step():
            g["alive"], g["died"] = False, now
            print(f"Game over! Score: {g['score']}  (press any key to play again)", flush=True)

    snake_c, food_c = fx.color("snake_color"), fx.color("food_color")
    bg = float(fx.param("background")) / 100.0
    body = {cell: i for i, cell in enumerate(g["snake"])}
    n = len(g["snake"])
    crash = (not g["alive"]) and (now - g["died"] < 1.0) and int((now - g["died"]) * 8) % 2 == 0
    score_lit = g["score"] % (len(F_KEYS) + 1)

    for y in range(fx.rows):
        for x in range(fx.cols):
            c = scale(fx.base(y, x, now), bg)
            if (y, x) in F_KEYS and F_KEYS.index((y, x)) < score_lit:
                c = fx.glow((255, 200, 0))
            if (y, x) in body:
                i = body[(y, x)]
                c = mix(fx.glow((255, 255, 255)), snake_c, 0.35) if i == 0 else scale(snake_c, 1.0 - 0.6 * i / max(1, n))
                if not g["alive"]:
                    c = fx.glow((255, 0, 0)) if crash else scale(c, 0.3)
            elif (y, x) == g["food"] and g["alive"]:
                c = scale(food_c, 0.6 + 0.4 * abs(((now * 2) % 2) - 1))
            fx.set(y, x, c)


fx.run(frame)
