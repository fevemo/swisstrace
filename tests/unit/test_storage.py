import time
from datetime import datetime
from pathlib import Path

import pytest

from twilite import Sample, get_isotope
from twilite.correction import CorrectionSettings
from twilite.storage import (
    Acquisition, AcquisitionWriter, export_crv, export_csv, export_events, export_pmod_blood, export_pmod_tac,
    find_partial_files, read_acquisition, recover, report_period, write_acquisition,
)

FIXTURES = Path(__file__).parents[1] / "fixtures"
T0_WALL = 1_790_000_000.0
T0_MONO = 500.0


def samples(n, extras=(1.7, 1.6)):
    return [Sample(i, 2000 + i, 1500 + i, 120 + i, extras, f"[{i}]", T0_WALL + i, T0_MONO + i) for i in range(n)]


def write(tmp_path, n=5, finish=True):
    writer = AcquisitionWriter(tmp_path, {"device": "10.0.52.25:23", "banner": "Coincident Counter\nv2"},
                               start_wall=T0_WALL, start_mono=T0_MONO)
    for sample in samples(n):
        writer.write_sample(sample)
    return writer, (writer.finish() if finish else writer.path)


def test_file_name_and_rename_on_finish(tmp_path):
    writer = AcquisitionWriter(tmp_path, start_wall=T0_WALL, start_mono=T0_MONO)
    assert writer.path.name.endswith("_twilite.partial.csv")
    final = writer.finish()
    assert final.name.endswith("_twilite.csv")
    assert final.exists() and not list(tmp_path.glob("*.partial.csv"))


def test_round_trip(tmp_path):
    _, path = write(tmp_path)
    acq = read_acquisition(path)
    assert len(acq) == 5
    assert acq.index == [0, 1, 2, 3, 4]
    assert acq.coincidences == [120, 121, 122, 123, 124]
    assert acq.t_rel_s == [0.0, 1.0, 2.0, 3.0, 4.0]
    assert acq.t_wall[2] == pytest.approx(T0_WALL + 2, abs=1e-3)
    assert acq.extras[0] == (1.7, 1.6)
    assert acq.extra_columns == ["extra1", "extra2"]
    assert acq.metadata["device"] == "10.0.52.25:23"
    assert acq.metadata["banner"] == "Coincident Counter | v2"
    assert "start_time" in acq.metadata


def test_header_columns(tmp_path):
    _, path = write(tmp_path, n=1)
    lines = path.read_text().splitlines()
    assert "index,t_wall_iso,t_rel_s,singles1,singles2,coincidences,extra1,extra2" in lines


def test_events_are_stored(tmp_path):
    writer = AcquisitionWriter(tmp_path, start_wall=T0_WALL, start_mono=T0_MONO)
    for sample in samples(2):
        writer.write_sample(sample)
    writer.write_event("connection", "lost: cable pulled", T0_WALL + 5)
    writer.write_event("connection", "reconnected", T0_WALL + 6)
    writer.write_event("mark", 'injection, "left" arm')
    acq = read_acquisition(writer.finish())
    assert [e.kind for e in acq.events] == ["connection", "connection", "mark"]
    assert acq.events[0].text == "lost: cable pulled"
    assert acq.events[2].text == 'injection, "left" arm'
    assert len(acq) == 2


def test_partial_file_is_found_and_recovered(tmp_path):
    writer, path = write(tmp_path, finish=False)
    writer.abandon()
    with open(path, "a") as file:
        file.write("5,2026-10-02T10:00:05.000,5.0,20")  # interrupted mid-line
    assert find_partial_files(tmp_path) == [path]
    final = recover(path)
    assert not path.exists()
    assert final.name.endswith("_twilite.csv")
    acq = read_acquisition(final)
    assert len(acq) == 5 and acq.skipped_lines == 0
    assert "5 samples kept, 1 lines dropped" in acq.metadata["recovered"]
    assert find_partial_files(tmp_path) == []


