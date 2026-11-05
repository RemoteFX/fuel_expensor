# Fuel Expensor

Fuel Expensor processes receipt images through a guided expense workflow. The current workflow detects receipts, extracts dates, lets the user select expense dates, and matches receipts to the selected weeks. Excel generation and image embedding are later workflow steps and are not implemented yet.

## Workflow summary

1. The user selects one or more receipt photos in the GUI (or supplies a file/directory to the command-line cropper).
2. The app detects receipt boundaries and saves each receipt as a separate image in a unique processing job.
3. OCR extracts a date from each crop; dates are associated with receipt images through their ISO filename prefix. Amount and vendor extraction are not implemented.
4. The user selects the travel dates and workdays to expense, grouped into expense weeks.
5. The app assigns each receipt to at most one selected expense week. A receipt qualifies when its date falls within the week or within two calendar days before or after it. If adjacent weeks qualify, the week containing the receipt date is chosen; alternate qualifying weeks are recorded without duplicating the receipt.
6. Weeks without a qualifying receipt are warned about and are not eligible for a future expense form. Excel generation is not implemented yet.
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

The OCR date-extraction step stores its result in each cropped image's
filename: successfully dated images begin with `YYYY-MM-DD_`, for example
`2025-04-02_shop_receipt_1.jpg`. These images in `data/processed/` are the
matching input. Images without a valid date prefix are retained and appear in
the unmatched list. The current OCR step does not persist amount, vendor, or
raw OCR text.

The GUI's **Add Receipt Photos** action accepts multiple images and runs
detection/OCR in a background worker. Each run writes to a separate directory
under `data/processed/jobs/`; interrupted jobs retain an `.incomplete` marker
and are ignored by receipt loading. Job directories remain as an archive, but
the GUI matches only jobs created during the current application run; previous
jobs are never automatically reused. Each launch starts with an empty date
selection and replaces the saved selection and match result, preventing a
previous period from being picked up by a later workflow. To launch the GUI
against a particular processed-receipt directory, use
`py -m src.gui.date_selection --receipts-dir <path>`.

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
The processing workflow may also store `date_error` for a crop whose date
could not be read, so later matching can distinguish that from an unprocessed
image.

Receipt status is recalculated immediately whenever a date is selected or
cleared. Selected dates are filled green when their week has a qualifying
receipt, or orange when it does not; the recheck button can be used after
receipt files change while the GUI is open. Weeks without receipts are
identified in the matching status and warned about when the selection is
submitted; a future expense-form generator must omit those weeks. Matching reads
`data/processed/expense_week_selection.json` and the processed receipt images,
then writes the version-1 result to
`data/processed/receipt_matches.json`. Each selected week remains in the result,
including weeks with zero matches. Dates are compared inclusively from two
days before the Monday-based week through two days after its Sunday; receipts
that qualify for adjacent weeks are assigned only once, preferring the week
that contains the receipt date. Other qualifying weeks are listed in
`overlaps_weeks` as alternatives and do not contain a duplicate receipt.
Missing/invalid dates and dated receipts outside every selected week are
recorded in `unmatched_receipts`. A brief per-week summary, unmatched reasons,
and output path appear below the calendar; matching no longer opens a results
dialog. The GUI's **Save Selection** action saves the current selection; it
does not submit a claim or generate an Excel file.

The match result is structured for later consumers: each week includes its
`week_id`, dates, `receipt_count`, receipt amounts, and image paths. The GUI
warns about zero-receipt weeks; `MatchResult.expense_form_weeks` exposes only
weeks eligible for a future expense form. Excel/image generation is not
implemented.

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
