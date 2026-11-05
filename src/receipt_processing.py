"""Reusable, isolated receipt-image processing jobs."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence, Tuple

from src.crop_receipts import (
    DEFAULT_MODEL_PATH,
    IMAGE_EXTENSIONS,
    crop_receipts_for_images,
)
from src.process_receipt_dates import process_receipts
from src.receipts import Receipt, load_receipts


DEFAULT_JOB_DIRECTORY = (
    Path(__file__).resolve().parents[1] / "data" / "processed" / "jobs"
)
INCOMPLETE_MARKER = ".incomplete"


@dataclass(frozen=True)
class ProcessingProgress:
    stage: str
    completed: int
    total: int
    message: str


@dataclass(frozen=True)
class ProcessingItemResult:
    image_path: Path
    stage: str
    status: str
    message: Optional[str] = None


@dataclass(frozen=True)
class ReceiptProcessingResult:
    job_id: str
    output_directory: Path
    input_count: int
    detected_receipt_count: int
    receipts: Tuple[Receipt, ...]
    item_results: Tuple[ProcessingItemResult, ...]
    errors: Tuple[str, ...]
    warnings: Tuple[str, ...]


ProgressCallback = Callable[[ProcessingProgress], None]


def process_uploaded_images(
    image_paths: Sequence[Path],
    output_root: Path = DEFAULT_JOB_DIRECTORY,
    model_path: Path = Path(DEFAULT_MODEL_PATH),
    progress_callback: Optional[ProgressCallback] = None,
) -> ReceiptProcessingResult:
    """Crop and date uploaded images in a unique job directory.

    An incomplete marker keeps partially written jobs out of normal receipt
    discovery if processing is interrupted.
    """
    normalized_paths = []
    seen_paths = set()
    for value in image_paths:
        image_path = Path(value).resolve()
        if image_path in seen_paths:
            continue
        seen_paths.add(image_path)
        if not image_path.is_file():
            raise FileNotFoundError("Input image does not exist: {}".format(image_path))
        if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise ValueError("Unsupported receipt image type: {}".format(image_path))
        normalized_paths.append(image_path)
    if not normalized_paths:
        raise ValueError("Select at least one receipt image.")

    job_id = uuid.uuid4().hex
    job_directory = Path(output_root).resolve() / job_id
    job_directory.mkdir(parents=True, exist_ok=False)
    marker_path = job_directory / INCOMPLETE_MARKER
    marker_path.write_text("Processing has not completed.\n", encoding="utf-8")

    errors = []
    warnings = []
    item_results = []

    def report(stage: str, completed: int, total: int, path: Path) -> None:
        if progress_callback is not None:
            progress_callback(
                ProcessingProgress(
                    stage=stage,
                    completed=completed,
                    total=total,
                    message=path.name,
                )
            )

    crop_results = crop_receipts_for_images(
        model_path,
        normalized_paths,
        job_directory,
        progress_callback=lambda completed, total, path: report(
            "detecting", completed, total, path
        ),
    )
    detected_count = sum(len(result.receipt_paths) for result in crop_results)
    for result in crop_results:
        if result.error:
            errors.append("{}: {}".format(result.source_path.name, result.error))
            item_results.append(
                ProcessingItemResult(
                    image_path=result.source_path,
                    stage="detection",
                    status="error",
                    message=result.error,
                )
            )
        elif not result.receipt_paths:
            warning = "No receipts were detected in {}.".format(
                result.source_path.name
            )
            warnings.append(warning)
            item_results.append(
                ProcessingItemResult(
                    image_path=result.source_path,
                    stage="detection",
                    status="no_receipts_found",
                    message=warning,
                )
            )

    ocr_summary = process_receipts(
        job_directory,
        progress_callback=lambda completed, total, path: report(
            "reading_dates", completed, total, path
        ),
    )
    errors.extend(ocr_summary["errors"])
    item_results.extend(
        ProcessingItemResult(
            image_path=Path(item["image_path"]),
            stage="date_extraction",
            status=item["status"],
            message=item.get("error"),
        )
        for item in ocr_summary["items"]
    )
    warnings.extend(
        "{}: {}".format(item["image_path"], item["error"])
        for item in ocr_summary["items"]
        if item["status"] == "date_not_found"
    )
    manifest_entries = []
    for item in ocr_summary["items"]:
        image_path = Path(item["image_path"]).resolve()
        if image_path.parent != job_directory:
            raise ValueError("Processed receipt escaped its job directory.")
        entry = {
            "receipt_id": image_path.name,
            "image_path": image_path.name,
        }
        if item["status"] in ("date_not_found", "error"):
            entry["date_error"] = item.get("error", "Date extraction failed.")
        manifest_entries.append(entry)
    (job_directory / "receipt_manifest.json").write_text(
        json.dumps({"version": 1, "receipts": manifest_entries}, indent=2) + "\n",
        encoding="utf-8",
    )
    receipts = load_receipts(
        job_directory,
        manifest_path=job_directory / "receipt_manifest.json",
        include_incomplete=True,
    )
    marker_path.unlink()
    return ReceiptProcessingResult(
        job_id=job_id,
        output_directory=job_directory,
        input_count=len(normalized_paths),
        detected_receipt_count=detected_count,
        receipts=receipts,
        item_results=tuple(item_results),
        errors=tuple(errors),
        warnings=tuple(warnings),
    )
