"""Streaming CSV storage of an acquisition, recovery of interrupted files, and exports.

One acquisition is one CSV file. Comment lines carry the metadata (``# key: value``,
at the top) and the events (``# event,<time>,<t_rel>,<kind>,<text>``, anywhere). The
file is called ``*.partial.csv`` while it is being written and renamed to ``*.csv``
when the acquisition ends cleanly. Raw counts are never changed: corrected values
only exist in exports.
"""

from __future__ import annotations

import csv
import io
import math
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from twilite.correction import CorrectionSettings, apply
from twilite.sample import Sample

PARTIAL_SUFFIX = ".partial.csv"
FINAL_SUFFIX = ".csv"
COLUMNS = ("index", "t_wall_iso", "t_rel_s", "singles1", "singles2", "coincidences")
EVENT_PREFIX = "# event,"


def _iso(t_wall: float) -> str:
    return datetime.fromtimestamp(t_wall).isoformat(timespec="milliseconds")


def _from_iso(text: str) -> float:
    return datetime.fromisoformat(text).timestamp()


def _one_line(value: object) -> str:
    return " | ".join(str(value).splitlines())


@dataclass(slots=True)
class EventRecord:
    """An event stored with an acquisition: a user mark or a connection change."""

    t_wall: float
    t_rel_s: float
    kind: str
    text: str


###############################################################################
# Writing                                                                     #
###############################################################################


class AcquisitionWriter:
    """Appends samples to ``<directory>/YYYYMMDD_HHMMSS_twilite.partial.csv``.

    Every sample is flushed at once and the file is synced to disk at most every
    ``sync_interval_s``. Thread-safe, so the GUI thread can mark events while the
    acquisition thread writes samples.

    Args:
        directory: Folder for the file; created if missing.
        metadata: ``{key: value}`` written as header comments.
        start_wall: PC time of the acquisition start; ``None`` for now.
        start_mono: Monotonic time of the start, the zero of ``t_rel_s``; ``None``
            for now.
        sync_interval_s: Longest time between two syncs to disk.
    """

    def __init__(self, directory: str | Path, metadata: dict[str, object] | None = None,
                 start_wall: float | None = None, start_mono: float | None = None,
                 sync_interval_s: float = 5.0):
        self.start_wall = time.time() if start_wall is None else start_wall
        self.start_mono = time.monotonic() if start_mono is None else start_mono
        self.sync_interval_s = sync_interval_s
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        stem = datetime.fromtimestamp(self.start_wall).strftime("%Y%m%d_%H%M%S") + "_twilite"
        self.path = _unique(self.directory / (stem + PARTIAL_SUFFIX))
        self.sample_count = 0
        self._lock = threading.Lock()
        self._extra_count: int | None = None
        self._last_sync = time.monotonic()
        self._file = open(self.path, "w", newline="", encoding="utf-8")
        self._csv = csv.writer(self._file, lineterminator="\n")
        header = {"start_time": _iso(self.start_wall), **(metadata or {})}
        for key, value in header.items():
            self._file.write(f"# {key}: {_one_line(value)}\n")
        self._sync()

    def relative_time(self, sample: Sample) -> float:
        return sample.t_mono - self.start_mono

    def write_sample(self, sample: Sample) -> None:
        with self._lock:
            if self._extra_count is None:
                self._extra_count = len(sample.raw_extra)
                extras = [f"extra{i + 1}" for i in range(self._extra_count)]
                self._csv.writerow([*COLUMNS, *extras])
            extras = list(sample.raw_extra[:self._extra_count])
            extras += [""] * (self._extra_count - len(extras))
            self._csv.writerow([
                sample.index, _iso(sample.t_wall), f"{self.relative_time(sample):.3f}",
                sample.singles1, sample.singles2, sample.coincidences, *extras,
            ])
            self.sample_count += 1
            self._file.flush()
            if time.monotonic() - self._last_sync >= self.sync_interval_s:
                self._sync()

    def write_event(self, kind: str, text: str = "", t_wall: float | None = None) -> EventRecord:
        """Store an event; returns it with its times filled in."""
        now_wall, now_mono = time.time(), time.monotonic()
        t_wall = now_wall if t_wall is None else t_wall
        record = EventRecord(t_wall, now_mono - self.start_mono - (now_wall - t_wall), kind, _one_line(text))
        with self._lock:
            buffer = io.StringIO()
            csv.writer(buffer, lineterminator="\n").writerow(
                [_iso(record.t_wall), f"{record.t_rel_s:.3f}", record.kind, record.text])
            self._file.write(EVENT_PREFIX + buffer.getvalue())
            self._file.flush()
            self._sync()
        return record

    def finish(self) -> Path:
        """Sync, close and rename to ``*.csv``; return the final path."""
        with self._lock:
            if self._file.closed:
                return self.path
            self._sync()
            self._file.close()
            final = _unique(self.path.with_name(self.path.name.removesuffix(PARTIAL_SUFFIX) + FINAL_SUFFIX))
            os.replace(self.path, final)
            self.path = final
            return final

    def abandon(self) -> Path:
        """Close the file but leave it as ``*.partial.csv`` (for tests of recovery)."""
        with self._lock:
            if not self._file.closed:
                self._file.close()
            return self.path

    def _sync(self) -> None:
        self._file.flush()
        os.fsync(self._file.fileno())
        self._last_sync = time.monotonic()


