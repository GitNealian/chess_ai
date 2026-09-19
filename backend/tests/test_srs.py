from datetime import date

from srs import quality_from_result, schedule


def test_quality_mapping():
    assert quality_from_result(0, False) == 5
    assert quality_from_result(1, False) == 4
    assert quality_from_result(2, False) == 3
    assert quality_from_result(3, False) == 2
    assert quality_from_result(0, True) == 2


def test_first_success_interval_one_day():
    result = schedule(ease_factor=2.5, interval=0, repetitions=0, lapses=0, quality=5, today=date(2026, 9, 19))
    assert result["repetitions"] == 1
    assert result["interval"] == 1
    assert result["due_date"] == date(2026, 9, 20)


def test_second_success_interval_six_days():
    result = schedule(ease_factor=2.5, interval=1, repetitions=1, lapses=0, quality=5, today=date(2026, 9, 19))
    assert result["interval"] == 6


def test_third_success_multiplies_ease():
    result = schedule(ease_factor=2.5, interval=6, repetitions=2, lapses=0, quality=5, today=date(2026, 9, 19))
    assert result["interval"] == 15


def test_low_quality_resets():
    result = schedule(ease_factor=2.5, interval=10, repetitions=3, lapses=0, quality=2, today=date(2026, 9, 19))
    assert result["repetitions"] == 0
    assert result["lapses"] == 1
    assert result["interval"] == 1
    assert result["due_date"] == date(2026, 9, 20)


def test_ease_factor_floor():
    result = schedule(ease_factor=1.3, interval=6, repetitions=2, lapses=0, quality=2, today=date(2026, 9, 19))
    assert result["ease_factor"] >= 1.3
