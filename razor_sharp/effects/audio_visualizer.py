"""Audio visualiser: the keyboard becomes an equaliser that bounces to whatever is playing on your laptop.

Needs: sudo apt install python3-numpy pulseaudio-utils   (works with PulseAudio and PipeWire)
"""

import atexit
import shutil
import subprocess
import threading

from razor_fx import Effect, mix, scale

CATEGORY = "Tools"
# Which Lighting settings this effect uses: "full", "colors" (just the two colours), or "none".
LIGHTING = {"param": "use_base", "on": "full", "off": "none"}

PARAMS = {
    "low_color": {"type": "color", "label": "Bottom colour", "default": "#00ff6a", "show_if": {"param": "use_base", "is": False}},
    "high_color": {"type": "color", "label": "Top colour", "default": "#ff0040", "show_if": {"param": "use_base", "is": False}},
    "use_base": {"type": "bool", "label": "Use lighting colours instead", "default": False},
    "sensitivity": {"type": "range", "label": "Sensitivity (%)", "min": 20, "max": 300, "default": 100, "step": 5},
    "smoothing": {"type": "range", "label": "Smoothing (%)", "min": 0, "max": 95, "default": 55, "step": 5},
    "peaks": {"type": "bool", "label": "Peak dots", "default": True},
    "mirror": {"type": "bool", "label": "Mirror (bass in the middle)", "default": False},
}

try:
    import numpy as np
except ImportError:
    raise SystemExit("This effect needs numpy:  sudo apt install python3-numpy")
if not shutil.which("parec"):
    raise SystemExit("This effect needs parec:  sudo apt install pulseaudio-utils")

RATE, CHUNK, WINDOW = 44100, 1024, 4096
fx = Effect(PARAMS)
C0, C1 = fx.bounds[2], fx.bounds[3]   # leftmost and rightmost key columns
BANDS = C1 - C0 + 1

# log-spaced frequency bands from 40 Hz to 16 kHz mapped to FFT bins
freqs = np.fft.rfftfreq(WINDOW, 1.0 / RATE)
edges = np.geomspace(40, 16000, BANDS + 1)
bins = []
for lo, hi in zip(edges, edges[1:]):
    i0 = int(np.searchsorted(freqs, lo))
    i1 = max(i0 + 1, int(np.searchsorted(freqs, hi)))
    bins.append((i0, i1))

raw = [0.0] * BANDS
lock = threading.Lock()


def monitor_source():
    try:
        sink = subprocess.run(["pactl", "get-default-sink"], capture_output=True, text=True, timeout=3).stdout.strip()
        if sink:
            return sink + ".monitor"
    except (OSError, subprocess.SubprocessError):
        pass
    return "@DEFAULT_MONITOR@"


def analyse(samples, state):
    """samples: float array of the latest WINDOW samples -> list of 0..1 band levels."""
    spec = np.abs(np.fft.rfft(samples * state["window"]))
    db = np.array([20 * np.log10(spec[i0:i1].mean() + 1e-9) for i0, i1 in bins])
    db += np.linspace(0, 12, BANDS)                      # lift treble a little so it isn't drowned by bass
    state["gain"] = max(state["gain"] * 0.997, float(db.max()))
    floor = state["gain"] - 42
    return list(np.clip((db - floor) / 42, 0, 1))


def capture():
    src = monitor_source()
    print(f"Listening to: {src}", flush=True)
    proc = subprocess.Popen(["parec", f"--device={src}", "--format=s16le", f"--rate={RATE}",
                             "--channels=1", "--latency-msec=20"],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    atexit.register(proc.terminate)
    buf = np.zeros(WINDOW)
    state = {"window": np.hanning(WINDOW), "gain": -20.0}
    while True:
        data = proc.stdout.read(CHUNK * 2)
        if not data:
            print("Audio capture stopped.", flush=True)
            return
        s = np.frombuffer(data, dtype="<i2").astype(np.float64) / 32768.0
        buf = np.concatenate([buf[len(s):], s])
        levels = analyse(buf, state) if np.abs(buf).max() > 1e-4 else [0.0] * BANDS
        with lock:
            raw[:] = levels


threading.Thread(target=capture, daemon=True).start()
shown = [0.0] * BANDS
peaks = [0.0] * BANDS
last = None


def frame(now):
    global last
    dt = 0.0 if last is None else min(0.1, now - last)
    last = now
    sens = float(fx.param("sensitivity")) / 100.0
    smooth = float(fx.param("smoothing")) / 100.0
    with lock:
        target = [min(1.0, v * sens) for v in raw]
    for i, v in enumerate(target):
        if v > shown[i]:
            shown[i] = v * 0.7 + shown[i] * 0.3
        else:
            shown[i] = shown[i] * smooth + v * (1 - smooth)
        peaks[i] = max(peaks[i] - dt * 0.6, shown[i])

    low, high = fx.color("low_color"), fx.color("high_color")
    use_base, show_peaks, mirror = fx.param("use_base"), fx.param("peaks"), fx.param("mirror")
    centre = C0 + (BANDS - 1) / 2.0
    for x in range(fx.cols):
        if not C0 <= x <= C1:
            band = None
        elif mirror:
            band = min(BANDS - 1, int(abs(x - centre) * 2))
        else:
            band = x - C0
        h = shown[band] * fx.rows if band is not None else 0.0
        pk = int(peaks[band] * fx.rows - 0.001) if band is not None else -1
        for y in range(fx.rows):
            level = fx.rows - 1 - y                 # 0 = bottom row
            fill = max(0.0, min(1.0, h - level))
            col = fx.base(y, x, now) if use_base else mix(low, high, level / max(1, fx.rows - 1))
            c = scale(col, fill)
            if show_peaks and level == pk and fill < 0.9 and peaks[band] > 0.05:
                c = mix(c, fx.glow((255, 255, 255)), 0.6)
            fx.set(y, x, c)


fx.run(frame)
