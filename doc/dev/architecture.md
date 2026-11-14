# Architecture

Two layers, strictly separated. Calls go inward, results come back out; only the top
layer knows about Qt.

```
apps/twiliteacq   View (Qt widgets)  →  ViewModel (QObject, threads)  →  Model (no Qt)
                                                                            │
packages/twilite  TwiliteClient ── telnet ──▶  real twilite  or  twilite.sim simulator
                  storage · correction · editing · isotopes
```

The driver talks to the device and to the simulator over the same protocol, so code
above it cannot tell which one it is connected to.

## `packages/twilite`: the driver

Pure Python, **standard library only: no Qt, no numpy, no dependencies**. CI tests it on
Linux, Windows and macOS without installing anything else. Keep it that way. snake_case.

| Module | Responsibility |
| --- | --- |
| `protocol.py` | Every device fact as a constant at the top (field order, prompts, line ending, login, idle timeout, keepalive interval). Pure functions: build commands, split and parse lines. A line that does not parse is logged and skipped, never fatal. |
| `driver.py` | `TwiliteClient`: blocking, single-connection, built on `socket` (Python 3.13 dropped `telnetlib`). `connect` (banner, login, prompt), `command`, `stream()` over `showc`, `keepalive`, optional raw byte log. Raises `ConnectionLost` on a read timeout or closed socket and never reconnects by itself: the Model decides. |
| `sample.py` | `Sample`: `index` (`[n]`), `singles1`, `singles2`, `coincidences`, extra fields, raw line, `t_wall` (PC clock), `t_mono`. |
| `storage.py` | Streaming acquisition writer, reader (`read_acquisition`, which also reads PSAMPLE `.crv` via `read_crv`), crash recovery, exports. See [data-and-correction.md](data-and-correction.md). |
| `correction.py` | Background, decay correction, calibration factor. Plain sequences in and out (lists or numpy arrays); NaN (gaps) skipped when averaging. |
| `editing.py` | Cut and resample an `Acquisition`, returning new ones; `plan_*` functions give previews for the UI. |
| `isotopes.py` | Isotope table (half-life, branching ratio). Values still to verify, see [decisions.md](decisions.md). |
| `sim/` | `TwiliteSimulator` (asyncio) speaking the same protocol, scenarios and `Faults` injection. See below. |

### Simulator

`python -m twilite.sim` runs on localhost:2323 by default. It copies the bytes recorded
from a *Coincident Counter V3.00*: banner, login that accepts anything, replies, one
`[n]` per printed line, counts/s over the `qrate` period, the 19 s idle timeout.

| Scenario | Produces | Used for |
| --- | --- | --- |
| `background` | Poisson singles ~2000/s, coincidences ~120/s | Background averaging |
| `bolus` | Background, then a gamma-variate peak decaying with the isotope | Live plot, full correction chain |
| `calibration-step` | Background, then a decaying step when the source goes in | Calibration workflow |
| `long-decay` | A constant source over several half-lives | QA: decay-corrected result is flat |
| `replay` | A recorded transcript at real speed | Regression on real data |

`Faults` drop the connection after N samples or stall for X seconds. Scenarios use a
fixed seed so tests are deterministic.

The driver and simulator implement exactly [protocol.md](protocol.md) and nothing more.
Change both together, and update that file when the device teaches something new.

## `apps/twiliteacq`: the EINstudio app

An app folder, not an installable package. `main.py` hands the folder to
`EINApplication`, which reads `config.yaml`, loads `layouts/mainLayout.py` and the
Model / ViewModel / View by file name. camelCase (EINstudio style).

| File | Responsibility |
| --- | --- |
| `model.py` | `Model`, no Qt. Blocking calls: `connect`, `acquire` (blocks until the run ends, so it also runs from a script). Owns the client, the in-app simulator (`simulate: true`), the writer, the live trace, the correction settings and `state.yaml` persistence. Imports `twilite` lazily inside `connect` so the app starts even if the package is broken. Reconnects after `ConnectionLost` during an acquisition (`reconnectAttempts`, 1 s apart) and records the loss and the reconnection as events. |
| `viewmodel.py` | `ViewModel(QObject)`. Runs Model calls in worker threads (`runFuncInThread`), checks prerequisites (connected? already running?) and reports problems via `errorOccurred` instead of raising. Throttles plot updates to ≤ 10/s. Sends keepalives while connected and idle. |
| `view.py` | `View(EINview)`. Wires controls to the ViewModel and signals to plots and labels. Holds the cut mode (drag selection on the plot), `ResampleDialog` and `SettingsDialog`. Saves settings and disconnects when the window closes. `expectedWidgets` lists `(objectName, type)` pairs that must match `layouts/mainLayout.py`: **adding a control means updating both**. |
| `layouts/mainLayout.py` | Pages *Acquisition*, *Correction*, *Calibration*, *Log*, *Settings* (opens the dialog), *Docs* (the built manual). |
| `config.yaml` | EINstudio app config (layout, `docPath`, logging, window, theme). |
| `instrumentConfig.yaml` | Per-installation device settings: host, port, `timeout_s`, `reconnectAttempts`, `dataDir`, `rawLog`, `simulate` + simulator options. Travels with the instrument PC, not the source. Edited from the *Settings* dialog, which keeps the file's comments. |
| `locations.py` | Where data, settings, state and logs go (below). |
| `__main__.py` | Briefcase's entry point; sets `TWILITEACQ_INSTALLED=1`. |

Rules:

- `main.py` must import PyQt6 before einstudio (atexit ordering for logging shutdown).
- App modules import each other relatively (`from . import locations`): EINstudio and
  the tests load the folder as a package named after it, which is `pysample` in the
  installer.
- Editing (cut, resample) happens in memory on the *Correction* page; the source file
  is never modified. The result is saved with `storage.write_acquisition`.

### Where files go (`locations.py`)

From a checkout everything stays in the app folder. Installed, the bundle is read-only,
so `main.py` overrides EINstudio's `logFile`, `instrumentConfigFile` and `docPath`:

| | macOS | Windows |
| --- | --- | --- |
| Data (`dataDir` empty) | `~/Twilite` | `%USERPROFILE%\Twilite` |
| `instrumentConfig.yaml`, `state.yaml` | `~/Library/Application Support/Twilite` | `%LOCALAPPDATA%\Twilite` |
| `log.txt`, `rawlogs/` | `~/Library/Logs/Twilite` | `%LOCALAPPDATA%\Twilite\Logs` |

- Data goes in the home folder, not *Documents*, which iCloud and OneDrive sync and may
  evict from disk.
- Settings go to local (not roaming) app data: they describe this computer's device.
- The installed app copies the shipped `instrumentConfig.yaml` on first launch and then
  only uses the copy, so updates never replace the user's settings.
- From a checkout, raw logs go to `<dataDir>/rawlogs`.
