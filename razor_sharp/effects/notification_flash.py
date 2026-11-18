"""Notification flash: a ripple and flash whenever a desktop notification arrives.

Test it with:  notify-send "Hello"
"""

import math
import shutil
import subprocess
import threading
import time

from razor_fx import Effect, mix

CATEGORY = "Tools"

PARAMS = {
    "color": {"type": "color", "label": "Flash colour", "default": "#ffd60a"},
    "ripple": {"type": "bool", "label": "Ripple from the centre", "default": True},
    "flashes": {"type": "range", "label": "Number of flashes", "min": 1, "max": 5, "default": 2, "step": 1},
    "duration": {"type": "range", "label": "Length (s)", "min": 0.3, "max": 4, "default": 1.4, "step": 0.1},
}

if not shutil.which("dbus-monitor"):
    raise SystemExit("This effect needs dbus-monitor:  sudo apt install dbus-bin")

fx = Effect(PARAMS)
events = []


def listen():
    proc = subprocess.Popen(
        ["dbus-monitor", "--session", "interface='org.freedesktop.Notifications',member='Notify'"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    print("Waiting for notifications…  (test: notify-send Hello)", flush=True)
    for line in proc.stdout:
        if "member=Notify" in line and "method call" in line:
            events.append(time.monotonic())


threading.Thread(target=listen, daemon=True).start()
CY, CX = (fx.bounds[0] + fx.bounds[1]) / 2.0, (fx.bounds[2] + fx.bounds[3]) / 2.0


def frame(now):
    dur = float(fx.param("duration"))
    events[:] = [t for t in events if now - t < dur]
    color = fx.color("color")
    n = int(fx.param("flashes"))
    ripple = fx.param("ripple")
    for y in range(fx.rows):
        for x in range(fx.cols):
            k = 0.0
            for t in events:
                p = (now - t) / dur
                flash = max(0.0, math.sin(math.pi * n * p)) * (1.0 - p) * 0.7
                ring = 0.0
                if ripple:
                    d = math.hypot((y - CY) * 1.6, x - CX)
                    ring = math.exp(-((d - p * 14) / 1.5) ** 2) * (1.0 - p)
                k = max(k, flash, ring)
            fx.set(y, x, mix(fx.base(y, x, now), color, k))


fx.run(frame, fps=30)
