#!/usr/bin/env python3
"""
Razor Sharp - lighting effects for Razer keyboards on Linux (via OpenRazer).

Pick an effect, choose colours (solid, gradient, rainbow, breathing...), tweak its
options and start it. Effects keep running after the window is closed.
Add your own effects as small Python scripts.

Copyright (C) 2026 Gassan. Licensed under the GNU GPL v3 or later.
"""

__version__ = "0.2.0"

import ast
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk
from tkinter import font as tkfont

APP_DIR = Path(__file__).resolve().parent
LIB_DIR = APP_DIR / "lib"
sys.path.insert(0, str(LIB_DIR))
import razor_fx as rfx  # noqa: E402

APP_NAME = "Razor Sharp"
APP_ID = "razor-sharp"
HOMEPAGE = "https://github.com/GassanHirra/razor-sharp"
ICON_DIR = APP_DIR / "icons"
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_ID
BUILTIN_EFFECTS = APP_DIR / "effects"     # shipped with the app (read-only when installed)
USER_EFFECTS = DATA_DIR / "effects"       # effects you add
SETTINGS_DIR = DATA_DIR / "settings"
PRESETS_FILE = DATA_DIR / "presets.json"
STATE_FILE = DATA_DIR / "last_effect"
RUN_FILE = DATA_DIR / "running.json"     # the effect running in the background (pid + name)
EFFECT_LOG = DATA_DIR / "effect.log"     # its output
AUTOSTART_FILE = Path.home() / ".config" / "autostart" / "razor-sharp.desktop"
OLD_DIR = Path.home() / ".local" / "share" / "razer-effects"   # the pre-release "Razer Effects" install

# ---------------------------------------------------------------- theme
BG = "#121212"        # window
CARD = "#1c1c1c"      # panels
INPUT = "#2a2a2a"     # inputs / buttons
HOVER = "#343434"
TRACK = "#333333"
BORDER = "#2c2c2c"
FG = "#ececec"
MUTED = "#8d8d8d"
FAINT = "#5c5c5c"
ACCENT = "#44d62c"
ACCENT_HOVER = "#62e84d"
DANGER = "#ff5f57"
FONTS = {}

MODES = [("solid", "Solid colour"), ("gradient", "Gradient"), ("rainbow", "Rainbow"),
         ("spectrum", "Spectrum cycle"), ("breathing", "Breathing")]
DIRECTIONS = [("horizontal", "Left → Right"), ("vertical", "Top → Bottom"),
              ("diagonal", "Diagonal"), ("center", "From centre")]
CATEGORY_ORDER = ["Reactive", "Ambient", "Tools", "Games"]

BUILTIN_PRESETS = {
    "Razer Green": {"mode": "solid", "color_a": "#44d62c"},
    "Ocean": {"mode": "gradient", "color_a": "#00e5ff", "color_b": "#0033ff", "direction": "horizontal", "animate": False},
    "Sunset": {"mode": "gradient", "color_a": "#ff8a00", "color_b": "#e0007a", "direction": "horizontal", "animate": False},
    "Cyberpunk": {"mode": "gradient", "color_a": "#00f0ff", "color_b": "#ff00c8", "direction": "diagonal", "animate": True, "anim_speed": 0.8},
    "Fire": {"mode": "gradient", "color_a": "#ffc400", "color_b": "#ff1a00", "direction": "vertical", "reverse": True, "animate": True, "anim_speed": 1.5},
    "Ice": {"mode": "gradient", "color_a": "#ffffff", "color_b": "#00a2ff", "direction": "center", "animate": False},
    "Aurora": {"mode": "gradient", "color_a": "#00ff87", "color_b": "#7a00ff", "direction": "horizontal", "animate": True, "anim_speed": 0.6},
    "Rainbow wave": {"mode": "rainbow", "direction": "horizontal", "animate": True, "anim_speed": 1.0},
    "Calm breathing": {"mode": "breathing", "color_a": "#0050ff", "color_b": "#000818", "anim_speed": 0.6},
}


# ---------------------------------------------------------------- background effect process
# Effects run as their own detached process, so they keep going when the window is closed.

def settings_path(name):
    return SETTINGS_DIR / (Path(name).stem + ".json")


def effect_path(name):
    """Your own copy of an effect wins over the built-in one with the same file name."""
    user = USER_EFFECTS / name
    return user if user.exists() else BUILTIN_EFFECTS / name


def all_effects():
    found = {p.name: p for p in BUILTIN_EFFECTS.glob("*.py")}
    found.update({p.name: p for p in USER_EFFECTS.glob("*.py")})
    return sorted(found.values(), key=lambda p: p.name.lower())


def is_builtin(name):
    return (BUILTIN_EFFECTS / name).exists() and not (USER_EFFECTS / name).exists()


def last_effect():
    try:
        name = STATE_FILE.read_text().strip()
        return name if effect_path(name).exists() else None
    except OSError:
        return None


def autostart_command():
    if shutil.which(APP_ID):
        return f"{APP_ID} --run-last"
    return f"{sys.executable} {APP_DIR / 'razor_sharp.py'} --run-last"


def write_autostart(on):
    if on:
        AUTOSTART_FILE.parent.mkdir(parents=True, exist_ok=True)
        AUTOSTART_FILE.write_text(
            f"[Desktop Entry]\nType=Application\nName={APP_NAME}\nIcon={APP_ID}\n"
            f"Comment=Start the last Razor Sharp effect\nExec={autostart_command()}\n"
            "X-GNOME-Autostart-enabled=true\nX-GNOME-Autostart-Delay=5\nNoDisplay=true\n")
    else:
        AUTOSTART_FILE.unlink(missing_ok=True)


def input_access():
    """'ok' if effects can read key presses, 'relogin' if added to the input group but not active yet, else 'no'."""
    try:
        import grp
        import pwd
        group = grp.getgrnam("input")
    except (KeyError, ImportError):
        return "ok"
    if os.geteuid() == 0 or group.gr_gid in os.getgroups():
        return "ok"
    user = pwd.getpwuid(os.getuid()).pw_name
    return "relogin" if user in group.gr_mem else "no"


def migrate_old_install():
    """Bring settings, presets and your own effects over from the pre-release "Razer Effects"."""
    marker = DATA_DIR / ".migrated"
    if not OLD_DIR.exists() or marker.exists():
        return []
    notes = []
    for d in (DATA_DIR, SETTINGS_DIR, USER_EFFECTS):
        d.mkdir(parents=True, exist_ok=True)
    try:  # stop an effect the old app left running
        old = json.loads((OLD_DIR / "running.json").read_text())
        if pid_alive(int(old["pid"]), old["name"]):
            os.killpg(int(old["pid"]), signal.SIGINT)
            notes.append(f"Stopped {pretty(old['name'])} (started by the old Razer Effects app).")
    except (OSError, ValueError, KeyError, ProcessLookupError, PermissionError):
        pass
    for f in (OLD_DIR / "settings").glob("*.json"):
        if not (SETTINGS_DIR / f.name).exists():
            shutil.copy2(f, SETTINGS_DIR / f.name)
    for name in ("presets.json", "last_effect"):
        if (OLD_DIR / name).exists() and not (DATA_DIR / name).exists():
            shutil.copy2(OLD_DIR / name, DATA_DIR / name)
    mine = [f for f in (OLD_DIR / "effects").glob("*.py") if not (BUILTIN_EFFECTS / f.name).exists()]
    for f in mine:
        text = f.read_text(encoding="utf-8", errors="replace")
        (USER_EFFECTS / f.name).write_text(text.replace("from razer_fx import", "from razor_fx import"))
    if mine:
        notes.append(f"Copied your own effects: {', '.join(pretty(f.name) for f in mine)}.")
    old_auto = Path.home() / ".config" / "autostart" / "razer-effects.desktop"
    if old_auto.exists():
        old_auto.unlink()
        write_autostart(True)
        notes.append("Moved “run last effect at login” over.")
    (Path.home() / ".local" / "share" / "applications" / "razer-effects.desktop").unlink(missing_ok=True)
    marker.write_text(time.strftime("%Y-%m-%d %H:%M"))
    notes.insert(0, "Brought your settings over from Razer Effects. You can delete ~/.local/share/razer-effects.")
    return notes


def notify(text):
    """A quiet desktop notification (used by the keyboard shortcuts)."""
    try:
        subprocess.Popen(["notify-send", "-a", APP_NAME, "-i", APP_ID, "-t", "1500",
                          "-h", "string:x-canonical-private-synchronous:razor-sharp", APP_NAME, text],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def detect_keyboard():
    """(name, rows, cols) of the connected OpenRazer keyboard, or None."""
    try:
        kb = rfx.find_keyboard()
        if kb is not None:
            return kb.name, kb.fx.advanced.rows, kb.fx.advanced.cols
    except Exception:
        pass
    return None


def pid_alive(pid, name=None):
    """True if the process exists, isn't a zombie, and (if given) is running that effect."""
    try:
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="ignore")
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1][:1]
    except (OSError, IndexError):
        return False
    if state == "Z":
        return False
    return name in cmd if name else True


def running_effect():
    """{"pid", "name"} of the effect running in the background, or None."""
    try:
        data = json.loads(RUN_FILE.read_text())
        if pid_alive(int(data["pid"]), data["name"]):
            return data
    except (OSError, ValueError, KeyError, TypeError):
        pass
    RUN_FILE.unlink(missing_ok=True)
    return None


def stop_effect(proc=None):
    """Stop the background effect (like Ctrl+C, so it can tidy up the lighting). Returns its name."""
    data = running_effect()
    if not data:
        if proc is not None:
            proc.poll()
        return None
    pid = int(data["pid"])
    try:
        os.killpg(pid, signal.SIGINT)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            break
        if not pid_alive(pid):
            break
        time.sleep(0.05)
    else:
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if proc is not None:
        proc.poll()
    RUN_FILE.unlink(missing_ok=True)
    return data["name"]


def launch_effect(name, remember=True):
    """Start an effect in the background (stopping any running one). Returns the Popen.
    remember=False is used by app profiles, so your own choice stays the "last effect"."""
    stop_effect()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(LIB_DIR) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["RAZER_FX_CONFIG"] = str(settings_path(name))
    with open(EFFECT_LOG, "w") as log:
        proc = subprocess.Popen([sys.executable, "-u", str(effect_path(name))],
                                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                start_new_session=True, cwd=str(effect_path(name).parent), env=env)
    RUN_FILE.write_text(json.dumps({"pid": proc.pid, "name": name}))
    if remember:
        STATE_FILE.write_text(name)
    return proc


# ---------------------------------------------------------------- command line helpers


def effect_order():
    """Effect file names in the same order as the app's list."""
    groups = {}
    for p in all_effects():
        groups.setdefault(read_script_info(p)["category"], []).append(p.name)
    cats = CATEGORY_ORDER + sorted(c for c in groups if c not in CATEGORY_ORDER)
    return [n for c in cats for n in groups.get(c, [])]


def resolve_effect(text):
    """Find an effect by file name, stem or display name ("fire", "Matrix Rain", "matrix_rain.py")."""
    want = str(text).strip().lower().replace("-", " ").replace("_", " ")
    for name in effect_order():
        stem = Path(name).stem.lower().replace("_", " ")
        if want in (name.lower(), stem, pretty(name).lower()) or want + ".py" == name.lower():
            return name
    matches = [n for n in effect_order() if want in pretty(n).lower()]
    return matches[0] if len(matches) == 1 else None


def cycle_effect(step):
    order = effect_order()
    if not order:
        return None
    cur = (running_effect() or {}).get("name") or last_effect()
    i = order.index(cur) if cur in order else -1
    name = order[(i + step) % len(order)]
    launch_effect(name)
    return name


# ---------------------------------------------------------------- app profiles
WATCH_FILE = DATA_DIR / "watcher.json"
WATCH_LOG = DATA_DIR / "watcher.log"


def user_processes():
    """Lower-case names of programs running as you (process name and executable name)."""
    uid, names = os.getuid(), set()
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        try:
            if d.stat().st_uid != uid:
                continue
            names.add((d / "comm").read_text().strip().lower())
            argv0 = (d / "cmdline").read_bytes().split(b"\0", 1)[0].decode(errors="ignore")
            if argv0:
                names.add(os.path.basename(argv0).lower())
        except OSError:
            continue
    names.discard("")
    return names


