import argparse
import os
import cv2
from ultralytics import YOLO


def get_project_root():
    """Derive project root from script location."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def normalize_path(path, base_dir):
    """Resolve a path relative to base_dir if it's not already absolute."""
    if os.path.isabs(path):
        return os.path.normpath(path)
    return os.path.normpath(os.path.join(base_dir, path))


def crop_receipts(model_path, input_path, output_path):
    """Run YOLO inference and crop detected receipts."""
    # Resolve paths relative to project root
    model_path = normalize_path(model_path, get_project_root())
    input_path = normalize_path(input_path, get_project_root())
    output_path = normalize_path(output_path, get_project_root())

    # Validate model file exists
    if not os.path.isfile(model_path):
        raise FileNotFoundError(f"Model file not found: {model_path}")

    # Validate input image exists
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input image not found: {input_path}")

    # Load the YOLO model
    print(f"Loading model: {model_path}")
    model = YOLO(model_path)

    # Read the input image
    image = cv2.imread(input_path)
    if image is None or image.size == 0:
        print("Error: Unable to load image.")
        return

    # Run inference with consistent settings
    results = model(image, verbose=False)

    # Extract bounding boxes and crop receipts
    receipt_count = 0
    for result in results:
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            continue

        xyxy = boxes.xyxy.detach().cpu().numpy().astype(int)  # shape (N, 4)
        for (x1, y1, x2, y2) in xyxy:

            # Apply ~10 pixels of padding
            pad = 10
            x1_padded = max(0, x1 - pad)
            y1_padded = max(0, y1 - pad)
            x2_padded = min(image.shape[1], x2 + pad)
            y2_padded = min(image.shape[0], y2 + pad)

            # Ensure valid crop dimensions
            if x2_padded <= x1_padded or y2_padded <= y1_padded:
                continue

            # Crop the receipt from the original image
            cropped_receipt = image[y1_padded:y2_padded, x1_padded:x2_padded]

            # Create unique output filename using model name prefix
            model_name = os.path.splitext(os.path.basename(model_path))[0]
            if not os.path.exists(output_path):
                os.makedirs(output_path, exist_ok=True)

            existing_files = [f for f in os.listdir(output_path) if f.startswith(model_name + "_receipt_")]
            index = 1
            while True:
                filename = f"{model_name}_receipt_{index}.jpg"
                if filename not in existing_files:
                    break
                index += 1

            output_filename = os.path.join(output_path, filename)
            cv2.imwrite(output_filename, cropped_receipt)
            receipt_count += 1

    # Print summary
    print(f"Number of receipts detected: {receipt_count}")


def main():
    default_model = os.path.join(get_project_root(), "data", "models", "receipt_detector_2.pt")
    parser = argparse.ArgumentParser(description="Receipt detection using YOLO models")
    parser.add_argument("--model", type=str, default=default_model, help="Path to the .pt file (relative to project root). Default: data/models/receipt_detector_2.pt")
    parser.add_argument("--input", type=str, required=True, help="Path to the input image (relative to project root)")
    parser.add_argument("--output", type=str, required=True, help="Path to the output directory (relative to project root)")
    args = parser.parse_args()

    try:
        crop_receipts(args.model, args.input, args.output)
    except Exception as e:
        print(f"Error during processing: {e}")


if __name__ == "__main__":
    main()