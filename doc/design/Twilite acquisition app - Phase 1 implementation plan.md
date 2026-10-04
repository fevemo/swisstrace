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

- The manual says the counting interval (1, 2, 5 or 10 s) is set on the twilite's touch screen and `qrate` only sets how often values are reported. The device contradicts this (see the open questions): over telnet, `qrate` sets the counting window, every line is a new sample, and `[n]` counts printed lines.
- PSAMPLE timestamps every sample with the PC's clock, and users must sync that clock with the PET scanner. We record the PC time too.
- The manual's command menu lists `qrate 50` as 50000 ms, which contradicts n × 100 ms. Probably a typo; to verify.

## Open questions before coding

Answer them in a 30-minute session on the device recording everything with PuTTY's session log:

- [x] Field order and units of a `showc` line. Counts per counting interval, or counts per second?
    - A: counts per second (sampling at 10hz gives only multiples of 10 for the counts)
    - Checked 2026-10-03: at `qrate 10` the values are plain integers. The device counts over the `qrate` period and scales to counts per second, so `qrate 1` gives a 10 cps resolution.
    - Field order: `[n] singles1 singles2 coincidences 0.0 0.0` (checked with a source at one detector). `ccnt` prints ` Counter 1 = …`, ` Counter 2 = …` and ` Counter 3 = …` in the same order.
- [x] Does `[n]` go up once per counting interval or once per printed line? Does it reset on reconnect or on power-up?
    - A: once per printed line i.e if you stop the output and restart it, `[n]` continues from the last printed value rather than resetting.
    - From the raw logs: `[n]` also continues across a reconnect (647 → 648, 733 → 734) and across a `qrate` change. It restarts at `[0]` on power-up (the device was power-cycled before 21:23 on 2026-10-03). `show` also advances it.
- [x] Can the counting interval be set over telnet at all, or only on the touch screen? This decides what "set the sampling rate" means in our scope.
    - A: qrate sets the reporting rate, counts are always in counts per second.
    - No: there is no telnet command for it. `qrate` sets both the report period and the counting window. The touch-screen interval does not seem to affect `showc`. Check whether it affects anything else.
- [x] Does `showc` need the green play button pressed on the touch screen (PMTs on) first? What does it print otherwise?
    - A: yes, it requires the green play button to be pressed; otherwise, it doesnt send any data.
- [x] Login: is there one on current firmware? Which firmware versions and twilite generations are in the field?
    - A: yes, default login is required on current firmware.
    - Recorded: banner `Coincident Counter - Telnet Server V3.00, please login...`, prompts `Username: ` and `Password: `, then `admin` / `ccount`. Still open: which firmware versions and generations are in the field.
    - The login checks nothing: any user name and password get in (tried 2026-10-03).
- [x] Exact line endings and any telnet option negotiation (IAC bytes) on connect.
    - A (from the raw logs): every line ends in `\r\n`. The prompts `> `, `Username: ` and `Password: ` have no line ending. There is no telnet negotiation: not one IAC byte in eight sessions. The device does not echo commands. The banner uses ANSI escape codes (`ESC[2J` clear screen, `ESC[37;44m` colours, `ESC[0m`), which the driver now strips. The device accepts `\r\n` from the client.
- [x] How do you stop `showc`? Another command, a blank line, or only a disconnect?
    - A: `showc` is stopped by pressing enter.
    - One more report line can arrive after the Enter, before the `> ` prompt; the driver reads up to the prompt.
    - The disconnects a few seconds after stopping are the device's **idle timeout**. It closes a connection after 19.0–19.6 s without traffic at the prompt, with or without a previous `showc`. A bare Enter resets the timer, and the `showc` stream counts as traffic. PuTTY sends nothing while you wait, so it drops too. The app now sends an Enter after 8 s of idle time.
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
│       ├── protocol.py         # device facts, line parsing, command strings
│       ├── driver.py           # TwiliteClient: connect, login, start/stop, stream
│       ├── sample.py           # Sample dataclass
│       ├── storage.py          # streaming writer, recovery, exports
│       ├── correction.py       # background, decay, branching ratio, calibration
│       ├── isotopes.py         # half-lives and branching ratios
│       └── sim/
│           ├── server.py       # asyncio telnet server
│           └── scenarios.py    # background, bolus, calibration step, replay
├── apps/twiliteacq/            # EINstudio app
│   ├── main.py
│   ├── model.py
│   ├── viewmodel.py
│   ├── view.py
│   ├── layouts/mainLayout.py
│   ├── config.yaml
│   └── instrumentConfig.yaml   # IP, port, simulate: true/false
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
client = TwiliteClient(host="10.0.52.25", port=23, timeout=5.0, raw_log=Path("session.log"))
client.connect()                 # banner, login, wait for prompt
client.set_query_rate(10)        # qrate 10 -> 1 report per second
for sample in client.stream():   # sends showc, yields Sample objects
    ...