def active_rule(rules, procs):
    for rule in rules:
        app = str(rule.get("app", "")).strip().lower()
        if app and rule.get("effect") and any(app in p for p in procs):
            return rule
    return None


def watcher_pid():
    try:
        pid = int(json.loads(WATCH_FILE.read_text())["pid"])
        if pid_alive(pid, "--watch"):
            return pid
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def start_watcher():
    if watcher_pid():
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(WATCH_LOG, "a") as log:
        proc = subprocess.Popen([sys.executable, "-u", str(APP_DIR / "razor_sharp.py"), "--watch"],
                                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                start_new_session=True)
    WATCH_FILE.write_text(json.dumps({"pid": proc.pid}))


def stop_watcher():
    pid = watcher_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    WATCH_FILE.unlink(missing_ok=True)


def run_watcher(interval=2.0, max_loops=None):
    """Background loop: switch effects while chosen apps are running, and switch back after."""
    WATCH_FILE.write_text(json.dumps({"pid": os.getpid()}))
    print(time.strftime("%H:%M:%S"), "App profiles watcher started.", flush=True)
    current, before, loops = None, None, 0
    while max_loops is None or loops < max_loops:
        loops += 1
        g = rfx.load_global()
        prof = g.get("profiles", {})
        if not prof.get("enabled"):
            print(time.strftime("%H:%M:%S"), "App profiles turned off; watcher stopping.", flush=True)
            break
        rule = active_rule(prof.get("rules", []), user_processes())
        running = (running_effect() or {}).get("name")
        new_key = (rule["app"], rule["effect"]) if rule else None
        old_key = (current["app"], current["effect"]) if current else None
        if new_key != old_key:
            if rule and effect_path(rule["effect"]).exists():
                if current is None:
                    before = running
                if running != rule["effect"]:
                    launch_effect(rule["effect"], remember=False)
                print(time.strftime("%H:%M:%S"), f"{rule['app']} is running: switched to {pretty(rule['effect'])}.", flush=True)
                current = rule
            elif current:
                if running == current["effect"]:   # you didn't change it yourself meanwhile
                    if before:
                        launch_effect(before, remember=False)
                    else:
                        stop_effect()
                    print(time.strftime("%H:%M:%S"), f"{current['app']} closed: back to "
                          f"{pretty(before) if before else 'no effect'}.", flush=True)
                else:
                    print(time.strftime("%H:%M:%S"), f"{current['app']} closed: keeping "
                          f"{pretty(running) if running else 'no effect'}, which you chose.", flush=True)
                current, before = None, None
        time.sleep(interval)
    WATCH_FILE.unlink(missing_ok=True)


# ---------------------------------------------------------------- helpers
_info_cache = {}


