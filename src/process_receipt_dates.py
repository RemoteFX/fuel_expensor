"""
OCR Receipt Purchase Date Detection and Renaming Workflow.

This script identifies the actual purchase date from fuel receipt images using
Tesseract OCR, validates UK date conventions, and renames files with the ISO
date prefix.

Usage:
    py src/process_receipt_dates.py --input-dir data/processed_receipts
    py src/process_receipt_dates.py --help
"""

import argparse
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import pytesseract
from PIL import Image

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# UK date patterns - day-first interpretation enforced
UK_DATE_PATTERNS = [
    # DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
    (r"\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})\b", 3),
    # DD-MMM-YYYY e.g. 05-Jun-2023
    (r"\b(\d{1,2})-([A-Za-z]{3})-(\d{4})\b", 3),
    # DD MMM YYYY e.g. 05 June 2023
    (r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})\b", 3),
]

# Keywords that indicate an explicit transaction date (highest priority)
PRIORITY_1_KEYWORDS = [
    "transaction date",
    "purchase date",
    "sale date",
    "trans date",
]

# Keywords indicating generic receipt dates (high priority but context-dependent)
PRIORITY_2_KEYWORDS = [
    "receipt date",
    "date",
    "purchase",
    "transaction",
]

# Keywords associated with transaction times (supporting evidence)
PRIORITY_3_INDICATORS = [
    "time",
    "at",
]

# Keywords that should deprioritize or reject a date
REJECT_KEYWORDS = [
    "printed",
    "print date",
    "receipt generated",
    "generated on",
    "card settlement",
    "settlement date",
    "payment processing",
    "offer ends",
    "promotion ends",
    "valid until",
    "loyalty points expiry",
    "expiry",
    "points",
    "bonus",
    "reward",
    "scheme",
    "settlement",
    "promotion",
]

# Month name mapping for month-name date formats
MONTH_NAMES = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

# Supported image extensions (case-insensitive)
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


