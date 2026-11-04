"""Pure receipt-to-expense-week matching and versioned result persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Final, Iterable, List, Optional, Tuple

from src.expense_weeks import (
    DEFAULT_SELECTION_PATH,
    WEEK_START_DAY,
    ExpenseWeekSelection,
    get_week_bounds,
    load_selection,
    parse_iso_date,
)
from src.receipts import (
    DEFAULT_RECEIPT_MANIFEST_PATH,
    DEFAULT_RECEIPTS_DIRECTORY,
    PROJECT_ROOT,
    Receipt,
    load_receipts,
)


RECEIPT_MARGIN_DAYS: Final[int] = 2
MATCH_RESULT_VERSION: Final[int] = 1
DEFAULT_MATCH_RESULT_PATH: Final[Path] = (
    PROJECT_ROOT / "data" / "processed" / "receipt_matches.json"
)


@dataclass(frozen=True)
class MatchedReceipt:
    """Receipt details attached to one qualifying expense week."""

    receipt_id: str
    receipt_date: str
    amount: Optional[Decimal]
    image_path: str
    overlaps_weeks: Tuple[str, ...]
    vendor: Optional[str] = None
    raw_ocr_text: Optional[str] = None

    def to_dict(self) -> dict:
        """Return the JSON representation used by downstream workflow steps."""
        return {
            "receipt_id": self.receipt_id,
            "receipt_date": self.receipt_date,
            "amount": str(self.amount) if self.amount is not None else None,
            "image_path": self.image_path,
            "overlaps_weeks": list(self.overlaps_weeks),
            "vendor": self.vendor,
            "raw_ocr_text": self.raw_ocr_text,
        }


@dataclass(frozen=True)
class WeekMatch:
    """Selected expense-week fields and all receipts qualifying for that week."""

    week_id: str
    week_start: str
    week_end: str
    selected_dates: Tuple[str, ...]
    matching_receipts: Tuple[MatchedReceipt, ...]

    @property
    def receipt_count(self) -> int:
        """Return the number of receipts associated with this week."""
        return len(self.matching_receipts)

    def to_dict(self) -> dict:
        """Return this week and its receipt associations as JSON-compatible data."""
        return {
            "week_id": self.week_id,
            "week_start": self.week_start,
            "week_end": self.week_end,
            "selected_dates": list(self.selected_dates),
            "matching_receipts": [
                receipt.to_dict() for receipt in self.matching_receipts
            ],
            "receipt_count": self.receipt_count,
        }


@dataclass(frozen=True)
class UnmatchedReceipt:
    """Receipt that could not be associated with any selected expense week."""

    receipt_id: str
    reason: str
    image_path: str
    date_error: Optional[str] = None

    def to_dict(self) -> dict:
        """Return the unmatched receipt record for JSON serialization."""
        result = {
            "receipt_id": self.receipt_id,
            "reason": self.reason,
            "image_path": self.image_path,
        }
        if self.date_error is not None:
            result["date_error"] = self.date_error
        return result


@dataclass(frozen=True)
class MatchResult:
    """Versioned receipt associations ready for downstream workflow steps."""

    version: int
    week_start_day: str
    receipt_margin_days: int
    created_at: str
    selection_file: str
    weeks: Tuple[WeekMatch, ...]
    unmatched_receipts: Tuple[UnmatchedReceipt, ...]

    def to_dict(self) -> dict:
        """Return the stable public JSON structure."""
        return {
            "version": self.version,
            "week_start_day": self.week_start_day,
            "receipt_margin_days": self.receipt_margin_days,
            "created_at": self.created_at,
            "selection_file": self.selection_file,
            "weeks": [week.to_dict() for week in self.weeks],
            "unmatched_receipts": [
                receipt.to_dict() for receipt in self.unmatched_receipts
            ],
        }

    def to_json(self) -> str:
        """Serialize this match result as consistently formatted JSON."""
        return json.dumps(self.to_dict(), indent=2) + "\n"


def match_receipts(
    receipts: Iterable[Receipt],
    selection: ExpenseWeekSelection,
    selection_file: str = str(DEFAULT_SELECTION_PATH),
    created_at: Optional[str] = None,
) -> MatchResult:
    """Associate each dated receipt with every selected week it qualifies for.

    A qualifying interval includes the two days before the configured week
    start and the two days after its end. Expense week boundaries are obtained
    from ``src.expense_weeks`` so this module does not define its own calendar.
    """
    timestamp = created_at or datetime.now().replace(microsecond=0).isoformat()
    if not isinstance(timestamp, str):
        raise ValueError("created_at must be an ISO-formatted datetime.")
    try:
        datetime.fromisoformat(timestamp)
    except ValueError as error:
        raise ValueError("created_at must be an ISO-formatted datetime.") from error

    week_data = []
    for week in selection.weeks:
        start, end = get_week_bounds(week.week_start)
        week_data.append((week, start, end))

    receipts_by_week: List[List[MatchedReceipt]] = [
        [] for _ in week_data
    ]
    unmatched = []
    for receipt in receipts:
        if receipt.receipt_date is None:
            unmatched.append(
                UnmatchedReceipt(
                    receipt_id=receipt.receipt_id,
                    reason="invalid_date" if receipt.date_error else "missing_date",
                    image_path=receipt.image_path,
                    date_error=receipt.date_error,
                )
            )
            continue

        qualifying_indices = [
            index
            for index, (_, week_start, week_end) in enumerate(week_data)
            if week_start - timedelta(days=RECEIPT_MARGIN_DAYS)
            <= receipt.receipt_date
            <= week_end + timedelta(days=RECEIPT_MARGIN_DAYS)
        ]
        if not qualifying_indices:
            unmatched.append(
                UnmatchedReceipt(
                    receipt_id=receipt.receipt_id,
                    reason="no_matching_week",
                    image_path=receipt.image_path,
                )
            )
            continue

        qualifying_week_ids = tuple(
            week_data[index][0].week_id for index in qualifying_indices
        )
        for index in qualifying_indices:
            week = week_data[index][0]
            overlaps = tuple(
                week_id for week_id in qualifying_week_ids if week_id != week.week_id
            )
            receipts_by_week[index].append(
                MatchedReceipt(
                    receipt_id=receipt.receipt_id,
                    receipt_date=receipt.receipt_date.isoformat(),
                    amount=receipt.amount,
                    image_path=receipt.image_path,
                    overlaps_weeks=overlaps,
                    vendor=receipt.vendor,
                    raw_ocr_text=receipt.raw_ocr_text,
                )
            )

    matched_weeks = tuple(
        WeekMatch(
            week_id=week.week_id,
            week_start=start.isoformat(),
            week_end=end.isoformat(),
            selected_dates=week.selected_dates,
            matching_receipts=tuple(receipts_by_week[index]),
        )
        for index, (week, start, end) in enumerate(week_data)
    )
    return MatchResult(
        version=MATCH_RESULT_VERSION,
        week_start_day=selection.week_start_day,
        receipt_margin_days=RECEIPT_MARGIN_DAYS,
        created_at=timestamp,
        selection_file=selection_file,
        weeks=matched_weeks,
        unmatched_receipts=tuple(unmatched),
    )


def _optional_amount(value: object, field_name: str) -> Optional[Decimal]:
    """Validate and parse the serialized decimal amount."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("{} must be a decimal string or null.".format(field_name))
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("{} is not a valid decimal.".format(field_name)) from error
    if not amount.is_finite():
        raise ValueError("{} must be finite.".format(field_name))
    return amount


