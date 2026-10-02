# Twilite acquisition app — Phase 1 implementation plan

Oct 1, 2026 · @Felipe Velasquez

Phase 1 replaces PMOD PSAMPLE's acquisition and correction functions for the Swisstrace twilite. The work is built bottom-up in four parts: a Qt-free `twilite` driver package, a simulated twilite that speaks the same telnet protocol, a test suite that runs against the simulator by default and against real hardware on request, and an EINstudio app on top. Everything below the GUI must be finished and tested before the hardware day, so instrument time goes on confirming behaviour, not writing code.

Sources so far: the telnet help screen from a twilite (screenshot) and the PMOD *PSAMPLE Software for twilite* manual (2019). Neither documents the data line format, so the first task is to record a raw session on the real device.

## What we know about the protocol

The twilite runs a line-based telnet server on TCP port 23 with a `>` prompt. The manual gives the default login as user `admin`, password `ccount`. The screenshot shows no login prompt, so the login may depend on the firmware version.

| Command | Effect | Source |
| --- | --- | --- |
| `ccnt` | Current counter values, once | Screenshot, manual |
| `show` | All current values, once | Screenshot, manual |
| `showc` | All values continuously, 0.1–10 per second | Screenshot, manual |
| `qrate n` | Query delay n × 100 ms, n = 1–100 | Screenshot, manual |
| `help`, `?` | Command list | Screenshot |
| `bye` | Disconnect | Screenshot |
| `adc` | Analog inputs, once | Manual only (twilite one hardware) |
| `rinfo` | Remote machine info | Manual only |

The `showc` output in the manual (page 23) looks like this:

```
[71] 2152 1576 124 1.731 1.592
[72] 2218 1497 122 1.739 1.607
```

My working hypothesis: `[n]` is a sample counter, followed by singles 1, singles 2, coincidences, then two analog voltages that are deprecated on twilite two/three. The values fit this reading, since the LYSO singles run in the thousands and the coincidence background in the low hundreds. **This is unconfirmed.** PSAMPLE numbers its channels the other way round (channel 1 = coincidences), so the field order has to be checked on the device.

The firmware has changed between versions. The manual's console shows a *SwissTrace BLOOD SAMPLER* banner with `adc` and `rinfo`; the screenshot shows a *Coincident Counter* banner without them. The driver must handle both.

Other facts from the manual that shape the design:

- The counting interval (1, 2, 5 or 10 s) is set on the twilite's touch screen. `qrate` only sets how often values are reported. Values can therefore repeat between counter updates, and the `[n]` counter is what lets us tell a new sample from a repeated one.
- PSAMPLE timestamps every sample with the PC's clock, and users must sync that clock with the PET scanner. We record the PC time too.
- The manual's command menu lists `qrate 50` as 50000 ms, which contradicts n × 100 ms. Probably a typo; to verify.

## Open questions before coding

Answer them in a 30-minute session on the device recording everything with PuTTY's session log:

- [ ] Field order and units of a `showc` line. Counts per counting interval, or counts per second?
- [ ] Does `[n]` go up once per counting interval or once per printed line? Does it reset on reconnect or on power-up?
- [ ] Can the counting interval be set over telnet at all, or only on the touch screen? This decides what "set the sampling rate" means in our scope.
- [ ] Does `showc` need the green play button pressed on the touch screen (PMTs on) first? What does it print otherwise?
- [ ] Login: is there one on current firmware? Which firmware versions and twilite generations are in the field?
- [ ] Exact line endings and any telnet option negotiation (IAC bytes) on connect.
- [ ] How do you stop `showc`? Another command, a blank line, or only a disconnect?
- [ ] A real PSAMPLE `.crv` file and a corrected TAC export, so our exports can match them byte for byte where it matters.
- [ ] Which isotopes customers use, and the calibration workflow they follow today (step function or Offset: Enter).
- [ ] Target OS for customers, and whether instrument PCs have internet access (this decides how the app is installed, see Risks).

## Architecture

&#91;embedded content: architecture · EINstudio layers over a Qt-free twilite package\]

The driver talks to the real device and to the simulator over the same protocol, so the code above it can't tell which one it's connected to. Only the top layer depends on Qt.

## Repository layout

A single public GPLv3 repo set up as a uv workspace. The driver is its own installable package with no Qt dependency, and the EINstudio app depends on it.

```
twilite-acq/
├── pyproject.toml              # uv workspace root
├── LICENSE                     # GPLv3
├── packages/twilite/           # pure Python, no Qt
│   └── src/twilite/
│       ├── protocol.py         # line parsing, IAC stripping, command strings
│       ├── driver.py           # TwiliteClient: connect, login, start/stop, stream
│       ├── sample.py           # Sample dataclass
│       ├── storage.py          # streaming writer, recovery, exports
│       ├── correction.py       # background, decay, branching ratio, calibration
│       ├── isotopes.py         # half-lives and branching ratios
│       └── sim/
│           ├── server.py       # asyncio telnet server
│           ├── profiles.py     # firmware variants (banner, login, commands)
│           └── scenarios.py    # background, bolus, calibration step, faults
├── apps/twiliteacq/            # EINstudio app
│   ├── main.py
│   ├── model.py
│   ├── viewmodel.py
│   ├── view.py
│   ├── layouts/mainLayout.py
│   ├── config.yaml
│   └── instrumentConfig.yaml   # IP, port, login, simulate: true/false
├── tests/
│   ├── fixtures/transcripts/   # raw sessions recorded from real devices
│   ├── unit/
│   ├── integration/
│   ├── app/
│   └── hardware/
└── docs/protocol.md            # the protocol as observed, kept up to date
```

