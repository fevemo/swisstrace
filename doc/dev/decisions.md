# Decisions and open questions

Phase 1 goal: replace PMOD PSAMPLE's acquisition and correction functions for the
Swisstrace twilite. Built bottom-up: Qt-free driver, simulator, tests against the
simulator (real hardware on request), EINstudio app on top, so instrument time goes on
confirming behaviour, not writing code.

Sources: the device's telnet help screen, the PMOD *PSAMPLE Software for twilite*
manual (2019) and raw sessions recorded from a *Coincident Counter V3.00* (2026-10-03).

## Decisions

### Protocol and driver

- **Only the observed protocol.** The driver and simulator implement exactly
  [protocol.md](protocol.md). Older firmware (the *SwissTrace BLOOD SAMPLER* console in
  the PSAMPLE manual, with `adc` and `rinfo`) is not supported until a session with one
  is recorded.
- **Plain socket, no telnet library.** The device sends no option negotiation and does
  not echo; `telnetlib` is gone in Python 3.13.
- **Blocking client in a plain thread.** Works the same from a script, a test or a
  ViewModel worker.
- **`[n]` is stored, not policed.** It cannot skip inside a TCP connection; a skip is
  only logged. Lost data shows as lost time, recorded as connection events.
- **Keepalive after 8 s idle**, against the device's ~19 s idle timeout.
- **The driver never reconnects by itself.** The Model decides, so tests can check both.
- **Raw byte log on by default.** The most useful tool for diagnosing problems at a
  customer site.
- **Lazy import of the driver in the Model**, so the app starts even if it is broken.

### Measurement and data

- **`qrate` is the sampling rate.** The PSAMPLE manual says the counting interval is set
  on the touch screen and `qrate` only sets the report rate; the device shows otherwise:
  over telnet `qrate` sets both the counting window and the report period, values are
  counts/s, and the touch-screen interval does not affect `showc`. The app sets `qrate`
  before every acquisition.
- **PC clock time stamps**, as PSAMPLE does; users sync the PC clock with the scanner.
- **Sample time = report arrival time**, as PSAMPLE, for recorded samples; the middle of
  merged reports for resampled ones. `.tac` frames use the counting intervals.
- **One streaming CSV per acquisition, raw counts never changed**; `.partial.csv` while
  writing so a crash loses nothing and can be recovered.
- **Edits never touch the source file**; edited data is saved as a new file with the
  edits listed in its header.
- **Resampling only merges** (whole multiples), weighted by counting interval, so no
  counts are lost and no data is invented.
- **Correction follows PSAMPLE's formula and order**, including cutting off output
  before the PET start.
- **`.crv` export matches PSAMPLE byte for byte** so existing scripts and PMOD tools
  keep working.

### App and distribution

- **EINstudio MVVM**: Model without Qt, ViewModel owns threads and turns exceptions into
  `errorOccurred`, plot updates throttled to 10/s.
- **Settings and state persist** (`instrumentConfig.yaml`, `state.yaml`), as PSAMPLE
  restores its settings.
- **Installers via Briefcase**, user data in the user's folders (see
  [architecture.md](architecture.md#where-files-go-locationspy)), data in the home folder
  rather than cloud-synced *Documents*.
- **Simulator on by default** in this test phase so the app can be tried without the
  device.

## Open questions

- [ ] What does the touch-screen counting interval affect, if not `showc`?
- [ ] Which `qrate` does the device use after power-up? (The app sets it anyway.)
- [ ] Which firmware versions and twilite generations are in the field?
- [ ] A corrected TAC exported by PMOD, to check the `.bld` and `.tac` exports against.
- [ ] Isotope half-lives and branching ratios to verify against a nuclear data table
  (see [data-and-correction.md](data-and-correction.md#isotopes)).
- [ ] Which isotopes customers use, and their calibration workflow today (step
  function or entered offset).
- [ ] Target OS for customers, and whether instrument PCs have internet access.
- [ ] Code-signing certificates (Apple Developer ID, Windows) for release builds.

Answered (details in [protocol.md](protocol.md)): field order and units of a report
line, `[n]` behaviour, how to stop `showc`, login, line endings and negotiation, the
need for the touch-screen play button, the PSAMPLE `.crv` format.

## Phase 2 candidates

Signed release installers; support for other firmware versions once recorded;
confirming the PMOD exports against real PMOD files.
