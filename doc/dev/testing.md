# Testing

pytest. `uv run pytest` runs everything except hardware in seconds, against the
simulator.

| Layer | Folder | Runs against | Covers |
| --- | --- | --- | --- |
| Unit | `tests/unit` | Pure functions | Parsing (recorded and malformed lines, lines split across packets), correction and calibration maths against hand-worked values, writer and recovery, editing, isotopes, scenarios |
| Integration | `tests/integration` | `target` fixture: simulator on a random port, or a real device with `--hardware --host` | Connect and login, commands, start/stop, full acquisition to disk, idle timeout and keepalive, dropped and stalled connections, replay, the simulator CLI |
| App | `tests/app` | Model, ViewModel, window, headless (Qt + EINstudio) | Model from a plain script, ViewModel signals, window smoke tests, `locations`. Loads app modules by path with `load_app_module`. |
| Hardware | `tests/hardware` | A real twilite | Long runs with zero lost samples, cable pull and reconnect, power cycle |

Markers: `hardware` (skipped without `--hardware`), `simulator_only` (fault injection;
skipped with `--hardware`), `app`.

```bash
uv run pytest tests/unit/test_protocol.py::test_name     # one test
QT_QPA_PLATFORM=offscreen uv run pytest tests/app        # app tests headless
uv run --no-default-groups --with pytest --package twilite pytest tests/unit tests/integration
                                                         # driver without Qt/EINstudio, as CI does
uv run pytest --hardware --host 10.0.52.25 -s            # real device
```

## CI

`.github/workflows/tests.yml`, on every push and PR, on Linux, Windows and macOS:

- `driver`: unit + integration with only pytest installed. This is what enforces
  "standard library only" for `packages/twilite`.
- `app`: `uv sync` then `tests/app`, offscreen.

## Fixtures

- `tests/fixtures/transcripts/`: real raw device sessions, replayed by the simulator's
  `replay` scenario. **Every transcript that reveals a problem gets a test reproducing
  it.** Name new ones `<date>_<site or device>_<what>.txt`. Record one with
  `uv run python scripts/record_session.py <ip>`; a customer's `rawlogs` folder works
  too.
- `tests/fixtures/psample/`: real PSAMPLE `.crv` files; golden-file tests check the
  `.crv` export byte for byte and the reader.

## Hardware day

Record a full session first with `scripts/record_session.py`: it answers open questions
in [protocol.md](protocol.md) and becomes a fixture. Then run the suite with
`--hardware --host <ip> -s`.
