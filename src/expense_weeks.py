"""Expense-week grouping and JSON persistence for travel-date selections."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Final, Iterable, Optional, Set, Tuple, Union


WEEK_START_DAY: Final[str] = "monday"
SELECTION_VERSION: Final[int] = 1
DEFAULT_SELECTION_PATH: Final[Path] = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "processed"
    / "expense_week_selection.json"
)

_WEEKDAY_INDEX = {"monday": 0}
DateInput = Union[date, str]


@dataclass(frozen=True)
class ExpenseWeek:
    """A calendar week and the selected travel dates within it."""

    week_id: str
    week_start: str
    week_end: str
    selected_dates: Tuple[str, ...]
    selection_mode: str

    def to_dict(self) -> dict:
        """Return the stable JSON-compatible representation of this week."""
        return {
            "week_id": self.week_id,
            "week_start": self.week_start,
            "week_end": self.week_end,
            "selected_dates": list(self.selected_dates),
            "selection_mode": self.selection_mode,
        }


@dataclass(frozen=True)
class ExpenseWeekSelection:
    """A versioned selection ready to persist or pass to later workflow steps."""

    version: int
    week_start_day: str
    created_at: str
    weeks: Tuple[ExpenseWeek, ...]

    def to_dict(self) -> dict:
        """Return this selection using the public JSON schema."""
        return {
            "version": self.version,
            "week_start_day": self.week_start_day,
            "created_at": self.created_at,
            "weeks": [week.to_dict() for week in self.weeks],
        }

    def to_json(self) -> str:
        """Serialize this selection as consistently formatted JSON."""
        return json.dumps(self.to_dict(), indent=2) + "\n"


def parse_iso_date(value: DateInput) -> date:
    """Parse a date or strict YYYY-MM-DD string."""
    if isinstance(value, datetime):
        raise ValueError("Datetime values are not valid expense dates.")
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise TypeError("Expense dates must be date objects or YYYY-MM-DD strings.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("Dates must use the YYYY-MM-DD format.") from error
    if parsed.isoformat() != value:
        raise ValueError("Dates must use the YYYY-MM-DD format.")
    return parsed


def get_week_bounds(value: DateInput) -> Tuple[date, date]:
    """Return the configured expense week's inclusive start and end dates."""
    parsed = parse_iso_date(value)
    weekday_index = _WEEKDAY_INDEX[WEEK_START_DAY]
    week_start = parsed - timedelta(days=(parsed.weekday() - weekday_index) % 7)
    return week_start, week_start + timedelta(days=6)


def weekdays_in_week(value: DateInput) -> Tuple[date, ...]:
    """Return Monday through Friday for the expense week containing ``value``."""
    week_start, _ = get_week_bounds(value)
    return tuple(week_start + timedelta(days=offset) for offset in range(5))


def week_starts_intersecting_range(
    start: DateInput, end: DateInput
) -> Tuple[date, ...]:
    """Return each expense-week start whose week intersects the inclusive range."""
    range_start = parse_iso_date(start)
    range_end = parse_iso_date(end)
    if range_start > range_end:
        raise ValueError("The range start must not be after the range end.")

    first_week_start, _ = get_week_bounds(range_start)
    week_starts = []
    current_week_start = first_week_start
    while current_week_start <= range_end:
        week_starts.append(current_week_start)
        current_week_start += timedelta(days=7)
    return tuple(week_starts)


def group_selected_dates(selected_dates: Iterable[DateInput]) -> Tuple[ExpenseWeek, ...]:
    """Group unique selected dates into sorted expense weeks."""
    dates_by_week = {}
    for value in selected_dates:
        selected_date = parse_iso_date(value)
        week_start, _ = get_week_bounds(selected_date)
        dates_by_week.setdefault(week_start, set()).add(selected_date)

    weeks = []
    for week_start in sorted(dates_by_week):
        week_end = week_start + timedelta(days=6)
        selected = tuple(
            item.isoformat() for item in sorted(dates_by_week[week_start])
        )
        weeks.append(
            ExpenseWeek(
                week_id=week_start.isoformat(),
                week_start=week_start.isoformat(),
                week_end=week_end.isoformat(),
                selected_dates=selected,
                selection_mode="whole_week"
                if set(selected) == {
                    item.isoformat() for item in weekdays_in_week(week_start)
                }
                else "partial",
            )
        )
    return tuple(weeks)


