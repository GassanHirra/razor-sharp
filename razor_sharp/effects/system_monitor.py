"""System monitor: CPU on the number row, RAM on the QWERTY row, temperature on the home row.

The legend keys (` for CPU, Tab for RAM, Caps Lock for temperature) stay white.
"""

import glob

from razor_fx import Effect, mix

CATEGORY = "Tools"

PARAMS = {
    "low": {"type": "color", "label": "Low colour", "default": "#00ff6a"},
    "high": {"type": "color", "label": "High colour", "default": "#ff0030"},
    "show_temp": {"type": "bool", "label": "Show temperature", "default": True},
    "max_temp": {"type": "range", "label": "Temperature for full bar (°C)", "min": 60, "max": 105, "default": 90, "step": 1, "show_if": {"param": "show_temp", "is": True}},
    "tint": {"type": "bool", "label": "Tint other keys by CPU load", "default": True},
}

fx = Effect(PARAMS)
CPU_KEYS = fx.positions(("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "MINUS", "EQUAL"))
RAM_KEYS = fx.positions(("Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "LEFTBRACE", "RIGHTBRACE"))
TEMP_KEYS = fx.positions(("A", "S", "D", "F", "G", "H", "J", "K", "L", "SEMICOLON", "APOSTROPHE"))
LEGEND = set(fx.positions(["GRAVE", "TAB", "CAPSLOCK"]))

prev_cpu = None
values = {"cpu": 0.0, "ram": 0.0, "temp": 0.0}
shown = dict(values)
next_sample = 0.0


def read_cpu():
    global prev_cpu
    with open("/proc/stat") as f:
        parts = [int(v) for v in f.readline().split()[1:]]
    idle, total = parts[3] + parts[4], sum(parts)
    load = 0.0
    if prev_cpu:
        dt, di = total - prev_cpu[1], idle - prev_cpu[0]
        load = 1.0 - di / dt if dt > 0 else 0.0
    prev_cpu = (idle, total)
    return max(0.0, min(1.0, load))


def read_ram():
    info = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":")
            info[k] = int(v.split()[0])
    return 1.0 - info.get("MemAvailable", 0) / info["MemTotal"]


def read_temp():
    best, preferred = 0.0, 0.0
    for zone in glob.glob("/sys/class/thermal/thermal_zone*"):
        try:
            t = int(open(zone + "/temp").read()) / 1000.0
            kind = open(zone + "/type").read().strip().lower()
        except (OSError, ValueError):
            continue
        best = max(best, t)
        if any(k in kind for k in ("x86_pkg", "cpu", "k10temp", "coretemp", "tctl")):
            preferred = max(preferred, t)
    for f in glob.glob("/sys/class/hwmon/hwmon*/temp1_input"):
        try:
            name = open(f.rsplit("/", 1)[0] + "/name").read().strip()
            if name in ("coretemp", "k10temp", "zenpower"):
                preferred = max(preferred, int(open(f).read()) / 1000.0)
        except (OSError, ValueError):
            pass
    return preferred or best


def draw_bar(cells, level, low, high, out):
    n = len(cells)
    for i, cell in enumerate(cells):
        fill = max(0.0, min(1.0, level * n - i))
        out[cell] = mix(mix(low, (0, 0, 0), 0.92), mix(low, high, i / max(1, n - 1)), fill)


def frame(now):
    global next_sample
    if now >= next_sample:
        next_sample = now + 0.5
        values["cpu"] = read_cpu()
        values["ram"] = read_ram()
        values["temp"] = read_temp()
    for k in shown:
        shown[k] += (values[k] - shown[k]) * 0.15

    low, high = fx.color("low"), fx.color("high")
    out = {}
    draw_bar(CPU_KEYS, shown["cpu"], low, high, out)
    draw_bar(RAM_KEYS, shown["ram"], low, high, out)
    if fx.param("show_temp"):
        t = (shown["temp"] - 30.0) / max(1.0, float(fx.param("max_temp")) - 30.0)
        draw_bar(TEMP_KEYS, max(0.0, min(1.0, t)), low, high, out)
    tint = shown["cpu"] * 0.6 if fx.param("tint") else 0.0

    for y in range(fx.rows):
        for x in range(fx.cols):
            if (y, x) in LEGEND:
                c = fx.glow((200, 200, 200))
            elif (y, x) in out:
                c = out[(y, x)]
            else:
                c = mix(fx.base(y, x, now), high, tint)
            fx.set(y, x, c)


fx.run(frame, fps=30)
