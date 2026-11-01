import math

import pytest

from twilite.editing import Section, cut, plan_cut, plan_resample, resample, sampling_sections
from twilite.storage import Acquisition, read_acquisition, sample_times, write_acquisition

T0 = 1_790_000_000.0


def make(n=20, period=1.0, jitter=0.0, rate=lambda i: 100.0 + i):
    """``n`` samples of ``period`` s arriving every ``period + jitter`` s from T0 + period."""
    acq = Acquisition("run.csv", metadata={"report_rate": f"qrate {round(period * 10)} ({period * 1000:g} ms)"},
                      extra_columns=["extra1", "extra2"])
    for i in range(n):
        t = (i + 1) * (period + jitter)
        acq.index.append(i)
        acq.t_wall.append(T0 + t)
        acq.t_rel_s.append(t)
        acq.singles1.append(10 * rate(i))
        acq.singles2.append(20 * rate(i))
        acq.coincidences.append(rate(i))
        acq.extras.append((0.0, 0.0))
        acq.duration_s.append(period)
        acq.interpolated.append(False)
    return acq


###############################################################################
# Cutting                                                                     #
###############################################################################


def test_cut_draws_a_line_between_the_edges():
    acq = make(rate=lambda i: 1000.0 if i in (8, 9, 10) else 100.0 + i)
    edited = cut(acq, acq.t_wall[8] - 0.2, acq.t_wall[10] + 0.2)
    # Edges: sample 7 (107) and sample 11 (111), 4 samples apart.
    assert edited.coincidences[7:12] == pytest.approx([107, 108, 109, 110, 111])
    assert edited.singles1[8] == pytest.approx(1080) and edited.singles2[10] == pytest.approx(2200)
    assert edited.interpolated[7:12] == [False, True, True, True, False]
    assert edited.t_wall == acq.t_wall and edited.duration_s == acq.duration_s
    assert acq.coincidences[8] == 1000.0 and not any(acq.interpolated)  # the original is unchanged
    assert edited.edits == ["cut 3 samples from 9.0 s to 11.0 s, edges averaged over 1 samples"]


def test_cut_edges_average_n_samples_at_the_edge_sample_time():
    acq = make(rate=lambda i: {5: 90.0, 6: 110.0, 10: 500.0, 11: 300.0}.get(i, 100.0))
    plan = plan_cut(acq, acq.t_wall[7], acq.t_wall[9], n_average=2)
    assert plan.selected == [7, 8, 9]
    # Left edge mean(90, 110) = 100 at sample 6, right edge mean(500, 300) = 400 at sample 10.
    assert plan.values["coincidences"] == pytest.approx([175, 250, 325])
    assert [(t, v["coincidences"]) for t, v in plan.edges] == [(acq.t_wall[6], 100), (acq.t_wall[10], 400)]


def test_cut_edge_mean_is_weighted_by_duration_and_skips_nan():
    acq = make(rate=lambda i: {3: math.nan, 4: 400.0, 5: 100.0}.get(i, 100.0))
    acq.duration_s[4] = 3.0
    plan = plan_cut(acq, acq.t_wall[6], acq.t_wall[6], n_average=3)
    assert plan.values["coincidences"][0] == pytest.approx(((400 * 3 + 100) / 4 + 100) / 2)


def test_cut_at_the_end_holds_the_other_side():
    acq = make()
    edited = cut(acq, acq.t_wall[17], acq.t_wall[19] + 5, n_average=2)
    assert edited.coincidences[17:] == pytest.approx([115.5] * 3)


@pytest.mark.parametrize("start, end, n_average, message", [
    (T0 + 100, T0 + 200, 1, "No samples"),
    (T0, T0 + 100, 1, "at least one side"),
    (T0 + 3, T0 + 5, 0, "at least one sample"),
])
def test_cut_errors(start, end, n_average, message):
    with pytest.raises(ValueError, match=message):
        cut(make(), start, end, n_average)


###############################################################################
# Resampling                                                                  #
###############################################################################


def test_resample_merges_samples_and_keeps_the_counts():
    acq = make(n=25)
    start, end = acq.t_wall[0] - 1, acq.t_wall[-1]
    edited = resample(acq, [Section(start, start + 5, 1.0), Section(start + 5, end, 10.0)])
    assert len(edited) == 5 + 2
    assert edited.coincidences[:5] == acq.coincidences[:5]
    assert edited.coincidences[5:] == pytest.approx([109.5, 119.5])
    assert edited.duration_s[5:] == pytest.approx([10.0, 10.0])
    assert edited.t_wall[5] == acq.t_wall[14] and edited.index[5] == 5
    # Samples as recorded stay at their arrival time; merged ones are in the middle of their reports.
    assert sample_times(edited)[:5] == acq.t_wall[:5]
    assert sample_times(edited)[5] == pytest.approx((acq.t_wall[5] + acq.t_wall[14]) / 2)
    assert sum(r * d for r, d in zip(edited.coincidences, edited.duration_s)) == pytest.approx(sum(acq.coincidences))
    assert edited.edits == ["resampled 5.0 s to 25.0 s every 10 s: 20 samples into 2"]


def test_resample_last_sample_of_a_section_is_shorter():
    acq = make(n=25)
    plan = plan_resample(acq, [Section(T0, acq.t_wall[-1], 10.0)])
    assert [len(g) for g in plan.groups] == [10, 10, 5] and plan.counts == [3] and plan.before == [25]
    assert resample(acq, [Section(T0, acq.t_wall[-1], 10.0)]).duration_s == pytest.approx([10, 10, 5])