## Standalone driver

`TwiliteClient` is a blocking, single-connection client built on `socket` (Python 3.13 dropped `telnetlib`). It runs in a plain thread, so it works the same from a script, from a test or from EINstudio's ViewModel worker.

```python
client = TwiliteClient(host="10.0.52.25", port=23, user="admin", password="ccount",
                       timeout=5.0, raw_log=Path("session.log"))
client.connect()                 # banner, optional login, wait for prompt
client.set_query_rate(10)        # qrate 10 -> 1 report per second
for sample in client.stream():   # sends showc, yields Sample objects
    ...
client.stop(); client.close()    # stop showc, send bye
```

`Sample` holds `index` (the `[n]` counter), `singles1`, `singles2`, `coincidences`, any extra fields kept as `raw_extra`, the raw line, `t_wall` (PC clock) and `t_mono` (monotonic clock).

How it behaves:

1. **Parsing lives in `protocol.py`** as pure functions: `strip_iac(bytes)`, `split_lines(buffer)` and `parse_sample(line)`. A line that doesn't parse is logged and skipped, never fatal. The field order comes from one table in the code, so fixing it after the hardware session is a one-line change.
2. **Telnet negotiation:** any `IAC DO/WILL` request is refused with `WONT/DONT`, and IAC sequences are removed from the data. That's the minimum a raw socket needs to talk to a telnet server.
3. **Duplicates and gaps:** the driver follows `[n]`. A repeated index means the counter hasn't updated, so the sample is dropped. A jump in the index is reported as a gap event with the number of samples missed. A drop in the index means the device restarted, which is reported as a reset event.
4. **Connection loss:** a read timeout or closed socket raises `ConnectionLost`. The driver doesn't reconnect by itself; the Model decides whether to, so tests can check both cases.
5. **Raw log:** every byte in and out is appended to a log file with timestamps. This is the most useful tool for diagnosing problems at a customer site.
6. **Lazy import:** the EINstudio Model imports the driver only inside `connect()`, as EINstudio's instrument guide recommends, so the app starts even when a package is missing.

## Simulated device

`twilite.sim` is an asyncio TCP server that behaves like the device, running on localhost:2323 by default. It is used in three ways: as the backend while developing the GUI, as the target for the integration tests, and for customer demos.

```
uv run python -m twilite.sim --profile coincident-counter --scenario bolus --isotope F-18
```

**Firmware profiles** set the banner, whether a login is required, the command set, line endings and IAC negotiation. Two profiles to start: `blood-sampler` (as in the manual) and `coincident-counter` (as in the screenshot). After the hardware session, the recorded transcript decides each profile's exact bytes.

**Scenarios** generate the counts:

| Scenario | What it produces | Used for |
| --- | --- | --- |
| `background` | Poisson singles \~2000/s and coincidences \~120/s, the levels in the manual's example | Background averaging |
| `bolus` | Background, then a gamma-variate peak decaying with the isotope half-life | Live plot, the full correction chain |
| `calibration-step` | Background, then a step when the source goes in, decaying | Calibration factor workflow |
| `long-decay` | A constant source over several half-lives | QA check: decay-corrected result is flat |
| `replay` | Plays back a recorded transcript at real speed | Regression on real data |

**Fault injection** via command-line flags or a test API: drop the connection after N samples, send a malformed line, stall for X seconds, skip or repeat `[n]`, restart the counter, refuse the login. The scenarios use a fixed random seed, so a test always gets the same numbers.

## Test suite

pytest, in four layers. `uv run pytest` runs the first three in a few seconds with no hardware. The hardware layer only runs with `--hardware --host <ip>`.