def test_recovery_of_garbled_row(tmp_path):
    writer, path = write(tmp_path, n=3, finish=False)
    writer.abandon()
    with open(path, "a") as file:
        file.write("x,y\n")
    assert len(read_acquisition(recover(path))) == 3


def test_rows_are_flushed_before_the_file_is_closed(tmp_path):
    writer = AcquisitionWriter(tmp_path, sync_interval_s=0.0)
    writer.write_sample(Sample(1, 1, 2, 3, (), "", time.time(), time.monotonic()))
    assert writer.sample_count == 1
    assert len(read_acquisition(writer.path)) == 1
    writer.finish()


def test_durations_come_from_the_report_rate(tmp_path):
    writer = AcquisitionWriter(tmp_path, {"report_rate": "qrate 5 (500 ms)"}, start_wall=T0_WALL, start_mono=T0_MONO)
    for sample in samples(3):  # 1 s apart, but the header says 0.5 s
        writer.write_sample(sample)
    acq = read_acquisition(writer.finish())
    assert acq.duration_s == [0.5, 0.5, 0.5] and acq.interpolated == [False] * 3 and acq.edits == []
    acq.metadata.clear()
    assert report_period(acq) == pytest.approx(1.0)  # the spacing without a header


def test_raw_data_written_back_is_unchanged(tmp_path):
    _, path = write(tmp_path)
    again = write_acquisition(read_acquisition(path), tmp_path / "again.csv")
    assert again.read_text() == path.read_text()


def test_edited_data_round_trip(tmp_path):
    _, path = write(tmp_path)
    acq = read_acquisition(path)
    acq.edits = ["cut 1 samples", "resampled, with a\nline break"]
    acq.duration_s[1] = 2.5
    acq.interpolated[3] = True
    text = write_acquisition(acq, tmp_path / "edited.csv").read_text()
    assert "# edit: cut 1 samples\n# edit: resampled, with a | line break\n" in text
    assert "index,t_wall_iso,t_rel_s,singles1,singles2,coincidences,extra1,extra2,duration_s,interpolated" in text
    back = read_acquisition(tmp_path / "edited.csv")
    assert back.edits == ["cut 1 samples", "resampled, with a | line break"]
    assert back.duration_s == [1.0, 2.5, 1.0, 1.0, 1.0]
    assert back.interpolated == [False, False, False, True, False]
    assert back.extras == acq.extras and back.extra_columns == ["extra1", "extra2"]
    assert back.coincidences == acq.coincidences and "edit" not in back.metadata


def test_names_do_not_collide(tmp_path):
    first = AcquisitionWriter(tmp_path, start_wall=T0_WALL).finish()
    second = AcquisitionWriter(tmp_path, start_wall=T0_WALL).finish()
    assert first != second and first.exists() and second.exists()


@pytest.fixture
def acquisition(tmp_path):
    writer = AcquisitionWriter(tmp_path, start_wall=T0_WALL, start_mono=T0_MONO)
    for sample in samples(10):
        writer.write_sample(sample)
    writer.write_event("mark", "injection", T0_WALL + 5)
    return read_acquisition(writer.finish())


def test_export_csv_raw_only(acquisition, tmp_path):
    out = export_csv(acquisition, tmp_path / "raw.csv")
    rows = [line for line in out.read_text().splitlines() if not line.startswith("#")]
    assert rows[0].endswith("coincidences,extra1,extra2")
    assert len(rows) == 11


def test_export_csv_with_correction(acquisition, tmp_path):
    # Coincidences are 120..129 at t = -5..4 s from the PET start: background = mean(120..124) = 122.
    settings = CorrectionSettings(get_isotope("F-18"), pet_start=T0_WALL + 5, background=None)
    text = export_csv(acquisition, tmp_path / "corrected.csv", settings).read_text()
    assert "# isotope: F-18" in text
    assert "# background: 122 (mean before PET start)" in text
    rows = [line.split(",") for line in text.splitlines() if not line.startswith("#")]
    assert rows[0][-2:] == ["t_pet_s", "activity_kBq_cc"]
    assert rows[1][-1] == ""  # before the PET start
    assert float(rows[6][-1]) == pytest.approx((125 - 122) / 0.967, rel=1e-5)  # t = 0