def _unique(path: Path) -> Path:
    """Return ``path``, or ``path`` with ``_2``, ``_3``... before the suffix if it exists."""
    if not path.exists():
        return path
    name = path.name
    suffix = PARTIAL_SUFFIX if name.endswith(PARTIAL_SUFFIX) else "".join(path.suffixes[-1:])
    stem = name.removesuffix(suffix)
    n = 2
    while (candidate := path.with_name(f"{stem}_{n}{suffix}")).exists():
        n += 1
    return candidate


###############################################################################
# Reading and recovery                                                        #
###############################################################################


@dataclass(slots=True)
class Acquisition:
    """An acquisition read back from its CSV file."""

    path: Path
    metadata: dict[str, str] = field(default_factory=dict)
    index: list[int] = field(default_factory=list)
    t_wall: list[float] = field(default_factory=list)
    t_rel_s: list[float] = field(default_factory=list)
    singles1: list[float] = field(default_factory=list)
    singles2: list[float] = field(default_factory=list)
    coincidences: list[float] = field(default_factory=list)
    extras: list[tuple[float, ...]] = field(default_factory=list)
    extra_columns: list[str] = field(default_factory=list)
    events: list[EventRecord] = field(default_factory=list)
    skipped_lines: int = 0

    def __len__(self) -> int:
        return len(self.index)


def read_acquisition(path: str | Path) -> Acquisition:
    """Read an acquisition file, skipping lines that do not parse (a half-written end)."""
    acq = Acquisition(Path(path))
    header_done = False
    with open(path, newline="", encoding="utf-8") as file:
        for line in file:
            if not line.endswith("\n"):
                acq.skipped_lines += 1  # the write was interrupted mid-line
                continue
            line = line.rstrip("\r\n")
            if line.startswith(EVENT_PREFIX):
                try:
                    stamp, t_rel, kind, text = next(csv.reader([line.removeprefix(EVENT_PREFIX)]))
                    acq.events.append(EventRecord(_from_iso(stamp), float(t_rel), kind, text))
                except (ValueError, StopIteration):
                    acq.skipped_lines += 1
            elif line.startswith("#"):
                key, _, value = line[1:].partition(":")
                acq.metadata[key.strip()] = value.strip()
            elif not header_done:
                columns = next(csv.reader([line]))
                acq.extra_columns = columns[len(COLUMNS):]
                header_done = True
            elif line:
                try:
                    _append_row(acq, next(csv.reader([line])))
                except (ValueError, IndexError):
                    acq.skipped_lines += 1
    return acq


def _append_row(acq: Acquisition, row: list[str]) -> None:
    if len(row) < len(COLUMNS):
        raise ValueError("short row")
    index, stamp, t_rel = int(row[0]), _from_iso(row[1]), float(row[2])
    s1, s2, c = (_number(v) for v in row[3:6])
    extras = tuple(_number(v) for v in row[6:] if v != "")
    acq.index.append(index)
    acq.t_wall.append(stamp)
    acq.t_rel_s.append(t_rel)
    acq.singles1.append(s1)
    acq.singles2.append(s2)
    acq.coincidences.append(c)
    acq.extras.append(extras)


def _number(text: str) -> float:
    try:
        return int(text)
    except ValueError:
        return float(text)


def find_partial_files(directory: str | Path) -> list[Path]:
    """Return the ``*.partial.csv`` files left in ``directory`` by interrupted runs."""
    directory = Path(directory)
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*" + PARTIAL_SUFFIX))