class DateCandidate:
    """Represents a detected date candidate with its context and score."""

    def __init__(self, raw_text: str, date_str: str, score: int, context: str):
        self.raw_text = raw_text.strip()
        self.date_str = date_str.strip()
        self.score = score
        self.context = context.strip()

    def to_iso(self) -> Optional[str]:
        """Convert the date string to ISO format (YYYY-MM-DD)."""
        try:
            dt = datetime.strptime(self.date_str, "%d/%m/%Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            try:
                dt = datetime.strptime(self.date_str, "%d-%m-%Y")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                try:
                    dt = datetime.strptime(self.date_str, "%d.%m.%Y")
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    try:
                        dt = datetime.strptime(self.date_str, "%d-%b-%Y")
                        return dt.strftime("%Y-%m-%d")
                    except ValueError:
                        try:
                            dt = datetime.strptime(self.date_str, "%d %B %Y")
                            return dt.strftime("%Y-%m-%d")
                        except ValueError:
                            return None


def preprocess_image(image_path: Path) -> Image.Image:
    """
    Preprocess an image for OCR using Pillow.

    Steps:
    1. Open the image safely.
    2. Correct orientation using EXIF metadata.
    3. Convert to grayscale.
    4. Apply contrast enhancement.
    5. Apply adaptive thresholding for binarization.
    """
    try:
        img = Image.open(image_path)
    except Exception as e:
        logger.error(f"Failed to open image {image_path}: {e}")
        raise

    # Correct orientation using EXIF data
    if hasattr(img, "getexif"):
        try:
            exif = img.getexif()
            orientation = exif.get(274)
            if orientation == 3:
                img = img.rotate(180, expand=True)
            elif orientation in (6, 8):
                img = img.rotate(90 if orientation == 6 else -90, expand=True)
        except Exception:
            pass

    # Convert to grayscale
    if img.mode != "L":
        img = img.convert("L")

    # Enhance contrast using histogram equalization
    img = img.point(lambda x: 255 * (x / 255.0))

    # Apply adaptive thresholding for binarization
    # This helps with thermal receipts that may have faint printing
    from PIL import ImageOps
    img = ImageOps.autocontrast(img)

    return img


def extract_text(image_path: Path) -> Optional[str]:
    """
    Extract text from an image using Tesseract OCR.

    Returns None if Tesseract is unavailable or the image cannot be processed.
    """
    try:
        # Check if Tesseract is available
        pytesseract.get_tesseract_version()
    except OSError as e:
        logger.error(
            f"Tesseract executable not found: {e}. "
            "Install Tesseract from https://github.com/UB-Mannheim/tesseract/wiki "
            "and ensure it's on your PATH."
        )
        return None

    try:
        img = preprocess_image(image_path)
        text = pytesseract.image_to_string(img, config="--psm 6 --oem 3 -l eng")
        return text if text.strip() else None
    except Exception as e:
        logger.error(f"OCR failed for {image_path}: {e}")
        return None


def find_date_candidates(text: str) -> list[DateCandidate]:
    """
    Find all date candidates in the OCR text with their context and priority.
    """
    candidates = []

    # Priority 1: Explicit transaction dates
    for keyword in PRIORITY_1_KEYWORDS:
        pattern = rf"(?i){keyword}\s*[:\-]\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4}|\d{1,2}[-\s][A-Za-z]{3,9}[-\s]\d{4})"
        matches = re.finditer(pattern, text)
        for match in matches:
            raw_text = match.group(0)
            date_str = match.group(1)
            candidates.append(DateCandidate(raw_text, date_str, 100, f"Priority 1: {keyword}"))

    # Priority 2: Generic receipt dates
    for keyword in PRIORITY_2_KEYWORDS:
        pattern = rf"(?i){keyword}\s*[:\-]\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4}|\d{1,2}[-\s][A-Za-z]{3,9}[-\s]\d{4})"
        matches = re.finditer(pattern, text)
        for match in matches:
            raw_text = match.group(0)
            date_str = match.group(1)
            candidates.append(DateCandidate(raw_text, date_str, 75, f"Priority 2: {keyword}"))

    # Priority 3: Dates near transaction times (supporting evidence)
    time_pattern = r"\b(\d{1,2}:\d{2})\b"
    time_matches = list(re.finditer(time_pattern, text))
    for time_match in time_matches:
        # Look backwards for a date before the time
        start = max(0, time_match.start() - 40)
        before_text = text[start:time_match.start()]
        date_match = re.search(
            r"(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4}|\d{1,2}[-\s][A-Za-z]{3,9}[-\s]\d{4})",
            before_text,
        )
        if date_match:
            raw_text = f"{date_match.group(0)} {time_match.group(1)}"
            date_str = date_match.group(0)
            candidates.append(DateCandidate(raw_text, date_str, 60, "Priority 3: near transaction time"))

    # Priority 4: Unlabelled dates in main body (not footer)
    # Find standalone dates that are not associated with reject keywords
    date_patterns = [
        r"\b(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})\b",
        r"\b(\d{1,2}[-\s][A-Za-z]{3,9}[-\s]\d{4})\b",
    ]
    for pattern in date_patterns:
        matches = re.finditer(pattern, text)
        for match in matches:
            raw_text = match.group(0)
            # Check if this date is near reject keywords
            context_start = max(0, match.start() - 30)
            context_end = min(len(text), match.end() + 30)
            context = text[context_start:context_end]
            is_rejected = any(kw.lower() in context.lower() for kw in REJECT_KEYWORDS)
            if not is_rejected:
                candidates.append(DateCandidate(raw_text, raw_text, 40, "Priority 4: unlabelled"))

    return candidates


def score_date_candidates(candidates: list[DateCandidate]) -> Optional[str]:
    """
    Score and select the best date candidate.

    Returns ISO date string or None if no reliable date found.
    """
    if not candidates:
        logger.warning("No date candidates found in receipt text.")
        return None

    # Filter out rejected candidates
    valid_candidates = [c for c in candidates if c.score > 0]

    if not valid_candidates:
        logger.warning("No valid date candidates found after rejection filtering.")
        return None

    # Sort by score descending
    valid_candidates.sort(key=lambda c: c.score, reverse=True)

    # Check for ambiguity - if top two scores are close, flag as ambiguous
    top_score = valid_candidates[0].score
    second_score = valid_candidates[1].score if len(valid_candidates) > 1 else 0
    score_diff = top_score - second_score

    # If the difference is small (within 20 points), consider it ambiguous
    if score_diff < 20 and len(valid_candidates) >= 2:
        logger.warning(
            f"Ambiguous date detected. Top candidates:\n"
            f"  1. {valid_candidates[0].date_str} ({valid_candidates[0].context})\n"
            f"  2. {valid_candidates[1].date_str} ({valid_candidates[1].context})"
        )
        return None

    # Select the highest-scoring candidate
    best = valid_candidates[0]
    iso_date = best.to_iso()

    if iso_date is None:
        logger.warning(f"Date candidate '{best.date_str}' could not be parsed to ISO format.")
        return None

    logger.info(f"Purchase date identified: {iso_date}")
    return iso_date


def detect_purchase_date(text: str) -> Optional[str]:
    """
    Detect and validate the actual purchase date from OCR text.

    Returns ISO date string or None.
    """
    candidates = find_date_candidates(text)
    return score_date_candidates(candidates)


def has_iso_prefix(filename: str) -> bool:
    """Check if filename already has a valid ISO date prefix."""
    iso_pattern = r"^(\d{4}-\d{2}-\d{2})_"
    return bool(re.match(iso_pattern, filename))


def rename_receipt(input_path: Path, iso_date: str) -> Optional[Path]:
    """
    Rename the receipt file with the ISO date prefix.

    Args:
        input_path: The original image path.
        iso_date: The validated ISO date (YYYY-MM-DD).

    Returns:
        The new path if renamed successfully, or None if no rename occurred.
    """
    stem = input_path.stem
    suffix = input_path.suffix

    # Check if already has ISO prefix
    if has_iso_prefix(stem):
        logger.info(f"File already has ISO prefix: {input_path.name}")
        return None

    # Build new filename
    new_stem = f"{iso_date}_{stem}"
    new_path = input_path.parent / (new_stem + suffix)

    # Check for collision - never overwrite existing files
    if new_path.exists():
        logger.error(f"Filename collision: {new_path.name} already exists. Not overwriting.")
        return None

    # Perform rename
    try:
        input_path.rename(new_path)
        logger.info(f"Renamed {input_path.name} -> {new_path.name}")
        return new_path
    except Exception as e:
        logger.error(f"Failed to rename {input_path.name}: {e}")
        return None


def process_directory(input_dir: Path) -> dict:
    """
    Process all supported image files in the input directory.

    Returns a summary dictionary with counts.
    """
    summary = {
        "discovered": 0,
        "processed": 0,
        "renamed": 0,
        "already_processed": 0,
        "no_date_found": 0,
        "manual_review": 0,
        "errors": 0,
    }

    if not input_dir.exists():
        logger.error(f"Input directory does not exist: {input_dir}")
        return summary

    # Find all supported images (case-insensitive)
    image_files = [f for f in input_dir.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]
    summary["discovered"] = len(image_files)

    for image_path in image_files:
        logger.info(f"Processing {image_path.name}")

        try:
            # Extract text
            text = extract_text(image_path)
            if not text:
                summary["errors"] += 1
                continue

            # Detect purchase date
            iso_date = detect_purchase_date(text)

            if iso_date is None:
                summary["no_date_found"] += 1
                logger.warning(f"No reliable purchase date found in {image_path.name}")
                continue

            # Rename file
            new_path = rename_receipt(image_path)
            if new_path is None:
                if has_iso_prefix(image_path.stem):
                    summary["already_processed"] += 1
                else:
                    summary["no_date_found"] += 1
            else:
                summary["renamed"] += 1

            summary["processed"] += 1

        except Exception as e:
            summary["errors"] += 1
            logger.error(f"Error processing {image_path.name}: {e}")

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="OCR receipt purchase date detection and renaming workflow."
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default="data/processed_receipts",
        help="Directory containing receipt images (default: data/processed_receipts)",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)

    logger.info(f"Starting receipt processing in: {input_dir}")

    summary = process_directory(input_dir)

    # Print final summary
    print("\n" + "=" * 50)
    print("PROCESSING SUMMARY")
    print("=" * 50)
    print(f"Images discovered:      {summary['discovered']}")
    print(f"Successfully processed: {summary['processed']}")
    print(f"Successfully renamed:   {summary['renamed']}")
    print(f"Already processed:      {summary['already_processed']}")
    print(f"No purchase date found: {summary['no_date_found']}")
    print(f"Manual review required: {summary['manual_review']}")
    print(f"Files with errors:      {summary['errors']}")
    print("=" * 50)


if __name__ == "__main__":
    main()