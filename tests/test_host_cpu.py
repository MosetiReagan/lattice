import pytest

from lattice.observability.host import (
    CpuStealSampler,
    CpuTimes,
    cpu_preflight_eligible,
    parse_cpu_times,
    steal_fraction,
)


def test_guest_ticks_are_not_double_counted():
    sample = parse_cpu_times("cpu 100 10 20 200 5 6 7 80 30 4")
    assert sample.total == 428
    assert sample.steal == 80
    assert steal_fraction(CpuTimes(100, 5), CpuTimes(200, 80)) == 0.75


def test_unavailable_or_reset_counters_are_not_zero_steal():
    assert steal_fraction(CpuTimes(100, 10), CpuTimes(100, 10)) is None
    assert steal_fraction(CpuTimes(100, 10), CpuTimes(200, 5)) is None
    assert steal_fraction(CpuTimes(100, 10), CpuTimes(101, 20)) is None
    with pytest.raises(ValueError):
        parse_cpu_times("cpu0 1 2 3 4 5 6 7 8")
    with pytest.raises(ValueError):
        parse_cpu_times("cpu 1 2 3 4 5 6 7 -8")


def test_sampler_reports_high_steal_without_hiding_it_in_idle_time():
    sampler = CpuStealSampler()
    sampler.samples = [
        {"monotonic_seconds": 0.0, "total": 100, "steal": 0},
        {"monotonic_seconds": 1.0, "total": 500, "steal": 300},
        {"monotonic_seconds": 2.0, "total": 900, "steal": 300},
    ]
    result = sampler.summary()
    assert result["available"]
    assert result["aggregate_steal_fraction"] == 0.375
    assert result["max_interval_steal_fraction"] == 0.75


def test_sampler_marks_missing_and_reset_counters_unavailable():
    sampler = CpuStealSampler()
    assert not sampler.summary()["available"]
    sampler.samples = [
        {"monotonic_seconds": 0.0, "total": 100, "steal": 20},
        {"monotonic_seconds": 1.0, "total": 50, "steal": 10},
    ]
    assert not sampler.summary()["available"]
    with pytest.raises(ValueError):
        CpuStealSampler(interval=0)


def test_preflight_requires_aggregate_interval_and_cpu_availability():
    eligible = {
        "available": True,
        "aggregate_steal_fraction": 0.01,
        "max_interval_steal_fraction": 0.05,
    }
    assert cpu_preflight_eligible(eligible, 0.95)
    assert not cpu_preflight_eligible(
        {**eligible, "max_interval_steal_fraction": 0.1001}, 0.95
    )
    assert not cpu_preflight_eligible(
        {**eligible, "aggregate_steal_fraction": 0.0501}, 0.95
    )
    assert not cpu_preflight_eligible(eligible, 0.8999)
    assert not cpu_preflight_eligible({**eligible, "available": False}, 0.95)