client.stop(); client.close()    # stop showc, send bye
```

`Sample` holds `index` (the `[n]` counter), `singles1`, `singles2`, `coincidences`, any extra fields kept as `raw_extra`, the raw line, `t_wall` (PC clock) and `t_mono` (monotonic clock).

How it behaves:

1. **Parsing lives in `protocol.py`** as pure functions: `split_lines(buffer)`, `parse_sample(line)` and `parse_counters(reply)`. A line that doesn't parse is logged and skipped, never fatal. Every device fact (field order, prompts, idle timeout) is a constant at the top of the module.
2. **Only the observed protocol:** the device sends no telnet negotiation and doesn't echo, so the driver speaks plain `\r\n` lines over a socket. Older firmware is not supported until a session with one is recorded (see `doc/protocol.md`).
3. **`[n]` is stored, not policed:** it goes up by one per printed line and can't skip inside a TCP connection, so the driver only logs a warning if it ever does. Lost data shows up as lost time, which the Model records as connection events.
4. **Idle keepalive:** the device drops a connection after 19 s of silence at the prompt, so the app sends an empty line after 8 s of idle time.
5. **Connection loss:** a read timeout or closed socket raises `ConnectionLost`. The driver doesn't reconnect by itself; the Model decides whether to, so tests can check both cases.
6. **Raw log:** every byte in and out is appended to a log file with timestamps. This is the most useful tool for diagnosing problems at a customer site.
7. **Lazy import:** the EINstudio Model imports the driver only inside `connect()`, as EINstudio's instrument guide recommends, so the app starts even when a package is missing.

## Simulated device

`twilite.sim` is an asyncio TCP server that behaves like the device, running on localhost:2323 by default. It is used in three ways: as the backend while developing the GUI, as the target for the integration tests, and for customer demos.

```
uv run python -m twilite.sim --scenario bolus --isotope F-18
```

It copies the bytes recorded from a Coincident Counter V3.00 on 2026-10-03: banner, login (which accepts anything), replies, one `[n]` per printed line, counts per second over the `qrate` period, and the 19 s idle timeout.

**Scenarios** generate the counts:

| Scenario | What it produces | Used for |
| --- | --- | --- |
| `background` | Poisson singles \~2000/s and coincidences \~120/s, the levels in the manual's example | Background averaging |
| `bolus` | Background, then a gamma-variate peak decaying with the isotope half-life | Live plot, the full correction chain |
| `calibration-step` | Background, then a step when the source goes in, decaying | Calibration factor workflow |
| `long-decay` | A constant source over several half-lives | QA check: decay-corrected result is flat |
| `replay` | Plays back a recorded transcript at real speed | Regression on real data |

**Fault injection** via command-line flags or a test API: drop the connection after N samples, or stall for X seconds. The scenarios use a fixed random seed, so a test always gets the same numbers.

## Test suite

pytest, in four layers. `uv run pytest` runs the first three in a few seconds with no hardware. The hardware layer only runs with `--hardware --host <ip>`.

| Layer | Runs against | Covers |
| --- | --- | --- |
| Unit | Pure functions | Line parsing (recorded device lines and malformed input), split lines across TCP packets, decay and calibration maths against values worked out by hand, streaming writer and recovery of a half-written file |
| Integration | Simulator on a random localhost port | Connect and login, `qrate`/`grate`/`ccnt`, start/stop, a full acquisition to disk, idle timeout and keepalive, dropped and stalled connections, replay of a recorded session |
| App | EINstudio Model and ViewModel, headless | Model runs in a plain script with the simulator (no Qt); ViewModel emits the right signals in the right order; one pytest-qt smoke test opens the window, connects and acquires for 5 s |
| Hardware | A real twilite | The integration tests repeated on the device, a 30-minute run with zero lost samples, cable pull and reconnect, power-cycle during acquisition |

Two habits keep the suite useful:

- **Every recorded transcript becomes a fixture.** If a customer reports a problem, their raw log goes into `tests/fixtures/transcripts/` along with a test that reproduces it.
- **Golden-file tests for exports.** Once we have a real PSAMPLE `.crv` file, the tests check that our writer produces the same columns and format.

GitHub Actions runs the first three layers on Windows, macOS and Linux for every push. That costs nothing in Phase 1 and gets the cross-platform builds ready for Phase 2.

## EINstudio GUI app

The app follows EINstudio's MVVM-Layout rules: calls go inward, results come back out as signals, and the Model never imports Qt.

- **`model.py`** owns the `TwiliteClient` (or the simulator's address when `simulate: true`), the sample buffer, the open storage writer, and the correction settings. Its `acquire()` loop runs in a plain thread. It takes a callback, so it can also run from a script.
- **`viewmodel.py`** owns the worker thread and turns Model callbacks into signals: `connectionChanged(bool)`, `acquisitionChanged(bool)`, `samplesAppended(t, s1, s2, coinc)`, `eventRecorded(kind, text)`, `errorOccurred(str)`. It checks prerequisites before every call (connected? already running?) and turns exceptions into messages. It sends plot updates at most 10 times a second, whatever the data rate.
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
