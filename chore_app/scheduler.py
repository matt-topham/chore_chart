from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from typing import Iterable

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

FREQUENCY_ALIASES = {
    "daily": "Daily",
    "twice-weekly": "Twice-Weekly",
    "twice weekly": "Twice-Weekly",
    "weekly": "Weekly",
    "bi-weekly": "Bi-Weekly",
    "biweekly": "Bi-Weekly",
    "monthly": "Monthly",
    "quaterly": "Quarterly",
    "quarterly": "Quarterly",
    "semi-annually": "Semi-Annually",
    "semi annually": "Semi-Annually",
    "semiannual": "Semi-Annually",
    "annually": "Annually",
    "annual": "Annually",
}


def normalize_frequency(value: str) -> str:
    key = re.sub(r"\s+", " ", (value or "").strip().lower())
    return FREQUENCY_ALIASES.get(key, value.strip().title() or "Weekly")


def parse_weekdays(value: str) -> list[int]:
    text = (value or "").strip().lower()
    if not text or text == "every day":
        return list(range(7))
    found = [number for name, number in WEEKDAYS.items() if name in text]
    return sorted(set(found)) or [5]


def next_weekday_on_or_after(start: date, weekdays: Iterable[int]) -> date:
    weekday_set = set(weekdays)
    for offset in range(8):
        candidate = start + timedelta(days=offset)
        if candidate.weekday() in weekday_set:
            return candidate
    return start


def next_weekday_after(start: date, weekdays: Iterable[int]) -> date:
    return next_weekday_on_or_after(start + timedelta(days=1), weekdays)


def add_months(value: date, months: int) -> date:
    total_months = value.year * 12 + (value.month - 1) + months
    year, month_index = divmod(total_months, 12)
    month = month_index + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def initial_due_date(
    frequency: str,
    preferred_day: str,
    imported_on: date,
    group_index: int = 0,
) -> date:
    """Choose a friendly first due date for a newly imported chore.

    Long-interval chores are spread across future preferred weekdays to avoid
    making every monthly or quarterly chore due on the first Saturday.
    """
    frequency = normalize_frequency(frequency)
    weekdays = parse_weekdays(preferred_day)

    if frequency == "Daily":
        return imported_on

    first = next_weekday_on_or_after(imported_on, weekdays)
    spread_slots = {
        "Bi-Weekly": 2,
        "Monthly": 4,
        "Quarterly": 12,
        "Semi-Annually": 12,
        "Annually": 8,
    }.get(frequency, 1)
    return first + timedelta(days=7 * (group_index % spread_slots))


def next_due_date(chore: dict, last_completed: date | None) -> date:
    frequency = normalize_frequency(chore["frequency"])
    weekdays = parse_weekdays(chore.get("preferred_day", ""))
    first_due = date.fromisoformat(chore["first_due"])

    if last_completed is None:
        return first_due

    if frequency == "Daily":
        return last_completed + timedelta(days=1)

    if frequency in {"Twice-Weekly", "Weekly"}:
        return next_weekday_after(last_completed, weekdays)

    if frequency == "Bi-Weekly":
        candidate = first_due
        while candidate <= last_completed:
            candidate += timedelta(days=14)
        return candidate

    month_steps = {
        "Monthly": 1,
        "Quarterly": 3,
        "Semi-Annually": 6,
        "Annually": 12,
    }
    if frequency in month_steps:
        target = add_months(last_completed, month_steps[frequency])
        return next_weekday_on_or_after(target, weekdays)

    return next_weekday_after(last_completed, weekdays)
