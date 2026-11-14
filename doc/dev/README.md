# Developer documentation

For people and AI agents changing the code. The user manual is in `doc/source/`
(Sphinx, shown on the app's *Docs* page) and holds no implementation details; keep it
that way.

| File | What it covers |
| --- | --- |
| [architecture.md](architecture.md) | The two layers (driver, app), module responsibilities, threading, where files go |
| [protocol.md](protocol.md) | The twilite telnet protocol as observed: **the source of truth** for driver and simulator |
| [data-and-correction.md](data-and-correction.md) | Acquisition file format, sample timing, correction and calibration maths, editing, exports |
| [testing.md](testing.md) | Test layers, markers, fixtures, CI, hardware day |
| [packaging.md](packaging.md) | Installers, icons, building the manual, versions |
| [decisions.md](decisions.md) | Decisions taken and why, open questions, Phase 2 candidates |

## Repository layout

```
packages/twilite/    driver and simulator: pure Python, standard library only
apps/twiliteacq/     EINstudio GUI app (an app folder, not an installable package)
tests/               unit, integration, app and hardware tests; fixtures
scripts/             record_session.py, build_installer.py, make_icons.py
resources/           source artwork (swisstrace-logo.svg)
doc/dev/             this documentation (Markdown)
doc/source/          user manual (Sphinx)
doc/PMOD_ex_data/    example files written by PMOD PSAMPLE
```

## Commands

uv workspace, Python ≥ 3.12. `einstudio` comes from a private GitLab index (`einlab`,
see the root `pyproject.toml`).

```bash
uv sync                                                    # driver, app deps, test tools
uv run python apps/twiliteacq/main.py                      # run the GUI (or ./run.sh)
uv run python -m twilite.sim --scenario bolus --isotope F-18   # standalone simulator (--help)

uv run pytest                                              # unit + integration + app, against the simulator
uv run pytest --hardware --host 10.0.52.25 -s              # also against a real twilite

uv run python scripts/record_session.py <ip>               # record a raw device session
uv run --group docs sphinx-build -b html doc/source doc/build/html   # user manual
uv run --group packaging python scripts/build_installer.py  # installer, see packaging.md
```

With `simulate: true` in `apps/twiliteacq/instrumentConfig.yaml` (the default) the app
starts its own simulated twilite and connects to it.
