"""Pomodoro timer: the F-keys count down your focus/break time and the keyboard pulses when it's up.

Pause/Break key = pause or resume.  Scroll Lock = skip to the next phase.
"""

import math

from razor_fx import Effect, mix, scale

CATEGORY = "Tools"
# Which Lighting settings this effect uses: "full", "colors" (just the two colours), or "none".
LIGHTING = {"param": "dim", "on": "full", "off": "none"}

PARAMS = {
    "work_min": {"type": "range", "label": "Focus (minutes)", "min": 1, "max": 90, "default": 25, "step": 1},
    "break_min": {"type": "range", "label": "Break (minutes)", "min": 1, "max": 30, "default": 5, "step": 1},
    "work_color": {"type": "color", "label": "Focus colour", "default": "#ff3b30"},
    "break_color": {"type": "color", "label": "Break colour", "default": "#34c759"},
    "dim": {"type": "range", "label": "Other keys brightness (%)", "min": 0, "max": 100, "default": 40, "step": 1},
}

fx = Effect(PARAMS)
F_KEYS = fx.positions([f"F{i}" for i in range(1, 13)]) or fx.positions(["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "MINUS", "EQUAL"])  # number row if no F-keys
HINTS = set(fx.positions(["PAUSE", "SCROLLLOCK"]))
ALARM = 4.0

state = {"phase": "work", "elapsed": 0.0, "paused": False, "alarm": None, "last": None}
print("Focus started. Pause/Break = pause/resume, Scroll Lock = skip.", flush=True)


def switch(now):
    state["phase"] = "break" if state["phase"] == "work" else "work"
    state["elapsed"] = 0.0
    state["alarm"] = None
    print(("Break time!" if state["phase"] == "break" else "Back to focus."), flush=True)


def frame(now):
    dt = 0.0 if state["last"] is None else now - state["last"]
    state["last"] = now
    for name, _r, _c in fx.key_events():
        if name == "PAUSE":
            state["paused"] = not state["paused"]
            print("Paused." if state["paused"] else "Resumed.", flush=True)
        elif name == "SCROLLLOCK":
            switch(now)

    work = state["phase"] == "work"
    duration = float(fx.param("work_min" if work else "break_min")) * 60.0
    color = fx.color("work_color" if work else "break_color")

    if state["alarm"] is not None:
        if now - state["alarm"] >= ALARM:
            switch(now)
            return
        k = 0.5 + 0.5 * math.sin((now - state["alarm"]) * 8)
        for y in range(fx.rows):
            for x in range(fx.cols):
                fx.set(y, x, scale(color, 0.15 + 0.85 * k))
        return

    if not state["paused"]:
        state["elapsed"] += dt
    if state["elapsed"] >= duration:
        state["alarm"] = now
        return

    remaining = max(0.0, 1.0 - state["elapsed"] / duration)
    lit = remaining * len(F_KEYS)
    blink = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(now * 3)) if state["paused"] else 1.0
    dim = float(fx.param("dim")) / 100.0
    for y in range(fx.rows):
        for x in range(fx.cols):
            if (y, x) in F_KEYS:
                fill = max(0.0, min(1.0, lit - F_KEYS.index((y, x))))
                c = scale(mix(fx.glow((10, 10, 10)), color, fill), blink)
            elif (y, x) in HINTS:
                c = fx.glow((90, 90, 90))
            else:
                c = scale(fx.base(y, x, now), dim)
            fx.set(y, x, c)


fx.run(frame, fps=30)