def read_script_info(path: Path):
    """dict(desc, params, uses_fx, category), parsed without running the script."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = None
    hit = _info_cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    info = {"desc": "No description.", "params": {}, "uses_fx": False, "category": "My effects",
            "lighting": "full", "effect_brightness": True}
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        info["uses_fx"] = "razor_fx" in text or "razer_fx" in text
        doc = ast.get_docstring(tree)
        if doc:
            first = next((l.strip() for l in doc.strip().splitlines() if l.strip()), "")
            if ": " in first[:32]:  # "Shockwave: each press..." -> "Each press..."
                first = first.split(": ", 1)[1]
            info["desc"] = first[:1].upper() + first[1:]
        for node in tree.body:
            if isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
                try:
                    value = ast.literal_eval(node.value)
                except Exception:
                    continue
                if "PARAMS" in names and isinstance(value, dict):
                    info["params"] = value
                if "CATEGORY" in names and isinstance(value, str):
                    info["category"] = value
                if "LIGHTING" in names and isinstance(value, (str, dict)):
                    info["lighting"] = value
                if "EFFECT_BRIGHTNESS" in names and isinstance(value, (bool, dict)):
                    info["effect_brightness"] = value
    except Exception:
        info["desc"] = "Could not read this script."
    _info_cache[path] = (mtime, info)
    return info


SMALL_WORDS = {"of", "and", "the", "a", "an", "to", "in", "on", "for"}
ACRONYMS = {"wpm", "cpu", "ram", "rgb", "fps", "gpu", "led", "ui"}


def pretty(name):
    """'game_of_life.py' -> 'Game of Life', 'wpm_meter' -> 'WPM Meter'."""
    words = Path(str(name)).stem.replace("-", "_").split("_")
    out = []
    for i, w in enumerate(x for x in words if x):
        lw = w.lower()
        out.append(lw.upper() if lw in ACRONYMS else lw if (i and lw in SMALL_WORDS) else lw.capitalize())
    return " ".join(out)


def text_color_for(hex_color):
    r, g, b = rfx.hex_to_rgb(hex_color)
    return "#000000" if 0.299 * r + 0.587 * g + 0.114 * b > 140 else "#ffffff"


def round_rect(canvas, x0, y0, x1, y1, r, **kw):
    r = max(0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
           x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return canvas.create_polygon(pts, smooth=True, **kw)


def bind_wheel(widget, fn):
    """fn(+1 / -1) on mouse wheel, on Linux (Button-4/5) and elsewhere."""
    widget.bind("<Button-4>", lambda e: fn(-1))
    widget.bind("<Button-5>", lambda e: fn(1))
    widget.bind("<MouseWheel>", lambda e: fn(-1 if e.delta > 0 else 1))


# ---------------------------------------------------------------- custom widgets
class Slider(tk.Canvas):
    VALUE_W = 48

    def __init__(self, master, lo, hi, step, command, width=230, bg=CARD):
        super().__init__(master, width=width, height=28, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.lo, self.hi, self.step = float(lo), float(hi), float(step) or 1.0
        self.command = command
        self.value = self.lo
        self.enabled = True
        s = repr(float(step)).rstrip("0").split(".")
        self.decimals = 0 if float(step).is_integer() else min(3, len(s[1]) if len(s) > 1 else 0)
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Button-1>", self.drag)
        self.bind("<B1-Motion>", self.drag)
        bind_wheel(self, lambda d: self.change(self.value - d * self.step))

    def bounds(self):
        w = self.winfo_width()
        if w <= 1:
            w = int(self["width"])
        return 9, w - self.VALUE_W

    def redraw(self):
        self.delete("all")
        x0, x1 = self.bounds()
        y = 14
        frac = (self.value - self.lo) / (self.hi - self.lo) if self.hi > self.lo else 0.0
        xv = x0 + frac * (x1 - x0)
        col = ACCENT if self.enabled else FAINT
        self.create_line(x0, y, x1, y, width=4, fill=TRACK, capstyle="round")
        if xv > x0 + 0.5:
            self.create_line(x0, y, xv, y, width=4, fill=col, capstyle="round")
        self.create_oval(xv - 7, y - 7, xv + 7, y + 7, fill=FG if self.enabled else "#6a6a6a", outline=col, width=2)
        self.create_text(x1 + 12, y, text=f"{self.value:.{self.decimals}f}", anchor="w",
                         fill=FG if self.enabled else FAINT, font=FONTS["mono"])

    def snap(self, v):
        v = self.lo + round((v - self.lo) / self.step) * self.step
        return round(max(self.lo, min(self.hi, v)), 6)

    def drag(self, e):
        if not self.enabled:
            return
        x0, x1 = self.bounds()
        self.change(self.lo + (e.x - x0) / max(1, x1 - x0) * (self.hi - self.lo))

    def change(self, v):
        if not self.enabled:
            return
        v = self.snap(v)
        if v != self.value:
            self.value = v
            self.redraw()
            self.command(v)

    def set(self, v):
        self.value = self.snap(float(v))
        self.redraw()

    def set_enabled(self, on):
        self.enabled = on
        self.config(cursor="hand2" if on else "")
        self.redraw()


class Toggle(tk.Frame):
    def __init__(self, master, text="", command=None, bg=CARD):
        super().__init__(master, bg=bg)
        self.command = command
        self.value = False
        self.enabled = True
        self.c = tk.Canvas(self, width=38, height=22, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.c.pack(side="left")
        self.c.bind("<Button-1>", self.click)
        self.label = None
        if text:
            self.label = tk.Label(self, text=text, bg=bg, fg=FG, font=FONTS["body"], cursor="hand2")
            self.label.pack(side="left", padx=(8, 0))
            self.label.bind("<Button-1>", self.click)
        self.redraw()

    def redraw(self):
        self.c.delete("all")
        on = self.value
        fill = (ACCENT if on else TRACK) if self.enabled else INPUT
        round_rect(self.c, 1, 2, 37, 20, 9, fill=fill, outline="")
        x = 28 if on else 10
        self.c.create_oval(x - 7, 4, x + 7, 18, fill="#ffffff" if self.enabled else "#777777", outline="")
        if self.label:
            self.label.config(fg=FG if self.enabled else FAINT)

    def click(self, _e=None):
        if not self.enabled:
            return
        self.value = not self.value
        self.redraw()
        if self.command:
            self.command(self.value)

    def set(self, v):
        self.value = bool(v)
        self.redraw()

    def set_enabled(self, on):
        self.enabled = on
        self.redraw()


class Dropdown(tk.Frame):
    def __init__(self, master, values, command, width=17):
        super().__init__(master, bg=INPUT, cursor="hand2")
        self.values = list(values)
        self.command = command
        self.enabled = True
        self.text = tk.Label(self, text="", bg=INPUT, fg=FG, font=FONTS["body"], anchor="w",
                             width=width, padx=10, pady=5)
        self.text.pack(side="left")
        self.arrow = tk.Label(self, text="▾", bg=INPUT, fg=MUTED, font=FONTS["body"], padx=8)
        self.arrow.pack(side="left")
        for w in (self, self.text, self.arrow):
            w.bind("<Button-1>", self.open)
            w.bind("<Enter>", lambda e: self.hover(True))
            w.bind("<Leave>", lambda e: self.hover(False))

    def hover(self, on):
        bg = HOVER if on and self.enabled else INPUT
        for w in (self, self.text, self.arrow):
            w.config(bg=bg)

    def open(self, _e=None):
        if not self.enabled or not self.values:
            return
        menu = tk.Menu(self, tearoff=0, bg=INPUT, fg=FG, activebackground=ACCENT, activeforeground="#000000",
                       bd=0, relief="flat", font=FONTS["body"], activeborderwidth=0)
        for i, v in enumerate(self.values):
            menu.add_command(label=f"  {v}  ", command=lambda i=i: self.pick(i))
        try:
            menu.tk_popup(self.winfo_rootx(), self.winfo_rooty() + self.winfo_height())
        finally:
            menu.grab_release()

    def pick(self, i):
        self.set_text(self.values[i])
        self.command(i)

    def set_values(self, values):
        self.values = list(values)

    def set_text(self, t):
        self.text.config(text=t)

    def set_index(self, i):
        if 0 <= i < len(self.values):
            self.set_text(self.values[i])

    def set_enabled(self, on):
        self.enabled = on
        self.text.config(fg=FG if on else FAINT)
        self.arrow.config(fg=MUTED if on else FAINT)
        self.config(cursor="hand2" if on else "")


class Swatch(tk.Canvas):
    """Rounded colour chip; click to pick a colour."""

    def __init__(self, master, color, on_change, width=104, bg=CARD):
        super().__init__(master, width=width, height=30, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.on_change = on_change
        self.enabled = True
        self.color = color
        self.bind("<Button-1>", self.pick)
        self.redraw()

    def redraw(self):
        self.delete("all")
        w = int(self["width"])
        fill = self.color if self.enabled else INPUT
        round_rect(self, 1, 1, w - 1, 29, 8, fill=fill, outline="#3c3c3c" if self.enabled else INPUT)
        self.create_text(w / 2, 15, text=self.color.upper(), font=FONTS["mono"],
                         fill=text_color_for(self.color) if self.enabled else FAINT)

    def set(self, color):
        self.color = color
        self.redraw()

    def set_enabled(self, on):
        self.enabled = on
        self.config(cursor="hand2" if on else "")
        self.redraw()

    def pick(self, _e=None):
        if not self.enabled:
            return
        res = colorchooser.askcolor(color=self.color, title="Choose colour", parent=self)
        if res and res[1]:
            self.set(res[1])
            self.on_change(res[1])


class ScrollArea(tk.Frame):
    def __init__(self, master, bg=CARD):
        super().__init__(master, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, yscrollincrement=14)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview, style="Thin.Vertical.TScrollbar")
        self.canvas.configure(yscrollcommand=self.on_scroll)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.win, width=e.width))
        self.wheel(self.canvas)
        self.wheel(self.inner)

    def on_scroll(self, first, last):
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.bar.pack_forget()
        elif not self.bar.winfo_ismapped():
            self.bar.pack(side="right", fill="y")
        self.bar.set(first, last)

    def wheel(self, widget):
        bind_wheel(widget, lambda d: self.canvas.yview_scroll(d * 3, "units")
                   if self.inner.winfo_height() > self.canvas.winfo_height() else None)


# ---------------------------------------------------------------- app
class App:
    def __init__(self, root: tk.Tk, notes=None):
        self.root = root
        self.proc = None            # Popen if this window started the effect
        self.running_name = None
        self.sel_name = None
        self.log_pos = 0
        self._next_alive_check = 0.0
        self.cfg_name = None
        self.cfg = rfx.load_config()
        self.spec = {}
        self.info = {}
        self.param_rows = []
        self._b_shown = True
        self._preview_shown = True
        self.loading = False
        self._save_job = None
        self.rows = {}
        self.log_lines = []
        self.log_open = False

        for d in (USER_EFFECTS, SETTINGS_DIR):
            d.mkdir(parents=True, exist_ok=True)
        self.device = None                          # (name, rows, cols) of the connected keyboard
        self.layout = rfx.layout_for_device("", 6, 18)

        root.title(APP_NAME)
        try:
            self.icon_big = tk.PhotoImage(file=str(ICON_DIR / "razor-sharp-256.png"))
            root.iconphoto(True, self.icon_big)
        except tk.TclError:
            self.icon_big = None
        root.geometry("1280x820")
        root.minsize(1180, 760)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.setup_fonts()
        self.setup_style()
        self.build_ui()
        for note in notes or []:
            self.write_log(note)
        self.gcfg = rfx.load_global()
        self._gsave_job = None
        self.highlight_cells = {}
        self.detect_device()
        self.update_banner()
        if self.gcfg.get("profiles", {}).get("enabled"):
            start_watcher()

        running = running_effect()   # an effect may still be running from before
        if running:
            self.running_name = running["name"]
            self.sel_name = running["name"]
            self.write_log(f"— {pretty(running['name'])} is running in the background —")
            try:  # show only its recent output
                self.log_pos = max(0, EFFECT_LOG.stat().st_size - 3000)
            except OSError:
                self.log_pos = 0
        else:
            self.sel_name = last_effect()
        self.refresh()
        self.update_buttons()
        self.root.after(100, self.poll)
        self.root.after(40, self.tick_preview)

    # ------------------------------------------------ look
    def setup_fonts(self):
        families = set(tkfont.families(self.root))
        sans = next((f for f in ("Inter", "Cantarell", "Ubuntu", "Noto Sans", "DejaVu Sans") if f in families), "Sans")
        mono = next((f for f in ("JetBrains Mono", "Ubuntu Mono", "DejaVu Sans Mono", "Noto Sans Mono") if f in families), "Monospace")
        FONTS.update(
            title=(sans, 16, "bold"), h=(sans, 9, "bold"), body=(sans, 10), bold=(sans, 10, "bold"),
            small=(sans, 9), list=(sans, 11), key=(sans, 7), mono=(mono, 9))

    def setup_style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=FG, font=FONTS["body"], bordercolor=BORDER,
                    focuscolor=BG)
        s.configure("TButton", background=INPUT, foreground=FG, borderwidth=0, padding=(14, 7),
                    lightcolor=INPUT, darkcolor=INPUT, bordercolor=INPUT)
        s.map("TButton", background=[("disabled", CARD), ("active", HOVER)],
              foreground=[("disabled", FAINT)], lightcolor=[("active", HOVER)], darkcolor=[("active", HOVER)])
        s.configure("Accent.TButton", background=ACCENT, foreground="#000000", font=FONTS["bold"],
                    lightcolor=ACCENT, darkcolor=ACCENT, bordercolor=ACCENT, padding=(22, 8))
        s.map("Accent.TButton", background=[("active", ACCENT_HOVER)],
              lightcolor=[("active", ACCENT_HOVER)], darkcolor=[("active", ACCENT_HOVER)])
        s.configure("Stop.TButton", background="#3a1c1b", foreground=DANGER, font=FONTS["bold"],
                    lightcolor="#3a1c1b", darkcolor="#3a1c1b", bordercolor="#3a1c1b", padding=(22, 8))
        s.map("Stop.TButton", background=[("active", "#4d2321")],
              lightcolor=[("active", "#4d2321")], darkcolor=[("active", "#4d2321")])
        s.configure("Small.TButton", padding=(10, 5), font=FONTS["small"])
        s.configure("Ghost.TButton", background=BG, foreground=MUTED, padding=(8, 2), font=FONTS["small"],
                    lightcolor=BG, darkcolor=BG, bordercolor=BG)
        s.map("Ghost.TButton", background=[("active", BG)], foreground=[("active", FG)],
              lightcolor=[("active", BG)], darkcolor=[("active", BG)])
        s.configure("Thin.Vertical.TScrollbar", gripcount=0, background="#3a3a3a", troughcolor=CARD,
                    bordercolor=CARD, lightcolor="#3a3a3a", darkcolor="#3a3a3a", arrowcolor=CARD, arrowsize=6)
        s.map("Thin.Vertical.TScrollbar", background=[("active", "#4a4a4a")])

    def card(self, master, title=None):
        frame = tk.Frame(master, bg=CARD, padx=18, pady=14)
        head = None
        if title:
            head = tk.Frame(frame, bg=CARD)
            head.pack(fill="x", pady=(0, 10))
            tk.Label(head, text=title.upper(), bg=CARD, fg=ACCENT, font=FONTS["h"]).pack(side="left")
        return frame, head

    def label(self, master, text, fg=FG, font=None, bg=CARD, **kw):
        return tk.Label(master, text=text, bg=bg, fg=fg, font=font or FONTS["body"], **kw)

    # ------------------------------------------------ layout
    def build_ui(self):
        root = self.root

        # header
        header = tk.Frame(root, bg=BG, padx=20, pady=14)
        header.pack(fill="x")
        try:
            self.icon_small = tk.PhotoImage(file=str(ICON_DIR / "razor-sharp-64.png")).subsample(2)
            tk.Label(header, image=self.icon_small, bg=BG).pack(side="left")
        except tk.TclError:
            self.icon_small = None
        tk.Label(header, text=APP_NAME, bg=BG, fg=FG, font=FONTS["title"]).pack(side="left", padx=(10, 0))
        tk.Label(header, text=f"v{__version__}", bg=BG, fg=FAINT, font=FONTS["small"]).pack(side="left", padx=(8, 0), pady=(6, 0))
        ttk.Button(header, text="About", style="Ghost.TButton", command=self.show_about).pack(side="left", padx=(10, 0), pady=(4, 0))
        ttk.Button(header, text="⚙  Settings", style="Small.TButton", command=self.open_settings).pack(side="left", padx=(6, 0), pady=(2, 0))

        self.run_btn = ttk.Button(header, text="▶  Start", style="Accent.TButton", command=self.toggle_run)
        self.run_btn.pack(side="right")
        status = tk.Frame(header, bg=CARD, padx=12, pady=6)
        status.pack(side="right", padx=(0, 14))
        self.status_dot = tk.Label(status, text="●", bg=CARD, fg=FAINT, font=FONTS["body"])
        self.status_dot.pack(side="left")
        self.status = tk.Label(status, text="Idle", bg=CARD, fg=MUTED, font=FONTS["body"])
        self.status.pack(side="left", padx=(6, 0))
        self.status_stop = tk.Label(status, text="  ■ stop", bg=CARD, fg=MUTED, font=FONTS["small"], cursor="hand2")
        self.status_stop.bind("<Button-1>", lambda e: self.stop())
        self.status_stop.bind("<Enter>", lambda e: self.status_stop.config(fg=DANGER))
        self.status_stop.bind("<Leave>", lambda e: self.status_stop.config(fg=MUTED))

        # bottom bar + log (packed before the body so they keep their space)
        self.bottom = tk.Frame(root, bg=BG)
        self.bottom.pack(side="bottom", fill="x", padx=20, pady=(0, 10))
        bar = tk.Frame(self.bottom, bg=BG)
        bar.pack(side="bottom", fill="x")
        self.last_line = tk.Label(bar, text="", bg=BG, fg=MUTED, font=FONTS["mono"], anchor="w")
        self.last_line.pack(side="left", fill="x", expand=True)
        self.log_btn = ttk.Button(bar, text="Show log ▴", style="Ghost.TButton", command=self.toggle_log)
        self.log_btn.pack(side="right")
        self.log = tk.Text(self.bottom, height=8, bg="#0b0b0b", fg="#b5b5b5", borderwidth=0, padx=10, pady=8,
                           highlightthickness=0, font=FONTS["mono"], state="disabled", wrap="word")

        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        self.build_sidebar(body)
        main = tk.Frame(body, bg=BG)
        main.pack(side="left", fill="both", expand=True, padx=(14, 0))
        self.build_banner(main)
        self.build_preview(main)
        lower = tk.Frame(main, bg=BG)
        lower.pack(fill="both", expand=True, pady=(14, 0))
        self.build_lighting(lower)
        self.build_options(lower)
        self.refresh_presets()

    def build_sidebar(self, body):
        side = tk.Frame(body, bg=CARD, width=290)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        top = tk.Frame(side, bg=CARD, padx=14, pady=14)
        top.pack(fill="x")
        tk.Label(top, text="EFFECTS", bg=CARD, fg=ACCENT, font=FONTS["h"]).pack(anchor="w", pady=(0, 8))
        sbox = tk.Frame(top, bg=INPUT, padx=10)
        sbox.pack(fill="x")
        tk.Label(sbox, text="⌕", bg=INPUT, fg=MUTED, font=FONTS["list"]).pack(side="left")
        self.search_var = tk.StringVar()
        self.search = tk.Entry(sbox, textvariable=self.search_var, bg=INPUT, fg=FG, insertbackground=FG,
                               relief="flat", font=FONTS["body"], highlightthickness=0, bd=0)
        self.search.pack(side="left", fill="x", expand=True, ipady=6, padx=(6, 0))
        self.search_hint = tk.Label(sbox, text="Search effects", bg=INPUT, fg=FAINT, font=FONTS["body"])
        self.search_hint.place(x=26, rely=0.5, anchor="w")
        self.search_hint.bind("<Button-1>", lambda e: self.search.focus_set())
        self.search_var.trace_add("write", lambda *a: (self.update_search_hint(), self.refresh()))
        self.search.bind("<Escape>", lambda e: self.search_var.set(""))

        # bottom of sidebar: description, actions, autostart
        foot = tk.Frame(side, bg=CARD, padx=14, pady=12)
        foot.pack(side="bottom", fill="x")
        self.desc = tk.Label(foot, text="", bg=CARD, fg=MUTED, anchor="nw", justify="left",
                             font=FONTS["small"], wraplength=258, height=3)
        self.desc.pack(fill="x", pady=(0, 10))
        actions = tk.Frame(foot, bg=CARD)
        actions.pack(fill="x")
        for i, (text, cmd) in enumerate((("+ Add", self.add_effect), ("Remove", self.remove_effect),
                                         ("Folder", self.open_folder))):
            actions.columnconfigure(i, weight=1, uniform="a")
            ttk.Button(actions, text=text, style="Small.TButton", command=cmd).grid(
                row=0, column=i, sticky="ew", padx=(0 if i == 0 else 3, 0 if i == 2 else 3))
        self.autostart_toggle = Toggle(foot, "Run last effect at login", self.toggle_autostart)
        self.autostart_toggle.set(AUTOSTART_FILE.exists())
        self.autostart_toggle.pack(anchor="w", pady=(12, 0))

        tk.Frame(side, bg=BORDER, height=1).pack(side="bottom", fill="x")
        self.list_area = ScrollArea(side)
        self.list_area.pack(fill="both", expand=True, padx=(6, 6))

    def build_banner(self, main):
        self.banner = tk.Frame(main, bg="#3a3012", padx=14, pady=10)
        self.banner_text = tk.Label(self.banner, text="", bg="#3a3012", fg="#ffd66b", font=FONTS["body"],
                                    justify="left", anchor="w", wraplength=640)
        self.banner_text.pack(side="left", fill="x", expand=True)
        self.banner_btn = ttk.Button(self.banner, text="Allow", style="Small.TButton", command=self.request_input_access)
        self._pk = None

    def update_banner(self):
        state = input_access()
        if state == "ok":
            self.banner.pack_forget()
            return
        if state == "relogin":
            self.banner_text.config(text="Almost there: log out and back in so typing effects can see your key presses.")
            self.banner_btn.pack_forget()
        else:
            self.banner_text.config(text="Typing effects (ripples, heatmap, snake…) can't see your key presses yet. "
                                         "Allow adds you to the “input” group. Note: any program you run then "
                                         "has the same access.")
            self.banner_btn.pack(side="right", padx=(12, 0))
        if not self.banner.winfo_manager():
            self.banner.pack(fill="x", pady=(0, 14))

    def request_input_access(self):
        import getpass
        try:
            self._pk = subprocess.Popen(["pkexec", "gpasswd", "-a", getpass.getuser(), "input"])
        except FileNotFoundError:
            messagebox.showinfo(APP_NAME, "Run this in a terminal, then log out and back in:\n\n"
                                          "sudo gpasswd -a $USER input")
            return
        self.root.after(400, self.check_input_request)

    def check_input_request(self):
        if self._pk is None:
            return
        if self._pk.poll() is None:
            self.root.after(400, self.check_input_request)
            return
        ok = self._pk.returncode == 0
        self._pk = None
        if ok:
            self.write_log("Added you to the input group. Log out and back in to finish.")
        self.update_banner()

    def show_about(self):
        messagebox.showinfo(
            f"About {APP_NAME}",
            f"{APP_NAME} {__version__}\n\nLighting effects for Razer keyboards on Linux, using OpenRazer.\n\n"
            f"{HOMEPAGE}\n\nFree software under the GNU GPL v3 or later.\n"
            "Not affiliated with or endorsed by Razer Inc.")

    def build_preview(self, main):
        frame, head = self.card(main, "Preview")
        frame.pack(fill="x")
        self.settings_for = tk.Label(head, text="", bg=CARD, fg=MUTED, font=FONTS["small"])
        self.settings_for.pack(side="right")
        kb = tk.Frame(frame, bg=CARD)
        kb.pack(fill="x", pady=(0, 10))
        self.kb_label = tk.Label(kb, text="Looking for your keyboard…", bg=CARD, fg=MUTED, font=FONTS["small"],
                                 anchor="w", justify="left")
        self.kb_label.pack(side="left", fill="x", expand=True)
        self.map_btn = ttk.Button(kb, text="⌨  Map keys", style="Small.TButton", command=self.open_key_mapper)
        self.map_btn.pack(side="right")
        self.preview = tk.Canvas(frame, width=660, height=250, bg="#0c0c0c", highlightthickness=0)
        self.preview.pack()
        self.preview_keys = []
        self.preview_msg = tk.Label(frame, text="", bg=CARD, fg=MUTED, font=FONTS["body"], anchor="w",
                                    justify="left", pady=6)
        self.note = tk.Label(frame, text="", bg=CARD, fg="#e0a030", font=FONTS["small"], anchor="w")
        self.draw_preview_keys()

    def draw_preview_keys(self):
        """Draw the keyboard picture for the current layout."""
        c = self.preview
        c.delete("all")
        self.preview_keys = []
        keys = [(n, rc, rfx.PHYSICAL[n]) for n, rc in self.layout.keys.items() if n in rfx.PHYSICAL]
        if not keys:
            c.config(width=660, height=60)
            c.create_text(330, 30, text="No layout for this keyboard yet — use Map keys.", fill=MUTED, font=FONTS["body"])
            return
        max_x = max(x + w for _, _, (x, y, w, h) in keys)
        max_y = max(y + h for _, _, (x, y, w, h) in keys)
        pad, gap = 10, 4
        unit = min(36.0, 680.0 / max_x)
        c.config(width=int(max_x * unit + pad * 2 - gap), height=int(max_y * unit + pad * 2 - gap))
        for name, (r, col), (x, y, w, h) in keys:
            x0, y0 = pad + x * unit, pad + y * unit
            x1, y1 = x0 + w * unit - gap, y0 + h * unit - gap
            rect = round_rect(c, x0, y0, x1, y1, 6, outline="", fill="#333333")
            txt = c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=rfx.LABELS.get(name, name), font=FONTS["key"])
            self.preview_keys.append((rect, txt, r, col))

    def detect_device(self):
        self.device = detect_keyboard()
        if self.device:
            name, rows, cols = self.device
            self.layout = rfx.layout_for_device(name, rows, cols)
            status = {"mapped": ("mapped by you", ACCENT),
                      "built-in": ("built-in layout" + (" ✓" if self.layout.verified else " (not yet confirmed)"),
                                   ACCENT if self.layout.verified else "#e0a030"),
                      "guessed": ("closest built-in layout — may be off", "#e0a030")}.get(
                self.layout.source, ("no layout", "#e0a030"))
            text = f"{name}  ·  {self.layout.name}, {status[0]}"
            if self.layout.source != "mapped" and not self.layout.verified:
                text += "\nIf keys light up in the wrong place, click Map keys."
            self.kb_label.config(text=text, fg=status[1] if status[1] != ACCENT else MUTED)
        else:
            self.layout = rfx.layout_for_device("", 6, 18)
            self.kb_label.config(text="No Razer keyboard found. Is OpenRazer installed and running?", fg="#e0a030")
        self.draw_preview_keys()
        if hasattr(self, "gcfg"):
            self.update_highlight_cells()

    def open_key_mapper(self):
        KeyMapper(self)

    def open_settings(self):
        if getattr(self, "settings_win", None) and self.settings_win.win.winfo_exists():
            self.settings_win.win.lift()
            return
        self.settings_win = SettingsWindow(self)

    def update_highlight_cells(self):
        cells = {}
        h = self.gcfg.get("highlights", {})
        if h.get("enabled"):
            for g in h.get("groups", []):
                try:
                    col = rfx.hex_to_rgb(g.get("color", "#ff0000"))
                except ValueError:
                    continue
                for k in g.get("keys", []):
                    p = self.layout.pos(k)
                    if p:
                        cells[p] = col
        self.highlight_cells = cells

    def save_global_soon(self):
        self.update_highlight_cells()
        if self._gsave_job:
            self.root.after_cancel(self._gsave_job)
        self._gsave_job = self.root.after(200, self.save_global_now)

    def save_global_now(self):
        self._gsave_job = None
        rfx.save_global(self.gcfg)

    def build_lighting(self, lower):
        frame, head = self.card(lower, "Lighting")
        frame.pack(side="left", fill="y", anchor="n")
        self.light_card = frame
        g = tk.Frame(frame, bg=CARD)
        g.pack(fill="x")
        g.columnconfigure(0, minsize=96)
        self.light_rows = {}

        def row(key, r, text, widget, pady=5):
            lbl = self.label(g, text, fg=MUTED)
            lbl.grid(row=r, column=0, sticky="w", pady=pady)
            widget.grid(row=r, column=1, sticky="w", pady=pady)
            self.light_rows[key] = (lbl, widget)

        pf = tk.Frame(g, bg=CARD)
        self.preset_dd = Dropdown(pf, [], lambda i: self.apply_preset(self.preset_dd.values[i]), width=15)
        self.preset_dd.pack(side="left")
        ttk.Button(pf, text="Save", style="Small.TButton", command=self.save_preset).pack(side="left", padx=(8, 0))
        ttk.Button(pf, text="Delete", style="Small.TButton", command=self.delete_preset).pack(side="left", padx=(6, 0))
        row("preset", 0, "Preset", pf)

        self.mode_dd = Dropdown(g, [m[1] for m in MODES], lambda i: self.set_light("mode", MODES[i][0]))
        row("mode", 1, "Mode", self.mode_dd)

        cf = tk.Frame(g, bg=CARD)
        self.sw_a = Swatch(cf, self.cfg["color_a"], lambda c: self.set_light("color_a", c))
        self.sw_a.pack(side="left")
        self.swap_btn = ttk.Button(cf, text="⇄", width=3, style="Small.TButton", command=self.swap_colors)
        self.swap_btn.pack(side="left", padx=8)
        self.sw_b = Swatch(cf, self.cfg["color_b"], lambda c: self.set_light("color_b", c))
        self.sw_b.pack(side="left")
        row("colours", 2, "Colours", cf)

        df = tk.Frame(g, bg=CARD)
        self.dir_dd = Dropdown(df, [d[1] for d in DIRECTIONS], lambda i: self.set_light("direction", DIRECTIONS[i][0]))
        self.dir_dd.pack(side="left")
        self.reverse_t = Toggle(df, "Reverse", lambda v: self.set_light("reverse", v))
        self.reverse_t.pack(side="left", padx=(14, 0))
        row("direction", 3, "Direction", df)

        self.animate_t = Toggle(g, "", lambda v: self.set_light("animate", v))
        row("animate", 4, "Animate", self.animate_t)

        self.speed_s = Slider(g, 0.1, 5, 0.1, lambda v: self.set_light("anim_speed", v), width=260)
        row("speed", 5, "Speed", self.speed_s, pady=3)

        self.bright_s = Slider(g, 0, 100, 1, lambda v: self.set_light("brightness", int(v)), width=260)
        row("brightness", 6, "Brightness", self.bright_s, pady=3)

        self.light_note = tk.Label(frame, text="", bg=CARD, fg=MUTED, font=FONTS["small"],
                                   justify="left", anchor="w", wraplength=360)

    def build_options(self, lower):
        frame, head = self.card(lower, "Effect options")
        frame.pack(side="left", fill="both", expand=True, anchor="n", padx=(14, 0))
        ttk.Button(head, text="Reset all", style="Small.TButton", command=self.reset_defaults).pack(side="right")
        self.params_frame = tk.Frame(frame, bg=CARD)
        self.params_frame.pack(fill="both", expand=True, anchor="n")
        self.params_frame.columnconfigure(1, weight=1)

    # ------------------------------------------------ preview
    def tick_preview(self):
        t = time.monotonic()
        for rect, txt, y, x in self.preview_keys:
            c = rfx.apply_brightness(rfx.palette_color(self.cfg, y, x, t, self.layout.bounds),
                                     self.cfg.get("brightness", 100))
            if (y, x) in self.highlight_cells:
                c = self.highlight_cells[(y, x)]
            h = rfx.rgb_to_hex(c)
            self.preview.itemconfig(rect, fill=h)
            self.preview.itemconfig(txt, fill=text_color_for(h))
        self.root.after(40, self.tick_preview)

    # ------------------------------------------------ effects list
    def effects(self):
        return all_effects()

    def update_search_hint(self):
        if self.search_var.get():
            self.search_hint.place_forget()
        else:
            self.search_hint.place(x=26, rely=0.5, anchor="w")

    def refresh(self):
        inner = self.list_area.inner
        for w in inner.winfo_children():
            w.destroy()
        self.rows = {}
        query = self.search_var.get().strip().lower()
        groups = {}
        names = []
        for p in self.effects():
            info = read_script_info(p)
            if query and query not in pretty(p.name).lower() and query not in info["desc"].lower():
                continue
            groups.setdefault(info["category"], []).append(p.name)
            names.append(p.name)
        order = CATEGORY_ORDER + sorted(c for c in groups if c not in CATEGORY_ORDER)
        names = [n for cat in order for n in groups.get(cat, [])]  # display order
        for cat in order:
            if cat not in groups:
                continue
            h = tk.Label(inner, text=cat.upper(), bg=CARD, fg=FAINT, font=FONTS["h"], anchor="w", padx=10)
            h.pack(fill="x", pady=(12, 4))
            self.list_area.wheel(h)
            for name in groups[cat]:
                self.add_row(inner, name)
        if not names:
            msg = "No matches." if query else "No effects yet.\nClick “+ Add” to load a .py file."
            e = tk.Label(inner, text=msg, bg=CARD, fg=MUTED, font=FONTS["small"], justify="left", padx=10)
            e.pack(anchor="w", pady=12)

        if self.sel_name not in [p.name for p in self.effects()]:
            self.sel_name = names[0] if names else None
        self.style_rows()
        if self.sel_name != self.cfg_name:
            self.load_settings()

    def add_row(self, inner, name):
        row = tk.Frame(inner, bg=CARD, cursor="hand2")
        row.pack(fill="x", pady=1)
        lbl = tk.Label(row, text=pretty(name), bg=CARD, fg=FG, font=FONTS["list"], anchor="w", padx=10, pady=6)
        lbl.pack(side="left", fill="x", expand=True)
        dot = tk.Label(row, text="", bg=CARD, fg=ACCENT, font=FONTS["small"], padx=10)
        dot.pack(side="right")
        for w in (row, lbl, dot):
            w.bind("<Button-1>", lambda e, n=name: self.select(n))
            w.bind("<Double-Button-1>", lambda e, n=name: (self.select(n), self.start()))
            w.bind("<Enter>", lambda e, n=name: self.style_row(n, hover=True))
            w.bind("<Leave>", lambda e, n=name: self.style_row(n))
            self.list_area.wheel(w)
        self.rows[name] = (row, lbl, dot)

    def style_row(self, name, hover=False):
        if name not in self.rows:
            return
        row, lbl, dot = self.rows[name]
        selected = name == self.sel_name
        bg = ACCENT if selected else (HOVER if hover else CARD)
        fg = "#000000" if selected else FG
        running = name == self.running_name
        for w in (row, lbl, dot):
            w.config(bg=bg)
        lbl.config(fg=fg, font=FONTS["bold"] if selected else FONTS["list"])
        dot.config(text="● running" if running else "", fg="#000000" if selected else ACCENT)

    def style_rows(self):
        for n in self.rows:
            self.style_row(n)

    def select(self, name):
        if name == self.sel_name:
            return
        self.sel_name = name
        self.style_rows()
        self.load_settings()
        self.update_buttons()

    def add_effect(self):
        paths = filedialog.askopenfilenames(title="Add effect scripts", filetypes=[("Python scripts", "*.py")])
        last = None
        for src in paths:
            src = Path(src)
            dest = USER_EFFECTS / src.name
            if dest.exists() and not messagebox.askyesno(APP_NAME, f"{src.name} already exists. Replace it?"):
                continue
            if (BUILTIN_EFFECTS / src.name).exists() and not dest.exists() and not messagebox.askyesno(
                    APP_NAME, f"{pretty(src.name)} is a built-in effect. Use your file instead of it?"):
                continue
            USER_EFFECTS.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            last = dest.name
            self.write_log(f"Added {src.name}")
        if last:
            self.sel_name = last
            self.cfg_name = None
        self.refresh()

    def remove_effect(self):
        name = self.sel_name
        if not name:
            return
        if is_builtin(name):
            messagebox.showinfo(APP_NAME, f"{pretty(name)} is built in and can't be removed.")
            return
        restores = (BUILTIN_EFFECTS / name).exists()
        msg = (f"Remove your version of {pretty(name)}? The built-in one comes back." if restores
               else f"Remove {pretty(name)}?")
        if not messagebox.askyesno(APP_NAME, msg):
            return
        if name == self.running_name:
            self.stop()
        (USER_EFFECTS / name).unlink(missing_ok=True)
        if not restores:
            settings_path(name).unlink(missing_ok=True)
        self.cfg_name = None
        self.sel_name = None
        self.write_log(f"Removed {name}")
        self.refresh()

    def open_folder(self):
        USER_EFFECTS.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["xdg-open", str(USER_EFFECTS)])

    # ------------------------------------------------ settings
    def load_settings(self):
        name = self.sel_name
        self.flush_save()
        self.cfg_name = name
        if not name:
            self.desc.config(text="")
            self.settings_for.config(text="")
            self.note.pack_forget()
            self.spec = {}
            self.cfg = rfx.load_config()
            self.populate()
            return
        info = read_script_info(effect_path(name))
        self.info = info
        self.spec = info["params"]
        self.desc.config(text=info["desc"])
        self.settings_for.config(text=f"Settings for {pretty(name)}")
        if info["uses_fx"]:
            self.note.pack_forget()
        else:
            self.note.config(text="⚠  This effect doesn’t use razor_fx, so these colours won’t change it.")
            self.note.pack(fill="x", pady=(8, 0))
        self.cfg = rfx.load_config(str(settings_path(name)), self.spec)
        self.populate()

    def populate(self):
        self.loading = True
        c = self.cfg
        self.mode_dd.set_index(next((i for i, m in enumerate(MODES) if m[0] == c["mode"]), 0))
        self.dir_dd.set_index(next((i for i, d in enumerate(DIRECTIONS) if d[0] == c["direction"]), 0))
        self.sw_a.set(c["color_a"])
        self.sw_b.set(c["color_b"])
        self.reverse_t.set(c["reverse"])
        self.animate_t.set(c["animate"])
        self.speed_s.set(c["anim_speed"])
        self.bright_s.set(c["brightness"])
        self.preset_dd.set_text(self.matching_preset() or "Custom")
        self.build_params()
        self.update_visibility()
        self.loading = False

    def build_params(self):
        for w in self.params_frame.winfo_children():
            w.destroy()
        self.param_rows = []
        eb = self.info.get("effect_brightness", True) if self.cfg_name else False
        if not self.spec and eb is False:
            self.label(self.params_frame, "This effect has no extra options.\nIt uses the lighting colours on the left.",
                       fg=MUTED, font=FONTS["small"], justify="left").grid(row=0, column=0, sticky="w")
            return
        first = 0
        if eb is not False:
            lbl = self.label(self.params_frame, "Effect brightness", fg=FG, font=FONTS["bold"])
            lbl.grid(row=0, column=0, sticky="w", pady=5, padx=(0, 16))
            sl = Slider(self.params_frame, 0, 100, 1, lambda v: self.set_light("effect_brightness", int(v)), width=240)
            sl.set(self.cfg.get("effect_brightness", 100))
            sl.grid(row=0, column=1, sticky="w", pady=4)
            sep = tk.Frame(self.params_frame, bg=BORDER, height=1)
            sep.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 8))
            spec = {"show_if": eb} if isinstance(eb, dict) else {}
            self.param_rows.append(("effect_brightness", spec, (lbl, sl, sep)))
            first = 2
        for i, (key, s) in enumerate(self.spec.items(), start=first):
            typ = s.get("type", "range")
            val = self.cfg["params"].get(key, s.get("default"))
            lbl = self.label(self.params_frame, s.get("label", key), fg=MUTED)
            lbl.grid(row=i, column=0, sticky="w", pady=5, padx=(0, 16))
            if typ == "color":
                w = Swatch(self.params_frame, val or "#ffffff", lambda col, k=key: self.set_param(k, col))
            elif typ == "bool":
                w = Toggle(self.params_frame, "", lambda v, k=key: self.set_param(k, v))
                w.set(val)
            else:
                lo, hi = s.get("min", 0), s.get("max", 100)
                is_int = all(isinstance(v, int) for v in (lo, hi, s.get("default", 0), s.get("step", 1)))
                step = s.get("step", 1 if is_int else (hi - lo) / 100)
                conv = int if is_int else (lambda v: round(float(v), 4))
                w = Slider(self.params_frame, lo, hi, step, lambda v, k=key, cv=conv: self.set_param(k, cv(v)), width=240)
                w.set(val)
            w.grid(row=i, column=1, sticky="w", pady=4)
            self.param_rows.append((key, s, (lbl, w)))
        self.update_param_visibility()

    def lighting_level(self):
        """What this effect uses from the Lighting card: full, colors, or brightness."""
        spec = self.info.get("lighting", "full") if self.cfg_name else "full"
        if isinstance(spec, dict):
            on = bool(self.cfg["params"].get(spec.get("param")))
            spec = spec.get("on", "full") if on else spec.get("off", "brightness")
        if spec == "brightness":   # older name for "none"
            spec = "none"
        return spec if spec in ("full", "colors", "none") else "full"

    def update_visibility(self):
        level = self.lighting_level()
        mode = self.cfg["mode"]
        two = mode in ("gradient", "breathing")
        spatial = mode in ("gradient", "rainbow")
        animated = (spatial and self.cfg["animate"]) or mode in ("spectrum", "breathing")
        if level == "full":
            show = {"preset", "mode", "brightness"}
            if mode not in ("rainbow", "spectrum"):
                show.add("colours")
            if spatial:
                show |= {"direction", "animate"}
            if animated:
                show.add("speed")
            show_b = two
        elif level == "colors":
            show, show_b = {"colours", "brightness"}, True
        else:
            show, show_b = set(), False
        for key, (lbl, widget) in self.light_rows.items():
            if key in show:
                lbl.grid()
                widget.grid()
            else:
                lbl.grid_remove()
                widget.grid_remove()
        # second colour + swap only when two colours are used
        if show_b != self._b_shown:
            self._b_shown = show_b
            if show_b:
                self.swap_btn.pack(side="left", padx=8)
                self.sw_b.pack(side="left")
            else:
                self.swap_btn.pack_forget()
                self.sw_b.pack_forget()

        name = pretty(self.cfg_name) if self.cfg_name else "This effect"
        notes = {
            "colors": f"{name} uses just these two colours in its own pattern.",
            "none": f"{name} doesn't use the lighting colours. Its colours and brightness are "
                    "under Effect options.",
        }
        if level in notes:
            self.light_note.config(text=notes[level])
            self.light_note.pack(fill="x", pady=(10, 0))
        else:
            self.light_note.pack_forget()

        # the preview only shows the lighting pattern, so hide it when that isn't what you'll see
        self.preview_msg.config(text=f"No preview — {name} draws its own animation on the keyboard.")
        want_preview = level == "full"
        if want_preview != self._preview_shown:
            self._preview_shown = want_preview
            self.note_was = self.note.winfo_manager() == "pack"
            if self.note_was:
                self.note.pack_forget()
            if want_preview:
                self.preview_msg.pack_forget()
                self.preview.pack()
            else:
                self.preview.pack_forget()
                self.preview_msg.pack(fill="x")
            if self.note_was:
                self.note.pack(fill="x", pady=(8, 0))

    def update_param_visibility(self):
        for key, spec, widgets in self.param_rows:
            cond = spec.get("show_if")
            if not cond:
                continue
            visible = bool(self.cfg["params"].get(cond.get("param"))) == bool(cond.get("is", True))
            for w in widgets:
                w.grid() if visible else w.grid_remove()

    def set_light(self, key, value):
        if self.loading or self.cfg.get(key) == value:
            return
        self.cfg[key] = value
        if key == "mode":
            self.mode_dd.set_index(next(i for i, m in enumerate(MODES) if m[0] == value))
        self.preset_dd.set_text(self.matching_preset() or "Custom")
        self.update_visibility()
        self.schedule_save()

    def set_param(self, key, value):
        if self.loading or self.cfg["params"].get(key) == value:
            return
        self.cfg["params"][key] = value
        self.update_param_visibility()
        self.update_visibility()
        self.schedule_save()

    def swap_colors(self):
        a, b = self.cfg["color_a"], self.cfg["color_b"]
        self.cfg["color_a"], self.cfg["color_b"] = b, a
        self.sw_a.set(b)
        self.sw_b.set(a)
        self.preset_dd.set_text(self.matching_preset() or "Custom")
        self.schedule_save()

    def reset_defaults(self):
        self.cfg = rfx.load_config(None, self.spec)
        self.populate()
        self.schedule_save()

    def schedule_save(self):
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(150, self.flush_save)

    def flush_save(self):
        if self._save_job:
            self.root.after_cancel(self._save_job)
            self._save_job = None
        if not self.cfg_name:
            return
        path = settings_path(self.cfg_name)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.cfg, indent=2))
        tmp.replace(path)  # atomic, so a running effect never reads half a file

    # ------------------------------------------------ presets
    def user_presets(self):
        try:
            return json.loads(PRESETS_FILE.read_text())
        except (OSError, ValueError):
            return {}

    def all_presets(self):
        p = dict(BUILTIN_PRESETS)
        p.update({"★ " + k: v for k, v in self.user_presets().items()})
        return p

    def refresh_presets(self):
        self.preset_dd.set_values(list(self.all_presets()))

    @staticmethod
    def relevant_keys(cfg):
        mode = cfg["mode"]
        keys = ["mode"]
        if mode in ("solid", "gradient", "breathing"):
            keys.append("color_a")
        if mode in ("gradient", "breathing"):
            keys.append("color_b")
        if mode in ("gradient", "rainbow"):
            keys += ["direction", "reverse", "animate"]
        if (mode in ("gradient", "rainbow") and cfg["animate"]) or mode in ("spectrum", "breathing"):
            keys.append("anim_speed")
        return keys

    def matching_preset(self):
        for name, p in self.all_presets().items():
            full = dict(rfx.DEFAULTS)
            full.update(p)
            if all(str(self.cfg.get(k)).lower() == str(full[k]).lower() for k in self.relevant_keys(full)):
                return name
        return None

    def apply_preset(self, name):
        p = self.all_presets().get(name)
        if not p:
            return
        base = {k: v for k, v in rfx.DEFAULTS.items() if k not in ("brightness", "effect_brightness")}
        base.update(p)
        self.cfg.update(base)
        self.populate()
        self.preset_dd.set_text(name)
        self.schedule_save()

    def save_preset(self):
        name = simpledialog.askstring(APP_NAME, "Name for this preset:", parent=self.root)
        if not name or not name.strip():
            return
        presets = self.user_presets()
        presets[name.strip()] = {k: self.cfg[k] for k in rfx.DEFAULTS if k not in ("brightness", "effect_brightness")}
        PRESETS_FILE.write_text(json.dumps(presets, indent=2))
        self.refresh_presets()
        self.preset_dd.set_text("★ " + name.strip())
        self.write_log(f"Saved preset “{name.strip()}”")

    def delete_preset(self):
        name = self.preset_dd.text.cget("text")
        if not name.startswith("★ "):
            messagebox.showinfo(APP_NAME, "Pick one of your own presets (marked ★) to delete it.")
            return
        if not messagebox.askyesno(APP_NAME, f"Delete preset “{name[2:]}”?"):
            return
        presets = self.user_presets()
        presets.pop(name[2:], None)
        PRESETS_FILE.write_text(json.dumps(presets, indent=2))
        self.refresh_presets()
        self.preset_dd.set_text(self.matching_preset() or "Custom")

    # ------------------------------------------------ running
    def toggle_run(self):
        if self.running_name and self.running_name == self.sel_name:
            self.stop()
        else:
            self.start()

    def start(self):
        name = self.sel_name
        if not name:
            return
        if self.running_name:
            self.stop()
        if self.cfg_name != name:
            self.load_settings()
        self.flush_save()
        self.proc = launch_effect(name)
        self.running_name = name
        self.log_pos = 0
        self.write_log(f"— Starting {pretty(name)} (keeps running if you close this window) —")
        self.style_rows()
        self.update_buttons()

    def stop(self):
        if not self.running_name:
            return
        self.read_effect_log()
        stop_effect(self.proc)
        self.read_effect_log()
        self.write_log(f"— Stopped {pretty(self.running_name)} —")
        self.proc = None
        self.running_name = None
        self.style_rows()
        self.update_buttons()

    def read_effect_log(self):
        """Show new output from the background effect."""
        try:
            with open(EFFECT_LOG, "r", errors="replace") as f:
                f.seek(0, 2)
                size = f.tell()
                if size < self.log_pos:      # a new effect started and the log was cleared
                    self.log_pos = 0
                f.seek(self.log_pos)
                text = f.read()
                self.log_pos = f.tell()
        except OSError:
            return
        for line in text.splitlines():
            if line.strip():
                self.write_log(line)

    def poll(self):
        self.read_effect_log()
        now = time.monotonic()
        if self.running_name and now >= self._next_alive_check:
            self._next_alive_check = now + 0.5
            if not running_effect():          # it ended by itself (finished or crashed)
                code = self.proc.poll() if self.proc else None
                self.read_effect_log()
                self.write_log(f"— {pretty(self.running_name)} stopped"
                               + (f" (exit code {code})" if code is not None else "") + " —")
                if code not in (0, None):
                    self.show_log(True)
                self.proc = None
                self.running_name = None
                self.style_rows()
                self.update_buttons()
        self.root.after(150, self.poll)

    def update_buttons(self):
        running = self.running_name is not None
        if running and self.running_name == self.sel_name:
            self.run_btn.config(text="■  Stop", style="Stop.TButton")
        else:
            self.run_btn.config(text="▶  Start", style="Accent.TButton")
        self.run_btn.state(["!disabled"] if self.sel_name else ["disabled"])
        if running:
            self.status_dot.config(fg=ACCENT)
            self.status.config(text=f"Running · {pretty(self.running_name)}", fg=FG)
            if not self.status_stop.winfo_ismapped():
                self.status_stop.pack(side="left")
        else:
            self.status_dot.config(fg=FAINT)
            self.status.config(text="Idle", fg=MUTED)
            self.status_stop.pack_forget()

    # ------------------------------------------------ log
    def write_log(self, text):
        self.last_line.config(text=text[:140])
        self.log.config(state="normal")
        self.log.insert("end", text + "\n")
        lines = int(self.log.index("end-1c").split(".")[0])
        if lines > 500:
            self.log.delete("1.0", f"{lines - 500}.0")
        self.log.see("end")
        self.log.config(state="disabled")

    def show_log(self, on):
        self.log_open = on
        if on:
            self.log.pack(side="top", fill="x", pady=(0, 6))
            self.log_btn.config(text="Hide log ▾")
        else:
            self.log.pack_forget()
            self.log_btn.config(text="Show log ▴")

    def toggle_log(self):
        self.show_log(not self.log_open)

    # ------------------------------------------------ autostart / close
    def toggle_autostart(self, on):
        write_autostart(on)
        self.write_log("Will start the last effect at login (in the background, no window)." if on else "Autostart off.")

    def on_close(self):
        # The effect runs on its own, so closing the window leaves it running.
        self.flush_save()
        self.root.destroy()


# ---------------------------------------------------------------- GNOME shortcuts
KB_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
KB_BASE = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
SHORTCUTS = [
    ("razor-sharp-next", "Razor Sharp: next effect", "--next", "<Super><Alt>Right"),
    ("razor-sharp-previous", "Razor Sharp: previous effect", "--previous", "<Super><Alt>Left"),
    ("razor-sharp-toggle", "Razor Sharp: lights on/off", "--toggle", "<Super><Alt>Down"),
]


def cli_command(option):
    if shutil.which(APP_ID):
        return f"{APP_ID} {option}"
    return f"{sys.executable} {APP_DIR / 'razor_sharp.py'} {option}"


def _gsettings(*args):
    return subprocess.run(["gsettings", *args], capture_output=True, text=True, timeout=5)


def gnome_shortcut_list():
    out = _gsettings("get", KB_SCHEMA, "custom-keybindings").stdout.strip()
    if out.startswith("@as"):
        out = out[3:].strip()
    try:
        value = ast.literal_eval(out) if out else []
        return [str(x) for x in value] if isinstance(value, (list, tuple)) else []
    except (ValueError, SyntaxError):
        raise RuntimeError(f"Unexpected answer from gsettings: {out!r}")


def gnome_shortcuts_installed():
    try:
        have = gnome_shortcut_list()
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return None
    return all(KB_BASE + sid + "/" in have for sid, *_ in SHORTCUTS)


def set_gnome_shortcuts(add):
    """Add or remove our three custom shortcuts, keeping everyone else's."""
    current = gnome_shortcut_list()
    ours = [KB_BASE + sid + "/" for sid, *_ in SHORTCUTS]
    new = [p for p in current if p not in ours] + (ours if add else [])
    if add:
        for (sid, name, opt, binding), path in zip(SHORTCUTS, ours):
            schema = f"{KB_SCHEMA}.custom-keybinding:{path}"
            for key, value in (("name", name), ("command", cli_command(opt)), ("binding", binding)):
                r = _gsettings("set", schema, key, value)
                if r.returncode != 0:
                    raise RuntimeError(r.stderr.strip() or "gsettings failed")
    value = "[" + ", ".join(repr(x) for x in new) + "]" if new else "@as []"
    r = _gsettings("set", KB_SCHEMA, "custom-keybindings", value)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "gsettings failed")


