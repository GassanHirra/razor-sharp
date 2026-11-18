#!/usr/bin/env bash
# Builds build/razor-sharp_<version>_all.deb from this repository.
# Needs: dpkg-deb, python3, gzip. Run from anywhere:  ./packaging/build-deb.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PKG=razor-sharp
VERSION=$(python3 -c "import re; print(re.search(r'__version__ = \"([^\"]+)\"', open('razor_sharp/razor_sharp.py').read()).group(1))")
HOMEPAGE=$(python3 -c "import re; print(re.search(r'HOMEPAGE = \"([^\"]+)\"', open('razor_sharp/razor_sharp.py').read()).group(1))")
MAINTAINER="${DEB_MAINTAINER:-Gassan <noreply@users.noreply.github.com>}"
ROOT="build/deb/${PKG}_${VERSION}_all"
OUT="build/${PKG}_${VERSION}_all.deb"

echo "Building $PKG $VERSION"
python3 -m py_compile razor_sharp/razor_sharp.py razor_sharp/lib/*.py razor_sharp/effects/*.py
rm -rf "$ROOT" && mkdir -p "$ROOT"

# app
APP="$ROOT/usr/share/$PKG"
mkdir -p "$APP"
cp -r razor_sharp/razor_sharp.py razor_sharp/lib razor_sharp/effects razor_sharp/layouts razor_sharp/icons "$APP/"
find "$APP" -name '__pycache__' -prune -exec rm -rf {} +

# launcher
mkdir -p "$ROOT/usr/bin"
cat > "$ROOT/usr/bin/$PKG" <<'EOF'
#!/bin/sh
exec /usr/bin/python3 /usr/share/razor-sharp/razor_sharp.py "$@"
EOF

# desktop entry, metadata, icons
install -Dm644 data/razor-sharp.desktop "$ROOT/usr/share/applications/razor-sharp.desktop"
install -Dm644 data/razor-sharp.metainfo.xml "$ROOT/usr/share/metainfo/razor-sharp.metainfo.xml"
for d in data/icons/hicolor/*/; do
  size=$(basename "$d")
  install -Dm644 "$d/apps/razor-sharp.png" "$ROOT/usr/share/icons/hicolor/$size/apps/razor-sharp.png"
done

# docs
DOC="$ROOT/usr/share/doc/$PKG"
mkdir -p "$DOC"
cp README.md CHANGELOG.md "$DOC/"
cat > "$DOC/copyright" <<EOF
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: Razor Sharp
Source: $HOMEPAGE

Files: *
Copyright: 2026 Gassan
License: GPL-3+
 This program is free software: you can redistribute it and/or modify it under
 the terms of the GNU General Public License as published by the Free Software
 Foundation, either version 3 of the License, or (at your option) any later version.
 .
 On Debian systems, the full text of the GNU General Public License version 3
 can be found in /usr/share/common-licenses/GPL-3.
EOF
printf '%s (%s) unstable; urgency=low\n\n  * See /usr/share/doc/%s/CHANGELOG.md\n\n -- %s  %s\n' \
  "$PKG" "$VERSION" "$PKG" "$MAINTAINER" "$(date -R)" | gzip -9n > "$DOC/changelog.gz"

# permissions
find "$ROOT" -type d -exec chmod 755 {} +
find "$ROOT" -type f -exec chmod 644 {} +
chmod 755 "$ROOT/usr/bin/$PKG" "$APP/razor_sharp.py"

# control
mkdir -p "$ROOT/DEBIAN"
SIZE=$(du -sk --exclude=DEBIAN "$ROOT" | cut -f1)
cat > "$ROOT/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Installed-Size: $SIZE
Depends: python3 (>= 3.8), python3-tk, python3-openrazer, openrazer-daemon, python3-evdev
Recommends: openrazer-driver-dkms, python3-numpy, pulseaudio-utils, libnotify-bin, dbus-bin | dbus, pkexec | policykit-1, libglib2.0-bin
Suggests: polychromatic
Maintainer: $MAINTAINER
Homepage: $HOMEPAGE
Description: Lighting effects for Razer keyboards
 Razor Sharp brings animated, typing-reactive lighting to Razer keyboards on
 Linux, using OpenRazer. It includes 24 effects (ripples, lightning, fire,
 rain, matrix rain, an audio visualiser, a system monitor, a WPM meter, a
 Pomodoro timer, and the games Snake and Breakout), key highlights, status
 keys, night mode, app profiles, keyboard shortcuts, a key-mapping tool for
 any keyboard, and Python scripting for your own effects.
 .
 Not affiliated with or endorsed by Razer Inc.
EOF

# stop running effects when the package is removed or upgraded (they'd use deleted files)
cat > "$ROOT/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
pkill -INT -f "/usr/share/razor-sharp/effects/" 2>/dev/null || true
exit 0
EOF
chmod 755 "$ROOT/DEBIAN/prerm"

mkdir -p build
dpkg-deb --root-owner-group --build "$ROOT" "$OUT" >/dev/null
echo "Built $OUT"
