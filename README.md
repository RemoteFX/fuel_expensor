# Fuel Expensor

Fuel Expensor turns uploaded receipt images into a completed fuel expense Excel claim using a user-provided template and a guided workflow. Receipt matching is a core part of the application: receipts are matched to expense weeks, and qualifying receipt images are included in the generated documents.

## Workflow summary

1. User uploads an image containing one or more receipts.
2. The app detects receipt boundaries and saves each receipt as a separate image.
3. OCR extracts receipt details such as date, amount, and vendor.
4. The user selects the travel dates and workdays to expense, grouped into expense weeks.
5. The app matches receipts to each expense week. A receipt qualifies when its date falls within the week or within two calendar days before or after it.
6. The app checks that every Excel document to be generated has at least one qualifying associated receipt. It notifies the user if a document is missing a receipt.
7. The app populates the spreadsheet template with the expense data and embeds the associated receipt image(s) in the generated Excel document.
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
2. Add your local Excel template file into `data/templates/`.
3. Add a few sample receipt images into `data/test/receipts/`.
4. Start implementing the application in `src/`.

## Notes

The workflow requires at least one receipt dated within each expense week (with a two-day margin) for every generated Excel document. The user must be notified if a document has no qualifying receipt. Whether that notification blocks export is not yet specified.
