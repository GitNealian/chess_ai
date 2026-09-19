from datetime import date, timedelta


def quality_from_result(mistake_count, revealed):
    if revealed:
        return 2
    if mistake_count <= 0:
        return 5
    if mistake_count == 1:
        return 4
    if mistake_count == 2:
        return 3
    return 2


def schedule(ease_factor, interval, repetitions, lapses, quality, today=None):
    today = today or date.today()
    ease = ease_factor
    if quality >= 3:
        if repetitions == 0:
            new_interval = 1
        elif repetitions == 1:
            new_interval = 6
        else:
            new_interval = round(interval * ease)
        new_repetitions = repetitions + 1
        new_lapses = lapses
    else:
        new_interval = 1
        new_repetitions = 0
        new_lapses = lapses + 1

    ease = ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    if ease < 1.3:
        ease = 1.3

    return {
        "ease_factor": round(ease, 4),
        "interval": new_interval,
        "repetitions": new_repetitions,
        "lapses": new_lapses,
        "due_date": today + timedelta(days=new_interval),
    }