# ---------------------------------------------------------------- backup
def export_backup(path):
    files = {}
    for f in SETTINGS_DIR.glob("*.json"):
        files["settings/" + f.name] = f.read_text()
    for name in ("presets.json", "global.json"):
        if (DATA_DIR / name).exists():
            files[name] = (DATA_DIR / name).read_text()
    for f in rfx.USER_LAYOUTS.glob("*.json"):
        files["layouts/" + f.name] = f.read_text()
    for f in USER_EFFECTS.glob("*.py"):
        files["effects/" + f.name] = f.read_text()
    Path(path).write_text(json.dumps({"razor_sharp_backup": 1, "version": __version__,
                                      "created": time.strftime("%Y-%m-%d %H:%M"), "files": files}, indent=1))
    return len(files)


def import_backup(path):
    data = json.loads(Path(path).read_text())
    if data.get("razor_sharp_backup") != 1:
        raise ValueError("This isn't a Razor Sharp backup file.")
    targets = {"settings": SETTINGS_DIR, "layouts": rfx.USER_LAYOUTS, "effects": USER_EFFECTS}
    count = 0
    for key, text in data.get("files", {}).items():
        folder, _, name = key.rpartition("/")
        if "/" in name or name.startswith(".") or not name:
            continue
        if folder == "" and name in ("presets.json", "global.json"):
            dest = DATA_DIR / name
        elif folder in targets and name.endswith((".json", ".py")):
            dest = targets[folder] / name
        else:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
        count += 1
    return count