def test_export_crv(acquisition, tmp_path):
    lines = export_crv(acquisition, tmp_path / "run.crv").read_bytes().split(b"\n")
    fields = lines[0].split(b"\t")
    assert len(fields) == 4 and fields[1:] == [b"120", b"2000", b"1500"]
    assert len(lines) == 11 and lines[-1] == b""


def test_export_crv_matches_psample(tmp_path):
    """Reading back a .crv written by PSAMPLE and exporting it again gives the same bytes."""
    original = FIXTURES / "psample" / "PMOD_Psample_Test_D1_D1.crv"
    acq = Acquisition(original)
    for i, line in enumerate(original.read_text().splitlines()):
        stamp, coincidences, singles1, singles2 = line.split("\t")
        *date, seconds = stamp.split(" ")
        whole, _, ms = seconds.partition(".")
        acq.t_wall.append(datetime(*map(int, date), int(whole), int(ms) * 1000).timestamp())
        acq.index.append(i)
        acq.coincidences.append(int(coincidences))
        acq.singles1.append(int(singles1))
        acq.singles2.append(int(singles2))
    assert len(acq) == 114
    assert export_crv(acq, tmp_path / "again.crv").read_bytes() == original.read_bytes()


def test_export_pmod_blood(acquisition, tmp_path):
    settings = CorrectionSettings(get_isotope("F-18"), pet_start=T0_WALL + 5, background=120.0,
                                  calibration_factor=0.5)
    lines = export_pmod_blood(acquisition, tmp_path / "run.bld", settings).read_text().splitlines()
    assert lines[0] == "sample-time[seconds]\twhole-blood[kBq/cc]"
    t, value = lines[1].split("\t")
    assert float(t) == pytest.approx(0.0, abs=0.01)
    assert float(value) == pytest.approx(0.5 * 5 / 0.967, rel=1e-5)
    assert len(lines) == 6


def test_export_pmod_tac(acquisition, tmp_path):
    settings = CorrectionSettings(get_isotope("F-18"), pet_start=T0_WALL + 5, background=120.0,
                                  calibration_factor=0.5)
    lines = export_pmod_tac(acquisition, tmp_path / "run.tac", settings).read_text().splitlines()
    assert lines[0] == "start[seconds]\tend[kBq/cc]\twhole-blood"
    assert [float(v) for v in lines[1].split("\t")[:2]] == [0.0, 0.0]  # frame clipped at the PET start
    start, end, value = lines[2].split("\t")
    assert (float(start), float(end)) == pytest.approx((0.0, 1.0), abs=0.01)  # the 1 s counting interval
    assert float(value) == pytest.approx(0.5 * 6 * 2 ** (1 / 6586.2) / 0.967, rel=1e-4)
    assert len(lines) == 6


def test_export_pmod_tac_frames_follow_the_durations(acquisition, tmp_path):
    acquisition.duration_s = [1.0] * 8 + [3.0, 1.0]  # sample 8 merges the reports of T0+6..T0+8 s
    settings = CorrectionSettings(get_isotope("F-18"), pet_start=T0_WALL, background=120.0)
    lines = export_pmod_tac(acquisition, tmp_path / "run.tac", settings).read_text().splitlines()
    frames = [tuple(float(v) for v in line.split("\t")[:2]) for line in lines[1:]]
    assert frames[-2:] == [(5.0, 8.0), (8.0, 9.0)]
    bld = export_pmod_blood(acquisition, tmp_path / "run.bld", settings).read_text().splitlines()
    assert [float(line.split("\t")[0]) for line in bld[-2:]] == [7.0, 9.0]  # the middle of a merged sample's reports


def test_export_events(acquisition, tmp_path):
    lines = export_events(acquisition, tmp_path / "events.csv").read_text().splitlines()
    assert lines[0] == "time,t_rel_s,kind,text"
    assert lines[1].endswith(",mark,injection")
