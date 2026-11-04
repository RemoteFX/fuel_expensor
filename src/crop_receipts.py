import argparse
import os
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


def crop_receipts(model_path, input_path, output_path):
    # Load the YOLO model
    model = YOLO(model_path)

    # Read the input image
    image = cv2.imread(input_path)
    if image is None:
        print("Error: Unable to load image.")
        return

    # Run inference
    results = model(image)

    # Extract bounding boxes and crop receipts
    for result in results:
        boxes = result.boxes.cpu().numpy()
        for idx, box in enumerate(boxes):
            xyxy = box.xyxy[0]
            if hasattr(xyxy, "cpu"):
                xyxy = xyxy.cpu().numpy()
            x1, y1, x2, y2 = xyxy.astype(int)
            x1 = max(0, x1 - 10)
            y1 = max(0, y1 - 10)
            x2 = min(image.shape[1], x2 + 10)
            y2 = min(image.shape[0], y2 + 10)

            # Crop the receipt
            cropped_receipt = image[y1:y2, x1:x2]
            output_filename = f"{output_path}/{model_path.split('/')[-1].split('.')[0]}_receipt_{idx + 1}.jpg"
            cv2.imwrite(output_filename, cropped_receipt)

    total_detections = 0
    for result in results:
        if result.boxes is not None:
            total_detections += len(result.boxes)
    print(f"Number of receipts detected: {total_detections}")


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
    parser.add_argument("--input", type=str, required=True, help="Path to the input image")
    parser.add_argument("--output", type=str, required=True, help="Path to the output directory")
    args = parser.parse_args()

    # Resolve relative paths against PROJECT_ROOT
    model_path = resolve_path(args.model)
    input_path = resolve_path(args.input)
    output_path = resolve_path(args.output)

    crop_receipts(model_path, input_path, output_path)