# ---------------------------------------------------------------- settings window
class SettingsWindow:
    SECTIONS = ["Highlights", "Status keys", "Night & idle", "App profiles", "Shortcuts", "Backup", "Performance"]
    TIMES = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)]

    def __init__(self, app):
        self.app = app
        self.g = app.gcfg
        w = self.win = tk.Toplevel(app.root, bg=BG)
        w.title(f"{APP_NAME} settings")
        w.geometry("900x620")
        w.minsize(820, 560)
        w.transient(app.root)
        nav = tk.Frame(w, bg=CARD, width=200, padx=8, pady=14)
        nav.pack(side="left", fill="y")
        nav.pack_propagate(False)
        tk.Label(nav, text="SETTINGS", bg=CARD, fg=ACCENT, font=FONTS["h"], anchor="w", padx=10).pack(fill="x", pady=(0, 8))
        self.nav = {}
        for name in self.SECTIONS:
            l = tk.Label(nav, text=name, bg=CARD, fg=FG, font=FONTS["list"], anchor="w", padx=10, pady=7, cursor="hand2")
            l.pack(fill="x", pady=1)
            l.bind("<Button-1>", lambda e, n=name: self.show(n))
            self.nav[name] = l
        self.body = tk.Frame(w, bg=BG, padx=26, pady=20)
        self.body.pack(side="left", fill="both", expand=True)
        self.show("Highlights")

    # ---- helpers
    def changed(self):
        self.app.save_global_soon()

    def clear(self, title, intro):
        for w in self.body.winfo_children():
            w.destroy()
        tk.Label(self.body, text=title, bg=BG, fg=FG, font=FONTS["title"], anchor="w").pack(fill="x")
        tk.Label(self.body, text=intro, bg=BG, fg=MUTED, font=FONTS["body"], justify="left", anchor="w",
                 wraplength=620).pack(fill="x", pady=(6, 16))

    def row(self, parent, label, widget_fn, pady=6):
        r = tk.Frame(parent, bg=BG)
        r.pack(fill="x", pady=pady)
        tk.Label(r, text=label, bg=BG, fg=MUTED, font=FONTS["body"], width=22, anchor="w").pack(side="left")
        w = widget_fn(r)
        w.pack(side="left")
        return w

    def toggle(self, parent, section, key, text="", after=None):
        def cb(v):
            self.g[section][key] = v
            self.changed()
            if after:
                after(v)
        t = Toggle(parent, text, cb, bg=BG)
        t.set(self.g[section].get(key))
        return t

    def show(self, name):
        for n, l in self.nav.items():
            sel = n == name
            l.config(bg=ACCENT if sel else CARD, fg="#000000" if sel else FG, font=FONTS["bold"] if sel else FONTS["list"])
        getattr(self, "page_" + name.split()[0].lower().replace("&", ""))()

    # ---- pages
    def page_highlights(self):
        self.clear("Key highlights", "Keep chosen keys in a fixed colour on top of every effect, for example WASD for "
                                     "games or your favourite shortcuts.")
        h = self.g["highlights"]
        top = tk.Frame(self.body, bg=BG)
        top.pack(fill="x")
        self.toggle(top, "highlights", "enabled", "Show highlights").pack(side="left")
        add = Dropdown(top, list(rfx.HIGHLIGHT_PRESETS) + ["Custom keys"], self.add_group, width=14)
        add.set_text("+ Add keys")
        add.pack(side="right")
        self.groups_frame = tk.Frame(self.body, bg=BG)
        self.groups_frame.pack(fill="x", pady=(14, 0))
        self.hint = tk.Label(self.body, text="Key names: A–Z, 0–9, F1–F12, ESC, TAB, SPACE, ENTER, BACKSPACE, UP, DOWN, "
                                             "LEFT, RIGHT, LEFTSHIFT, LEFTCTRL, LEFTALT, LEFTMETA, INSERT, DELETE, HOME, END…",
                             bg=BG, fg=FAINT, font=FONTS["small"], justify="left", wraplength=620, anchor="w")
        self.hint.pack(fill="x", pady=(10, 0))
        self.build_groups()

    def build_groups(self):
        for w in self.groups_frame.winfo_children():
            w.destroy()
        groups = self.g["highlights"]["groups"]
        if not groups:
            tk.Label(self.groups_frame, text="No highlighted keys yet. Use “+ Add keys”.", bg=BG, fg=MUTED,
                     font=FONTS["body"]).pack(anchor="w")
        for i, grp in enumerate(groups):
            r = tk.Frame(self.groups_frame, bg=CARD, padx=12, pady=8)
            r.pack(fill="x", pady=3)
            Swatch(r, grp.get("color", "#ff0000"), lambda c, g=grp: (g.update(color=c), self.changed()),
                   width=96).pack(side="left")
            var = tk.StringVar(value=" ".join(grp.get("keys", [])))
            e = tk.Entry(r, textvariable=var, bg=INPUT, fg=FG, insertbackground=FG, relief="flat",
                         font=FONTS["mono"], highlightthickness=0, width=46)
            e.pack(side="left", padx=12, ipady=5, fill="x", expand=True)
            note = tk.Label(r, text="", bg=CARD, fg="#e0a030", font=FONTS["small"])
            note.pack(side="left")

            def save_keys(*_a, g=grp, v=var, n=note):
                keys = [k.upper() for k in v.get().replace(",", " ").split()]
                unknown = [k for k in keys if k not in rfx.PHYSICAL]
                g["keys"] = [k for k in keys if k in rfx.PHYSICAL]
                n.config(text=("Unknown: " + " ".join(unknown)) if unknown else "")
                self.changed()
            var.trace_add("write", save_keys)
            x = tk.Label(r, text="✕", bg=CARD, fg=MUTED, font=FONTS["body"], cursor="hand2", padx=6)
            x.pack(side="right")
            x.bind("<Button-1>", lambda e, i=i: self.remove_group(i))

    def add_group(self, i):
        names = list(rfx.HIGHLIGHT_PRESETS) + ["Custom keys"]
        name = names[i]
        colors = ["#ff2020", "#00e5ff", "#ffd000", "#ff00c8", "#44d62c", "#ffffff"]
        color = colors[len(self.g["highlights"]["groups"]) % len(colors)]
        self.g["highlights"]["groups"].append({"name": name, "keys": list(rfx.HIGHLIGHT_PRESETS.get(name, [])),
                                               "color": color})
        self.g["highlights"]["enabled"] = True
        self.changed()
        self.page_highlights()

    def remove_group(self, i):
        del self.g["highlights"]["groups"][i]
        self.changed()
        self.build_groups()

    def page_status(self):
        self.clear("Status keys", "Show what's going on, on top of every effect: lock keys glow while they're on, "
                                  "Esc pulses red on low battery, and a key of your choice turns red while your "
                                  "microphone is muted.")
        sk = self.g["status_keys"]
        self.row(self.body, "Status keys", lambda p: self.toggle(p, "status_keys", "enabled", "On"))
        self.row(self.body, "Lock key colour", lambda p: Swatch(p, sk.get("color", "#ffffff"),
                 lambda c: (sk.update(color=c), self.changed()), bg=BG))
        self.row(self.body, "Low battery warning", lambda p: self.toggle(p, "status_keys", "battery", "Pulse Esc"))
        self.row(self.body, "Warn below", lambda p: Slider(p, 5, 50, 1, lambda v: (sk.update(battery_level=int(v)),
                 self.changed()), width=260, bg=BG)).set(sk.get("battery_level", 20))
        keys = ["Off"] + [f"F{i}" for i in range(1, 13)] + ["PAUSE", "SCROLLLOCK", "INSERT", "ESC", "GRAVE"]

        def pick(i):
            sk["mic_key"] = "" if i == 0 else keys[i]
            self.changed()
        dd = self.row(self.body, "Mic muted key", lambda p: Dropdown(p, keys, pick, width=12))
        dd.set_text(sk.get("mic_key") or "Off")
        b = battery_text()
        tk.Label(self.body, text=b, bg=BG, fg=FAINT, font=FONTS["small"], anchor="w").pack(fill="x", pady=(14, 0))

    def page_night(self):
        self.clear("Night & idle", "Dim everything at night, and switch the lights off when you haven't touched the "
                                   "keyboard or mouse for a while. Both apply to every effect.")
        n, idle = self.g["night"], self.g["idle_off"]
        self.row(self.body, "Night mode", lambda p: self.toggle(p, "night", "enabled", "On"))

        def time_dd(p, key):
            d = Dropdown(p, self.TIMES, lambda i: (n.update({key: self.TIMES[i]}), self.changed()), width=7)
            d.set_text(n.get(key, "23:00"))
            return d
        self.row(self.body, "From", lambda p: time_dd(p, "start"))
        self.row(self.body, "Until", lambda p: time_dd(p, "end"))
        self.row(self.body, "Night brightness (%)", lambda p: Slider(p, 5, 100, 5, lambda v: (n.update(brightness=int(v)),
                 self.changed()), width=260, bg=BG)).set(n.get("brightness", 30))
        tk.Frame(self.body, bg=BORDER, height=1).pack(fill="x", pady=16)
        self.row(self.body, "Lights off when idle", lambda p: self.toggle(p, "idle_off", "enabled", "On"))
        self.row(self.body, "After (minutes)", lambda p: Slider(p, 1, 60, 1, lambda v: (idle.update(minutes=int(v)),
                 self.changed()), width=260, bg=BG)).set(idle.get("minutes", 10))
        works = idle_seconds_available()
        tk.Label(self.body, text="Idle time is read from GNOME." if works else
                 "Couldn't read idle time on this desktop (works on GNOME, or install xprintidle on X11).",
                 bg=BG, fg=FAINT if works else "#e0a030", font=FONTS["small"], anchor="w").pack(fill="x", pady=(10, 0))

    def page_app(self):
        self.clear("App profiles", "Switch effects automatically while certain apps are running, for example Fire "
                                   "while Steam is open, and switch back when they close. Rules are checked top to "
                                   "bottom. This keeps working when the window is closed.")
        prof = self.g["profiles"]

        def on_toggle(v):
            (start_watcher if v else stop_watcher)()
            self.app.root.after(600, self.page_app_status)
        top = tk.Frame(self.body, bg=BG)
        top.pack(fill="x")
        self.toggle(top, "profiles", "enabled", "Use app profiles", after=on_toggle).pack(side="left")
        ttk.Button(top, text="+ Add rule", style="Small.TButton", command=self.add_rule).pack(side="right")
        self.watch_status = tk.Label(self.body, text="", bg=BG, fg=FAINT, font=FONTS["small"], anchor="w")
        self.watch_status.pack(fill="x", pady=(6, 0))
        self.rules_frame = tk.Frame(self.body, bg=BG)
        self.rules_frame.pack(fill="x", pady=(10, 0))
        self.build_rules()
        self.page_app_status()

    def page_app_status(self):
        if not getattr(self, "watch_status", None) or not self.watch_status.winfo_exists():
            return
        on = watcher_pid() is not None
        self.watch_status.config(text="Watching for apps." if on else
                                 ("Not running." if not self.g["profiles"].get("enabled") else "Starting…"))

    def build_rules(self):
        for w in self.rules_frame.winfo_children():
            w.destroy()
        rules = self.g["profiles"]["rules"]
        effects = effect_order()
        labels = [pretty(n) for n in effects]
        if not rules:
            tk.Label(self.rules_frame, text="No rules yet. Use “+ Add rule”.", bg=BG, fg=MUTED,
                     font=FONTS["body"]).pack(anchor="w")
        procs = sorted(p for p in user_processes() if len(p) > 2 and not p.startswith(("kworker", "(")))
        for i, rule in enumerate(rules):
            r = tk.Frame(self.rules_frame, bg=CARD, padx=12, pady=8)
            r.pack(fill="x", pady=3)
            tk.Label(r, text="When", bg=CARD, fg=MUTED, font=FONTS["body"]).pack(side="left")
            var = tk.StringVar(value=rule.get("app", ""))
            e = tk.Entry(r, textvariable=var, bg=INPUT, fg=FG, insertbackground=FG, relief="flat",
                         font=FONTS["body"], highlightthickness=0, width=16)
            e.pack(side="left", padx=8, ipady=5)
            var.trace_add("write", lambda *_a, rl=rule, v=var: (rl.update(app=v.get().strip()), self.changed()))
            pick = Dropdown(r, procs[:60] or ["(none found)"], lambda j, v=var, ps=procs: ps and v.set(ps[j]), width=2)
            pick.set_text("…")
            pick.pack(side="left")
            tk.Label(r, text="is running, use", bg=CARD, fg=MUTED, font=FONTS["body"]).pack(side="left", padx=(10, 8))
            eff = Dropdown(r, labels, lambda j, rl=rule: (rl.update(effect=effects[j]), self.changed()), width=16)
            eff.set_text(pretty(rule["effect"]) if rule.get("effect") else "Choose effect")
            eff.pack(side="left")
            x = tk.Label(r, text="✕", bg=CARD, fg=MUTED, font=FONTS["body"], cursor="hand2", padx=6)
            x.pack(side="right")
            x.bind("<Button-1>", lambda ev, i=i: self.remove_rule(i))

    def add_rule(self):
        self.g["profiles"]["rules"].append({"app": "", "effect": ""})
        self.changed()
        self.build_rules()

    def remove_rule(self, i):
        del self.g["profiles"]["rules"][i]
        self.changed()
        self.build_rules()

    def page_shortcuts(self):
        self.clear("Keyboard shortcuts", "Switch effects without opening the app. Razor Sharp can add these to GNOME's "
                                         "keyboard shortcuts for you, or you can bind the commands yourself.")
        for sid, name, opt, binding in SHORTCUTS:
            r = tk.Frame(self.body, bg=CARD, padx=12, pady=8)
            r.pack(fill="x", pady=3)
            tk.Label(r, text=name.split(": ", 1)[1].capitalize(), bg=CARD, fg=FG, font=FONTS["body"], width=20,
                     anchor="w").pack(side="left")
            tk.Label(r, text=binding.replace("><", " + ").strip("<>").replace(">", " + "), bg=CARD, fg=ACCENT,
                     font=FONTS["mono"], width=22, anchor="w").pack(side="left")
            tk.Label(r, text=cli_command(opt).replace(sys.executable + " ", "python3 "), bg=CARD, fg=MUTED,
                     font=FONTS["mono"], anchor="w").pack(side="left")
        state = gnome_shortcuts_installed()
        btns = tk.Frame(self.body, bg=BG)
        btns.pack(fill="x", pady=(16, 0))
        self.sc_status = tk.Label(self.body, text="", bg=BG, fg=FAINT, font=FONTS["small"], anchor="w", justify="left")
        self.sc_status.pack(fill="x", pady=(10, 0))
        if state is None:
            self.sc_status.config(text="GNOME's settings aren't available here. Add the commands above as custom "
                                       "shortcuts in your desktop's keyboard settings.")
            return
        ttk.Button(btns, text="Remove shortcuts" if state else "Add to GNOME shortcuts",
                   style="Small.TButton" if state else "Accent.TButton",
                   command=lambda: self.set_shortcuts(not state)).pack(side="left")
        self.sc_status.config(text="Installed. Change the keys any time in Settings → Keyboard → Keyboard Shortcuts."
                              if state else "")

    def set_shortcuts(self, add):
        try:
            set_gnome_shortcuts(add)
        except (OSError, RuntimeError, subprocess.SubprocessError) as e:
            messagebox.showerror(APP_NAME, f"Couldn't change GNOME's shortcuts:\n\n{e}", parent=self.win)
            return
        self.page_shortcuts()

    def page_backup(self):
        self.clear("Backup", "Save all your settings (effect settings, presets, highlights, profiles, key layouts "
                             "and your own effects) to one file, to keep or move to another computer.")
        btns = tk.Frame(self.body, bg=BG)
        btns.pack(fill="x")
        ttk.Button(btns, text="Export…", style="Accent.TButton", command=self.do_export).pack(side="left")
        ttk.Button(btns, text="Import…", command=self.do_import).pack(side="left", padx=(10, 0))
        self.bk_status = tk.Label(self.body, text="", bg=BG, fg=MUTED, font=FONTS["body"], anchor="w")
        self.bk_status.pack(fill="x", pady=(14, 0))

    def do_export(self):
        path = filedialog.asksaveasfilename(parent=self.win, title="Export Razor Sharp settings",
                                            defaultextension=".json", initialfile="razor-sharp-backup.json",
                                            filetypes=[("Razor Sharp backup", "*.json")])
        if path:
            self.app.flush_save()
            self.app.save_global_now()
            n = export_backup(path)
            self.bk_status.config(text=f"Saved {n} files to {path}")

    def do_import(self):
        path = filedialog.askopenfilename(parent=self.win, title="Import Razor Sharp settings",
                                          filetypes=[("Razor Sharp backup", "*.json")])
        if not path:
            return
        try:
            n = import_backup(path)
        except (OSError, ValueError) as e:
            messagebox.showerror(APP_NAME, str(e), parent=self.win)
            return
        self.app.gcfg.clear()
        self.app.gcfg.update(rfx.load_global())
        self.app.cfg_name = None
        self.app.refresh_presets()
        self.app.refresh()
        self.app.detect_device()
        self.bk_status.config(text=f"Imported {n} files.")

    def page_performance(self):
        self.clear("Performance", "A lower frame rate uses less CPU and battery. 40 is smooth; 20–30 is fine for "
                                  "most effects.")
        opts = ["20", "30", "40", "60"]

        def pick(i):
            self.g["fps"] = int(opts[i])
            self.changed()
        d = self.row(self.body, "Frame rate (per second)", lambda p: Dropdown(p, opts, pick, width=5))
        d.set_text(str(self.g.get("fps", 40)))


