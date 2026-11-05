"""Tests for receipt-date processing failures and batch-script contracts."""

from pathlib import Path

import pytest

from src import process_receipt_dates


def test_extract_best_date_distinguishes_ocr_failure_from_missing_date(monkeypatch):
    monkeypatch.setattr(
        process_receipt_dates, "preprocess_image", lambda _path: [object()]
    )

    def unavailable_tesseract(*_args, **_kwargs):
        raise RuntimeError("Tesseract is unavailable")

    monkeypatch.setattr(
        process_receipt_dates.pytesseract, "image_to_string", unavailable_tesseract
    )
    with pytest.raises(RuntimeError, match="All Tesseract OCR attempts failed"):
        process_receipt_dates.extract_best_date(Path("receipt.jpg"))

    monkeypatch.setattr(
        process_receipt_dates.pytesseract,
        "image_to_string",
        lambda *_args, **_kwargs: "",
    )
    assert process_receipt_dates.extract_best_date(Path("receipt.jpg")) is None


def test_process_receipts_reports_per_image_ocr_errors(tmp_path, monkeypatch):
    (tmp_path / "receipt.jpg").touch()
    monkeypatch.setattr(
        process_receipt_dates,
        "extract_best_date",
        lambda _path: (_ for _ in ()).throw(RuntimeError("OCR unavailable")),
    )

    summary = process_receipt_dates.process_receipts(tmp_path)

    assert summary["processed"] == 1
    assert summary["failed"] == 1
    assert summary["items"][0]["status"] == "error"
    assert "OCR unavailable" in summary["errors"][0]


def test_process_receipts_rejects_missing_directory_and_rename_collision(
    tmp_path, monkeypatch
):
    with pytest.raises(FileNotFoundError):
        process_receipt_dates.process_receipts(tmp_path / "missing")

    (tmp_path / "source.jpg").touch()
    (tmp_path / "2025-04-02_source.jpg").touch()
    monkeypatch.setattr(
        process_receipt_dates, "extract_best_date", lambda _path: "2025-04-02"
    )

    summary = process_receipt_dates.process_receipts(tmp_path)

    assert any("Refusing to overwrite" in error for error in summary["errors"])


def test_batch_scripts_use_the_supported_input_dir_option():
    project_root = Path(__file__).resolve().parents[1]

    for name in ("test_workflow.bat", "test_receipt_OCR.bat"):
        content = (project_root / name).read_text(encoding="utf-8")
        assert "process_receipt_dates.py --input-dir" in content
        assert "process_receipt_dates.py --input " not in content
