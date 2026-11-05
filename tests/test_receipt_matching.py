"""Headless tests for receipt loading, matching, and result serialization."""

import json
import queue
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.expense_weeks import create_selection, load_selection
from src.gui.date_selection import DateSelectionApp
from src.receipt_processing import ProcessingProgress, ReceiptProcessingResult
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


def test_receipt_qualifying_for_adjacent_weeks_is_assigned_once():
    selection = _selection("2025-04-01", "2025-04-08")

    result = match_receipts(
        [_receipt("overlap", date(2025, 4, 6))],
        selection,
    )

    assert [week.week_id for week in result.weeks] == [
        "2025-03-31",
        "2025-04-07",
    ]
    assert [week.receipt_count for week in result.weeks] == [1, 0]
    assert result.weeks[0].matching_receipts[0].overlaps_weeks == ("2025-04-07",)
    assigned_receipts = [
        receipt.receipt_id
        for week in result.weeks
        for receipt in week.matching_receipts
    ]
    assert assigned_receipts == ["overlap"]
    assert result.weeks[1].matching_receipts == ()


def test_overlapping_receipt_prefers_week_containing_its_date():
    selection = _selection("2025-04-01", "2025-04-08")

    result = match_receipts(
        [_receipt("monday", date(2025, 4, 7))],
        selection,
    )

    assert [week.receipt_count for week in result.weeks] == [0, 1]
    assert result.weeks[1].matching_receipts[0].overlaps_weeks == ("2025-03-31",)


def test_duplicate_receipt_ids_are_rejected():
    selection = _selection("2025-04-02")

    with pytest.raises(ValueError, match="Duplicate receipt_id"):
        match_receipts(
            [
                _receipt("duplicate", date(2025, 4, 1)),
                _receipt("duplicate", date(2025, 4, 2)),
            ],
            selection,
        )


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


def test_explicit_job_list_prevents_old_jobs_from_being_matched(tmp_path):
    processed = tmp_path / "processed"
    old_job = processed / "jobs" / "old-job"
    current_job = processed / "jobs" / "current-job"
    old_job.mkdir(parents=True)
    current_job.mkdir(parents=True)
    (old_job / "2025-04-02_old-receipt.jpg").touch()
    (current_job / "2025-04-02_current-receipt.jpg").touch()

    selection_path = tmp_path / "expense_week_selection.json"
    selection_path.write_text(_selection("2025-04-02").to_json(), encoding="utf-8")
    output_path = tmp_path / "receipt_matches.json"
    output_path.write_text(
        match_receipts(
            [_receipt("previously-matched", date(2025, 4, 2))],
            _selection("2025-04-02"),
        ).to_json(),
        encoding="utf-8",
    )

    result, _ = run_matching_step(
        selection_path=selection_path,
        receipts_directory=processed,
        output_path=output_path,
        receipt_job_directories=[current_job],
    )
    assert [receipt.receipt_id for receipt in result.weeks[0].matching_receipts] == [
        "2025-04-02_current-receipt.jpg"
    ]

    empty_result, _ = run_matching_step(
        selection_path=selection_path,
        receipts_directory=processed,
        output_path=output_path,
        receipt_job_directories=(),
    )
    assert empty_result.weeks[0].receipt_count == 0
    assert output_path.read_text(encoding="utf-8") == empty_result.to_json()


def test_gui_match_action_saves_current_selection_before_matching(
    tmp_path, monkeypatch
):
    import src.gui.date_selection as date_selection

    selection_path = tmp_path / "expense_week_selection.json"
    output_path = tmp_path / "receipt_matches.json"
    seen_selection = []

    def run_saved_selection(
        selection_path,
        receipts_directory,
        manifest_path,
        receipt_job_directories,
    ):
        assert receipts_directory == tmp_path / "processed"
        assert manifest_path == tmp_path / "processed" / "receipt_manifest.json"
        assert receipt_job_directories == [tmp_path / "processed" / "jobs" / "active"]
        selection = load_selection(selection_path)
        seen_selection.append(selection)
        return match_receipts([], selection), output_path

    monkeypatch.setattr(date_selection, "DEFAULT_SELECTION_PATH", selection_path)
    monkeypatch.setattr(date_selection, "run_matching_step", run_saved_selection)
    class TextVariable:
        def set(self, value):
            self.value = value

    class BooleanVariable:
        def get(self):
            return False

    app = type("App", (), {})()
    app.selected_dates = {"2025-04-02", "2025-04-08"}
    app.receipts_directory = tmp_path / "processed"
    app.active_receipt_jobs = [tmp_path / "processed" / "jobs" / "active"]
    app.week_receipt_status = {}
    app.root = None
    app.match_status_var = TextVariable()
    app.summary_label = object()
    app.verbose_output = BooleanVariable()
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
    assert "orange dates" in app.match_status_var.value
    assert "receipt_matches.json" in app.match_status_var.value
    assert app.weeks_without_receipts == ("2025-03-31", "2025-04-07")
    assert "will not be included in an expense form" in app.match_status_var.value


