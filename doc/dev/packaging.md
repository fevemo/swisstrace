# Packaging and release

## Installers

```bash
uv run --group packaging python scripts/build_installer.py          # dist/*.dmg (macOS) or dist/*.msi (Windows)
uv run --group packaging python scripts/build_installer.py --fresh  # recreate the bundle, reinstall all deps
uv run --group packaging python scripts/build_installer.py --identity "Developer ID Application: ..."  # sign + notarize
```

Builds for the platform it runs on (macOS: Apple Silicon only) with Briefcase;
configuration in `[tool.briefcase]` of the root `pyproject.toml`. The script:

1. builds the user manual into `doc/build/html` (it ships inside the app as `html`,
   where `main.py` points `docPath`);
2. writes the `uv.lock` versions as pip constraints, so the installer has exactly the
   tested dependencies;
3. copies `apps/twiliteacq` to `build/installer-src/pysample` (Briefcase names the
   package after the app: identifier `ch.swisstrace.twilite.pysample`, run as
   `python -m pysample`), without a checkout's runtime output;
4. has Briefcase create or update, build and package. The bundle is kept between builds
   and only updated, unless `uv.lock`, `[tool.briefcase]`, the Briefcase version or
   `QT_MODULES` changed, or `--fresh` is given.

Size: `cleanup_paths` drops unused packages (PyObjC tests, scipy, QML, translations,
`.sip` files). On macOS the script also removes Qt libraries not needed by
`QT_MODULES` (`scripts/build_installer.py`). **Importing another PyQt6 module, in the
app or through a new dependency, means adding it to `QT_MODULES`**, or the installed app
fails with an ImportError.

Signing: without `--identity` the app is only ad-hoc signed. macOS then needs the
*Open Anyway* steps and Windows shows SmartScreen; the manual's *Installation* page walks
users through them. Remove those steps from the manual once releases are signed.

## Versions

The app's version is `[project] version` in `apps/twiliteacq/pyproject.toml`. EINstudio
shows it on the splash, the View in the window title, the Model writes it into
acquisition files (`locations.appVersion()`). `[tool.briefcase] version` in the root
`pyproject.toml` must match; a test and `build_installer.py` check it.

## Icons and splash

```bash
uv run python scripts/make_icons.py
```

From `resources/swisstrace-logo.svg`: `apps/twiliteacq/icons/icon.icns` (macOS only),
`icon.ico` and `splash.png`. On macOS `main.py` uses the `.icns` for the window icon
(the Dock expects Apple's margin).

## User manual

```bash
uv run --group docs sphinx-build -b html doc/source doc/build/html
```

`doc/source/conf.py` uses `einstudio.sphinxext` (theme, colours, rules for the in-app
page). Formulas use `imgmath` (rendered at build time, needs LaTeX) so the manual works
offline inside the app; without LaTeX, avoid `.. math::` or switch to MathJax, which
needs internet. From a checkout the *Docs* page reads `doc/build/html` (`docPath` in
`config.yaml`).

The manual is for users: tasks, buttons and outcomes. Implementation details belong in
`doc/dev/`.
