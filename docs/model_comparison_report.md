# YOLO Receipt Detection Model Comparison Report

## Executive Summary

Two pretrained YOLO models were evaluated against two test images. **`receipt_detector_2.pt`** is the winner and has been configured as the default model in `src/crop_receipts.py`.

## Test Configuration

- **Application**: `src/crop_receipts.py` (Ultralytics YOLO + OpenCV)
- **Test Images**:
  - `IMG_6448.jpeg` — Expected: **4** receipts
  - `IMG_6449.jpeg` — Expected: **1** receipt
- **Models Tested**:
  - `receipt_detector.pt` (Model 1)
  - `receipt_detector_2.pt` (Model 2)

## Results

| Model                   | IMG_6448.jpeg       | IMG_6449.jpeg      | Status   |
| ----------------------- | ------------------- | ------------------ | -------- |
| `receipt_detector.pt`   | 0 detections ❌     | 1 detection ✅     | **FAIL** |
| `receipt_detector_2.pt` | **4 detections** ✅ | **1 detection** ✅ | **PASS** |

## Winner

**`receipt_detector_2.pt`** — Perfect accuracy on both test images.

## Application Changes

- Default model path set to `fuel_expensor/data/models/receipt_detector_2.pt`
- `--model` argument removed; only `--input` and `--output` remain
- Detection count now correctly reports total boxes across all result frames

## Final Verification

```
$ py src/crop_receipts.py --input fuel_expensor/data/test/receipts/IMG_6448.jpeg --output fuel_expensor/data/uploads
0: 480x640 4 papers, 66.2ms
Number of receipts detected: 4

$ py src/crop_receipts.py --input fuel_expensor/data/test/receipts/IMG_6449.jpeg --output fuel_expensor/data/uploads
0: 320x640 1 paper, 55.3ms
Number of receipts detected: 1
```

## Usage

From PowerShell:

```powershell
# Run on a single image (default model: receipt_detector_2.pt)
py src/crop_receipts.py --input fuel_expensor\data\test\receipts\IMG_6448.jpeg --output fuel_expensor\data\uploads

# Point to any image and output folder
py src/crop_receipts.py --input C:\path\to\your\image.jpg --output C:\path\to\output\folder
```

Each detected receipt becomes its own cropped JPG in the output folder.

## Generated Crops

Located in `fuel_expensor/data/uploads/`:

- `receipt_detector_2_receipt_2.jpg` — IMG_6448 crop 1
- `receipt_detector_2_receipt_3.jpg` — IMG_6448 crop 2
- `receipt_detector_2_receipt_4.jpg` — IMG_6448 crop 3
- `receipt_detector_2_receipt_5.jpg` — IMG_6448 crop 4
- `receipt_detector_2_receipt_6.jpg` — IMG_6449 crop 1

---

_Report generated: 2026-11-02_
