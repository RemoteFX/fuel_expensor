# Fuel Expensor

Fuel Expensor is a tool for turning uploaded receipt images into a completed fuel expense Excel claim using a user-provided template and a simple guided workflow.

## Workflow summary

1. User uploads an image containing one or more receipts.
2. The app detects receipt boundaries and saves each receipt as a separate image.
3. OCR extracts receipt details such as date, amount, and vendor.
4. The user selects the date ranges and workdays to expense.
5. The app populates the spreadsheet template and exports the claim.

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

## Tesseract OCR installation

This project uses Tesseract for OCR. Install it before running the script:

- **Windows:** Download from https://github.com/UB-Mannheim/tesseract/wiki, then add the `tesseract.exe` directory to your system `PATH`.
- **Linux/macOS:** `sudo apt install tesseract-ocr` or `brew install tesseract`.

Verify installation with:

```bash
py -m pytesseract --version
```

## Notes

This repo currently contains the project skeleton only. The app logic and tests will be added next.
