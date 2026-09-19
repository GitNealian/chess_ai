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


def test_half_interval_rounds_up():
    result = schedule(ease_factor=1.5, interval=15, repetitions=2, lapses=0, quality=5, today=date(2026, 9, 19))
    assert result["interval"] == 23
    assert result["due_date"] == date(2026, 10, 12)


def test_low_quality_resets():
    result = schedule(ease_factor=2.5, interval=10, repetitions=3, lapses=0, quality=2, today=date(2026, 9, 19))
    assert result["repetitions"] == 0
    assert result["lapses"] == 1
    assert result["interval"] == 1
    assert result["due_date"] == date(2026, 9, 20)


def test_ease_factor_floor():
    result = schedule(ease_factor=1.3, interval=6, repetitions=2, lapses=0, quality=2, today=date(2026, 9, 19))
    assert result["ease_factor"] >= 1.3


def test_quality_four_keeps_ease():
    result = schedule(ease_factor=2.5, interval=6, repetitions=2, lapses=0, quality=4, today=date(2026, 9, 19))
    assert result["ease_factor"] == 2.5


def test_quality_three_reduces_ease():
    result = schedule(ease_factor=2.5, interval=6, repetitions=2, lapses=0, quality=3, today=date(2026, 9, 19))
    assert result["ease_factor"] == 2.36


def test_consecutive_low_quality_converges_to_floor():
    ease = 2.5
    expected = [2.18, 1.86, 1.54, 1.3, 1.3]
    for i in range(5):
        result = schedule(ease_factor=ease, interval=6, repetitions=2, lapses=0, quality=2, today=date(2026, 9, 19))
        ease = result["ease_factor"]
        assert ease == expected[i]


def test_third_success_due_date_crosses_month():
    result = schedule(ease_factor=2.5, interval=6, repetitions=2, lapses=0, quality=5, today=date(2026, 9, 19))
    assert result["due_date"] == date(2026, 10, 4)


def test_success_keeps_lapses():
    result = schedule(ease_factor=2.5, interval=6, repetitions=2, lapses=3, quality=5, today=date(2026, 9, 19))
    assert result["lapses"] == 3


def test_quality_from_result_negative_mistakes():
    assert quality_from_result(-1, False) == 5
