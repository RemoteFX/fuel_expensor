import argparse
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

import pytesseract
from PIL import Image, ImageEnhance, ImageOps

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Supported image extensions
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}

POSITIVE_KEYWORDS = [
    "transaction date",
    "purchase date",
    "sale date",
    "trans date",
    "receipt date",
    "date",
    "time",
    "tax invoice",
    "sale",
    "total",
    "paid",
]

NEGATIVE_KEYWORDS = [
    "expiry",
    "expires",
    "offer",
    "offer ends",
    "promotion ends",
    "print date",
    "printed",
    "valid until",
    "valid from",
    "best before",
    "use by",
    "member since",
    "card ending",
    "dob",
    "birth",
    "settlement",
]

MONTH_NAMES = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9, "sept": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def preprocess_image(image_path: Path) -> List[Image.Image]:
    """
    Preprocess image with Pillow for optimal OCR legibility on thermal receipts.
    Combines binarization (thresholding) and contrast enhancement to eliminate thermal noise.
    """
    img = Image.open(image_path)
    if img.mode != "RGB":
        img = img.convert("RGB")

    gray = ImageOps.grayscale(img)

    thresh150 = gray.point(lambda p: 255 if p > 150 else 0)
    thresh130 = gray.point(lambda p: 255 if p > 130 else 0)
    contrast3 = ImageEnhance.Contrast(gray).enhance(3.0)
    auto_contrast = ImageOps.autocontrast(gray)

    return [thresh150, thresh130, contrast3, auto_contrast, gray]


def parse_uk_date(day_s: str, month_s: str, year_s: str) -> Optional[datetime]:
    """
    Parse day, month, year strictly following UK date convention (DD/MM/YYYY).
    """
    try:
        day = int(day_s)

        month_s_clean = month_s.strip().lower()
        if month_s_clean in MONTH_NAMES:
            month = MONTH_NAMES[month_s_clean]
        else:
            month = int(month_s)

        year = int(year_s)
        if year < 100:
            year += 2000 if year < 70 else 1900

        if not (1 <= month <= 12 and 1 <= day <= 31 and 1990 <= year <= 2035):
            return None

        return datetime(year, month, day)
    except (ValueError, TypeError):
        return None


