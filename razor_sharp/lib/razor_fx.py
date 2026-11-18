"""
razor_fx - the helper library behind Razor Sharp effects.

An effect is a small Python script:

    from razor_fx import Effect, mix

    CATEGORY = "Reactive"            # where it's listed in the app
    PARAMS = {                       # options shown in the app under "Effect options"
        "flash":  {"type": "color", "label": "Flash colour", "default": "#ffffff"},
        "fade":   {"type": "range", "label": "Fade (s)", "min": 0.1, "max": 3, "default": 0.8, "step": 0.1},
        "spread": {"type": "bool",  "label": "Light neighbours", "default": False},
    }

    fx = Effect(PARAMS)

    def frame(now):
        for row, col in fx.key_presses():          # keys pressed since the last frame
            ...
        for y in range(fx.rows):
            for x in range(fx.cols):
                fx.set(y, x, fx.base(y, x, now))   # base = lighting colours chosen in the app

    fx.run(frame)

Colours and brightness
    fx.base(y, x, t)     lighting colour of a key, at the lighting brightness
    fx.color("name")     a colour option, at the effect brightness
    fx.glow(colour)      any other colour the effect makes, at the effect brightness
    fx.light_colors()    the two lighting colours, at the lighting brightness
    mix(a, b, t), add(a, b, k), scale(c, k), hsv(h), gradient(stops, t)

Keys
    fx.key_presses()     [(row, col), ...] since the last call
    fx.key_events()      [("UP", row, col), ...]  key names too (use one of the two per frame)
    fx.pos("F1")         matrix (row, col) of a named key, or None if the keyboard doesn't have it
    fx.is_key(y, x)      whether a matrix cell is a real key

Settings changed in the app apply while the effect runs. While the screen is
blanked or locked the effect pauses and the keys go dark.
"""

import colorsys
import json
import math
import os
import re
import select
import subprocess
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
BUILTIN_LAYOUTS = APP_DIR / "layouts"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "razor-sharp"
USER_LAYOUTS = CONFIG_DIR / "layouts"
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "razor-sharp"
GLOBAL_FILE = DATA_DIR / "global.json"   # settings that apply to every effect

# ---------------------------------------------------------------- physical keyboard (for previews)
# key name -> (x, y, width, height) in key units, ANSI full-size. Names are evdev KEY_* without "KEY_".
PHYSICAL = {}


def _row(y, items):
    for item in items:
        name, x = item[0], item[1]
        w = item[2] if len(item) > 2 else 1.0
        h = item[3] if len(item) > 3 else 1.0
        PHYSICAL[name] = (x, y, w, h)


_row(0, [("ESC", 0), ("F1", 2), ("F2", 3), ("F3", 4), ("F4", 5), ("F5", 6.5), ("F6", 7.5), ("F7", 8.5),
         ("F8", 9.5), ("F9", 11), ("F10", 12), ("F11", 13), ("F12", 14),
         ("SYSRQ", 15.25), ("SCROLLLOCK", 16.25), ("PAUSE", 17.25)])
_row(1.25, [("GRAVE", 0)] + [(str((i + 1) % 10), 1 + i) for i in range(10)] +
     [("MINUS", 11), ("EQUAL", 12), ("BACKSPACE", 13, 2), ("INSERT", 15.25), ("HOME", 16.25), ("PAGEUP", 17.25),
      ("NUMLOCK", 18.5), ("KPSLASH", 19.5), ("KPASTERISK", 20.5), ("KPMINUS", 21.5)])
_row(2.25, [("TAB", 0, 1.5)] + [(k, 1.5 + i) for i, k in enumerate("QWERTYUIOP")] +
     [("LEFTBRACE", 11.5), ("RIGHTBRACE", 12.5), ("BACKSLASH", 13.5, 1.5), ("DELETE", 15.25), ("END", 16.25),
      ("PAGEDOWN", 17.25), ("KP7", 18.5), ("KP8", 19.5), ("KP9", 20.5), ("KPPLUS", 21.5, 1, 2)])
