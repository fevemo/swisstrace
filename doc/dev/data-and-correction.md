# Data, correction and exports

Code: `packages/twilite/src/twilite/storage.py`, `correction.py`, `editing.py`,
`isotopes.py`.

## Acquisition file

One acquisition = one CSV in `dataDir`, `YYYYMMDD_HHMMSS_twilite.csv`.

- Written as `*.partial.csv`, flushed after every sample and synced to disk every few
  seconds; renamed to `*.csv` on a clean stop. At startup the app finds
  `*.partial.csv` files and offers to recover them (`find_partial_files`, `recover`).
- Header: `# key: value` comment lines (start time, device address, firmware banner,
  report rate `qrate n`, app version from `locations.appVersion()`, correction
  settings).
- Events (user marks, connection lost / reconnected) anywhere in the file:
  `# event,<iso time>,<t_rel>,<kind>,<text>`.
- Columns: `index, t_wall_iso, t_rel_s, singles1, singles2, coincidences`, then one
  column per extra device field. Values are counts per second as the device reports
  them.
- **Raw counts are never changed.** Corrected values exist only in exports.

### Edited files

The *Correction* page edits in memory and saves with `write_acquisition`, by default as
`..._edited.csv`, same format plus:

- one `# edit: ...` header line per edit applied, in order;
- columns `duration_s` (counting interval, ending at the time stamp) and
  `interpolated` (1 for a value replaced by a cut).

An acquisition as recorded is never overwritten; an edited file may be.

### PSAMPLE `.crv`

Reading (`read_crv`) and writing (`export_crv`). No header; `Y M D h m s.mmm` with
unpadded fields, then coincidences, singles 1, singles 2, tab-separated, `\n` line
endings. The export matches PSAMPLE byte for byte (golden-file test against
`tests/fixtures/psample/`). A `.crv` has no metadata: its report period comes from the
median spacing of the time stamps; isotope and PET start come from the UI.

## Sample timing

Sample `i` counts over `[t_wall - duration_s, t_wall]`. Its time everywhere (plot,
correction, `.bld`) is `storage.sample_times`:

- as recorded: `t_wall`, the arrival time of the report (end of its counting interval),
  as PSAMPLE does;
- resampled: the middle of the merged reports, `t_wall - (duration_s - period) / 2`.

`.tac` frames are the counting intervals themselves. `report_period` comes from the
`report_rate` header (`qrate n` → n × 0.1 s), else the median spacing, else 1 s.

## Correction

PSAMPLE's order: subtract background, decay-correct to the PET scan start, divide by
branching ratio, multiply by calibration factor. With R(t) the coincidence rate, t in
seconds from the PET scan start, λ = ln 2 / T½:

```
C(t) = CF · (R(t) − B) · e^(λt) / BR
```

- B is either the mean of R over all samples before t = 0 or a fixed value.
- Output before t = 0 is cut off, as in PSAMPLE.
- The PET start is a PC-clock time of day; its date is the data's. The PC clock must be
  synced with the scanner (PSAMPLE has the same requirement).

## Calibration

From a phantom run (background, then the source in until the rate is stable):

```
CF = A_PET / mean over plateau of [(R(t) − B) · e^(λt) / BR]
```

- B is averaged over a background window before the step; both windows are chosen by
  dragging regions on the plot.
- t runs from the PET reference time (the time A_PET is decay-corrected to), which
  defaults to the run's start.
- The isotope is the one selected on the *Correction* page.
- Fails if the plateau is not above background.

## Isotopes

| Isotope | Half-life | Branching ratio |
| --- | --- | --- |
| F-18 | 109.77 min | 0.967 |
| Ga-68 | 67.71 min | 0.891 |
| C-11 | 20.36 min | 0.998 |
| N-13 | 9.97 min | 0.998 |
| O-15 | 122.2 s | 0.999 |
| Cu-64 | 12.70 h | 0.174 |

Ga-68 and Cu-64 branching ratios come from the PSAMPLE manual. The others are standard
figures **still to verify** against a nuclear data table (the manual points to Turku PET
Centre) before clinical use. Users can enter a custom isotope.

## Editing (`editing.py`)

Both operations return a new `Acquisition`; the UI previews with `plan_cut` /
`plan_resample`. No undo: the user reloads the file.

**Cut** replaces samples in `[start, end]` on all three channels by a straight line from
the mean of the `n_average` samples just before to the mean of those just after, each
placed at the neighbouring sample. With neighbours on one side only, that side's mean is
held flat. Replaced samples are flagged `interpolated`. The UI selection snaps to
midway between samples.

**Resample** takes sections (start, end on the plot's time axis, period). It only
merges, never splits: a section's period must be a whole multiple of the current
sampling in it (`section_problems` explains why a section is invalid). A merged sample
lasts as long as its parts, has their duration-weighted mean rate (no counts lost) and
sits in their middle. A section's last sample may be shorter; a gap (lost connection)
starts a new sample. A sample on a boundary belongs to the earlier section; samples
outside every section are unchanged. `sampling_sections` gives the current sampling
as sections, used to initialise the dialog.

## Exports

| Export | Function | Content |
| --- | --- | --- |
| Raw CSV | `export_csv` without settings | Raw counts |
| PSAMPLE `.crv` | `export_crv` | See above |
| Events CSV | `export_events` | Marks and connection events |
| Corrected CSV | `export_csv` | Raw counts + time from PET start + kBq/cc, settings in header |
| PMOD blood `.bld` | `export_pmod_blood` | `sample-time[seconds]`, `whole-blood[kBq/cc]`; times from `sample_times` |
| PMOD TAC `.tac` | `export_pmod_tac` | Frame start/end (counting interval, clipped at 0) and kBq/cc. Header `start[seconds]	end[kBq/cc]	whole-blood` is PMOD's convention (time unit on the first column, concentration unit on the second), not a typo |

The corrected exports include in-memory edits and need the PET scan start. `.bld` times
and `.tac` are **provisional** until compared with files exported by PMOD.
