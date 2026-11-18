# Writing effects

A Razor Sharp effect is one Python file. The app finds its options, shows them as sliders, toggles and colour pickers, and runs the script in the background when you press **Start**.

## The smallest effect

```python
"""Breathe: the whole keyboard gently pulses."""
import math
from razor_fx import Effect, scale

fx = Effect()

def frame(now):
    k = 0.6 + 0.4 * math.sin(now * 2)
    for y in range(fx.rows):
        for x in range(fx.cols):
            fx.set(y, x, scale(fx.base(y, x, now), k))

fx.run(frame)
```

- The **first line of the docstring** is the description shown in the app. Text before a colon is dropped, so "Breathe: the whole keyboard…" shows as "The whole keyboard…".
- `fx.run(frame)` calls `frame(now)` about 40 times a second and sends the result to the keyboard. `now` is the time in seconds.
- The keyboard is a grid of `fx.rows` × `fx.cols` cells. `fx.set(y, x, (r, g, b))` sets one cell. Colours are 0–255 and can be floats.

Add it with **+ Add** in the app, or drop it into `~/.local/share/razor-sharp/effects/`.

## Options: `PARAMS`

```python
PARAMS = {
    "ring_color": {"type": "color", "label": "Ring colour", "default": "#ffffff"},
    "speed":      {"type": "range", "label": "Speed", "min": 1, "max": 30, "default": 12, "step": 1},
    "fade":       {"type": "range", "label": "Fade (s)", "min": 0.1, "max": 3, "default": 0.8, "step": 0.1},
    "rainbow":    {"type": "bool",  "label": "Rainbow rings", "default": False},
}
fx = Effect(PARAMS)
```

Read them with `fx.param("speed")`, or `fx.color("ring_color")` for colours. Values update live while the effect runs.

To show an option only when another one has a certain value, add `show_if`:

```python
"ring_color": {"type": "color", "label": "Ring colour", "default": "#ffffff",
               "show_if": {"param": "rainbow", "is": False}},
```

## Colours and brightness

The app has two brightness sliders: **Brightness** for the lighting colours, and **Effect brightness** for everything the effect draws. To keep them separate:

| Use | For |
|---|---|
| `fx.base(y, x, now)` | the lighting colour of a key (already at the lighting brightness) |
| `fx.color("name")` | a colour option (already at the effect brightness) |
| `fx.glow((r, g, b))` | any other colour your effect makes, like white flashes or rainbow sparks |
| `fx.light_colors()` | the two lighting colours, if you use them in your own pattern |

Colour helpers: `mix(a, b, t)`, `add(a, b, k)`, `scale(c, k)`, `hsv(h, s, v)`, `gradient(stops, t)`, `hex_to_rgb("#ff0000")`.

## Key presses

```python
for row, col in fx.key_presses():            # positions pressed since the last frame
    ...
for name, row, col in fx.key_events():       # with key names: "A", "SPACE", "UP", "F5", ...
    ...
```

Use one of the two in each frame; both empty the same queue. Key names are Linux's `KEY_*` names without the prefix. For games, `fx.key_events(repeats=True)` also includes the auto-repeat while a key is held.

- `fx.pos("F1")` gives a key's `(row, col)`, or `None` if this keyboard doesn't have it. Check for `None`, because laptops and 60% keyboards lack some keys.
- `fx.positions(["F1", "F2", ...])` gives the positions of the keys that exist.
- `fx.is_key(y, x)` tells you whether a cell is a real key.
- `fx.bounds` is `(first_row, last_row, first_col, last_col)` of the real keys.

Key presses need the `input` group (see the README). Without it, these return nothing and the effect still runs.

## How it shows in the app

```python
CATEGORY = "Reactive"        # Reactive, Ambient, Tools, Games, or your own; default "My effects"

# Which Lighting settings your effect uses ("full" by default):
LIGHTING = "full"            # everything
LIGHTING = "colors"          # only the two colours and brightness
LIGHTING = "none"            # hide the Lighting panel
LIGHTING = {"param": "use_base", "on": "full", "off": "none"}   # depends on an option

EFFECT_BRIGHTNESS = False    # hide the Effect brightness slider (only uses lighting colours)
```

## What you get for free

Highlights, status keys, night mode, lights-off-when-idle, the frame-rate setting, and pausing while the screen is locked all apply to every effect, yours included. You don't need to do anything for them.

## Running it from a terminal

While developing, it's handy to run the script directly and watch its output:

```bash
PYTHONPATH=/usr/share/razor-sharp/lib python3 my_effect.py      # .deb install
PYTHONPATH=~/.local/share/razor-sharp/app/lib python3 my_effect.py   # script install
```

Stop it with Ctrl+C. The keyboard keeps showing the lighting colours. Errors also appear in the app under **Show log**.

## Tips

- Keep `frame` light. It runs 40 times a second over roughly 100–130 keys.
- Use `now` for anything time-based, rather than counting frames.
- Look at the built-in effects in `/usr/share/razor-sharp/effects/`. `reactive_fade.py` and `shockwave.py` are good places to start.

Made something nice? Open a pull request to add it to the built-in set.