| Layer | Runs against | Covers |
| --- | --- | --- |
| Unit | Pure functions | Line parsing (including the manual's sample lines and malformed input), IAC stripping, split lines across TCP packets, duplicate/gap/reset detection, decay and calibration maths against values worked out by hand, streaming writer and recovery of a half-written file |
| Integration | Simulator on a random localhost port | Connect and login for both profiles, `qrate`, start/stop, a full acquisition to disk, every fault injection, a timeout firing within its limit |
| App | EINstudio Model and ViewModel, headless | Model runs in a plain script with the simulator (no Qt); ViewModel emits the right signals in the right order; one pytest-qt smoke test opens the window, connects and acquires for 5 s |
| Hardware | A real twilite | The integration tests repeated on the device, a 30-minute run with zero lost samples, cable pull and reconnect, power-cycle during acquisition |

Two habits keep the suite useful:

- **Every recorded transcript becomes a fixture.** If a customer reports a problem, their raw log goes into `tests/fixtures/transcripts/` along with a test that reproduces it.
- **Golden-file tests for exports.** Once we have a real PSAMPLE `.crv` file, the tests check that our writer produces the same columns and format.

GitHub Actions runs the first three layers on Windows, macOS and Linux for every push. That costs nothing in Phase 1 and gets the cross-platform builds ready for Phase 2.

## EINstudio GUI app

The app follows EINstudio's MVVM-Layout rules: calls go inward, results come back out as signals, and the Model never imports Qt.

- **`model.py`** owns the `TwiliteClient` (or the simulator's address when `simulate: true`), the sample buffer, the open storage writer, and the correction settings. Its `acquire()` loop runs in a plain thread. It takes a callback, so it can also run from a script.
- **`viewmodel.py`** owns the worker thread and turns Model callbacks into signals: `connectionChanged(bool)`, `acquisitionChanged(bool)`, `samplesAppended(t, s1, s2, coinc)`, `gapDetected(int)`, `errorOccurred(str)`. It checks prerequisites before every call (connected? already running?) and turns exceptions into messages. It sends plot updates at most 10 times a second, whatever the data rate.
- **`view.py`** wires buttons to ViewModel methods and signals to plot and status updates. Closing the window disconnects cleanly first.
- **`layouts/mainLayout.py`** places the widgets.

Screens and controls for Phase 1:

1. **Connection bar:** IP and port, Connect/Disconnect, a status indicator (disconnected, connecting, connected, acquiring, error) and the firmware banner text.
2. **Acquisition:** Start/Stop, report rate (`qrate`), "End by" user/time, a mark-event button with a text field (replacing PSAMPLE's timestamp dialog), elapsed time and sample count.
3. **Live plot:** coincidences, singles 1 and singles 2 against time, each with a show/hide checkbox, plus a large readout of the latest coincidence value. Gaps show as breaks in the line.
4. **Correction panel:** isotope, PET start time, background window or a typed-in value, calibration factor, and a toggle between raw and corrected display.
5. **Calibration panel:** load a calibration run, choose the background and plateau windows by dragging, enter the PET activity in kBq/cc, then compute and save the factor.

The app saves its settings on exit and restores them on the next start, as PSAMPLE does.

## Storage, export and correction

**Streaming storage.** Each acquisition writes one CSV, `YYYYMMDD_HHMMSS_twilite.partial.csv`, flushed after every sample and synced to disk every few seconds. The header comment lines record the start time, device IP, firmware banner, report rate, app version and the correction settings. The columns are `index, t_wall_iso, t_rel_s, singles1, singles2, coincidences`, plus one column per extra device field. On a clean stop the file is renamed to `.csv`. On startup the app looks for `.partial.csv` files and offers to recover them. Raw counts are never overwritten: corrected values exist only in exports.

**Exports:**

- **CSV:** raw plus corrected columns, with the settings in the header.
- **PSAMPLE-compatible `.crv`:** tab-separated date and time, then coincidences and singles, as the manual describes. Customers' existing scripts and PMOD tools keep working. Needs a real `.crv` file to match against.
- **Corrected TAC in PMOD's blood format** (sample mid-time and kBq/cc), for customers who still model in PKIN. Small and worth including, but confirm it's in scope.
- **Events file** for the marked events.

**Correction maths.** The manual's order: subtract the LYSO background, correct for decay to the PET scan start, divide by the branching ratio, multiply by the calibration factor. With R(t) the coincidence rate, t in seconds from the PET scan start and λ = ln 2 / T½:

```latex
C(t) = \mathrm{CF} \cdot \frac{\left(R(t) - B\right) e^{\lambda t}}{\mathrm{BR}}
```

The background B is either the mean of R over all samples before t = 0, or a value typed in. Output before t = 0 is cut off, as PSAMPLE does. The calibration factor comes from a phantom run, using the plateau window after the source goes in:

```latex
\mathrm{CF} = \frac{A_{\mathrm{PET}}}{\operatorname{mean}_{\text{plateau}}\left[\left(R(t) - B\right) e^{\lambda t} / \mathrm{BR}\right]}
```

Here A\_PET is the phantom activity measured by the PET in kBq/cc, and B is averaged over a background window placed before the step.

| Isotope | Half-life | Branching ratio |
| --- | --- | --- |
| F-18 | 109.77 min | 0.967 |
| Ga-68 | 67.71 min | 0.891 |
| C-11 | 20.36 min | 0.998 |
| N-13 | 9.97 min | 0.998 |
| O-15 | 122.2 s | 0.999 |
| Cu-64 | 12.70 h | 0.174 |

The Ga-68 and Cu-64 branching ratios come from the manual. The other values are approximate standard figures from memory and must be checked against a nuclear data table (the manual points to Turku PET Centre) before they go into `isotopes.py`. Users can also enter a custom isotope.

PSAMPLE's cutting and resampling tools are not in the Phase 1 scope. They are candidates for Phase 2.
