---
name: einstudio-apps
description: Use when setting up or shipping an EINstudio app — ein new (new folder or an existing project), templates, upgrading einstudio, app styling (shape/color profiles, styles/app.yaml, setTone, Fluent overrides), building the app's Sphinx manual, ein package and ein deploy.
---

# EINstudio app setup, styling and shipping

<!-- check-agent-docs: ignore lightQss darkQss -->

Paths are relative to the installed `einstudio` package. `uv run ein <command> --help`
is authoritative for every command. Manual:
<https://einlab.pages.uzh.ch/eincode/einstudio/reference/cli/index.html> and
<https://einlab.pages.uzh.ch/eincode/einstudio/how_to/index.html>.

## Creating an app

```bash
uv run ein new <name>                          # simple layout, minimal version, in ./<name>/
uv run ein new <name> --template pages --full  # another layout, complete example app
uv run ein template pages [--minimal]          # run a template in place to look at it
```

- Layouts: `simple`, `controls`, `pages`, `responsive`, `columns`, `multipanel`.
- `minimal`: the layout's pages and cards with placeholder widgets. `full`: simulated
  instrument, plot, `options.yaml`, logger, and (all but `simple`) a `doc/source/` manual.
  Generate a `full` app in a scratch folder to copy a working pattern from.
- `<name>` becomes `[project] name` in `pyproject.toml`: letters or digits at both ends,
  `.` `-` `_` inside. The target folder must not exist.
- The app depends on the published `einstudio`, from the EINlab registry declared in its
  `pyproject.toml`. Upgrade it from the app folder with `uv lock --upgrade-package einstudio`.
- `ein new` writes an `AGENTS.md` for coding agents unless the folder already has one;
  an existing `AGENTS.md` is never replaced.

## Adding a GUI to an existing project

`uv run ein new` with no name (or `ein new <name> --here`) scaffolds into the current
folder. The existing `pyproject.toml` is kept, never replaced:

| Existing `pyproject.toml` | Result |
|---------------------------|--------|
| Declares einstudio with a range that admits the running version | Left unchanged |
| Declares einstudio with a range excluding the running version | Refused — run that project's own `uv run ein new`, or widen the range |
| No einstudio | einstudio added, previous file kept as `pyproject.toml.bak` |
| Unparseable | Refused |

Any other template file that already exists (most often `main.py`) refuses the command
and is listed: move it aside, scaffold, then merge by hand. `--force` overwrites
everything, `pyproject.toml` included — never use it to preserve a project.

## Styling

Live showcase of every widget and token: `uv run ein styleboard`. Example:
`uv run ein demo 8`. Manual: <https://einlab.pages.uzh.ch/eincode/einstudio/how_to/styling.html>.

- `config.yaml` `shape` and `color` pick a profile. Shipped: shape `EINstudioStandard`,
  `EINstudioCompact`, `EINstudioLarge`; color `graphite_blue`, `midnight_copper`,
  `obsidian_teal`. A bare name looks in `<app>/styles/shape|color/` first, then the
  shipped ones; a value ending in `.yaml` or containing a path separator is a path.
  A missing file raises `FileNotFoundError` at startup.
- An app profile overrides shipped tokens key by key; a key the built-in default lacks
  raises `KeyError`. App-specific tokens go in `<app>/styles/app.yaml`, with keys
  starting `app_` or `c_app_`.
- Show states with `setTone("error"|"warning"|"success"|None)` (labels, text boxes, spin
  boxes), `EINstatusLight.setStatus(...)` and button tones, not
  `setStyleSheet("color: red")`. Channel colours are `c_channel_1..7` / `c_channel_sync`.
- `token("c_x")` returns the raw hex string, `color("c_x")` a `QColor`; `str(QColor)` is
  not a colour string. Read tokens inside methods: calling `token()` at import time loads
  the defaults before the app's profile is applied.
- Size controls with `length=`, not fixed widths.
- Application-level QSS loses to the widget-level QSS that Fluent widgets install. To
  restyle a Fluent widget, call `setCustomStyleSheet(widget, lightQss, darkQss)` (from
  `qfluentwidgets.common.style_sheet`) after `super().__init__()`.

## The app's manual

- `full` templates ship `doc/source/` (Sphinx, `conf.py` lists `'einstudio.sphinxext'`,
  which gives the shared dark look in the app's palette and keeps it offline) and a
  `docs` dependency group. Otherwise add the group: `uv add --group docs "einstudio[docs]"`.
- Build from the app folder: `uv run --group docs ein doc build --app .` (`--remake`
  after renames or toctree changes). `config.yaml` `docPath: 'doc/build/html'` shows it
  in the app. Do not call `sphinx-build` or add a `Makefile`.
- The manual is read offline inside the app: no CDN scripts or web fonts; formulas use
  `sphinx.ext.imgmath` (needs LaTeX at build time).
- `ERROR: Error in "code-block" directive` almost always means a missing blank line
  after the directive line.

## Packaging and deployment

Manual: <https://einlab.pages.uzh.ch/eincode/einstudio/how_to/packaging_an_app.html>.

- `ein package <name>` writes `dist/<name>-<version>-<target>.zip` beside the app: app
  source, `uv.lock`, a bootstrap installer and an install README. One bundle per OS
  (`--target`). The installer needs no Python or uv preinstalled. It is not a fully
  offline installer, and there is no frozen executable.
- `ein deploy <name>`: `uv sync --frozen`, then launchers — on Windows a hidden-console
  launcher plus Desktop and Start Menu shortcuts.
- Vendor runtimes uv cannot install (e.g. NI-DAQmx) go in the app's `pyproject.toml`:
  `[tool.einstudio] requiredDrivers = ["NI-DAQmx runtime ..."]`. Each entry becomes a
  line in the bundle README; nothing reads it at run time.

## Agent skills

These skills ship inside the `einstudio` package and are installed into a project with
`uvx library-skills` (`--claude` also installs them for Claude Code; `--copy` where
symlinks are unavailable, e.g. Windows without Developer Mode). Symlinked skills follow
einstudio upgrades; copied skills need the command again after an upgrade.
