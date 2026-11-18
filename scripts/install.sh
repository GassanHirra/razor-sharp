#!/usr/bin/env bash
# Installs Razor Sharp for the current user, from this folder.
# On Debian/Ubuntu/Mint/Pop!_OS, use the .deb from the Releases page instead.
set -euo pipefail
cd "$(dirname "$0")/.."

APP="$HOME/.local/share/razor-sharp/app"
BIN="$HOME/.local/bin"

missing=()
python3 -c "import tkinter" 2>/dev/null || missing+=("Tk for Python (python3-tk / tk)")
python3 -c "import openrazer.client" 2>/dev/null || missing+=("OpenRazer Python bindings (python3-openrazer / python-openrazer)")
python3 -c "import evdev" 2>/dev/null || missing+=("python-evdev (python3-evdev / python-evdev)")
if [ ${#missing[@]} -gt 0 ]; then
  echo "Please install these first with your package manager:"
  printf '  - %s\n' "${missing[@]}"
  echo "Optional: numpy + parec (audio visualiser), dbus-monitor (notification flash)."
  exit 1
fi

rm -rf "$APP" && mkdir -p "$APP" "$BIN"
cp -r razor_sharp/razor_sharp.py razor_sharp/lib razor_sharp/effects razor_sharp/layouts razor_sharp/icons "$APP/"
find "$APP" -name '__pycache__' -prune -exec rm -rf {} +

cat > "$BIN/razor-sharp" <<EOF
#!/bin/sh
exec python3 "$APP/razor_sharp.py" "\$@"
EOF
chmod +x "$BIN/razor-sharp"

for d in data/icons/hicolor/*/; do
  size=$(basename "$d")
  install -Dm644 "$d/apps/razor-sharp.png" "$HOME/.local/share/icons/hicolor/$size/apps/razor-sharp.png"
done
sed "s|^Exec=.*|Exec=$BIN/razor-sharp|" data/razor-sharp.desktop > "$HOME/.local/share/applications/razor-sharp.desktop"

echo "Installed. Open “Razor Sharp” from your app menu, or run: razor-sharp"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "(Add $BIN to your PATH to run it from a terminal.)";; esac
