from datetime import datetime, timedelta, timezone as dt_timezone

import pytest

from apps.scheduling.booking_rules import (
    assert_ends_match_duration,
    assert_matching_price,
    assert_starts_not_in_past,
    compute_ends_at,
    expand_footprint,
    ranges_overlap,
)
from apps.scheduling.exceptions import (
    AppointmentInPastError,
    ScheduleDurationMismatchError,
    ServicePriceMismatchError,
)


def test_compute_ends_and_footprint():
    start = datetime(2026, 8, 1, 14, 0, tzinfo=dt_timezone.utc)
    end = compute_ends_at(start, 30)
    assert end == start + timedelta(minutes=30)
    fp_s, fp_e = expand_footprint(start, end, 5, 10)
    assert fp_s == start - timedelta(minutes=5)
    assert fp_e == end + timedelta(minutes=10)


def test_ranges_overlap_half_open():
    a0 = datetime(2026, 8, 1, 10, 0, tzinfo=dt_timezone.utc)
    a1 = datetime(2026, 8, 1, 11, 0, tzinfo=dt_timezone.utc)
    b0 = datetime(2026, 8, 1, 11, 0, tzinfo=dt_timezone.utc)
    b1 = datetime(2026, 8, 1, 12, 0, tzinfo=dt_timezone.utc)
    assert not ranges_overlap(a0, a1, b0, b1)
    assert ranges_overlap(a0, a1, a0 + timedelta(minutes=30), b1)


def test_assert_starts_not_in_past():
    now = datetime(2026, 8, 1, 12, 0, tzinfo=dt_timezone.utc)
    assert_starts_not_in_past(now - timedelta(seconds=30), now=now)
    with pytest.raises(AppointmentInPastError):
        assert_starts_not_in_past(now - timedelta(minutes=5), now=now)


def test_assert_duration_and_price():
    start = datetime(2026, 8, 1, 14, 0, tzinfo=dt_timezone.utc)
    assert_ends_match_duration(
        starts_at=start, ends_at=start + timedelta(minutes=30), duration_minutes=30
    )
    with pytest.raises(ScheduleDurationMismatchError):
        assert_ends_match_duration(
            starts_at=start, ends_at=start + timedelta(minutes=45), duration_minutes=30
        )
    assert_matching_price(None, 5000)
    assert_matching_price(5000, 5000)
    with pytest.raises(ServicePriceMismatchError):
        assert_matching_price(4000, 5000)