def test_new_gui_session_clears_previous_selection_and_uses_no_old_jobs(
    tmp_path, monkeypatch
):
    import src.gui.date_selection as date_selection

    selection_path = tmp_path / "expense_week_selection.json"
    selection_path.write_text(_selection("2025-04-02").to_json(), encoding="utf-8")
    seen = []

    def run_empty_session(
        selection_path,
        receipts_directory,
        manifest_path,
        receipt_job_directories,
    ):
        assert receipts_directory == tmp_path / "processed"
        assert manifest_path == tmp_path / "processed" / "receipt_manifest.json"
        assert receipt_job_directories == []
        selection = load_selection(selection_path)
        seen.append(selection)
        return match_receipts([], selection), tmp_path / "receipt_matches.json"

    monkeypatch.setattr(date_selection, "DEFAULT_SELECTION_PATH", selection_path)
    monkeypatch.setattr(date_selection, "run_matching_step", run_empty_session)

    class TextVariable:
        def set(self, value):
            self.value = value

    app = type("App", (), {})()
    app.selected_dates = set()
    app.active_receipt_jobs = []
    app.receipts_directory = tmp_path / "processed"
    app.week_receipt_status = {}
    app.root = None
    app.match_status_var = TextVariable()
    app.verbose_output = type("Verbose", (), {"get": lambda self: False})()
    app._refresh_calendar_buttons = lambda: None

    DateSelectionApp._match_receipts(app)

    assert load_selection(selection_path).weeks == ()
    assert seen[0].weeks == ()
    assert app.week_receipt_status == {}


def test_calendar_refresh_colors_selected_dates_by_week_receipt_status():
    class Widget:
        def configure(self, **kwargs):
            self.options = kwargs

    app = type("App", (), {})()
    app.day_buttons = {
        "2025-04-01": Widget(),
        "2025-04-08": Widget(),
        "2025-04-15": Widget(),
    }
    app.selected_dates = {"2025-04-01", "2025-04-08"}
    app.week_receipt_status = {
        "2025-03-31": True,
        "2025-04-07": False,
    }
    app._refresh_counts = lambda: None

    DateSelectionApp._refresh_calendar_buttons(app)

    assert app.day_buttons["2025-04-01"].options["style"] == "Matched.TButton"
    assert app.day_buttons["2025-04-08"].options["style"] == "Unmatched.TButton"
    assert app.day_buttons["2025-04-15"].options["style"] == "Day.TButton"


def test_date_click_triggers_receipt_check_immediately(monkeypatch):
    checked = []
    app = type("App", (), {})()
    app.selected_dates = set()
    app.mode = type("Mode", (), {"get": lambda self: "custom"})()
    app._refresh_calendar_buttons = lambda: None
    app._match_receipts = lambda: checked.append(set(app.selected_dates))

    DateSelectionApp._on_date_click(app, date(2025, 4, 2))

    assert checked == [{"2025-04-02"}]


def test_match_result_exposes_only_receipt_eligible_expense_form_weeks():
    result = match_receipts(
        [_receipt("matched", date(2025, 4, 2))],
        _selection("2025-04-02", "2025-04-08"),
    )

    assert tuple(week.week_id for week in result.expense_form_weeks) == (
        "2025-03-31",
    )
    assert result.weeks_without_receipts == ("2025-04-07",)


def test_saving_selection_warns_about_weeks_without_receipts(tmp_path, monkeypatch):
    import src.gui.date_selection as date_selection

    warnings = []
    selection_path = tmp_path / "selection.json"
    monkeypatch.setattr(date_selection, "DEFAULT_SELECTION_PATH", selection_path)
    monkeypatch.setattr(
        date_selection,
        "save_selection",
        lambda _selection, path: path,
    )
    monkeypatch.setattr(
        date_selection.messagebox,
        "showwarning",
        lambda title, message, parent: warnings.append((title, message)),
    )

    app = type("App", (), {})()
    app.selected_dates = {"2025-04-02", "2025-04-08"}
    app.weeks_without_receipts = ("2025-04-07",)
    app.root = None

    DateSelectionApp._save_selection(app)

    assert len(warnings) == 1
    assert "2025-04-07" in warnings[0][1]
    assert "will not be included in an expense form" in warnings[0][1]


