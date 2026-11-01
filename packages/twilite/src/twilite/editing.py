"""Edits of an acquisition: cutting artifacts out and resampling.

Both take an :class:`~twilite.storage.Acquisition` and return a new one, leaving the
one given unchanged, so they can follow each other in any order. Every edit adds a
line to ``edits``. Sample ``i`` counts over ``[t_wall[i] - duration_s[i], t_wall[i]]``,
and its time is :func:`~twilite.storage.sample_times`: when its report arrived (as in
PSAMPLE), or the middle of the reports a resampled sample merges. All times here are PC
times, seconds since the epoch.

- :func:`cut` replaces the samples in a window by a straight line between the mean of
  the samples on each side of it, and flags them as interpolated.
- :func:`resample` merges consecutive samples into longer ones, section by section:
  each new sample has the duration-weighted mean rate of the samples it is made of,
  so the counts are kept.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace

from twilite.storage import Acquisition, sample_durations, sample_times

CHANNELS = ("singles1", "singles2", "coincidences")
#: Relative tolerance on sample durations: clock jitter, rounding in the files.
TOLERANCE = 0.05


@dataclass(frozen=True, slots=True)
class Section:
    """A time window and the sampling period wanted in it, in seconds."""

    start: float
    end: float
    period: float


###############################################################################
# Cutting                                                                     #
###############################################################################


@dataclass(frozen=True, slots=True)
class CutPlan:
    """What :func:`cut` will do: the samples it replaces and the line it puts there.

    Attributes:
        selected: Indices of the samples replaced, consecutive.
        times: Their times.
        values: ``{channel: values}`` replacing them.
        edges: ``(time, {channel: value})`` of the ends of the line, one per side
            with samples left.
    """

    selected: list[int]
    times: list[float]
    values: dict[str, list[float]]
    edges: list[tuple[float, dict[str, float]]]


def plan_cut(acq: Acquisition, start: float, end: float, n_average: int = 1) -> CutPlan:
    """Work out the replacement of the samples whose time is in ``[start, end]``.

    The value at each edge is the duration-weighted mean of the ``n_average`` samples
    next to the window on that side, placed at the time of the sample nearest the
    window. With samples on one side only, that side's value is held flat.

    Raises:
        ValueError: No sample in the window, none left on either side, or
            ``n_average`` below 1.
    """
    if n_average < 1:
        raise ValueError("Average at least one sample at each edge")
    times = sample_times(acq)
    selected = [i for i, t in enumerate(times) if start <= t <= end]
    if not selected:
        raise ValueError("No samples in the selection")
    first, last = selected[0], selected[-1]
    durations = sample_durations(acq)
    edges = []
    for side, anchor in ((range(max(first - n_average, 0), first), first - 1),
                         (range(last + 1, min(last + 1 + n_average, len(acq))), last + 1)):
        if side:
            weights = [durations[i] for i in side]
            edges.append((times[anchor], {ch: _weighted_mean([getattr(acq, ch)[i] for i in side], weights)
                                          for ch in CHANNELS}))
    if not edges:
        raise ValueError("A cut must leave samples on at least one side")
    values = {ch: [_line(edges, ch, times[i]) for i in selected] for ch in CHANNELS}
    return CutPlan(selected, [times[i] for i in selected], values, edges)


def cut(acq: Acquisition, start: float, end: float, n_average: int = 1) -> Acquisition:
    """Return a copy of ``acq`` with the samples in ``[start, end]`` interpolated.

    See :func:`plan_cut`. The replaced samples keep their times and durations.
    """
    plan = plan_cut(acq, start, end, n_average)
    edited = _copy(acq)
    for ch in CHANNELS:
        series = getattr(edited, ch)
        for i, value in zip(plan.selected, plan.values[ch]):
            series[i] = value
    for i in plan.selected:
        edited.interpolated[i] = True
    zero = _zero(acq)
    edited.edits.append(f"cut {len(plan.selected)} samples from {plan.times[0] - zero:.1f} s to "
                        f"{plan.times[-1] - zero:.1f} s, edges averaged over {n_average} samples")
    return edited


def _line(edges, channel, t):
    if len(edges) == 1:
        return edges[0][1][channel]
    (t0, v0), (t1, v1) = edges
    return v0[channel] + (v1[channel] - v0[channel]) * (t - t0) / (t1 - t0)


###############################################################################
# Resampling                                                                  #
###############################################################################


def plan_resample(acq: Acquisition, sections: Sequence[Section]) -> tuple[list[list[int]], list[int]]:
    """Group the samples into the samples :func:`resample` will make.

    A sample belongs to the first section its time falls in (``start <= t <= end``), so a
    sample on a boundary goes to the earlier section. Samples are only merged, never
    split, so a section's period must be a whole multiple of the sampling of the data
    in it (:func:`sampling_sections`): 2 s samples can become 4 or 6 s ones, not 1 or 3 s.
    Within a section, consecutive samples are merged while the group spans at most
    ``period``, with half a sample of slack so the clock's jitter does not split groups.
    A gap in the data (a lost connection) ends a group; samples outside every section
    stay alone.

    Returns:
        ``(groups, counts)``: the indices of the samples making each new sample, and
        the number of new samples in each section.

    Raises:
        ValueError: A section cannot be applied; see :func:`section_problems`.
    """
    for k, problem in enumerate(section_problems(acq, sections)):
        if problem:
            raise ValueError(f"Section {k + 1}: {problem}")

    times = sample_times(acq)
    durations = sample_durations(acq)
    groups: list[list[int]] = []
    counts = [0] * len(sections)
    current_section = None
    group_start = 0.0
    for i, t in enumerate(times):
        k = _section_of(sections, t)
        fits = (k is not None and k == current_section and groups
                and acq.t_wall[i] - group_start <= sections[k].period + durations[i] / 2)
        if fits:
            groups[-1].append(i)
            continue
        groups.append([i])
        current_section = k
        group_start = acq.t_wall[i] - durations[i]
        if k is not None:
            counts[k] += 1
    return groups, counts


def section_problems(acq: Acquisition, sections: Sequence[Section]) -> list[str]:
    """Why each section cannot be resampled, ``""`` for one that can; one per section.

    A section must end after it starts, start after the previous one ends, and have a
    period that is a whole multiple of the data's sampling in it (see
    :func:`plan_resample`). The sections without a problem can be resampled together.
    """
    problems = []
    previous_end = -math.inf
    for section in sections:
        if not section.start < section.end:
            problems.append("it must end after it starts")
        elif section.start < previous_end:
            problems.append("it overlaps the previous section")
        elif not section.period > 0:
            problems.append("the sampling period must be positive")
        else:
            problems.append("")
        previous_end = section.end

    valid = [k for k, problem in enumerate(problems) if not problem]
    current = sampling_sections(acq)
    covered: dict[int, set[float]] = {k: set() for k in valid}
    for t in sample_times(acq):
        j = _section_of([sections[k] for k in valid], t)
        if j is not None:
            covered[valid[j]].add(current[_section_of(current, t)].period)
    for k, periods in covered.items():
        problems[k] = next((p for p in (_multiple_problem(sections[k].period, period)
                                        for period in sorted(periods, reverse=True)) if p), "")
    return problems


def _multiple_problem(period: float, current: float) -> str:
    if period < current * (1 - TOLERANCE):
        return f"the data there is sampled every {current:g} s; resampling cannot make it finer"
    if abs(period - round(period / current) * current) > TOLERANCE * current:
        return f"use a multiple of {current:g} s, the data's sampling there"
    return ""


def resample(acq: Acquisition, sections: Sequence[Section]) -> Acquisition:
    """Return a copy of ``acq`` resampled section by section; see :func:`plan_resample`.

    A merged sample ends when its last sample ends and lasts as long as its samples
    together (their counting time: the PC clock's jitter between reports is not counted),
    so the counts are kept exactly. Its rates are the duration-weighted means (NaN
    ignored), its index is its first sample's and it counts as interpolated if any of its
    samples was.
    """
    groups, counts = plan_resample(acq, sections)
    edited = _copy(acq)
    for name in ("index", "t_wall", "t_rel_s", *CHANNELS, "extras", "duration_s", "interpolated"):
        getattr(edited, name).clear()
    durations = sample_durations(acq)
    for group in groups:
        first, last = group[0], group[-1]
        weights = [durations[i] for i in group]
        edited.index.append(acq.index[first])
        edited.t_wall.append(acq.t_wall[last])
        edited.t_rel_s.append(acq.t_rel_s[last])
        for ch in CHANNELS:
            series = getattr(acq, ch)
            getattr(edited, ch).append(series[first] if len(group) == 1
                                       else _weighted_mean([series[i] for i in group], weights))
        edited.extras.append(_mean_extras([acq.extras[i] for i in group]))
        edited.duration_s.append(sum(weights))
        edited.interpolated.append(any(acq.interpolated[i] for i in group) if acq.interpolated else False)

    zero = _zero(acq)
    for k, (section, count) in enumerate(zip(sections, counts)):
        before = sum(1 for t in sample_times(acq) if _section_of(sections, t) == k)
        if count != before:
            edited.edits.append(f"resampled {section.start - zero:.1f} s to {section.end - zero:.1f} s "
                                f"every {section.period:g} s: {before} samples into {count}")
    return edited


def sampling_sections(acq: Acquisition, tolerance: float = TOLERANCE) -> list[Section]:
    """Describe how ``acq`` is sampled: consecutive sections of about equal durations.

    Durations within ``tolerance`` (relative) of a section's first are one section;
    a single shorter sample after a section (its last one, cut short by the end of a
    resampled section) joins it. The sections follow each other without gaps, from the
    acquisition start to the last sample's time; each period is the median duration.
    """
    if len(acq) == 0:
        return []
    durations = sample_durations(acq)
    runs: list[list[int]] = []
    for i, d in enumerate(durations):
        if runs and abs(d - durations[runs[-1][0]]) <= tolerance * durations[runs[-1][0]]:
            runs[-1].append(i)
        else:
            runs.append([i])
    merged: list[list[int]] = []
    for run in runs:
        if merged and len(run) == 1 and durations[run[0]] < durations[merged[-1][0]]:
            merged[-1].extend(run)
        else:
            merged.append(run)
    sections = []
    start = min(_zero(acq), acq.t_wall[0])
    for run in merged:
        end = acq.t_wall[run[-1]]
        period = sorted(durations[i] for i in run)[len(run) // 2]
        sections.append(Section(start, end, period))
        start = end
    return sections


###############################################################################
# Helpers                                                                     #
###############################################################################


def _section_of(sections: Sequence[Section], t: float) -> int | None:
    return next((k for k, s in enumerate(sections) if s.start <= t <= s.end), None)


def _weighted_mean(values: Sequence[float], weights: Sequence[float]) -> float:
    pairs = [(v, w) for v, w in zip(values, weights) if not math.isnan(v)]
    total = sum(w for _, w in pairs)
    if not pairs or total <= 0:
        return math.nan
    return sum(v * w for v, w in pairs) / total


def _mean_extras(extras: list[tuple[float, ...]]) -> tuple[float, ...]:
    if len(extras) == 1 or len({len(e) for e in extras}) != 1:
        return extras[0]
    return tuple(sum(column) / len(column) for column in zip(*extras))


def _copy(acq: Acquisition) -> Acquisition:
    """A copy whose lists can be changed without changing ``acq``'s."""
    return replace(
        acq, metadata=dict(acq.metadata), index=list(acq.index), t_wall=list(acq.t_wall),
        t_rel_s=list(acq.t_rel_s), singles1=list(acq.singles1), singles2=list(acq.singles2),
        coincidences=list(acq.coincidences), extras=list(acq.extras), extra_columns=list(acq.extra_columns),
        events=list(acq.events), duration_s=list(sample_durations(acq)),
        interpolated=list(acq.interpolated) if acq.interpolated else [False] * len(acq), edits=list(acq.edits),
    )


def _zero(acq: Acquisition) -> float:
    """PC time of the acquisition start, the zero of the times in the edit lines."""
    return acq.t_wall[0] - acq.t_rel_s[0] if len(acq) else 0.0