_row(3.25, [("CAPSLOCK", 0, 1.75)] + [(k, 1.75 + i) for i, k in enumerate("ASDFGHJKL")] +
     [("SEMICOLON", 10.75), ("APOSTROPHE", 11.75), ("ENTER", 12.75, 2.25), ("KP4", 18.5), ("KP5", 19.5), ("KP6", 20.5)])
_row(4.25, [("LEFTSHIFT", 0, 2.25)] + [(k, 2.25 + i) for i, k in enumerate("ZXCVBNM")] +
     [("COMMA", 9.25), ("DOT", 10.25), ("SLASH", 11.25), ("RIGHTSHIFT", 12.25, 2.75), ("UP", 16.25),
      ("KP1", 18.5), ("KP2", 19.5), ("KP3", 20.5), ("KPENTER", 21.5, 1, 2)])
_row(5.25, [("LEFTCTRL", 0, 1.25), ("LEFTMETA", 1.25, 1.25), ("LEFTALT", 2.5, 1.25), ("SPACE", 3.75, 6.25),
            ("RIGHTALT", 10, 1.25), ("FN", 11.25, 1.25), ("COMPOSE", 12.5, 1.25), ("RIGHTCTRL", 13.75, 1.25),
            ("LEFT", 15.25), ("DOWN", 16.25), ("RIGHT", 17.25), ("KP0", 18.5, 2), ("KPDOT", 20.5)])

LABELS = {
    "ESC": "Esc", "GRAVE": "`", "MINUS": "-", "EQUAL": "=", "BACKSPACE": "Bksp", "TAB": "Tab",
    "LEFTBRACE": "[", "RIGHTBRACE": "]", "BACKSLASH": "\\", "CAPSLOCK": "Caps", "SEMICOLON": ";",
    "APOSTROPHE": "'", "ENTER": "Enter", "LEFTSHIFT": "Shift", "COMMA": ",", "DOT": ".", "SLASH": "/",
    "RIGHTSHIFT": "Shift", "LEFTCTRL": "Ctrl", "LEFTMETA": "Super", "LEFTALT": "Alt", "SPACE": "",
    "RIGHTALT": "Alt", "FN": "Fn", "COMPOSE": "Menu", "RIGHTCTRL": "Ctrl", "SYSRQ": "Prt",
    "SCROLLLOCK": "Scr", "PAUSE": "Pse", "INSERT": "Ins", "HOME": "Home", "PAGEUP": "PgUp",
    "DELETE": "Del", "END": "End", "PAGEDOWN": "PgDn", "UP": "↑", "DOWN": "↓", "LEFT": "←", "RIGHT": "→",
    "NUMLOCK": "Num", "KPSLASH": "/", "KPASTERISK": "*", "KPMINUS": "-", "KPPLUS": "+", "KPENTER": "Ent",
    "KPDOT": ".", **{f"KP{i}": str(i) for i in range(10)},
}


# ---------------------------------------------------------------- layouts
class Layout:
    """Which matrix cell (row, col) each named key lights up."""

    def __init__(self, data, source=""):
        self.name = data.get("name", "Custom")
        self.rows = int(data.get("rows", 6))
        self.cols = int(data.get("cols", 18))
        self.verified = bool(data.get("verified", False))
        self.note = data.get("note", "")
        self.source = source
        self.keys = {k: (int(v[0]), int(v[1])) for k, v in data.get("keys", {}).items()}
        self.cells = set(self.keys.values())
        rows = [r for r, _ in self.cells] or [0, 5]
        cols = [c for _, c in self.cells] or [0, 16]
        self.bounds = (min(rows), max(rows), min(cols), max(cols))

    def pos(self, name):
        return self.keys.get(name)


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "keyboard"


