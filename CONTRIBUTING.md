# Contributing

Thanks for helping! The most useful contributions right now:

1. **Keyboard layouts.** Map your keyboard with **Map keys** and share the file from `~/.config/razor-sharp/layouts/` using the *Keyboard layout* issue template.
2. **Bug reports.** Include your keyboard model, distro, and the log (**Show log** in the app).
3. **New effects.** See [docs/writing-effects.md](docs/writing-effects.md).

## Running from source

You need OpenRazer, Tk for Python, and python-evdev installed.

```bash
git clone https://github.com/GassanHirra/razor-sharp.git
cd razor-sharp
python3 razor_sharp/razor_sharp.py
```

Built-in effects are loaded from `razor_sharp/effects/`, so changes there show up the next time you start an effect.

## Project layout

```
razor_sharp/
  razor_sharp.py     the app (Tk)
  lib/razor_fx.py    the library effects use (colours, keys, layouts, the run loop)
  effects/           built-in effects
  layouts/           built-in keyboard layouts (JSON)
  icons/             icons used inside the app
data/                desktop entry, AppStream metadata, icons for the system
packaging/           .deb build script
scripts/             install/uninstall for non-Debian distros
docs/                guides and README media
```

## Adding a built-in layout

Put the JSON in `razor_sharp/layouts/`. Add the exact OpenRazer device name to `"devices"`, and set `"verified": true` only if it's been checked on that keyboard. Layouts are matched by device name first, then by matrix size.

## Building the .deb

```bash
./packaging/build-deb.sh          # creates build/razor-sharp_<version>_all.deb
```

Pushing a tag like `v0.2.0` builds the package on GitHub and attaches it to a release.

## Arch Linux (AUR)

`packaging/aur/PKGBUILD` builds from the GitHub release tarball. After tagging a release, update `pkgver`, run `updpkgsums` and `makepkg --printsrcinfo > .SRCINFO`, and push those two files to the AUR repository.

## Releasing

1. Update `__version__` in `razor_sharp/razor_sharp.py`, `CHANGELOG.md`, `data/razor-sharp.metainfo.xml` and `packaging/aur/PKGBUILD`.
2. Commit, then `git tag v<version> && git push --tags`.

## Style

Plain Python 3.8+ using only the standard library and the system packages listed in the README. Keep effects to a single file, and keep any user-facing text short and friendly.
