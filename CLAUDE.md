# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Acquisition and correction software for the Swisstrace twilite blood sampler (a telnet-controlled coincidence counter), replacing PMOD PSAMPLE's acquisition and correction functions.

## Commands

uv workspace; Python ≥ 3.12. `einstudio` comes from a private GitLab index (`einlab`, see root `pyproject.toml`).

```bash
uv sync                                         # install driver, app deps, test tools
uv run python apps/twiliteacq/main.py           # run the GUI (or ./run.sh)
uv run python -m twilite.sim --scenario bolus --isotope F-18   # standalone simulator; --help for faults/idle timeout

uv run pytest                                   # unit + integration + app, all against the simulator
uv run pytest tests/unit/test_protocol.py::test_name   # single test
uv run pytest --hardware --host 10.0.52.25 -s   # integration + hardware tests against a real twilite

# What CI runs for the driver (must work without Qt/EINstudio):
uv run --no-default-groups --with pytest --package twilite pytest tests/unit tests/integration
# App tests headless:
QT_QPA_PLATFORM=offscreen uv run pytest tests/app

uv run python scripts/record_session.py <ip>    # record a raw device session (becomes a test fixture)
uv run --group docs sphinx-build -b html doc/source doc/build/html   # manual, shown in the app's Docs page
uv run --group packaging python scripts/build_installer.py         # .dmg (macOS, Apple Silicon only) / .msi (Windows) via Briefcase, in dist/
uv run python scripts/make_icons.py resources/icon.png   # app icon, installer and window: apps/twiliteacq/icons/icon.icns, .ico
```

The README mentions `python install.py`, but that file does not exist; use `uv sync`.

## Architecture

Two layers, strictly separated:

- **`packages/twilite/`** — the driver, pure Python, **standard library only, no Qt, no dependencies** (CI tests it on Linux/Windows/macOS without installing anything else; keep it that way — no numpy here).
  - `protocol.py`: byte-level command building and line parsing. `driver.py`: `TwiliteClient` (socket, login, `command`, `stream()` over `showc`, `keepalive`, optional raw log). `storage.py`: acquisition CSV writer/reader (`read_acquisition` also reads PSAMPLE `.crv` via `read_crv`), crash recovery of partial files, exports (CSV, PMOD `.crv`, PMOD blood, events). `correction.py`: background subtraction, decay correction, calibration factor. `editing.py`: cut (linear interpolation) and resample (duration-weighted merging) of an `Acquisition`, returning new ones; the app's Correction page applies them in memory and saves the result with `storage.write_acquisition` as an `_edited.csv` with `# edit:` header lines and `duration_s`/`interpolated` columns. `isotopes.py`: isotope table.
  - Sample `i` counts over `[t_wall - duration_s, t_wall]`; its time everywhere (plot, corrections, `.bld`) is `storage.sample_times`: `t_wall`, the arrival time, as in PSAMPLE, for samples as recorded; the middle of the merged reports (`t_wall - (duration_s - report period) / 2`) for resampled ones. `.tac` frames are the counting intervals themselves.
  - `sim/`: an asyncio `TwiliteSimulator` speaking the same telnet protocol, with scenarios (`background`, `bolus`, `calibration-step`, `long-decay`, `replay` of recorded transcripts) and `Faults` injection. Code above the driver cannot tell simulator from device.
- **`apps/twiliteacq/`** — an EINstudio app folder (not an installable package). `main.py` hands the folder to `EINApplication`, which reads `config.yaml`, loads `layouts/mainLayout.py` and the MVC triple by file name:
  - `model.py`: `Model` — no Qt; blocking calls (`connect`, `acquire` blocks until the run ends), owns the client, the in-app simulator (when `simulate: true`), the writer, correction settings, and `state.yaml` persistence. Imports `twilite` lazily inside `connect`.
  - `viewmodel.py`: `ViewModel(QObject)` — runs Model calls in worker threads (`runFuncInThread`), checks prerequisites and reports problems via `errorOccurred` instead of raising, throttles plot updates, drives keepalives while idle.
  - `view.py`: `View(EINview)` — `expectedWidgets` lists `(objectName, type)` pairs that must match the `objectName`s set in `layouts/mainLayout.py`; adding a control means updating both.
  - `instrumentConfig.yaml`: per-installation device settings (host, timeouts, `dataDir`, `rawLog`, `simulate` + simulator options).
  - `locations.py`: where data, settings, state and logs go. From a checkout, the app folder (as always); installed (`__main__.py`, Briefcase's entry, sets `TWILITEACQ_INSTALLED=1`), the user's folders, since the bundle is read-only. `main.py` then overrides EINstudio's `logFile`, `instrumentConfigFile` and `docPath`. App modules import each other relatively (`from . import locations`): EINstudio and the tests load the app folder as a package named after the folder, which is `pysample` in the installer (Briefcase's app name, giving the identifier `ch.swisstrace.twilite.pysample`; `scripts/build_installer.py` copies the folder under that name).

## Protocol facts that shape the code

`doc/protocol.md` is the source of truth; the driver and simulator implement exactly that (firmware *Coincident Counter - Telnet Server V3.00*) and nothing more. Change both together, and update the doc when the device teaches something new. Key points:

- Report line: `[n] singles1 singles2 coincidences 0.0 0.0`, values in counts/s over the `qrate` period; `[n]` never resets except on power-up.
- The device drops connections after ~19 s idle at the prompt, so anything holding a connection must send keepalives (empty line after 8 s idle).
- `showc` stops on an empty line; one extra report line may follow before the `> ` prompt.
- Login accepts anything; the driver sends `admin` / `ccount`.

## Tests

- Layers: `tests/unit`, `tests/integration` (use the `target` fixture: simulator by default, real device with `--hardware --host`), `tests/app` (Qt + EINstudio; loads app modules by path via `load_app_module`), `tests/hardware`.
- Markers: `hardware` (skipped without `--hardware`), `simulator_only` (fault injection; skipped with `--hardware`), `app`.
- `tests/fixtures/transcripts/`: real raw sessions, replayed by the simulator's `replay` scenario. Every transcript that reveals a problem gets a test reproducing it; name new ones `<date>_<site or device>_<what>.txt`.

## Conventions

- The app code uses camelCase (EINstudio style); the `twilite` package uses snake_case.
- `main.py` must import PyQt6 before einstudio (atexit ordering for logging shutdown).
- The macOS installer keeps only the PyQt6 modules in `QT_MODULES` (`scripts/build_installer.py`) and the Qt libraries they need: importing another PyQt6 module (in the app or a new dependency) means adding it there, or the installed app fails with an ImportError.
- Design notes and open questions: `doc/design/Twilite acquisition app - Phase 1 implementation plan.md`.
