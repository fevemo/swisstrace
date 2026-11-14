---
name: einstudio
description: Use when writing or changing an app built on EINstudio (PyQt6 lab GUIs) — the model / viewmodel / view / layout files, the View lifecycle, config.yaml, the ein CLI and the runnable demos. Read it first; the other einstudio-* skills cover layouts, options, threading and app setup.
---

# EINstudio apps

<!-- check-agent-docs: ignore styles/ -->

EINstudio is a PyQt6 framework for lab and instrument GUIs (pyqtgraph plots,
PyQt6-Fluent-Widgets controls, YAML configuration, Sphinx manuals).

This skill holds EINstudio's own conventions. Rules marked **contract** are how the
framework works: ignoring them breaks the app, often silently. The rest is the pattern the
templates and demos follow, with the reason. Where the project's own instructions differ
on code style (naming, formatting, error handling), follow the project.

Paths such as `tools/einview.py` are relative to the installed `einstudio` package.
Manual: <https://einlab.pages.uzh.ch/eincode/index.html>.

## Commands (from the app folder)

| Command | Purpose |
|---------|---------|
| `uv run ein run <appFolder>` | Launch the app |
| `uv run ein list` | List apps, demos and templates |
| `uv run ein demo <N>` | Run demo N (source in `demos/demoNN_<slug>/`) |
| `uv run ein template <name>` | Run an app template in place |
| `uv run ein new <name> --template <t> [--full]` | Create an app from a template |
| `uv run --group docs ein doc build --app .` | Build the app's manual |

`uv run ein --help` lists the rest. Start new apps and new pages with `ein new` and edit
the result; do not write the files from scratch.

## App files

An app folder holds `main.py`, `config.yaml`, `model.py`, `viewmodel.py`, `view.py`,
`layouts/mainLayout.py` (with `mainLayout.yaml`), and optionally `options.yaml`,
`instrumentConfig.yaml`, `styles/`, `widgets/` and `doc/source/`.

**Contract** (built by `EINApplication`, so keep these signatures):
`Model(logger, instrumentConfig)`, `ViewModel(model, logger)`, the layout class
`MainWidget(options=None, instrumentConfig=None)`, `View(EINview)` without its own
`__init__`. `main.py` only calls `EINApplication(appDir=<its folder>).launch()`.

## The four layers

```
Function calls:  View → ViewModel → Model
Signals:                ViewModel → View      (Model may invoke ViewModel callbacks)
```

| File | Owns |
|------|------|
| `model.py` | Instruments, persistent data (arrays, tables, caches), file I/O, computation |
| `viewmodel.py` | Qt signals, threads and timers, turning user actions into Model calls |
| `view.py` | Widget event handlers, signal slots, redrawing; transient UI handles in `self.handles` |
| `layouts/mainLayout.py` | Creating and arranging widgets, `setObjectName` |

The templates keep data in the Model and let the View fetch what it shows on each
signal, so a redraw never works from a stale copy and the Model can be tested without
Qt. `self.handles` holds display objects kept between signals (a plot curve), not data.
Layouts hold no logic and no signal connections; the View wires everything.

## View lifecycle (contract)

`EINview.__init__` (`tools/einview.py`) runs: `makeWidgetsList()` → option widgets added
→ layout built → `self.widgets` filled by `findChild(type, name)` for every entry →
`configure()` → `bindWidgetsActions()` → `bindSignals()`.

- Every name in `expectedWidgets` must match a `setObjectName(...)` in the layout, with
  the same widget class; a missing one raises at startup.
- Use `self.widgets.<name>`, not `findChild` yourself.
- A signal emitted during `configure()` is lost (nothing is connected yet). Defer it:
  `QTimer.singleShot(0, self.viewModel.loadState)` (`demo09_persistence`).

## config.yaml (contract)

Key reference: <https://einlab.pages.uzh.ch/eincode/einstudio/reference/config/config_yaml.html>.

- `layoutFile`, `useLogger` and `docPath` are always read (`docPath: ''` for none).
- `useOptions: true` is required for `optionsFile` to load, `useInstrumentConfig: true`
  for `instrumentConfigFile`. Without the flag the file is silently ignored and the
  options / `instrumentConfig` are `None`.
- A missing `config.yaml` loads as an empty namespace, so the failure shows up later as
  an `AttributeError`.
- `ConfigManager.loadYaml(path)` resolves values starting with `./` or `../` relative to
  that YAML file.

## Launch (contract)

- `EINApplication` changes into the app folder itself; `main.py` must not `chdir`.
- There is one `QApplication` per process; never create a second one.
- The app folder is imported as a package named after the folder: `model.py` is
  `<folder>.model`, and `from <folder>.widgets import X` works without `sys.path` edits.
  Import app modules only through that name; another path loads a second copy, and enum
  `is` comparisons between them silently fail.

## Framework pitfalls

| Wrong | Right |
|-------|-------|
| Changing an option's `type`, `options` or `default` in code | Declare it in `options.yaml` (see `einstudio-options`) |
| The View appends readings to its own list | The Model stores them; the View fetches per signal |
| `findChild(EINdropDown, "mode_edit")` | `self.widgets.mode_edit` |
| `options.get("key", 5)` for a declared option | `options["key"]`: declared options always exist, and a default hides a typo |
| `Qt.AlignLeft`, `EINslider.TicksBelow` | `Qt.AlignmentFlag.AlignLeft`, `EINslider.TickPosition.TicksBelow` (Qt6; the short form fails only when the line runs) |
| Blocking hardware or computation in a View slot | Run it in a thread from the ViewModel (see `einstudio-threading`) |

## Demos: copy their shape

Each demo is a small runnable app; open the matching one before writing similar code.

| Demo | Shows |
|------|-------|
| `demo01_hello` | The four-file skeleton, `EINApplication.launch()` |
| `demo02_live_plot` | ViewModel-owned `QTimer`, `self.handles`, signal-driven plots |
| `demo03_options` | `options.yaml`, auto-generated `<name>_edit` widgets |
| `demo04_threading` | `runFuncInThread` from the ViewModel, `(result, error)` callback |
| `demo05_sections` | `EINnavbarLayout.addPage`, `EINcardWidget`, `EINoptionRow` |
| `demo06_logging` | Logger, in-app log panel |
| `demo07_instrument` | `instrumentConfigFile`, Model owning a (simulated) instrument |
| `demo08_styling` | Shape and color profiles, app-local style overrides |
| `demo09_persistence` | Saving and restoring state, deferred emission from `configure()` |
| `demo10_docs` | In-app documentation (`docPath`) |

## Other EINstudio skills

| Skill | Read when |
|-------|-----------|
| `einstudio-layouts` | Editing `layouts/*.py`: pages, cards, rows, navigation, `objectName` |
| `einstudio-options` | Editing `options.yaml` or option widgets |
| `einstudio-threading` | Background work, `runFuncInThread`, timers |
| `einstudio-apps` | `ein new` into a project, styling, the app manual, packaging and deployment |
