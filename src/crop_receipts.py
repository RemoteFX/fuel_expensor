import argparse
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence, Tuple

import cv2
from ultralytics import YOLO

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Resolve project root: find the directory containing both data/ and src/ (repo root)
PROJECT_ROOT = SCRIPT_DIR
while not os.path.isdir(os.path.join(PROJECT_ROOT, "data")) or not os.path.isdir(os.path.join(PROJECT_ROOT, "src")):
    parent = os.path.dirname(PROJECT_ROOT)
    if parent == PROJECT_ROOT:
        break
    PROJECT_ROOT = parent

# Fallback: ensure we found a valid root with both markers
if not os.path.isdir(os.path.join(PROJECT_ROOT, "data")) or not os.path.isdir(os.path.join(PROJECT_ROOT, "src")):
    # Try common known locations relative to script
    candidates = [
        os.path.join(SCRIPT_DIR, "..", "fuel_expensor"),
        os.path.join(SCRIPT_DIR, "..", "fuel_expensor", "data"),
    ]
    for candidate in candidates:
        if os.path.isdir(candidate) and os.path.isdir(os.path.join(candidate, "data")) and os.path.isdir(os.path.join(candidate, "src")):
            PROJECT_ROOT = candidate
            break

# Default to a built-in Ultralytics model when no custom local model is provided
DEFAULT_MODEL_NAME = "yolov8n.pt"
DEFAULT_MODEL_PATH = os.path.join(PROJECT_ROOT, "data", "models", "receipt_detector_2.pt")
IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


@dataclass(frozen=True)
class ImageCropResult:
    source_path: Path
    receipt_paths: Tuple[Path, ...]
    error: Optional[str] = None


def _image_paths(input_path):
    input_is_directory = os.path.isdir(input_path)
    if input_is_directory:
        image_paths = sorted(
            os.path.join(input_path, filename)
            for filename in os.listdir(input_path)
            if os.path.isfile(os.path.join(input_path, filename))
            and Path(filename).suffix.lower() in IMAGE_EXTENSIONS
        )
        if not image_paths:
            raise ValueError(f"No supported image files found in input directory: {input_path}")
    elif os.path.isfile(input_path):
        image_paths = [input_path]
    else:
        raise FileNotFoundError(f"Input image or directory does not exist: {input_path}")
    return image_paths


