import random
import statistics

import pytest

from twilite import get_isotope
from twilite.sim.scenarios import (
    BACKGROUND_COINCIDENCES, Counter, Replay, load_transcript, make_scenario, poisson,
)

from tests.conftest import FIXTURES


def test_poisson_mean_and_variance():
    rng = random.Random(3)
    for mean in (0.5, 5, 120, 2000):
        draws = [poisson(rng, mean) for _ in range(4000)]
        assert statistics.mean(draws) == pytest.approx(mean, rel=0.05, abs=0.05)
        assert statistics.variance(draws) == pytest.approx(mean, rel=0.15, abs=0.1)


def test_background_rates():
    assert make_scenario("background").rates(100)[2] == BACKGROUND_COINCIDENCES


def test_bolus_rises_and_falls():
    bolus = make_scenario("bolus")
    assert bolus.signal(10) == 0
    peak_t = bolus.arrival_s + bolus.time_to_peak_s
    assert bolus.signal(peak_t) > bolus.signal(peak_t - 10)
    assert bolus.signal(peak_t) > bolus.signal(peak_t + 30)
    assert bolus.signal(peak_t) == pytest.approx(bolus.peak_cps, rel=0.1)


def test_calibration_step_and_long_decay_follow_half_life():
    iso = get_isotope("O-15")
    step = make_scenario("calibration-step", iso, step_s=10)
    assert step.signal(5) == 0
    assert step.signal(10 + iso.half_life_s) == pytest.approx(step.signal(10) / 2)
    decay = make_scenario("long-decay", iso)
    assert decay.signal(2 * iso.half_life_s) == pytest.approx(decay.level_cps / 4)


def test_unknown_scenario():
    with pytest.raises(KeyError):
        make_scenario("nope")


def test_replay_of_plain_transcript():
    lines, delays = load_transcript(FIXTURES / "transcripts" / "manual_page23.txt")
    assert lines == ["[71] 2152 1576 124 1.731 1.592", "[72] 2218 1497 122 1.739 1.607"]
    assert delays == [None, None]


def test_replay_of_raw_log(tmp_path):
    log = tmp_path / "raw.log"
    log.write_text(
        "2026-10-02T10:00:00.000 >> b'showc\\r\\n'\n"
        "2026-10-02T10:00:00.100 << b'[1] 1 2 3\\r\\n[2] 4'\n"
        "2026-10-02T10:00:01.100 << b' 5 6\\r\\n'\n"
    )
    replay = Replay(transcript=log)
    assert replay.lines == ["[1] 1 2 3", "[2] 4 5 6"]
    assert replay.delays_s == [None, pytest.approx(1.0)]


def test_counter_is_counts_per_second_and_one_index_per_line():
    def run(seed):
        counter = Counter(make_scenario("background"), seed=seed)
        out = []
        for i in range(5):
            counter.report(0.1 * (i + 1), 0.1)
            out.append((counter.index, counter.values))
        return out

    first = run(3)
    assert first == run(3)
    assert first != run(4)
    assert [i for i, _ in first] == [0, 1, 2, 3, 4]
    # 100 ms windows scaled to counts per second: multiples of 10, as on the device.
    assert all(v % 10 == 0 for _, values in first for v in values)


def test_counter_values_without_advancing():
    counter = Counter(make_scenario("background"))
    counter.report(1.0, 1.0)
    counter.report(2.0, 1.0, advance=False)  # ccnt: new values, same [n]
    assert counter.index == 0
    assert counter.line().startswith("[0] ") and counter.line().endswith(" 0.0 0.0")
