# Twilite acquisition

Acquisition and correction software for the Swisstrace twilite blood sampler,
replacing PMOD PSAMPLE's acquisition and correction functions.

- **Users**: the manual (`doc/source/`, also on the app's *Docs* page) covers
  installing the app, recording, calibrating, correcting and exporting.
- **Developers and AI agents**: start with [doc/dev/](doc/dev/README.md): architecture,
  device protocol, data and correction, testing, packaging, decisions.

```
packages/twilite/    driver and simulator: pure Python, no Qt, no dependencies
apps/twiliteacq/     EINstudio GUI app
tests/               unit, integration, app and hardware tests
scripts/             record_session.py, build_installer.py, make_icons.py
doc/dev/             developer documentation (Markdown)
doc/source/          user manual (Sphinx)
```

## Quick start

```bash
uv sync                                    # install everything
uv run python apps/twiliteacq/main.py      # run the app (starts a simulated twilite by default)
uv run pytest                              # tests, no hardware needed
uv run --group docs sphinx-build -b html doc/source doc/build/html   # build the manual
```

More commands (simulator, hardware tests, installers) in
[doc/dev/README.md](doc/dev/README.md).
