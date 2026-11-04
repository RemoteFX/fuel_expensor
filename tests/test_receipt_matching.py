"""Headless tests for receipt loading, matching, and result serialization."""

import json
from datetime import date
from decimal import Decimal

import pytest

from src.expense_weeks import create_selection, load_selection
from src.gui.date_selection import DateSelectionApp
from src.receipt_matching import (
    RECEIPT_MARGIN_DAYS,
    load_match_result,
    match_result_from_json,
    match_receipts,
    run_matching_step,
)
from src.receipts import Receipt, load_receipts


def _selection(*dates):
    return create_selection(dates, created_at="2025-04-02T10:15:00")


def _receipt(receipt_id, receipt_date, amount=None, date_error=None):
    return Receipt(
        receipt_id=receipt_id,
        image_path="data/processed/{}.jpg".format(receipt_id),
        receipt_date=receipt_date,
        amount=amount,
        date_error=date_error,
    )


def test_receipt_inside_selected_week_is_matched():
    selection = _selection("2025-04-02")

    result = match_receipts(
        [_receipt("r_0001", date(2025, 4, 2), Decimal("42.10"))],
        selection,
        created_at="2025-04-02T10:20:00",
    )

    assert result.weeks[0].week_id == "2025-03-31"
    assert result.weeks[0].receipt_count == 1
    assert result.weeks[0].matching_receipts[0].amount == Decimal("42.10")
    assert result.weeks[0].matching_receipts[0].overlaps_weeks == ()
    assert not result.unmatched_receipts


@pytest.mark.parametrize(
    "receipt_date",
    [date(2025, 3, 29), date(2025, 4, 8)],
)
def test_receipt_on_either_margin_boundary_is_included(receipt_date):
    selection = _selection("2025-04-02")

    result = match_receipts([_receipt("boundary", receipt_date)], selection)

    assert RECEIPT_MARGIN_DAYS == 2
    assert result.weeks[0].receipt_count == 1


@pytest.mark.parametrize(
    "receipt_date",
    [date(2025, 3, 28), date(2025, 4, 9)],
)
def test_receipt_one_day_outside_margin_is_unmatched(receipt_date):
    selection = _selection("2025-04-02")

    result = match_receipts([_receipt("outside", receipt_date)], selection)

    assert result.weeks[0].receipt_count == 0
    assert result.unmatched_receipts[0].reason == "no_matching_week"


def test_receipt_qualifying_for_adjacent_weeks_is_kept_in_both():
    selection = _selection("2025-04-01", "2025-04-08")

    result = match_receipts(
        [_receipt("overlap", date(2025, 4, 6))],
        selection,
    )

    assert [week.week_id for week in result.weeks] == [
        "2025-03-31",
        "2025-04-07",
    ]
    assert [week.receipt_count for week in result.weeks] == [1, 1]
    assert result.weeks[0].matching_receipts[0].overlaps_weeks == ("2025-04-07",)
    assert result.weeks[1].matching_receipts[0].overlaps_weeks == ("2025-03-31",)


def test_missing_and_unparseable_receipt_dates_have_distinct_reasons():
    selection = _selection("2025-04-02")

    result = match_receipts(
        [
            _receipt("missing", None),
            _receipt("invalid", None, date_error="not an ISO date"),
        ],
        selection,
    )

    assert [
        (receipt.receipt_id, receipt.reason)
        for receipt in result.unmatched_receipts
    ] == [("missing", "missing_date"), ("invalid", "invalid_date")]


def test_week_with_no_qualifying_receipts_remains_in_result():
    result = match_receipts([], _selection("2025-04-02"))

    assert len(result.weeks) == 1
    assert result.weeks[0].week_id == "2025-03-31"
    assert result.weeks[0].receipt_count == 0
    assert result.weeks[0].matching_receipts == ()


def test_match_result_json_round_trip_preserves_decimals_and_overlaps():
    result = match_receipts(
        [_receipt("r_0001", date(2025, 4, 6), Decimal("42.10"))],
        _selection("2025-04-01", "2025-04-08"),
        selection_file="data/processed/expense_week_selection.json",
        created_at="2025-04-02T10:20:00",
    )

    restored = match_result_from_json(result.to_json())

    assert restored == result
    serialized = json.loads(result.to_json())
    assert serialized["weeks"][0]["matching_receipts"][0]["amount"] == "42.10"
    assert serialized["weeks"][0]["receipt_count"] == 1


