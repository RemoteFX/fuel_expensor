"""Receipt records and loading for the processed receipt images."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Final, List, Optional, Tuple

from src.expense_weeks import parse_iso_date


PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
DEFAULT_RECEIPTS_DIRECTORY: Final[Path] = PROJECT_ROOT / "data" / "processed"
DEFAULT_RECEIPT_MANIFEST_PATH: Final[Path] = (
    DEFAULT_RECEIPTS_DIRECTORY / "receipt_manifest.json"
)
_IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
_DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})_")


@dataclass(frozen=True)
class Receipt:
    """OCR-derived receipt details and the image used by later workflow steps."""

    receipt_id: str
    image_path: str
    receipt_date: Optional[date]
    amount: Optional[Decimal] = None
    vendor: Optional[str] = None
    raw_ocr_text: Optional[str] = None
    date_error: Optional[str] = None


def _path_for_output(path: Path) -> str:
    """Prefer a project-relative path while retaining external fixture paths."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(resolved)


def _date_from_filename(path: Path) -> Tuple[Optional[date], Optional[str]]:
    """Read the ISO date prefix written by ``process_receipt_dates``."""
    match = _DATE_PREFIX.match(path.name)
    if match is None:
        return None, None
    try:
        return parse_iso_date(match.group(1)), None
    except ValueError:
        return None, "The filename contains an invalid ISO receipt date."


def _parse_manifest_date(
    value: object, fallback: Tuple[Optional[date], Optional[str]]
) -> Tuple[Optional[date], Optional[str]]:
    """Parse an optional manifest date, falling back to the OCR filename date."""
    if value is None:
        return fallback
    if not isinstance(value, str):
        return None, "The manifest receipt_date must be an ISO date string."
    try:
        return parse_iso_date(value), None
    except (TypeError, ValueError):
        return None, "The manifest receipt_date is not a valid ISO date."


def _parse_amount(value: object, receipt_id: str) -> Optional[Decimal]:
    """Convert a manifest amount to Decimal without introducing float errors."""
    if value is None:
        return None
    if not isinstance(value, (str, int, Decimal)) or isinstance(value, bool):
        raise ValueError(
            "Amount for receipt {!r} must be a decimal string or number.".format(
                receipt_id
            )
        )
    try:
        amount = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(
            "Amount for receipt {!r} is not a valid decimal.".format(receipt_id)
        ) from error
    if not amount.is_finite():
        raise ValueError(
            "Amount for receipt {!r} must be finite.".format(receipt_id)
        )
    return amount


def _load_manifest(
    manifest_path: Path, receipts_directory: Path
) -> List[Tuple[Path, dict]]:
    """Load and validate manifest entries, resolving their image paths."""
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("Receipt manifest is not valid JSON.") from error
    if not isinstance(data, dict) or type(data.get("version")) is not int:
        raise ValueError("Receipt manifest must be a versioned JSON object.")
    if data["version"] != 1:
        raise ValueError("Unsupported receipt manifest version.")
    entries = data.get("receipts")
    if not isinstance(entries, list):
        raise ValueError("Receipt manifest receipts must be a list.")

    loaded: List[Tuple[Path, dict]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError("Receipt manifest entry {} must be an object.".format(index))
        image_path_value = entry.get("image_path")
        if not isinstance(image_path_value, str) or not image_path_value:
            raise ValueError(
                "Receipt manifest entry {} needs an image_path.".format(index)
            )
        image_path = Path(image_path_value)
        if not image_path.is_absolute():
            candidates = (receipts_directory / image_path, PROJECT_ROOT / image_path)
            image_path = next(
                (candidate for candidate in candidates if candidate.is_file()),
                candidates[0],
            )
        image_path = image_path.resolve()
        if not image_path.is_file():
            raise FileNotFoundError(
                "Receipt image does not exist: {}".format(image_path)
            )
        loaded.append((image_path, entry))
    return loaded


def load_receipts(
    receipts_directory: Path = DEFAULT_RECEIPTS_DIRECTORY,
    manifest_path: Optional[Path] = DEFAULT_RECEIPT_MANIFEST_PATH,
) -> Tuple[Receipt, ...]:
    """Load processed receipt images, using filename dates and optional metadata.

    The existing OCR step prefixes successfully dated images with
    ``YYYY-MM-DD_``. An optional version-1 JSON manifest can supply explicit
    dates and additional OCR fields for those images.
    """
    directory = Path(receipts_directory).resolve()
    if not directory.is_dir():
        raise FileNotFoundError(
            "Processed receipts directory does not exist: {}".format(directory)
        )

    manifest_entries = (
        _load_manifest(Path(manifest_path), directory)
        if manifest_path is not None and Path(manifest_path).is_file()
        else []
    )
    metadata_by_image = {str(path): entry for path, entry in manifest_entries}
    image_paths = {
        path.resolve()
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in _IMAGE_EXTENSIONS
    }
    image_paths.update(path for path, _ in manifest_entries)

    receipts = []
    seen_ids = set()
    for image_path in sorted(image_paths, key=lambda item: item.name.lower()):
        entry = metadata_by_image.get(str(image_path), {})
        filename_date = _date_from_filename(image_path)
        receipt_date, date_error = _parse_manifest_date(
            entry.get("receipt_date"), filename_date
        )
        receipt_id = entry.get("receipt_id", image_path.name)
        if not isinstance(receipt_id, str) or not receipt_id.strip():
            raise ValueError("Receipt IDs in the manifest must be non-empty strings.")
        if receipt_id in seen_ids:
            raise ValueError("Duplicate receipt_id in receipt data: {}".format(receipt_id))
        seen_ids.add(receipt_id)

        vendor = entry.get("vendor")
        raw_ocr_text = entry.get("raw_ocr_text")
        if vendor is not None and not isinstance(vendor, str):
            raise ValueError("Vendor for receipt {!r} must be a string.".format(receipt_id))
        if raw_ocr_text is not None and not isinstance(raw_ocr_text, str):
            raise ValueError(
                "raw_ocr_text for receipt {!r} must be a string.".format(receipt_id)
            )

        receipts.append(
            Receipt(
                receipt_id=receipt_id,
                image_path=_path_for_output(image_path),
                receipt_date=receipt_date,
                amount=_parse_amount(entry.get("amount"), receipt_id),
                vendor=vendor,
                raw_ocr_text=raw_ocr_text,
                date_error=date_error,
            )
        )
    return tuple(receipts)
