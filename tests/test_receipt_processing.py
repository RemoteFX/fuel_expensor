"""Tests for isolated, resumable receipt-processing jobs."""

import json
from pathlib import Path

import pytest

from src import receipt_processing
from src.crop_receipts import ImageCropResult
from src.receipts import load_receipts


def test_processing_job_isolated_and_returns_receipts_and_progress(
    tmp_path, monkeypatch
):
    source = tmp_path / "receipt.jpg"
    source.touch()
    progress = []

    def fake_crop(_model_path, image_paths, output_path, progress_callback=None):
        output = Path(output_path) / "receipt_crop.jpg"
        output.touch()
        if progress_callback:
            progress_callback(1, len(image_paths), image_paths[0])
        return (ImageCropResult(image_paths[0], (output,)),)

    def fake_ocr(input_dir, progress_callback=None):
        source_crop = Path(input_dir) / "receipt_crop.jpg"
        dated_crop = Path(input_dir) / "2025-04-02_receipt_crop.jpg"
        source_crop.rename(dated_crop)
        if progress_callback:
            progress_callback(1, 1, dated_crop)
        return {
            "errors": [],
            "items": [
                {
                    "image_path": str(dated_crop),
                    "status": "dated",
                    "receipt_date": "2025-04-02",
                }
            ],
        }

    monkeypatch.setattr(receipt_processing, "crop_receipts_for_images", fake_crop)
    monkeypatch.setattr(receipt_processing, "process_receipts", fake_ocr)

    result = receipt_processing.process_uploaded_images(
        [source, source],
        output_root=tmp_path / "jobs",
        model_path=Path("unused.pt"),
        progress_callback=progress.append,
    )

    assert result.input_count == 1
    assert result.detected_receipt_count == 1
    assert result.receipts[0].receipt_date.isoformat() == "2025-04-02"
    assert result.item_results[0].stage == "date_extraction"
    assert result.item_results[0].status == "dated"
    assert not (result.output_directory / ".incomplete").exists()
    assert [event.stage for event in progress] == ["detecting", "reading_dates"]
    assert load_receipts(tmp_path / "jobs") == result.receipts


def test_incomplete_processing_job_is_not_loaded(tmp_path, monkeypatch):
    source = tmp_path / "receipt.jpg"
    source.touch()
    created_jobs = []

    def fake_crop(_model_path, image_paths, output_path, progress_callback=None):
        output = Path(output_path) / "receipt_crop.jpg"
        output.touch()
        created_jobs.append(Path(output_path))
        return (ImageCropResult(image_paths[0], (output,)),)

    def fail_ocr(_input_dir, progress_callback=None):
        raise RuntimeError("OCR backend failed")

    monkeypatch.setattr(receipt_processing, "crop_receipts_for_images", fake_crop)
    monkeypatch.setattr(receipt_processing, "process_receipts", fail_ocr)

    with pytest.raises(RuntimeError, match="OCR backend failed"):
        receipt_processing.process_uploaded_images(
            [source], output_root=tmp_path / "jobs", model_path=Path("unused.pt")
        )

    assert (created_jobs[0] / ".incomplete").exists()
    assert load_receipts(tmp_path / "jobs") == ()


def test_receipt_loader_skips_images_under_incomplete_job(tmp_path):
    job = tmp_path / "jobs" / "job-1"
    job.mkdir(parents=True)
    (job / "2025-04-02_receipt.jpg").touch()
    (job / ".incomplete").touch()

    assert load_receipts(tmp_path) == ()


def test_receipt_loader_preserves_date_processing_error(tmp_path):
    image = tmp_path / "receipt.jpg"
    image.touch()
    (tmp_path / "receipt_manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "receipts": [
                    {
                        "receipt_id": "receipt.jpg",
                        "image_path": "receipt.jpg",
                        "date_error": "Tesseract OCR failed.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    receipt = load_receipts(
        tmp_path, manifest_path=tmp_path / "receipt_manifest.json"
    )[0]

    assert receipt.receipt_date is None
    assert receipt.date_error == "Tesseract OCR failed."


def test_root_loader_reads_manifests_from_completed_jobs(tmp_path):
    job = tmp_path / "jobs" / "job-1"
    job.mkdir(parents=True)
    (job / "receipt.jpg").touch()
    (job / "receipt_manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "receipts": [
                    {
                        "receipt_id": "job-receipt",
                        "image_path": "receipt.jpg",
                        "date_error": "Tesseract OCR failed.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    receipts = load_receipts(tmp_path, manifest_path=None)

    assert len(receipts) == 1
    assert receipts[0].receipt_id == "job-receipt"
    assert receipts[0].date_error == "Tesseract OCR failed."