def toggle_week_dates(
    selected_dates: Iterable[DateInput],
    week_start: DateInput,
    enabled_dates: Iterable[DateInput],
    select: Optional[bool] = None,
) -> Set[str]:
    """Select or clear enabled dates in a week while preserving other selections.

    When ``select`` is omitted, the week is selected unless all enabled dates
    are already selected, in which case those enabled dates are cleared.
    """
    week_start_date = parse_iso_date(week_start)
    expected_start, week_end = get_week_bounds(week_start_date)
    if week_start_date != expected_start:
        raise ValueError("week_start must be the configured first day of a week.")

    normalized_enabled = {parse_iso_date(value) for value in enabled_dates}
    if any(not week_start_date <= value <= week_end for value in normalized_enabled):
        raise ValueError("Enabled dates must belong to the requested expense week.")

    result = {parse_iso_date(value) for value in selected_dates}
    enabled_are_selected = bool(normalized_enabled) and normalized_enabled.issubset(result)
    should_select = not enabled_are_selected if select is None else select
    if should_select:
        result.update(normalized_enabled)
    else:
        result.difference_update(normalized_enabled)
    return {value.isoformat() for value in result}


def create_selection(
    selected_dates: Iterable[DateInput], created_at: Optional[str] = None
) -> ExpenseWeekSelection:
    """Create a versioned selection, omitting all weeks without selected days."""
    timestamp = (
        created_at
        if created_at is not None
        else datetime.now().replace(microsecond=0).isoformat()
    )
    if not isinstance(timestamp, str):
        raise ValueError("created_at must be an ISO-formatted datetime.")
    try:
        datetime.fromisoformat(timestamp)
    except ValueError as error:
        raise ValueError("created_at must be an ISO-formatted datetime.") from error
    if "T" not in timestamp and " " not in timestamp:
        raise ValueError("created_at must include a time.")
    return ExpenseWeekSelection(
        version=SELECTION_VERSION,
        week_start_day=WEEK_START_DAY,
        created_at=timestamp,
        weeks=group_selected_dates(selected_dates),
    )


def selection_from_json(payload: str) -> ExpenseWeekSelection:
    """Parse and validate a serialized expense-week selection."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValueError("Selection is not valid JSON.") from error
    if not isinstance(data, dict):
        raise ValueError("Selection JSON must contain an object.")
    if type(data.get("version")) is not int or data["version"] != SELECTION_VERSION:
        raise ValueError("Unsupported expense-week selection version.")
    if data.get("week_start_day") != WEEK_START_DAY:
        raise ValueError("Selection uses an unsupported expense-week boundary.")
    created_at = data.get("created_at")
    if not isinstance(created_at, str):
        raise ValueError("Selection created_at must be an ISO-formatted datetime.")
    try:
        datetime.fromisoformat(created_at)
    except ValueError as error:
        raise ValueError("Selection created_at must be an ISO-formatted datetime.") from error

    raw_weeks = data.get("weeks")
    if not isinstance(raw_weeks, list):
        raise ValueError("Selection weeks must be a list.")
    weeks = []
    seen_dates = set()
    for raw_week in raw_weeks:
        if not isinstance(raw_week, dict):
            raise ValueError("Each expense week must be an object.")
        raw_dates = raw_week.get("selected_dates")
        if not isinstance(raw_dates, list) or not raw_dates:
            raise ValueError("Saved expense weeks must have selected dates.")
        selected_dates = tuple(parse_iso_date(value).isoformat() for value in raw_dates)
        if tuple(sorted(set(selected_dates))) != selected_dates:
            raise ValueError("Selected dates must be unique and sorted.")
        if seen_dates.intersection(selected_dates):
            raise ValueError("A selected date cannot appear in multiple weeks.")
        seen_dates.update(selected_dates)

        expected = group_selected_dates(selected_dates)
        if len(expected) != 1 or raw_week != expected[0].to_dict():
            raise ValueError("Expense week fields do not match its selected dates.")
        weeks.append(expected[0])

    if tuple(sorted(weeks, key=lambda week: week.week_id)) != tuple(weeks):
        raise ValueError("Expense weeks must be sorted by week start.")
    return ExpenseWeekSelection(
        version=SELECTION_VERSION,
        week_start_day=WEEK_START_DAY,
        created_at=created_at,
        weeks=tuple(weeks),
    )


def save_selection(
    selection: ExpenseWeekSelection,
    path: Path = DEFAULT_SELECTION_PATH,
) -> Path:
    """Write a selection to disk, creating its parent directory as needed."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(selection.to_json(), encoding="utf-8")
    return output_path


def load_selection(path: Path = DEFAULT_SELECTION_PATH) -> ExpenseWeekSelection:
    """Load and validate a previously saved selection."""
    return selection_from_json(Path(path).read_text(encoding="utf-8"))