def _read_layout(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def builtin_layouts():
    out = []
    for p in sorted(BUILTIN_LAYOUTS.glob("*.json")):
        data = _read_layout(p)
        if data:
            out.append((p, data))
    return out


def user_layout_path(device_name):
    return USER_LAYOUTS / (slug(device_name) + ".json")


def layout_for_device(device_name="", rows=6, cols=18):
    """The best layout for a keyboard: your own mapping first, then a built-in one."""
    user = _read_layout(user_layout_path(device_name)) if device_name else None
    if user:
        return Layout(user, "mapped")
    candidates = builtin_layouts()
    for p, data in candidates:
        if device_name and device_name in data.get("devices", []):
            return Layout(data, "built-in")
    for p, data in candidates:
        if int(data.get("cols", 0)) == cols and int(data.get("rows", 0)) == rows:
            return Layout(data, "built-in")
    if candidates:  # closest width
        p, data = min(candidates, key=lambda pd: abs(int(pd[1].get("cols", 0)) - cols))
        return Layout(data, "guessed")
    return Layout({"name": "Empty", "rows": rows, "cols": cols, "keys": {}}, "none")


def save_user_layout(device_name, rows, cols, keys):
    USER_LAYOUTS.mkdir(parents=True, exist_ok=True)
    data = {"name": f"{device_name} (mapped)", "verified": True, "devices": [device_name],
            "rows": rows, "cols": cols, "keys": {k: list(v) for k, v in keys.items()}}
    path = user_layout_path(device_name)
    path.write_text(json.dumps(data, indent=1))
    return path


# ---------------------------------------------------------------- colours
DEFAULTS = {
    "mode": "gradient",        # solid | gradient | rainbow | spectrum | breathing
    "color_a": "#44d62c",
    "color_b": "#00a2ff",
    "direction": "horizontal", # horizontal | vertical | diagonal | center
    "reverse": False,
    "animate": False,
    "anim_speed": 1.0,
    "brightness": 100,         # lighting (background) brightness
    "effect_brightness": 100,  # brightness of what the effect itself draws
}
DEFAULT_BOUNDS = (0, 5, 0, 16)
LAYOUT_COLS = 17   # kept for older effect scripts


def hex_to_rgb(h):
    h = str(h).lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in c)


def mix(a, b, t):
    """Blend colour a towards colour b (t = 0..1)."""
    t = max(0.0, min(1.0, t))
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def scale(c, k):
    return tuple(v * k for v in c)


def add(a, b, k=1.0):
    """Add colour b (times k) on top of colour a, like light."""
    return tuple(min(255.0, a[i] + b[i] * k) for i in range(3))


def gradient(stops, t):
    """Colour at t (0..1) along [(pos, (r, g, b)), ...] stops."""
    t = max(0.0, min(1.0, t))
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if t <= p1:
            return mix(c0, c1, (t - p0) / (p1 - p0) if p1 > p0 else 0)
    return stops[-1][1]


def hsv(h, s=1.0, v=1.0):
    return tuple(x * 255 for x in colorsys.hsv_to_rgb(h % 1.0, s, v))


def apply_brightness(c, brightness):
    return scale(c, max(0, min(100, float(brightness))) / 100.0)


def _position(cfg, y, x, bounds):
    r0, r1, c0, c1 = bounds
    nx = min(max((x - c0) / max(1, c1 - c0), 0.0), 1.0)
    ny = min(max((y - r0) / max(1, r1 - r0), 0.0), 1.0)
    d = cfg.get("direction", "horizontal")
    if d == "vertical":
        p = ny
    elif d == "diagonal":
        p = (nx + ny * 0.5) / 1.5
    elif d == "center":
        p = min(1.0, math.hypot(nx - 0.5, (ny - 0.5) * 0.35) / 0.5)
    else:
        p = nx
    return 1.0 - p if cfg.get("reverse") else p


def palette_color(cfg, y, x, t, bounds=DEFAULT_BOUNDS):
    """Lighting colour of matrix cell (y, x) at time t, before brightness."""
    mode = cfg.get("mode", "solid")
    a = hex_to_rgb(cfg.get("color_a", DEFAULTS["color_a"]))
    b = hex_to_rgb(cfg.get("color_b", DEFAULTS["color_b"]))
    speed = float(cfg.get("anim_speed", 1.0))
    if mode == "solid":
        return a
    if mode == "spectrum":
        return hsv(t * speed * 0.1)
    if mode == "breathing":
        return mix(a, b, 0.5 - 0.5 * math.cos(t * speed * 2.0))
    p = _position(cfg, y, x, bounds)
    if mode == "rainbow":
        if cfg.get("animate"):
            p += t * speed * 0.2
        return hsv(p)
    if cfg.get("animate"):
        u = (p * 0.5 + t * speed * 0.15) % 1.0
        p = 1.0 - abs(2.0 * u - 1.0)   # flows A -> B -> A without a hard edge
    return mix(a, b, p)


