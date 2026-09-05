import pytest

from clock_core import format_date, format_time


class TestFormatTime:
    def test_seconds_shown(self):
        assert format_time(9, 5, 3, show_seconds=True, hour24=True) == "09:05:03"

    def test_seconds_hidden(self):
        assert format_time(9, 5, 3, show_seconds=False, hour24=True) == "09:05"

    def test_hour24_zero_padding(self):
        assert format_time(1, 2, 3, show_seconds=True, hour24=True) == "01:02:03"

    def test_hour24_midnight_and_noon(self):
        assert format_time(0, 0, 0, hour24=True) == "00:00:00"
        assert format_time(12, 0, 0, hour24=True) == "12:00:00"

    def test_hour12_morning_suffix(self):
        assert format_time(9, 5, 3, show_seconds=True, hour24=False) == "9:05:03 AM"

    def test_hour12_afternoon_suffix(self):
        assert format_time(13, 5, 3, show_seconds=True, hour24=False) == "1:05:03 PM"

    def test_hour12_noon_and_midnight_are_twelve(self):
        assert format_time(12, 0, 0, show_seconds=False, hour24=False) == "12:00 PM"
        assert format_time(0, 5, 0, show_seconds=False, hour24=False) == "12:05 AM"

    def test_invalid_hour_raises(self):
        with pytest.raises(ValueError):
            format_time(24, 0, 0)

    def test_invalid_minute_raises(self):
        with pytest.raises(ValueError):
            format_time(0, 60, 0)


class TestFormatDate:
    def test_date_zero_padding(self):
        assert format_date(2026, 9, 5) == "2026-09-05"

    def test_date_full_padding(self):
        assert format_date(999, 1, 2) == "0999-01-02"

    def test_invalid_month_raises(self):
        with pytest.raises(ValueError):
            format_date(2026, 13, 1)

    def test_invalid_day_raises(self):
        with pytest.raises(ValueError):
            format_date(2026, 9, 0)