def battery_text():
    b = rfx.battery_state()
    if not b:
        return "No battery found, so the low-battery warning won't show."
    return f"Battery now: {b[0]}% ({'discharging' if b[1] else 'charging or full'})."


def idle_seconds_available():
    return rfx.idle_seconds() is not None


# ---------------------------------------------------------------- key mapping
class KeyMapper:
    """Lights one matrix position at a time; you press the key that lit up. Saves a layout for your keyboard."""

    def __init__(self, app):
        self.app = app
        self.win = None
        try:
            self.kb = rfx.find_keyboard()
        except Exception:
            self.kb = None
        if self.kb is None:
            messagebox.showerror(APP_NAME, "No Razer keyboard found. Is OpenRazer installed and running?")
            return
        try:
            import evdev
            from evdev import ecodes
        except ImportError:
            messagebox.showerror(APP_NAME, "Key mapping needs python3-evdev:\n\nsudo apt install python3-evdev")
            return
        self.ecodes = ecodes
        self.inputs = []
        for path in evdev.list_devices():
            try:
                d = evdev.InputDevice(path)
            except OSError:
                continue
            if "razer" in d.name.lower() and ecodes.EV_KEY in d.capabilities():
                self.inputs.append(d)
        if not self.inputs:
            messagebox.showinfo(APP_NAME, "Razor Sharp can't read key presses yet, which mapping needs.\n\n"
                                          "Click “Allow” on the yellow banner, then log out and back in.")
            return
        if app.running_name:
            if not messagebox.askyesno(APP_NAME, "Mapping keys needs the keyboard to itself. Stop the running effect?"):
                return
            app.stop()

        adv = self.kb.fx.advanced
        self.rows, self.cols = adv.rows, adv.cols
        self.cells = [(r, c) for r in range(self.rows) for c in range(self.cols)]
        self.i = 0
        self.mapped = {}        # key name -> (r, c)
        self.history = []       # (cell, key name or None) in order, for Back
        self.names = {}
        for code, names in ecodes.KEY.items():
            names = names if isinstance(names, (list, tuple)) else [names]
            n = next((x for x in names if x.startswith("KEY_")), None)
            if n:
                self.names[code] = n[4:]
        self.build()
        self.light()
        self.poll()

    def build(self):
        w = self.win = tk.Toplevel(self.app.root, bg=BG, padx=24, pady=20)
        w.title(f"Map keys — {self.kb.name}")
        w.transient(self.app.root)
        w.resizable(False, False)
        w.protocol("WM_DELETE_WINDOW", self.cancel)
        tk.Label(w, text="Map your keys", bg=BG, fg=FG, font=FONTS["title"]).pack(anchor="w")
        tk.Label(w, text="One key on your keyboard is lit white. Press that key.\n"
                         "If nothing is lit, or the light isn't under a key, click “Nothing lit”.\n"
                         "Pressed the wrong key? Click Back. You can save at any time; "
                         "positions you haven't reached keep their current mapping.",
                 bg=BG, fg=MUTED, font=FONTS["body"], justify="left").pack(anchor="w", pady=(8, 14))
        self.progress = tk.Label(w, text="", bg=BG, fg=ACCENT, font=FONTS["bold"])
        self.progress.pack(anchor="w")
        self.bar = tk.Canvas(w, width=520, height=8, bg=CARD, highlightthickness=0)
        self.bar.pack(anchor="w", pady=(6, 10))
        self.last = tk.Label(w, text="", bg=BG, fg=FG, font=FONTS["body"], anchor="w")
        self.last.pack(anchor="w", fill="x")
        btns = tk.Frame(w, bg=BG)
        btns.pack(fill="x", pady=(18, 0))
        for text, cmd, style in (("Nothing lit", self.skip, "Accent.TButton"), ("Back", self.back, "TButton"),
                                 ("Save", self.save, "TButton"), ("Cancel", self.cancel, "TButton")):
            b = ttk.Button(btns, text=text, style=style, command=cmd, takefocus=False)
            b.pack(side="left", padx=(0, 8))
        w.focus_set()

    def light(self):
        if self.i >= len(self.cells):
            self.save()
            return
        adv = self.kb.fx.advanced
        target = self.cells[self.i]
        for r in range(self.rows):
            for c in range(self.cols):
                adv.matrix[r, c] = (255, 255, 255) if (r, c) == target else (0, 28, 0)
        adv.draw()
        r, c = target
        self.progress.config(text=f"Position {self.i + 1} of {len(self.cells)}  ·  row {r + 1}, column {c + 1}"
                                  f"  ·  {len(self.mapped)} keys mapped")
        self.bar.delete("all")
        self.bar.create_rectangle(0, 0, 520 * self.i / len(self.cells), 8, fill=ACCENT, outline="")

    def record(self, name):
        if name is not None and name in self.mapped:
            r, c = self.mapped[name]
            self.last.config(text=f"{rfx.LABELS.get(name, name)} is already mapped (row {r + 1}, column {c + 1}). "
                                  "Press the lit key, or click Back to change it.", fg="#e0a030")
            return
        cell = self.cells[self.i]
        if name is not None:
            self.mapped[name] = cell
            self.last.config(text=f"✓ {rfx.LABELS.get(name, name) or name}", fg=FG)
        else:
            self.last.config(text="Skipped", fg=MUTED)
        self.history.append((cell, name))
        self.i += 1
        self.light()

    def skip(self):
        self.record(None)

    def back(self):
        if not self.history:
            return
        cell, name = self.history.pop()
        if name:
            self.mapped.pop(name, None)
        self.i -= 1
        self.last.config(text="Went back one position.", fg=MUTED)
        self.light()

    def poll(self):
        if not self.win or not self.win.winfo_exists():
            return
        import select as _select
        try:
            ready, _, _ = _select.select(self.inputs, [], [], 0)
            for d in ready:
                for ev in d.read():
                    if ev.type == self.ecodes.EV_KEY and ev.value == 1:
                        name = self.names.get(ev.code)
                        if name and self.i < len(self.cells):
                            self.record(name)
        except (BlockingIOError, OSError):
            pass
        self.win.after(25, self.poll)

    def finish_lights(self):
        try:
            adv = self.kb.fx.advanced
            for r in range(self.rows):
                for c in range(self.cols):
                    adv.matrix[r, c] = (0, 0, 0)
            adv.draw()
        except Exception:
            pass

    def save(self):
        visited = {cell for cell, _ in self.history}
        keys = {k: v for k, v in self.app.layout.keys.items()
                if v not in visited and k not in self.mapped and 0 <= v[0] < self.rows and 0 <= v[1] < self.cols}
        keys.update(self.mapped)
        path = rfx.save_user_layout(self.kb.name, self.rows, self.cols, keys)
        self.finish_lights()
        self.win.destroy()
        self.app.detect_device()
        self.app.write_log(f"Saved your key layout ({len(keys)} keys) to {path}")
        messagebox.showinfo(APP_NAME, "Saved. Start an effect to use your new key layout.")

    def cancel(self):
        self.finish_lights()
        self.win.destroy()