def match_result_from_json(payload: str) -> MatchResult:
    """Parse and validate a serialized version-1 match result."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValueError("Match result is not valid JSON.") from error
    if not isinstance(data, dict):
        raise ValueError("Match result JSON must contain an object.")
    if type(data.get("version")) is not int or data["version"] != MATCH_RESULT_VERSION:
        raise ValueError("Unsupported receipt match result version.")
    if data.get("week_start_day") != WEEK_START_DAY:
        raise ValueError("Match result uses an unsupported expense-week boundary.")
    margin = data.get("receipt_margin_days")
    if type(margin) is not int or margin < 0:
        raise ValueError("receipt_margin_days must be a non-negative integer.")
    created_at = data.get("created_at")
    selection_file = data.get("selection_file")
    if not isinstance(created_at, str) or not isinstance(selection_file, str):
        raise ValueError("Match result timestamp and selection_file must be strings.")
    try:
        datetime.fromisoformat(created_at)
    except ValueError as error:
        raise ValueError("Match result created_at must be an ISO datetime.") from error

    raw_weeks = data.get("weeks")
    raw_unmatched = data.get("unmatched_receipts")
    if not isinstance(raw_weeks, list) or not isinstance(raw_unmatched, list):
        raise ValueError("Match result weeks and unmatched_receipts must be lists.")

    weeks = []
    for raw_week in raw_weeks:
        if not isinstance(raw_week, dict):
            raise ValueError("Each match-result week must be an object.")
        week_id = raw_week.get("week_id")
        week_start_value = raw_week.get("week_start")
        week_end_value = raw_week.get("week_end")
        raw_selected_dates = raw_week.get("selected_dates")
        raw_receipts = raw_week.get("matching_receipts")
        if (
            not isinstance(week_id, str)
            or not isinstance(week_start_value, str)
            or not isinstance(week_end_value, str)
            or not isinstance(raw_selected_dates, list)
            or not all(isinstance(value, str) for value in raw_selected_dates)
            or not isinstance(raw_receipts, list)
        ):
            raise ValueError("Match-result week fields have invalid types.")
        expected_start, expected_end = get_week_bounds(week_start_value)
        if (
            week_id != expected_start.isoformat()
            or week_start_value != expected_start.isoformat()
            or week_end_value != expected_end.isoformat()
        ):
            raise ValueError("Match-result week boundaries are inconsistent.")

        matched_receipts = []
        for raw_receipt in raw_receipts:
            if not isinstance(raw_receipt, dict):
                raise ValueError("Each matched receipt must be an object.")
            receipt_id = raw_receipt.get("receipt_id")
            receipt_date_value = raw_receipt.get("receipt_date")
            image_path = raw_receipt.get("image_path")
            overlaps = raw_receipt.get("overlaps_weeks")
            vendor = raw_receipt.get("vendor")
            raw_ocr_text = raw_receipt.get("raw_ocr_text")
            if (
                not isinstance(receipt_id, str)
                or not isinstance(receipt_date_value, str)
                or not isinstance(image_path, str)
                or not isinstance(overlaps, list)
                or not all(isinstance(value, str) for value in overlaps)
                or (vendor is not None and not isinstance(vendor, str))
                or (raw_ocr_text is not None and not isinstance(raw_ocr_text, str))
            ):
                raise ValueError("Matched receipt fields have invalid types.")
            parse_iso_date(receipt_date_value)
            matched_receipts.append(
                MatchedReceipt(
                    receipt_id=receipt_id,
                    receipt_date=receipt_date_value,
                    amount=_optional_amount(
                        raw_receipt.get("amount"),
                        "amount for receipt {!r}".format(receipt_id),
                    ),
                    image_path=image_path,
                    overlaps_weeks=tuple(overlaps),
                    vendor=vendor,
                    raw_ocr_text=raw_ocr_text,
                )
            )
        receipt_count = raw_week.get("receipt_count")
        if type(receipt_count) is not int or receipt_count != len(matched_receipts):
            raise ValueError("Week receipt_count does not match matching_receipts.")
        weeks.append(
            WeekMatch(
                week_id=week_id,
                week_start=week_start_value,
                week_end=week_end_value,
                selected_dates=tuple(raw_selected_dates),
                matching_receipts=tuple(matched_receipts),
            )
        )

    unmatched = []
    for raw_receipt in raw_unmatched:
        if not isinstance(raw_receipt, dict):
            raise ValueError("Each unmatched receipt must be an object.")
        receipt_id = raw_receipt.get("receipt_id")
        reason = raw_receipt.get("reason")
        image_path = raw_receipt.get("image_path")
        date_error = raw_receipt.get("date_error")
        if (
            not isinstance(receipt_id, str)
            or not isinstance(reason, str)
            or not isinstance(image_path, str)
            or (date_error is not None and not isinstance(date_error, str))
        ):
            raise ValueError("Unmatched receipt fields have invalid types.")
        unmatched.append(
            UnmatchedReceipt(
                receipt_id=receipt_id,
                reason=reason,
                image_path=image_path,
                date_error=date_error,
            )
        )
    return MatchResult(
        version=data["version"],
        week_start_day=data["week_start_day"],
        receipt_margin_days=margin,
        created_at=created_at,
        selection_file=selection_file,
        weeks=tuple(weeks),
        unmatched_receipts=tuple(unmatched),
    )


def save_match_result(
    result: MatchResult, path: Path = DEFAULT_MATCH_RESULT_PATH
) -> Path:
    """Write a match result, creating the parent directory if necessary."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.to_json(), encoding="utf-8")
    return output_path


def load_match_result(path: Path = DEFAULT_MATCH_RESULT_PATH) -> MatchResult:
    """Load and validate a saved receipt match result."""
    return match_result_from_json(Path(path).read_text(encoding="utf-8"))


def _path_for_output(path: Path) -> str:
    """Use a project-relative path when possible, otherwise an absolute path."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(resolved)


def run_matching_step(
    selection_path: Path = DEFAULT_SELECTION_PATH,
    receipts_directory: Path = DEFAULT_RECEIPTS_DIRECTORY,
    output_path: Path = DEFAULT_MATCH_RESULT_PATH,
    manifest_path: Optional[Path] = DEFAULT_RECEIPT_MANIFEST_PATH,
) -> Tuple[MatchResult, Path]:
    """Load step-4 selections and receipts, match them, and persist the result."""
    saved_selection_path = Path(selection_path)
    selection = load_selection(saved_selection_path)
    receipts = load_receipts(
        receipts_directory=receipts_directory,
        manifest_path=manifest_path,
    )
    result = match_receipts(
        receipts,
        selection,
        selection_file=_path_for_output(saved_selection_path),
    )
    return result, save_match_result(result, output_path)
