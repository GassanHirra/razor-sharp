"""Breakout: bounce the ball to smash the bricks. Move the paddle with ← → (or A / D).

Tip: click on the desktop first so your key presses don't type into another window.
Bricks are the top rows, the paddle lives on the Shift row. Press any key after a game to play again.
"""

import math
import random

from razor_fx import Effect, add, hsv, mix, scale

CATEGORY = "Games"
LIGHTING = {"param": "background", "on": "full", "off": "none"}

PARAMS = {
    "speed": {"type": "range", "label": "Ball speed", "min": 2, "max": 12, "default": 5, "step": 0.5},
    "paddle": {"type": "range", "label": "Paddle width", "min": 2, "max": 6, "default": 3, "step": 1},
    "lives": {"type": "range", "label": "Lives", "min": 1, "max": 9, "default": 3, "step": 1},
    "ball_color": {"type": "color", "label": "Ball colour", "default": "#ffffff"},
    "paddle_color": {"type": "color", "label": "Paddle colour", "default": "#00e5ff"},
    "background": {"type": "range", "label": "Lighting colours behind (%)", "min": 0, "max": 100, "default": 6, "step": 1},
}

fx = Effect(PARAMS)
_tl = fx.pos("GRAVE") or fx.pos("1") or (1, 0)
_br = fx.pos("BACKSPACE") or fx.pos("EQUAL") or (1, min(13, fx.cols - 1))
_pad = fx.pos("Z") or fx.pos("LEFTSHIFT") or (4, 0)
TOP, PADDLE_ROW = 0, _pad[0]
LEFT, RIGHT = _tl[1], max(_tl[1] + 5, _br[1])
BRICK_ROWS = [r for r in (0, 1) if r < PADDLE_ROW - 1]
MOVES = {"LEFT": -1, "A": -1, "RIGHT": 1, "D": 1}
g = {}


def cell(v):
    """Nearest key column/row (always rounds .5 up, unlike round())."""
    return int(math.floor(v + 0.5))


def new_game(now):
    g.update(lives=int(fx.param("lives")), score=0, over=None, won=None)
    g["bricks"] = {(r, c): hsv(r * 0.12 + c * 0.03) for r in BRICK_ROWS for c in range(LEFT, RIGHT + 1)
                   if fx.is_key(r, c)}
    g["paddle"] = float((LEFT + RIGHT) // 2)
    serve(now)
    print("Breakout! ← → to move.", flush=True)


def serve(now):
    a = random.uniform(-0.6, 0.6) - math.pi / 2
    g.update(bx=g["paddle"], by=PADDLE_ROW - 1.0, vx=math.cos(a), vy=math.sin(a), wait=now + 0.8)


def frame(now):
    if not g:
        new_game(now)
        g["last"] = now
    dt = min(0.05, now - g["last"])
    g["last"] = now
    width = int(fx.param("paddle"))
    for name, _r, _c in fx.key_events(repeats=True):
        if g["over"] or g["won"]:
            if now - (g["over"] or g["won"]) > 1.0:
                new_game(now)
            continue
        if name in MOVES:
            g["paddle"] = max(LEFT + (width - 1) / 2, min(RIGHT - (width - 1) / 2, g["paddle"] + MOVES[name]))
            if width % 2 == 1:
                g["paddle"] = float(cell(g["paddle"]))

    if not g["over"] and not g["won"] and now >= g["wait"]:
        sp = float(fx.param("speed"))
        steps = max(1, int(sp * dt / 0.2) + 1)
        for _ in range(steps):
            nx, ny = g["bx"] + g["vx"] * sp * dt / steps, g["by"] + g["vy"] * sp * dt / steps
            if nx < LEFT - 0.4 or nx > RIGHT + 0.4:
                g["vx"] = -g["vx"]
                nx = max(LEFT - 0.4, min(RIGHT + 0.4, nx))
            if ny < TOP - 0.4:
                g["vy"] = abs(g["vy"])
                ny = TOP - 0.4
            hit = (cell(ny), cell(nx))
            if hit in g["bricks"]:
                del g["bricks"][hit]
                g["score"] += 1
                g["vy"] = -g["vy"]
                if not g["bricks"]:
                    g["won"] = now
                    print(f"You won! Score {g['score']}. Press any key to play again.", flush=True)
            if g["vy"] > 0 and PADDLE_ROW - 0.6 <= ny <= PADDLE_ROW - 0.2 and abs(nx - g["paddle"]) <= width / 2 + 0.3:
                off = (nx - g["paddle"]) / (width / 2 + 0.3)            # where it hit the paddle: -1 .. 1
                a = -math.pi / 2 + off * 1.0
                g["vx"], g["vy"] = math.cos(a), math.sin(a)
            if ny > PADDLE_ROW + 0.6:
                g["lives"] -= 1
                if g["lives"] <= 0:
                    g["over"] = now
                    print(f"Game over. Score {g['score']}. Press any key to play again.", flush=True)
                else:
                    serve(now)
                break
            g["bx"], g["by"] = nx, ny

    bg = float(fx.param("background")) / 100.0
    ball, pad_col = fx.color("ball_color"), fx.color("paddle_color")
    half = (width - 1) / 2.0
    pad_cells = {cell(g["paddle"] - half + i) for i in range(width)}
    for y in range(fx.rows):
        for x in range(fx.cols):
            c = scale(fx.base(y, x, now), bg)
            if (y, x) in g["bricks"]:
                c = fx.glow(g["bricks"][(y, x)])
            if y == PADDLE_ROW and x in pad_cells:
                c = pad_col
            if g["over"]:
                c = mix(c, fx.glow((255, 0, 0)), 0.5 + 0.5 * math.sin((now - g["over"]) * 10)) if (y, x) in pad_cells or y == PADDLE_ROW else c
            elif g["won"]:
                c = fx.glow(hsv(x * 0.06 + y * 0.1 - now * 0.6))
            elif cell(g["by"]) == y and cell(g["bx"]) == x:
                c = ball
            if y == PADDLE_ROW + 1 and LEFT <= x < LEFT + g.get("lives", 0):
                c = add(c, fx.glow((255, 40, 60)), 0.8)      # lives shown below the paddle
            fx.set(y, x, c)


fx.run(frame)