def test_loader_uses_ocr_filename_dates_and_optional_manifest(tmp_path):
    dated_image = tmp_path / "2025-04-02_shop.jpg"
    missing_date_image = tmp_path / "no-date.jpg"
    undated_image = tmp_path / "unknown.jpg"
    dated_image.touch()
    missing_date_image.touch()
    undated_image.touch()
    manifest_path = tmp_path / "receipt_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "receipts": [
                    {
                        "receipt_id": "shop-receipt",
                        "image_path": dated_image.name,
                        "amount": "42.10",
                        "vendor": "Shop",
                        "raw_ocr_text": "Paid 42.10",
                    },
                    {
                        "receipt_id": "unknown-receipt",
                        "image_path": undated_image.name,
                        "receipt_date": "not-a-date",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    receipts = load_receipts(tmp_path, manifest_path)

    receipts_by_id = {receipt.receipt_id: receipt for receipt in receipts}
    assert receipts_by_id["shop-receipt"].receipt_date == date(2025, 4, 2)
    assert receipts_by_id["shop-receipt"].amount == Decimal("42.10")
    assert receipts_by_id["shop-receipt"].vendor == "Shop"
    assert receipts_by_id["shop-receipt"].raw_ocr_text == "Paid 42.10"
    assert receipts_by_id["no-date.jpg"].receipt_date is None
    assert receipts_by_id["unknown-receipt"].receipt_date is None
    assert receipts_by_id["unknown-receipt"].date_error is not None

    result = match_receipts(receipts, _selection("2025-04-02"))
    assert {
        receipt.receipt_id: receipt.reason
        for receipt in result.unmatched_receipts
    } == {
        "no-date.jpg": "missing_date",
        "unknown-receipt": "invalid_date",
    }


def test_run_matching_step_writes_versioned_json_consumable_by_later_steps(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    (processed / "2025-04-02_receipt.jpg").touch()
    selection_path = tmp_path / "expense_week_selection.json"
    selection_path.write_text(_selection("2025-04-02").to_json(), encoding="utf-8")
    output_path = tmp_path / "receipt_matches.json"

    result, saved_path = run_matching_step(
        selection_path=selection_path,
        receipts_directory=processed,
        output_path=output_path,
        manifest_path=None,
    )

    assert saved_path == output_path
    assert result.weeks[0].receipt_count == 1
    assert load_match_result(output_path) == result
    assert json.loads(output_path.read_text(encoding="utf-8"))["version"] == 1


def test_gui_match_action_saves_current_selection_before_matching(
    tmp_path, monkeypatch
):
    import src.gui.date_selection as date_selection

    selection_path = tmp_path / "expense_week_selection.json"
    output_path = tmp_path / "receipt_matches.json"
    seen_selection = []

    def run_saved_selection(selection_path):
        selection = load_selection(selection_path)
        seen_selection.append(selection)
        return match_receipts([], selection), output_path

    monkeypatch.setattr(date_selection, "DEFAULT_SELECTION_PATH", selection_path)
    monkeypatch.setattr(date_selection, "run_matching_step", run_saved_selection)
    class TextVariable:
        def set(self, value):
            self.value = value

    class StatusLabel:
        def pack(self, **kwargs):
            self.pack_options = kwargs

        def pack_forget(self):
            pass

    app = type("App", (), {})()
    app.selected_dates = {"2025-04-02", "2025-04-08"}
    app.week_receipt_status = {}
    app.root = None
    app.match_status_var = TextVariable()
    app.match_status_label = StatusLabel()
    app.summary_label = object()
    app._refresh_calendar_buttons = lambda: None

    DateSelectionApp._match_receipts(app)

    assert load_selection(selection_path).weeks == _selection(
        "2025-04-02", "2025-04-08"
    ).weeks
    assert seen_selection[0].weeks == load_selection(selection_path).weeks
    assert app.week_receipt_status == {
        "2025-03-31": False,
        "2025-04-07": False,
    }
    assert "orange outlines" in app.match_status_var.value
    assert "receipt_matches.json" in app.match_status_var.value


def test_calendar_refresh_draws_match_status_outlines():
    class Widget:
        def configure(self, **kwargs):
            self.options = kwargs

    app = type("App", (), {})()
    app.day_buttons = {
        "2025-04-01": Widget(),
        "2025-04-08": Widget(),
        "2025-04-15": Widget(),
    }
    app.day_frames = {
        date_text: Widget() for date_text in app.day_buttons
    }
    app.selected_dates = {"2025-04-01", "2025-04-08"}
    app.week_receipt_status = {
        "2025-03-31": True,
        "2025-04-07": False,
    }
    app._refresh_counts = lambda: None

    DateSelectionApp._refresh_calendar_buttons(app)

    assert app.day_frames["2025-04-01"].options["style"] == "MatchedBorder.TFrame"
    assert app.day_frames["2025-04-08"].options["style"] == "UnmatchedBorder.TFrame"
    assert app.day_frames["2025-04-15"].options["style"] == "DayBorder.TFrame"