def extract_date_candidates(text: str) -> List[tuple]:
    """
    Scans text line by line to locate UK format date candidates with context score.
    No hardcoded character replacements.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    candidates = []

    # UK date regexes: Day/Month/Year or Day Month Year
    numeric_pattern = re.compile(
        r'\b([0-3]?\d)[\s/\.\-\\]([0-1]?\d)[\s/\.\-\\](20\d{2}|\d{2})\b'
    )
    named_month_pattern = re.compile(
        r'\b([0-3]?\d)[\s/\.\-]*([A-Za-z]{3,9})[\s/\.\-]*(20\d{2}|\d{2})\b',
        re.IGNORECASE
    )

    for i, line in enumerate(lines):
        window_start = max(0, i - 2)
        window_end = min(len(lines), i + 3)
        context_text = " ".join(lines[window_start:window_end]).lower()

        base_score = 10

        for pos_kw in POSITIVE_KEYWORDS:
            if pos_kw in context_text:
                base_score += 15

        for neg_kw in NEGATIVE_KEYWORDS:
            if neg_kw in context_text:
                base_score -= 35

        for match in numeric_pattern.finditer(line):
            day_s, month_s, year_s = match.groups()
            dt = parse_uk_date(day_s, month_s, year_s)
            if dt:
                score = base_score
                if "date" in line.lower():
                    score += 20
                candidates.append((dt, score, line))

        for match in named_month_pattern.finditer(line):
            day_s, month_s, year_s = match.groups()
            dt = parse_uk_date(day_s, month_s, year_s)
            if dt:
                score = base_score + 10
                if "date" in line.lower():
                    score += 20
                candidates.append((dt, score, line))

    return candidates


def extract_best_date(image_path: Path) -> Optional[str]:
    """
    Performs OCR and extracts the best valid purchase date as ISO string (YYYY-MM-DD).
    """
    images = preprocess_image(image_path)
    configs = ["--psm 6", "--psm 4", "--psm 3", ""]
    all_candidates = []
    successful_attempts = 0
    last_error = None

    for img in images:
        for config in configs:
            try:
                ocr_text = pytesseract.image_to_string(img, config=config) if config else pytesseract.image_to_string(img)
                successful_attempts += 1
                if ocr_text:
                    candidates = extract_date_candidates(ocr_text)
                    all_candidates.extend(candidates)
                    if any(score >= 25 for _, score, _ in candidates):
                        break
            except Exception as e:
                last_error = e
                logger.debug("OCR attempt error: %s", e)
                continue
        if any(score >= 25 for _, score, _ in all_candidates):
            break

    if successful_attempts == 0 and last_error is not None:
        raise RuntimeError("All Tesseract OCR attempts failed.") from last_error

    valid_candidates = [c for c in all_candidates if c[1] > -10]
    if not valid_candidates:
        return None

    valid_candidates.sort(key=lambda x: x[1], reverse=True)
    best_dt = valid_candidates[0][0]
    return best_dt.strftime("%Y-%m-%d")


def process_receipts(
    input_dir: Path,
    progress_callback: Optional[Callable[[int, int, Path], None]] = None,
) -> dict:
    """
    Process all receipt images in directory and prepend ISO date prefix YYYY-MM-DD_.
    """
    summary = {
        "processed": 0,
        "renamed": 0,
        "failed": 0,
        "errors": [],
        "items": [],
    }

    if not input_dir.is_dir():
        raise FileNotFoundError("Input directory does not exist: {}".format(input_dir))

    files = sorted(
        (
            file_path
            for file_path in input_dir.iterdir()
            if file_path.is_file()
            and file_path.suffix.lower() in SUPPORTED_EXTENSIONS
        ),
        key=lambda file_path: file_path.name.lower(),
    )

    iso_prefix_regex = re.compile(r'^\d{4}-\d{2}-\d{2}_')

    for index, file_path in enumerate(files, start=1):
        summary["processed"] += 1
        clean_name = iso_prefix_regex.sub('', file_path.name)

        logger.info(f"Processing: {file_path.name}")
        try:
            extracted_date = extract_best_date(file_path)

            if extracted_date:
                new_name = f"{extracted_date}_{clean_name}"
                new_path = file_path.parent / new_name

                if file_path != new_path:
                    if new_path.exists():
                        raise FileExistsError(
                            "Refusing to overwrite an existing dated receipt: {}".format(
                                new_path
                            )
                        )
                    file_path.rename(new_path)
                    summary["renamed"] += 1
                    logger.info(f"Successfully extracted date {extracted_date} -> Renamed to {new_name}")
                else:
                    logger.info(f"Filename already up to date: {file_path.name}")
                summary["items"].append(
                    {
                        "image_path": str(new_path),
                        "status": "dated",
                        "receipt_date": extracted_date,
                    }
                )
            else:
                summary["failed"] += 1
                logger.warning(f"Could not extract valid date from: {file_path.name}")
                summary["items"].append(
                    {
                        "image_path": str(file_path),
                        "status": "date_not_found",
                        "error": "Could not extract a valid receipt date.",
                    }
                )
        except Exception as error:
            summary["failed"] += 1
            error_message = "{}: {}".format(file_path.name, error)
            summary["errors"].append(error_message)
            summary["items"].append(
                {
                    "image_path": str(file_path),
                    "status": "error",
                    "error": str(error),
                }
            )
            logger.exception("Could not process receipt image: %s", file_path)
        if progress_callback is not None:
            progress_callback(index, len(files), file_path)

    return summary


def main():
    parser = argparse.ArgumentParser(description="OCR receipt date extraction and file renaming.")
    parser.add_argument("--input-dir", type=str, default="data/processed", help="Path to input directory")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    logger.info(f"Starting receipt date extraction in {input_dir}")
    try:
        summary = process_receipts(input_dir)
    except (OSError, ValueError) as error:
        logger.error("Receipt date extraction could not start: %s", error)
        return 1

    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"Total processed: {summary['processed']}")
    print(f"Successfully renamed: {summary['renamed']}")
    print(f"Failed to extract date: {summary['failed']}")
    print(f"Processing errors: {len(summary['errors'])}")
    print("=" * 50)
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())