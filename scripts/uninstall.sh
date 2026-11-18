#!/usr/bin/env bash
# Removes a Razor Sharp install made with scripts/install.sh.
# Your settings, presets and own effects stay in ~/.local/share/razor-sharp unless you pass --all.
set -euo pipefail
DATA="$HOME/.local/share/razor-sharp"

python3 "$DATA/app/razor_sharp.py" --stop 2>/dev/null || true
rm -rf "$DATA/app"
rm -f "$HOME/.local/bin/razor-sharp" "$HOME/.local/share/applications/razor-sharp.desktop" \
      "$HOME/.config/autostart/razor-sharp.desktop"
rm -f "$HOME"/.local/share/icons/hicolor/*/apps/razor-sharp.png
if [ "${1:-}" = "--all" ]; then
  rm -rf "$DATA" "$HOME/.config/razor-sharp"
  echo "Removed Razor Sharp and all its settings."
else
  echo "Removed Razor Sharp. Your settings and effects are still in $DATA"
fi
