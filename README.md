# Fuel Expensor

Fuel Expensor processes receipt images through a guided expense workflow. The current workflow detects receipts, extracts dates, lets the user select expense dates, and matches receipts to the selected weeks. Excel generation and image embedding are later workflow steps and are not implemented yet.

## Workflow summary

1. User uploads an image containing one or more receipts.
2. The app detects receipt boundaries and saves each receipt as a separate image.
3. OCR extracts receipt details such as date, amount, and vendor.
4. The user selects the travel dates and workdays to expense, grouped into expense weeks.
5. The app matches receipts to each selected expense week. A receipt qualifies when its date falls within the week or within two calendar days before or after it. Overlapping matches are retained for every qualifying week.
6. (Later) Check that every Excel document to be generated has at least one qualifying associated receipt and notify the user if one does not.
7. (Later) Populate the spreadsheet template and embed associated receipt images.
8. The completed claim is exported.

## Repository structure

- `src/` - application code
- `tests/` - automated tests and fixtures
- `data/` - local development data and user-uploaded files
- `docs/` - planning and workflow notes

## Local-only data

The following folders are intended for local development only and are ignored by git:

- `data/templates/` - place your Excel template files here
- `data/uploads/` - uploaded receipt images before processing
- `data/test/receipts/` - sample test receipts and fixtures
- `data/processed/` - generated output files

Do not commit actual Excel templates or receipt images.

## Getting started

1. Clone the repo.
2. Install Python dependencies:

   ```bash
   py -m pip install -r requirements.txt
   ```

   This installs `pytesseract` and `Pillow`. **Tesseract OCR** must also be installed separately (see below).

3. Add your local Excel template file into `data/templates/`.
4. Add a few sample receipt images into `data/test/receipts/`.
5. Start implementing the application in `src/`.

## Receipt matching (step 5)

The OCR date-extraction step currently stores its result in each cropped image's
filename: successfully dated images begin with `YYYY-MM-DD_`, for example
`2025-04-02_shop_receipt_1.jpg`. These images in `data/processed/` are the
matching input. Images without a valid date prefix are retained and appear in
the unmatched list. The current OCR step does not persist amount, vendor, or
raw OCR text.

An optional `data/processed/receipt_manifest.json` can provide additional
receipt metadata or an explicit date. Its version-1 shape is:

```json
{
  "version": 1,
  "receipts": [
    {
      "receipt_id": "shop-receipt-1",
      "image_path": "2025-04-02_shop_receipt_1.jpg",
      "receipt_date": "2025-04-02",
      "amount": "42.10",
      "vendor": "Shop",
      "raw_ocr_text": "Paid 42.10"
    }
  ]
}
```

Manifest image paths may be absolute or relative to `data/processed/`.
`receipt_id` is optional (the image filename is used by default), as are
`receipt_date`, `amount`, `vendor`, and `raw_ocr_text`. If no manifest is
present, filename dates are used and the other fields remain empty.

Choose **Match receipts** in the GUI to save the dates currently selected and run matching.
If no dates are currently selected, it uses the previously saved selection. It reads
`data/processed/expense_week_selection.json` and the processed receipt images,
then writes the version-1 result to
`data/processed/receipt_matches.json`. Each selected week remains in the result,
including weeks with zero matches. Dates are compared inclusively from two
days before the Monday-based week through two days after its Sunday; receipts
that qualify for adjacent weeks are included in both and list the other week
IDs in `overlaps_weeks`. The selected calendar dates get a green outline when
their week has a qualifying receipt and an orange outline when it has none.
Missing/invalid dates and dated receipts outside every selected week are
recorded in `unmatched_receipts`. A brief per-week summary, unmatched reasons,
and output path appear below the calendar; matching no longer opens a results
dialog.

The match result is structured for later consumers: each week includes its
`week_id`, dates, `receipt_count`, receipt amounts, and image paths. Step 6's
missing-receipt notification policy and step 7's Excel/image generation are not
implemented by this step.

## Tesseract OCR installation

This project uses Tesseract for OCR. Install it before running the script:

- **Windows:** Download from https://github.com/UB-Mannheim/tesseract/wiki, then add the `tesseract.exe` directory to your system `PATH`.
- **Linux/macOS:** `sudo apt install tesseract-ocr` or `brew install tesseract`.

Verify installation with:

```bash
py -m pytesseract --version
```

## Notes

The workflow requires at least one receipt dated within each expense week (with a two-day margin) for every generated Excel document. The user must be notified if a document has no qualifying receipt. Whether that notification blocks export is not yet specified.