def run_last_headless():
    """Used at login: start the last effect in the background without opening a window."""
    migrate_old_install()
    if rfx.load_global().get("profiles", {}).get("enabled"):
        start_watcher()
    name = last_effect()
    if not name:
        print("No effect has been run yet.")
        return
    if running_effect():
        print("An effect is already running.")
        return
    launch_effect(name)
    print(f"Started {pretty(name)} in the background.")


def main():
    if "--run-last" in sys.argv or "--autostart" in sys.argv:
        run_last_headless()
        return
    if "--version" in sys.argv:
        print(f"{APP_NAME} {__version__}")
        return
    if "--stop" in sys.argv:
        name = stop_effect()
        print(f"Stopped {pretty(name)}." if name else "No effect was running.")
        return
    if "--watch" in sys.argv:
        try:
            run_watcher()
        except KeyboardInterrupt:
            WATCH_FILE.unlink(missing_ok=True)
        return
    if "--effect" in sys.argv:
        i = sys.argv.index("--effect")
        wanted = " ".join(sys.argv[i + 1:]).strip()
        name = resolve_effect(wanted) if wanted else None
        if not name:
            print(f"No effect called “{wanted}”. Effects: " + ", ".join(pretty(n) for n in effect_order()))
            sys.exit(1)
        launch_effect(name)
        print(f"Started {pretty(name)}.")
        return
    if "--next" in sys.argv or "--previous" in sys.argv:
        name = cycle_effect(1 if "--next" in sys.argv else -1)
        print(f"Started {pretty(name)}." if name else "No effects found.")
        if name:
            notify(f"{pretty(name)}")
        return
    if "--toggle" in sys.argv:
        if running_effect():
            name = stop_effect()
            print(f"Stopped {pretty(name)}.")
        else:
            name = last_effect()
            if name:
                launch_effect(name)
                print(f"Started {pretty(name)}.")
        return
    if "--help" in sys.argv or "-h" in sys.argv:
        print(f"{APP_NAME} {__version__}\n\nUsage: razor-sharp [option]\n"
              "  (no option)        open the app\n"
              "  --effect NAME      start an effect, e.g. --effect \"matrix rain\"\n"
              "  --next/--previous  switch to the next/previous effect\n"
              "  --toggle           stop the running effect, or start the last one\n"
              "  --stop             stop the running effect\n"
              "  --run-last         start the last effect in the background (used at login)\n"
              "  --version          show the version")
        return
    notes = migrate_old_install()
    root = tk.Tk(className="RazorSharp")
    App(root, notes)
    root.mainloop()


if __name__ == "__main__":
    main()