def test_resample_tolerates_clock_jitter():
    acq = make(n=100, jitter=0.002)  # reports drift by 2 ms each
    groups = plan_resample(acq, [Section(T0, acq.t_wall[-1], 10.0)]).groups
    assert {len(g) for g in groups} == {10}
    same = plan_resample(acq, [Section(T0, acq.t_wall[-1], 1.0)])
    assert len(same.groups) == 100 and not same.changes


def test_resample_does_not_bridge_a_gap():
    acq = make(n=20)
    for i in range(10, 20):
        acq.t_wall[i] += 3.0  # the connection was lost for 3 s
    groups = plan_resample(acq, [Section(T0, acq.t_wall[-1], 6.0)]).groups
    assert [len(g) for g in groups] == [6, 4, 6, 4]


def test_resample_samples_outside_every_section_stay():
    acq = make(n=20)
    edited = resample(acq, [Section(T0 + 11, T0 + 15, 5.0)])
    assert len(edited) == 16 and edited.coincidences[:10] == acq.coincidences[:10]
    assert edited.coincidences[10] == pytest.approx(112)


def test_resample_twice_and_interpolated_flags_carry_over():
    raw = make(n=40)
    acq = cut(raw, raw.t_wall[3], raw.t_wall[3])
    once = resample(acq, [Section(T0, acq.t_wall[-1], 5.0)])
    twice = resample(once, [Section(T0, once.t_wall[-1], 20.0)])
    assert len(once) == 8 and len(twice) == 2
    assert once.interpolated == [True] + [False] * 7 and twice.interpolated == [True, False]
    assert twice.coincidences == pytest.approx([109.5, 129.5])
    assert len(twice.edits) == 3


def test_resample_without_change_adds_no_edit():
    acq = make()
    assert resample(acq, sampling_sections(acq)).edits == []


def test_resample_again_merges_whole_samples():
    acq = make(n=40, jitter=0.002)
    end = acq.t_wall[-1]
    twice = resample(acq, [Section(T0, end, 2.0)])
    assert len(twice) == 20 and twice.duration_s == pytest.approx([2.0] * 20, abs=0.01)
    four = resample(twice, [Section(T0, end, 4.0)])
    assert len(four) == 10 and four.duration_s == pytest.approx([4.0] * 10, abs=0.02)
    assert four.coincidences[0] == pytest.approx(101.5)  # the mean of samples 0..3
    assert sum(r * d for r, d in zip(four.coincidences, four.duration_s)) == \
        pytest.approx(sum(r * d for r, d in zip(acq.coincidences, acq.duration_s)), rel=1e-3)
    assert resample(twice, [Section(T0, end, 2.0)]).edits == twice.edits  # the same sampling: no change
    with pytest.raises(ValueError, match="Section 1: the data there is sampled every 2 s; .* cannot make it finer"):
        plan_resample(twice, [Section(T0, end, 1.0)])
    with pytest.raises(ValueError, match="Section 1: use a multiple of 2 s"):
        plan_resample(twice, [Section(T0, end, 3.0)])


def test_resample_period_fits_every_sampling_in_the_section():
    acq = resample(make(n=40), [Section(T0 + 21, T0 + 40, 10.0)])  # 1 s, then 10 s samples
    with pytest.raises(ValueError, match="multiple of 10 s"):
        plan_resample(acq, [Section(T0, T0 + 40, 15.0)])
    with pytest.raises(ValueError, match="sampled every 10 s"):
        plan_resample(acq, [Section(T0, T0 + 40, 5.0)])
    plan = plan_resample(acq, [Section(T0, T0 + 40, 10.0)])
    assert plan.counts == [4] and [len(g) for g in plan.groups] == [10, 10, 1, 1]
    # A section's last sample, cut short, does not count as its sampling.
    odd = resample(make(n=21), [Section(T0, T0 + 21, 2.0)])
    assert odd.duration_s[-1] == pytest.approx(1.0)
    assert len(resample(odd, [Section(T0, T0 + 21, 4.0)])) == 6


@pytest.mark.parametrize("sections, message", [
    ([Section(T0 + 5, T0 + 5, 1.0)], "end after"),
    ([Section(T0, T0 + 10, 1.0), Section(T0 + 9, T0 + 20, 1.0)], "overlap"),
    ([Section(T0, T0 + 10, 0.0)], "positive"),
])
def test_resample_errors(sections, message):
    with pytest.raises(ValueError, match=message):
        resample(make(), sections)


def test_sampling_sections():
    acq = make(n=25)
    assert sampling_sections(acq) == [Section(T0, T0 + 25, 1.0)]  # from the acquisition start
    edited = resample(acq, [Section(T0 + 6, T0 + 25, 10.0)])
    assert sampling_sections(edited) == [Section(T0, T0 + 5, 1.0), Section(T0 + 5, T0 + 25, 10.0)]
    shorter = resample(make(n=31), [Section(T0 + 6, T0 + 22, 10.0), Section(T0 + 22, T0 + 31, 3.0)])
    # The 7 s last sample of the 10 s section joins it; the 3 s samples are their own section.
    assert [s.period for s in sampling_sections(shorter)] == [1.0, 10.0, 3.0]
    single = resample(make(n=15), [Section(T0 + 6, T0 + 15, 10.0)])
    assert [s.period for s in sampling_sections(single)] == [1.0, 10.0]  # a longer single sample stays


def test_edited_data_survives_a_file(tmp_path):
    acq = make(n=25)
    edited = resample(cut(acq, acq.t_wall[2], acq.t_wall[3]), [Section(T0 + 6, T0 + 25, 10.0)])
    back = read_acquisition(write_acquisition(edited, tmp_path / "edited.csv"))
    assert back.coincidences == pytest.approx(edited.coincidences)
    assert back.duration_s == pytest.approx(edited.duration_s)
    assert back.interpolated == edited.interpolated and back.edits == edited.edits
    assert sampling_sections(back) == pytest.approx(sampling_sections(edited))