def load_config(path=None, params=None):
    """Settings with defaults filled in, for the lighting and the effect's PARAMS."""
    cfg = dict(DEFAULTS)
    cfg["params"] = {k: v.get("default") for k, v in (params or {}).items()}
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for k in DEFAULTS:
                if k in data:
                    cfg[k] = data[k]
            for k, v in data.get("params", {}).items():
                if k in cfg["params"]:
                    cfg["params"][k] = v
        except (OSError, ValueError):
            pass
    return cfg


def find_keyboard():
    """The first OpenRazer keyboard with per-key lighting, or None."""
    from openrazer.client import DeviceManager
    dm = DeviceManager()
    dm.sync_effects = False
    return next((d for d in dm.devices if d.type == "keyboard" and d.has("lighting_led_matrix")), None)


# ---------------------------------------------------------------- settings for every effect
GLOBAL_DEFAULTS = {
    "highlights": {"enabled": False, "groups": []},     # groups: [{"name", "keys": [...], "color"}]
    "status_keys": {"enabled": True, "color": "#ffffff", "battery": True, "battery_level": 20, "mic_key": ""},
    "night": {"enabled": False, "start": "23:00", "end": "07:00", "brightness": 30},
    "idle_off": {"enabled": False, "minutes": 10},
    "fps": 40,
    "profiles": {"enabled": False, "rules": []},       # rules: [{"app", "effect"}]
}
HIGHLIGHT_PRESETS = {
    "WASD": ["W", "A", "S", "D"],
    "Arrow keys": ["UP", "DOWN", "LEFT", "RIGHT"],
    "Function keys": [f"F{i}" for i in range(1, 13)],
    "Number row": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
    "Modifiers": ["LEFTCTRL", "LEFTSHIFT", "LEFTALT", "LEFTMETA", "RIGHTCTRL", "RIGHTSHIFT", "RIGHTALT"],
    "Copy & paste": ["LEFTCTRL", "C", "V", "X", "Z"],
    "Escape": ["ESC"],
}


def load_global(path=None):
    path = Path(path) if path else GLOBAL_FILE
    cfg = json.loads(json.dumps(GLOBAL_DEFAULTS))
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return cfg
    for k, v in data.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        elif k in cfg:
            cfg[k] = v
    return cfg


def save_global(cfg, path=None):
    path = Path(path) if path else GLOBAL_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2))
    tmp.replace(path)


def _minutes(hhmm):
    try:
        h, m = str(hhmm).split(":")
        return (int(h) % 24) * 60 + int(m) % 60
    except ValueError:
        return 0


def night_factor(gcfg, now_struct=None):
    """Brightness multiplier from night mode (1.0 outside the night window)."""
    n = gcfg.get("night", {})
    if not n.get("enabled"):
        return 1.0
    t = now_struct or time.localtime()
    cur = t.tm_hour * 60 + t.tm_min
    a, b = _minutes(n.get("start", "23:00")), _minutes(n.get("end", "07:00"))
    inside = (a <= cur < b) if a <= b else (cur >= a or cur < b)
    return max(0.0, min(1.0, float(n.get("brightness", 30)) / 100.0)) if inside else 1.0


def lock_states():
    """{'CAPSLOCK': bool, 'NUMLOCK': bool, 'SCROLLLOCK': bool} from the kernel's keyboard LEDs (no permissions needed)."""
    out = {"CAPSLOCK": False, "NUMLOCK": False, "SCROLLLOCK": False}
    for key, suffix in (("CAPSLOCK", "capslock"), ("NUMLOCK", "numlock"), ("SCROLLLOCK", "scrolllock")):
        for f in Path("/sys/class/leds").glob(f"*::{suffix}/brightness"):
            try:
                if int(f.read_text().strip() or 0) > 0:
                    out[key] = True
                    break
            except (OSError, ValueError):
                pass
    return out


