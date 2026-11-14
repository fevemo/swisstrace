# Twilite acquisition

Acquisition and correction software for the Swisstrace twilite blood sampler, replacing
PMOD PSAMPLE's acquisition and correction functions. See
[the Phase 1 plan](doc/design/) and [the protocol notes](doc/protocol.md).

```
packages/twilite/    driver and simulator: pure Python, no Qt, no dependencies
apps/twiliteacq/     EINstudio GUI app
tests/               unit, integration, app and hardware tests
scripts/             record_session.py: record a raw session with a device
doc/                 manual (Sphinx) and protocol notes
```

## Setup

```bash
python install.py          # installs uv if needed, then: uv sync
```

## Run

```bash
uv run python apps/twiliteacq/main.py
```

With `simulate: true` in `apps/twiliteacq/instrumentConfig.yaml` (the default for
now), the app starts a simulated twilite and connects to it.

The simulator also runs on its own, for development and demos:

```bash
uv run python -m twilite.sim --scenario bolus --isotope F-18
uv run python -m twilite.sim --help        # scenarios, idle timeout, fault injection
```

## Test

```bash
uv run pytest                                  # unit, integration, app: no hardware
uv run pytest --hardware --host 10.0.52.25 -s  # against a real twilite
```

## Hardware day

Record a full session first; it answers the open questions in
[doc/protocol.md](doc/protocol.md) and becomes a test fixture:

```bash
uv run python scripts/record_session.py 10.0.52.25
```

## Building docs

```bash
uv run --group docs ein doc build --app apps/twiliteacq/
```