def recover(path: str | Path) -> Path:
    """Turn an interrupted ``*.partial.csv`` into a clean ``*.csv``; return its path.

    The rows that were written completely are kept, a half-written last line is
    dropped, and a ``recovered`` line is added to the header.
    """
    path = Path(path)
    acq = read_acquisition(path)
    final = _unique(path.with_name(path.name.removesuffix(PARTIAL_SUFFIX) + FINAL_SUFFIX))
    tmp = final.with_name(final.name + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as file:
        for key, value in acq.metadata.items():
            file.write(f"# {key}: {value}\n")
        file.write(f"# recovered: {_iso(time.time())}, {len(acq)} samples kept, "
                   f"{acq.skipped_lines} lines dropped\n")
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([*COLUMNS, *acq.extra_columns])
        for i in range(len(acq)):
            extras = list(acq.extras[i]) + [""] * (len(acq.extra_columns) - len(acq.extras[i]))
            writer.writerow([acq.index[i], _iso(acq.t_wall[i]), f"{acq.t_rel_s[i]:.3f}",
                             acq.singles1[i], acq.singles2[i], acq.coincidences[i], *extras])
        for event in acq.events:
            buffer = io.StringIO()
            csv.writer(buffer, lineterminator="\n").writerow(
                [_iso(event.t_wall), f"{event.t_rel_s:.3f}", event.kind, event.text])
            file.write(EVENT_PREFIX + buffer.getvalue())
        file.flush()
        os.fsync(file.fileno())
    os.replace(tmp, final)
    path.unlink()
    return final


###############################################################################
# Exports                                                                     #
###############################################################################

#: PROVISIONAL until a real PSAMPLE .crv file is available to compare against: the
#: manual only says "tab-separated date and time, then coincidences and singles".
CRV_DATE_FORMAT = "%d.%m.%Y"
CRV_TIME_FORMAT = "%H:%M:%S"


def export_csv(acq: Acquisition, path: str | Path, settings: CorrectionSettings | None = None) -> Path:
    """Write raw counts plus, with ``settings``, time from PET start and corrected values."""
    path = Path(path)
    corrected: dict[int, float] = {}
    header = dict(acq.metadata)
    if settings is not None:
        t_pet = [t - settings.pet_start for t in acq.t_wall]
        _, values, background = apply(settings, acq.t_wall, acq.coincidences)
        kept = [i for i, t in enumerate(t_pet) if t >= 0]
        corrected = dict(zip(kept, values))
        header.update(_settings_header(settings, background))
    with open(path, "w", newline="", encoding="utf-8") as file:
        for key, value in header.items():
            file.write(f"# {key}: {value}\n")
        writer = csv.writer(file, lineterminator="\n")
        columns = [*COLUMNS, *acq.extra_columns]
        if settings is not None:
            columns += ["t_pet_s", "activity_kBq_cc"]
        writer.writerow(columns)
        for i in range(len(acq)):
            row = [acq.index[i], _iso(acq.t_wall[i]), f"{acq.t_rel_s[i]:.3f}",
                   acq.singles1[i], acq.singles2[i], acq.coincidences[i], *acq.extras[i]]
            row += [""] * (len(COLUMNS) + len(acq.extra_columns) - len(row))
            if settings is not None:
                row.append(f"{acq.t_wall[i] - settings.pet_start:.3f}")
                row.append(f"{corrected[i]:.6g}" if i in corrected else "")
            writer.writerow(row)
    return path


def export_crv(acq: Acquisition, path: str | Path) -> Path:
    """Write a PSAMPLE-style ``.crv``: date, time, coincidences, singles 1, singles 2."""
    path = Path(path)
    with open(path, "w", newline="", encoding="latin-1") as file:
        for i in range(len(acq)):
            stamp = datetime.fromtimestamp(acq.t_wall[i])
            file.write("\t".join([
                stamp.strftime(CRV_DATE_FORMAT), stamp.strftime(CRV_TIME_FORMAT),
                str(acq.coincidences[i]), str(acq.singles1[i]), str(acq.singles2[i]),
            ]) + "\r\n")
    return path


def export_pmod_blood(acq: Acquisition, path: str | Path, settings: CorrectionSettings) -> Path:
    """Write the corrected TAC in PMOD's two-column blood format (seconds, kBq/cc).

    PROVISIONAL: the sample time is the time the report arrived; whether it should be
    moved to the middle of the counting interval depends on the open protocol
    questions.
    """
    path = Path(path)
    t_out, values, _ = apply(settings, acq.t_wall, acq.coincidences)
    with open(path, "w", newline="", encoding="latin-1") as file:
        file.write("sample-time[seconds]\twhole-blood[kBq/cc]\r\n")
        for t, value in zip(t_out, values):
            if not math.isnan(value):
                file.write(f"{t:.1f}\t{value:.6g}\r\n")
    return path


def export_events(acq: Acquisition, path: str | Path) -> Path:
    """Write the events of an acquisition as a CSV."""
    path = Path(path)
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(["time", "t_rel_s", "kind", "text"])
        for event in acq.events:
            writer.writerow([_iso(event.t_wall), f"{event.t_rel_s:.3f}", event.kind, event.text])
    return path


def _settings_header(settings: CorrectionSettings, background: float) -> dict[str, str]:
    iso = settings.isotope
    return {
        "isotope": f"{iso.name} (half-life {iso.half_life_s:g} s, branching ratio {iso.branching_ratio:g})",
        "pet_start": _iso(settings.pet_start),
        "background": f"{background:.6g}" + (" (mean before PET start)" if settings.background is None else ""),
        "calibration_factor": f"{settings.calibration_factor:.6g}",
    }