def battery_state():
    """(percent, discharging) of the laptop battery, or None on desktops."""
    for b in sorted(Path("/sys/class/power_supply").glob("BAT*")):
        try:
            pct = int((b / "capacity").read_text().strip())
            status = (b / "status").read_text().strip().lower()
            return pct, status == "discharging"
        except (OSError, ValueError):
            continue
    return None


def mic_muted():
    try:
        out = subprocess.run(["pactl", "get-source-mute", "@DEFAULT_SOURCE@"],
                             capture_output=True, text=True, timeout=1).stdout
        return "yes" in out.lower()
    except (OSError, subprocess.SubprocessError):
        return False


def idle_seconds():
    """Seconds since the last keyboard/mouse input on GNOME (Mutter); None if unknown."""
    try:
        out = subprocess.run(["gdbus", "call", "--session", "--dest", "org.gnome.Mutter.IdleMonitor",
                              "--object-path", "/org/gnome/Mutter/IdleMonitor/Core",
                              "--method", "org.gnome.Mutter.IdleMonitor.GetIdletime"],
                             capture_output=True, text=True, timeout=1).stdout
        nums = re.findall(r"\d+", out.replace("uint64", ""))
        if nums:
            return int(nums[-1]) / 1000.0
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        out = subprocess.run(["xprintidle"], capture_output=True, text=True, timeout=1).stdout
        return int(out.strip()) / 1000.0
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


class Globals:
    """Reads the shared settings (reloading when they change) and keeps live status up to date."""

    def __init__(self, path=None):
        self.path = Path(path) if path else GLOBAL_FILE
        self.cfg = load_global(self.path)
        self._mtime = self._mt()
        self._next = {"reload": 0.0, "locks": 0.0, "battery": 0.0, "mic": 0.0, "night": 0.0}
        self.locks, self.battery, self.mic, self.dim = lock_states(), battery_state(), False, night_factor(self.cfg)

    def _mt(self):
        try:
            return self.path.stat().st_mtime
        except OSError:
            return None

    def update(self, now):
        n = self._next
        if now >= n["reload"]:
            n["reload"] = now + 0.5
            m = self._mt()
            if m != self._mtime:
                self._mtime = m
                self.cfg = load_global(self.path)
                n["night"] = n["mic"] = 0.0
        sk = self.cfg["status_keys"]
        if sk.get("enabled") and now >= n["locks"]:
            n["locks"] = now + 0.3
            self.locks = lock_states()
        if sk.get("enabled") and sk.get("battery") and now >= n["battery"]:
            n["battery"] = now + 30
            self.battery = battery_state()
        if sk.get("enabled") and sk.get("mic_key") and now >= n["mic"]:
            n["mic"] = now + 2
            self.mic = mic_muted()
        if now >= n["night"]:
            n["night"] = now + 20
            self.dim = night_factor(self.cfg)

    def overlay(self, fx, now):
        """{(row, col): colour} drawn on top of every effect."""
        out = {}
        h = self.cfg["highlights"]
        if h.get("enabled"):
            for g in h.get("groups", []):
                try:
                    col = hex_to_rgb(g.get("color", "#ff0000"))
                except ValueError:
                    continue
                for p in fx.positions(g.get("keys", [])):
                    out[p] = col
        sk = self.cfg["status_keys"]
        if sk.get("enabled"):
            col = hex_to_rgb(sk.get("color", "#ffffff"))
            for key, on in self.locks.items():
                p = fx.pos(key)
                if on and p:
                    out[p] = col
            if sk.get("battery") and self.battery:
                pct, discharging = self.battery
                p = fx.pos("ESC")
                if discharging and pct <= int(sk.get("battery_level", 20)) and p:
                    out[p] = scale((255, 30, 0), 0.35 + 0.65 * (0.5 + 0.5 * math.sin(now * 4)))
            if sk.get("mic_key") and self.mic:
                p = fx.pos(sk["mic_key"])
                if p:
                    out[p] = (255, 0, 0)
        return out


