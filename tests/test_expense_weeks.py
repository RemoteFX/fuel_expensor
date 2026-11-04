"""Tests for expense-week selection and serialization."""

import json
from datetime import date, timedelta

import pytest

from src.expense_weeks import (
    DEFAULT_SELECTION_PATH,
    WEEK_START_DAY,
    create_selection,
    get_week_bounds,
    group_selected_dates,
    load_selection,
    save_selection,
    selection_from_json,
    toggle_week_dates,
    weekdays_in_week,
    week_starts_intersecting_range,
)


def test_group_selected_dates_sorts_dates_and_groups_by_monday_week():
    weeks = group_selected_dates(["2025-04-02", "2025-03-31", "2025-04-02"])

    assert len(weeks) == 1
    assert weeks[0].week_id == "2025-03-31"
    assert weeks[0].week_start == "2025-03-31"
    assert weeks[0].week_end == "2025-04-06"
    assert weeks[0].selected_dates == ("2025-03-31", "2025-04-02")
    assert weeks[0].selection_mode == "partial"


@pytest.mark.parametrize(
    ("selected_date", "expected_start", "expected_end"),
    [
        ("2025-01-01", "2024-12-30", "2025-01-05"),
        ("2025-12-31", "2025-12-29", "2026-01-04"),
        ("2025-03-31", "2025-03-31", "2025-04-06"),
    ],
)
def test_week_boundaries_cross_month_and_year(
    selected_date, expected_start, expected_end
):
    week_start, week_end = get_week_bounds(selected_date)

    assert week_start.isoformat() == expected_start
    assert week_end.isoformat() == expected_end


def test_range_lists_all_intersecting_weeks_including_partial_edges():
    starts = week_starts_intersecting_range("2025-03-30", "2025-04-07")

    assert [item.isoformat() for item in starts] == [
        "2025-03-24",
        "2025-03-31",
        "2025-04-07",
    ]


def test_toggle_week_selects_then_deselects_only_enabled_dates():
    original = {"2025-03-24"}
    enabled = ["2025-03-31", "2025-04-01", "2025-04-02"]

    selected = toggle_week_dates(original, "2025-03-31", enabled)
    deselected = toggle_week_dates(selected, "2025-03-31", enabled)

    assert selected == original.union(enabled)
    assert deselected == original


def test_toggle_week_can_be_explicit_and_preserves_other_week_dates():
    selected = toggle_week_dates(
        {"2025-03-31"}, "2025-03-31", ["2025-04-01", "2025-04-02"], select=False
    )

    assert selected == {"2025-03-31"}


def test_whole_week_dates_include_weekdays_only():
    selected_weekdays = [item.isoformat() for item in weekdays_in_week("2025-04-02")]

    assert selected_weekdays == [
        "2025-03-31",
        "2025-04-01",
        "2025-04-02",
        "2025-04-03",
        "2025-04-04",
    ]


def test_toggling_whole_week_never_selects_or_clears_weekends():
    enabled_weekdays = [item.isoformat() for item in weekdays_in_week("2025-04-02")]
    weekend_selections = {"2025-04-05", "2025-04-06"}

    selected = toggle_week_dates(
        weekend_selections, "2025-03-31", enabled_weekdays
    )
    deselected = toggle_week_dates(selected, "2025-03-31", enabled_weekdays)

    assert selected == weekend_selections.union(enabled_weekdays)
    assert deselected == weekend_selections


def test_selection_json_round_trip_and_file_persistence(tmp_path):
    selection = create_selection(
        ["2025-03-31", "2025-04-01"], created_at="2025-04-02T10:15:00"
    )

    restored = selection_from_json(selection.to_json())
    output_path = save_selection(selection, tmp_path / "nested" / "selection.json")

    assert restored == selection
    assert load_selection(output_path) == selection
    assert json.loads(selection.to_json())["week_start_day"] == WEEK_START_DAY
    assert DEFAULT_SELECTION_PATH.name == "expense_week_selection.json"


def test_only_weeks_with_selected_dates_are_serialized(tmp_path):
    selection = create_selection(["2025-03-31", "2025-04-07"])
    output_path = save_selection(selection, tmp_path / "selection.json")
    saved_data = json.loads(output_path.read_text(encoding="utf-8"))

    assert [week["week_id"] for week in saved_data["weeks"]] == [
        "2025-03-31",
        "2025-04-07",
    ]
    assert all(week["selected_dates"] for week in saved_data["weeks"])


def test_empty_selection_serializes_with_no_weeks():
    selection = create_selection([], created_at="2025-04-02T10:15:00")

    assert selection.to_dict()["weeks"] == []


def test_complete_workweek_is_marked_as_whole_week():
    selected_dates = [
        (date(2025, 3, 31) + timedelta(days=offset)).isoformat()
        for offset in range(5)
    ]

    assert group_selected_dates(selected_dates)[0].selection_mode == "whole_week"
