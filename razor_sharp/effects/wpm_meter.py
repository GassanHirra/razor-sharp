"""WPM meter: the number row shows how fast you're typing, from calm green to blazing red.

Words per minute are counted over the last few seconds (5 key presses = 1 word).
"""

from razor_fx import Effect, add, mix, scale

CATEGORY = "Tools"

PARAMS = {
    "max_wpm": {"type": "range", "label": "WPM for a full bar", "min": 30, "max": 200, "default": 100, "step": 5},
    "window": {"type": "range", "label": "Measure over (s)", "min": 3, "max": 20, "default": 8, "step": 1},
    "low": {"type": "color", "label": "Slow colour", "default": "#00ff6a"},
    "high": {"type": "color", "label": "Fast colour", "default": "#ff0030"},
    "peak": {"type": "bool", "label": "Show your best speed", "default": True},
    "flash": {"type": "bool", "label": "Flash pressed keys", "default": True},
}

fx = Effect(PARAMS)
BAR = fx.positions(["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "MINUS", "EQUAL"]) or \
      fx.positions([f"F{i}" for i in range(1, 13)])
presses, flashes = [], {}
state = {"shown": 0.0, "best": 0.0, "best_at": 0.0, "last": None, "said": 0.0}


def frame(now):
    dt = 0.0 if state["last"] is None else min(0.2, now - state["last"])
    state["last"] = now
    for r, c in fx.key_presses():
        presses.append(now)
        flashes[(r, c)] = now
    window = float(fx.param("window"))
    presses[:] = [t for t in presses if now - t < window]
    span = max(1.5, min(window, now - presses[0])) if presses else window
    wpm = len(presses) / 5.0 * 60.0 / span if len(presses) > 2 else 0.0
    state["shown"] += (wpm - state["shown"]) * min(1.0, dt * 3)
    if state["shown"] > state["best"]:
        state["best"], state["best_at"] = state["shown"], now
    if now - state["said"] > 30 and wpm > 5:
        state["said"] = now
        print(f"Typing at {wpm:.0f} WPM (best {state['best']:.0f})", flush=True)

    top = float(fx.param("max_wpm"))
    level = min(1.0, state["shown"] / top) * len(BAR)
    best_i = min(len(BAR) - 1, int(state["best"] / top * len(BAR))) if fx.param("peak") and state["best"] > 5 else -1
    low, high = fx.color("low"), fx.color("high")
    bar = {}
    for i, cell in enumerate(BAR):
        fill = max(0.0, min(1.0, level - i))
        seg = mix(low, high, i / max(1, len(BAR) - 1))
        c = mix(scale(seg, 0.08), seg, fill)
        if i == best_i and fill < 0.5:
            c = fx.glow((200, 200, 200))
        bar[cell] = c
    for y in range(fx.rows):
        for x in range(fx.cols):
            c = bar.get((y, x)) or fx.base(y, x, now)
            t = flashes.get((y, x))
            if t is not None and fx.param("flash") and (y, x) not in bar:
                c = add(c, fx.glow((255, 255, 255)), max(0.0, 1.0 - (now - t) / 0.25) * 0.7)
            fx.set(y, x, c)
    for k, t in list(flashes.items()):
        if now - t > 0.3:
            del flashes[k]


fx.run(frame, fps=30)