def crop_receipts_for_images(
    model_path,
    image_paths: Sequence[Path],
    output_path,
    progress_callback: Optional[Callable[[int, int, Path], None]] = None,
    verbose: bool = False,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[ImageCropResult, ...]:
    """Crop each input independently, retaining per-image failures."""
    normalized_paths = tuple(Path(image_path) for image_path in image_paths)
    if not normalized_paths:
        raise ValueError("At least one input image is required.")

    os.makedirs(output_path, exist_ok=True)
    model = YOLO(model_path)
    results = []

    for index, image_path in enumerate(normalized_paths, start=1):
        receipt_paths = []
        error_message = None
        try:
            image = cv2.imread(str(image_path))
            if image is None:
                raise ValueError(f"Unable to load image: {image_path}")

            detections = model(image, verbose=verbose)

            source_digest = hashlib.sha256(
                str(image_path.resolve()).encode("utf-8")
            ).hexdigest()[:10]
            output_stem = "{}_{}_{}".format(
                image_path.stem, source_digest, Path(output_path).name
            )
            for detection in detections:
                if detection.boxes is None:
                    continue
                boxes = detection.boxes.cpu().numpy()
                for box in boxes:
                    xyxy = box.xyxy[0]
                    if hasattr(xyxy, "cpu"):
                        xyxy = xyxy.cpu().numpy()
                    x1, y1, x2, y2 = xyxy.astype(int)
                    x1 = max(0, x1 - 10)
                    y1 = max(0, y1 - 10)
                    x2 = min(image.shape[1], x2 + 10)
                    y2 = min(image.shape[0], y2 + 10)
                    if x2 <= x1 or y2 <= y1:
                        continue

                    cropped_receipt = image[y1:y2, x1:x2]
                    output_file = Path(output_path) / "{}_receipt_{}.jpg".format(
                        output_stem, len(receipt_paths) + 1
                    )
                    if output_file.exists():
                        raise FileExistsError(
                            "Refusing to overwrite an existing receipt crop: {}".format(
                                output_file
                            )
                        )
                    if not cv2.imwrite(str(output_file), cropped_receipt):
                        raise OSError(
                            "Unable to write cropped receipt: {}".format(output_file)
                        )
                    receipt_paths.append(output_file)
        except Exception as error:
            error_message = str(error)

        results.append(
            ImageCropResult(
                source_path=image_path,
                receipt_paths=tuple(receipt_paths),
                error=error_message,
            )
        )
        if verbose and log_callback is not None:
            log_callback(
                "{}: {} receipt(s) detected{}".format(
                    image_path,
                    len(receipt_paths),
                    ": {}".format(error_message) if error_message else "",
                )
            )
        if progress_callback is not None:
            progress_callback(index, len(normalized_paths), image_path)

    return tuple(results)


def crop_receipts(model_path, input_path, output_path, verbose=True):
    image_paths = [Path(path) for path in _image_paths(input_path)]
    results = crop_receipts_for_images(
        model_path, image_paths, output_path, verbose=verbose
    )
    total_detections = 0
    errors = []
    for result in results:
        total_detections += len(result.receipt_paths)
        if verbose:
            print(
                "{}: {} receipt(s) detected".format(
                    result.source_path, len(result.receipt_paths)
                )
            )
        if result.error:
            errors.append("{}: {}".format(result.source_path, result.error))

    if verbose:
        print("Number of receipts detected: {}".format(total_detections))
    if errors:
        raise RuntimeError("One or more images could not be processed:\n{}".format(
            "\n".join(errors)
        ))
    return total_detections


def resolve_path(path):
    """Resolve a path relative to PROJECT_ROOT if it looks like a project-relative path."""
    # Absolute paths are used as-is
    if os.path.isabs(path):
        return path

    # If the path exists as-is (relative to CWD), return it
    if os.path.isfile(path) or os.path.isdir(path):
        return path

    # If the path starts with a known project-relative prefix, strip it and resolve against PROJECT_ROOT
    prefix = "fuel_expensor/"
    if path.startswith(prefix):
        stripped = path[len(prefix):]
        resolved = os.path.join(PROJECT_ROOT, stripped)
        if os.path.exists(resolved):
            return resolved

    # Otherwise, try resolving relative to PROJECT_ROOT
    resolved = os.path.join(PROJECT_ROOT, path)
    return resolved if os.path.exists(resolved) else path


if __name__ == "__main__":
    # Default model: use built-in yolov8n.pt unless a custom local model exists
    default_model_path = DEFAULT_MODEL_PATH
    if not os.path.isfile(default_model_path):
        print(f"Local model '{default_model_path}' not found. Falling back to built-in '{DEFAULT_MODEL_NAME}'.")
        default_model_path = DEFAULT_MODEL_NAME

    parser = argparse.ArgumentParser(description="Receipt detection using YOLO models")
    parser.add_argument("--model", type=str, default=default_model_path, help="Path to the YOLO model (default: receipt_detector_2.pt or yolov8n.pt)")
    parser.add_argument("--input", type=str, required=True, help="Path to an input image or a directory of images")
    parser.add_argument("--output", type=str, required=True, help="Path to the output directory")
    args = parser.parse_args()

    # Resolve relative paths against PROJECT_ROOT
    model_path = resolve_path(args.model)
    input_path = resolve_path(args.input)
    output_path = resolve_path(args.output)

    crop_receipts(model_path, input_path, output_path)