def test_failed_matching_clears_stale_coverage_and_reports_error(
    tmp_path, monkeypatch
):
    import src.gui.date_selection as date_selection

    errors = []
    selection_path = tmp_path / "selection.json"
    monkeypatch.setattr(date_selection, "DEFAULT_SELECTION_PATH", selection_path)
    monkeypatch.setattr(
        date_selection,
        "run_matching_step",
        lambda **_kwargs: (_ for _ in ()).throw(OSError("receipt folder unavailable")),
    )
    monkeypatch.setattr(
        date_selection.messagebox,
        "showerror",
        lambda _title, message, parent: errors.append(message),
    )

    class TextVariable:
        def set(self, value):
            self.value = value

    app = type("App", (), {})()
    app.selected_dates = {"2025-04-02"}
    app.receipts_directory = tmp_path / "processed"
    app.active_receipt_jobs = []
    app.week_receipt_status = {"2025-03-31": True}
    app.weeks_without_receipts = ("2025-04-07",)
    app.matching_error = None
    app.root = None
    app.match_status_var = TextVariable()
    app.verbose_output = type("Verbose", (), {"get": lambda self: False})()
    app._refresh_calendar_buttons = lambda: None

    DateSelectionApp._match_receipts(app)

    assert app.week_receipt_status == {}
    assert app.weeks_without_receipts == ()
    assert "receipt folder unavailable" in app.matching_error
    assert "receipt folder unavailable" in app.match_status_var.value
    assert errors == ["receipt folder unavailable"]


def test_diagnostics_are_hidden_by_default_and_shown_when_verbose_is_enabled():
    class TextWidget:
        def __init__(self):
            self.content = ""
            self.state = "disabled"

        def configure(self, **kwargs):
            self.state = kwargs.get("state", self.state)

        def delete(self, _start, _end):
            self.content = ""

        def insert(self, _position, value):
            self.content += value

        def see(self, _position):
            pass

    class Frame:
        def __init__(self):
            self.visible = False

        def pack(self, **_kwargs):
            self.visible = True

        def pack_forget(self):
            self.visible = False

    class Variable:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

    app = type("App", (), {})()
    app.verbose_output = Variable(False)
    app.diagnostics_frame = Frame()
    app.diagnostics_text = TextWidget()
    app.summary_label = object()
    app.match_status_var = Variable("Recent matching result")
    app._append_diagnostic = lambda message, replace=False: (
        DateSelectionApp._append_diagnostic(app, message, replace)
    )

    DateSelectionApp._toggle_verbose_output(app)
    assert not app.diagnostics_frame.visible

    app.verbose_output.value = True
    DateSelectionApp._toggle_verbose_output(app)
    assert app.diagnostics_frame.visible
    assert app.diagnostics_text.content == "Recent matching result\n"

    app.verbose_output.value = False
    DateSelectionApp._toggle_verbose_output(app)
    assert not app.diagnostics_frame.visible


def test_verbose_processing_summary_is_shown_after_completion(tmp_path):
    diagnostics = []
    progress_values = []
    events = queue.Queue()
    events.put(
        (
            "progress",
            ProcessingProgress("detecting", 1, 1, "receipts.jpg"),
        )
    )
    events.put(
        (
            "complete",
            ReceiptProcessingResult(
                "job-1", tmp_path, 1, 1, (), (), (), ()
            ),
        )
    )
    app = SimpleNamespace(
        _processing_queue=events,
        _processing_active=True,
        active_receipt_jobs=[],
        verbose_output=SimpleNamespace(get=lambda: True),
        processing_progress=SimpleNamespace(
            configure=lambda **kwargs: progress_values.append(kwargs["value"])
        ),
        upload_button=SimpleNamespace(configure=lambda **_kwargs: None),
        _append_diagnostic=diagnostics.append,
        _match_receipts=lambda: None,
    )

    DateSelectionApp._poll_receipt_processing(app)

    assert diagnostics == [
        "Processing complete: 1 image(s), 1 receipt(s), 0 error(s), "
        "0 warning(s). Output: {}".format(tmp_path)
    ]
    assert progress_values == [50, 100]


def test_processing_progress_bar_shows_overall_stage_progress():
    progress_values = []
    events = queue.Queue()
    events.put(
        (
            "progress",
            ProcessingProgress("detecting", 1, 2, "receipts.jpg"),
        )
    )
    app = SimpleNamespace(
        _processing_queue=events,
        _processing_active=True,
        verbose_output=SimpleNamespace(get=lambda: False),
        processing_progress=SimpleNamespace(
            configure=lambda **kwargs: progress_values.append(kwargs["value"])
        ),
        upload_button=SimpleNamespace(configure=lambda **_kwargs: None),
        root=SimpleNamespace(after=lambda *_args: None),
        _poll_receipt_processing=lambda: None,
    )

    DateSelectionApp._poll_receipt_processing(app)

    assert progress_values == [25]