# ---------------------------------------------------------------- effect runner
class Effect:
    def __init__(self, params=None, keyboard_name="razer"):
        self.params = params or {}
        self.cfg_path = os.environ.get("RAZER_FX_CONFIG") or os.environ.get("RAZOR_FX_CONFIG")
        self.cfg = load_config(self.cfg_path, self.params)
        self._mtime = self._cfg_mtime()
        self._last_check = 0.0
        self._keyboard_name = keyboard_name.lower()
        self._inputs = None
        self._keymap = {}

        self.kb = find_keyboard()
        if self.kb is None:
            raise SystemExit("No OpenRazer keyboard with per-key lighting found. Is OpenRazer running?")
        self.rows = self.kb.fx.advanced.rows
        self.cols = self.kb.fx.advanced.cols
        self.layout = layout_for_device(self.kb.name, self.rows, self.cols)
        self.bounds = self.layout.bounds
        self.globals = Globals()
        self._dim = self.globals.dim
        print(f"{self.kb.name}: {self.rows}x{self.cols} matrix, layout: {self.layout.name} ({self.layout.source})",
              flush=True)

    # settings
    def param(self, name, default=None):
        v = self.cfg["params"].get(name)
        if v is None:
            v = self.params.get(name, {}).get("default", default)
        return v

    def color(self, name, default="#ffffff"):
        """A colour option, at the effect brightness."""
        return self.glow(hex_to_rgb(self.param(name, default) or default))

    def glow(self, c):
        """Scale a colour the effect makes itself (sparks, rings, white flashes...) by the effect brightness."""
        return apply_brightness(c, self.cfg.get("effect_brightness", 100))

    def base(self, y, x, t=None):
        """The lighting colour of a key, at the lighting brightness."""
        c = palette_color(self.cfg, y, x, time.monotonic() if t is None else t, self.bounds)
        return apply_brightness(c, self.cfg.get("brightness", 100))

    def light_colors(self):
        """The two lighting colours (A, B), at the lighting brightness."""
        b = self.cfg.get("brightness", 100)
        return (apply_brightness(hex_to_rgb(self.cfg["color_a"]), b),
                apply_brightness(hex_to_rgb(self.cfg["color_b"]), b))

    def _cfg_mtime(self):
        try:
            return os.path.getmtime(self.cfg_path) if self.cfg_path else None
        except OSError:
            return None

    def _maybe_reload(self):
        now = time.monotonic()
        if now - self._last_check < 0.25:
            return
        self._last_check = now
        m = self._cfg_mtime()
        if m != self._mtime:
            self._mtime = m
            self.cfg = load_config(self.cfg_path, self.params)

    # keys
    def pos(self, name):
        """Matrix (row, col) of a key by name, e.g. fx.pos("F1"); None if this keyboard doesn't have it."""
        p = self.layout.pos(name)
        if p is None or not (0 <= p[0] < self.rows and 0 <= p[1] < self.cols):
            return None
        return p

    def positions(self, names):
        """Matrix positions of the named keys this keyboard has, in order."""
        return [p for p in (self.pos(n) for n in names) if p is not None]

    def is_key(self, y, x):
        """True if matrix cell (y, x) is a real key on the keyboard."""
        return (y, x) in self.layout.cells

    def _open_inputs(self):
        self._inputs = []
        try:
            import evdev
            from evdev import ecodes
        except ImportError:
            print("python3-evdev is not installed, so key presses can't be read.", flush=True)
            return
        self._ev_key = ecodes.EV_KEY
        for name, (r, c) in self.layout.keys.items():
            code = getattr(ecodes, "KEY_" + name, None)
            if code is not None and 0 <= r < self.rows and 0 <= c < self.cols:
                self._keymap[code] = (name, r, c)
        for path in evdev.list_devices():
            try:
                d = evdev.InputDevice(path)
            except OSError:
                continue
            if self._keyboard_name in d.name.lower() and ecodes.EV_KEY in d.capabilities():
                self._inputs.append(d)
        if not self._inputs:
            print("Can't read key presses yet. Open Razor Sharp and click “Allow” on the banner "
                  "(or run: sudo gpasswd -a $USER input), then log out and back in.", flush=True)

    def key_events(self, repeats=False):
        """List of (key name, row, col) for keys pressed since the last call, e.g. ("UP", 4, 15).
        repeats=True also includes the auto-repeat while a key is held (handy for games)."""
        if self._inputs is None:
            self._open_inputs()
        out = []
        if not self._inputs:
            return out
        ready, _, _ = select.select(self._inputs, [], [], 0)
        for d in ready:
            try:
                for ev in d.read():
                    if ev.type == self._ev_key and (ev.value == 1 or (repeats and ev.value == 2)) \
                            and ev.code in self._keymap:
                        out.append(self._keymap[ev.code])
            except (BlockingIOError, OSError):
                pass
        return out

    def key_presses(self):
        """List of (row, col) for keys pressed since the last call. Use this OR key_events each frame."""
        return [(r, c) for _name, r, c in self.key_events()]

    # drawing
    def set(self, y, x, rgb):
        d = self._dim
        self.kb.fx.advanced.matrix[y, x] = tuple(max(0, min(255, int(v * d))) for v in rgb)

    def draw(self, now=None):
        now = time.monotonic() if now is None else now
        try:
            for (y, x), c in self.globals.overlay(self, now).items():
                self.set(y, x, c)
        except Exception as e:  # an overlay problem must never stop the effect
            print(f"Overlay error: {e}", flush=True)
        self.kb.fx.advanced.draw()
        self._maybe_reload()

    def blank(self):
        try:
            for y in range(self.rows):
                for x in range(self.cols):
                    self.kb.fx.advanced.matrix[y, x] = (0, 0, 0)
            self.kb.fx.advanced.draw()
        except Exception:
            pass

    def restore(self):
        """Leave the keyboard showing the chosen lighting colours (frozen)."""
        try:
            t = time.monotonic()
            for y in range(self.rows):
                for x in range(self.cols):
                    self.set(y, x, self.base(y, x, t))
            self.kb.fx.advanced.draw()
        except Exception:
            pass

    # main loop
    def run(self, frame, fps=40):
        """Calls frame(now) and draws, fps times a second, until stopped (Ctrl+C / Stop in the app)."""
        paused = None
        next_check = 0.0
        try:
            while True:
                t0 = time.monotonic()
                self.globals.update(t0)
                self._dim = self.globals.dim
                period = 1.0 / max(5, min(fps, int(self.globals.cfg.get("fps", 40) or 40)))
                if t0 >= next_check:
                    next_check = t0 + 1.5
                    reason = None
                    if screen_locked():
                        reason = "Screen off/locked"
                    else:
                        idle_cfg = self.globals.cfg["idle_off"]
                        if idle_cfg.get("enabled"):
                            idle = idle_seconds()
                            if idle is not None and idle >= float(idle_cfg.get("minutes", 10)) * 60:
                                reason = "No input for a while"
                    if reason and not paused:
                        print(f"{reason}: lights paused.", flush=True)
                        self.blank()
                    elif paused and not reason:
                        print("Welcome back: resuming.", flush=True)
                        next_check = t0 + 0.5
                    paused = reason
                if paused:
                    self.key_events()   # throw away presses made while away
                    time.sleep(0.25 if paused.startswith("Screen") else 0.15)
                    if not paused.startswith("Screen"):
                        next_check = min(next_check, time.monotonic() + 0.3)  # wake fast on input
                    continue
                frame(t0)
                self.draw(t0)
                time.sleep(max(0.0, period - (time.monotonic() - t0)))
        except KeyboardInterrupt:
            pass
        finally:
            self.restore()


def screen_locked():
    """True while the desktop screensaver is active (screen blanked or locked)."""
    for dest, path in (("org.gnome.ScreenSaver", "/org/gnome/ScreenSaver"),
                       ("org.freedesktop.ScreenSaver", "/org/freedesktop/ScreenSaver")):
        try:
            out = subprocess.run(["gdbus", "call", "--session", "--dest", dest, "--object-path", path,
                                  "--method", dest + ".GetActive"],
                                 capture_output=True, text=True, timeout=1).stdout
        except (OSError, subprocess.SubprocessError):
            return False
        if "true" in out:
            return True
        if "false" in out:
            return False
    return False
