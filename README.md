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
2. Add your local Excel template file into `data/templates/`.
3. Add a few sample receipt images into `data/test/receipts/`.
4. Start implementing the application in `src/`.

## Notes

This repo currently contains the project skeleton only. The app logic and tests will be added next.
