# Workflow notes

This project follows a receipt-to-claim workflow:

1. User uploads an image containing one or more receipts.
2. System detects and isolates each receipt in the image.
3. OCR reads receipt metadata such as date and amount.
4. User selects the travel dates and workdays for each expense week.
5. The system assigns each receipt to at most one selected expense week, including a two-calendar-day margin before and after the week. If adjacent weeks qualify, it chooses the week containing the receipt date and records any other qualifying weeks as alternatives. Unmatched receipts are listed with reasons. The versioned result is written to `data/processed/receipt_matches.json`.
6. (Later) Check that each Excel document has at least one qualifying receipt and notify the user if it does not.
7. (Later) Insert expense data into the Excel template and embed associated receipt images.
8. (Later) Generate the claim.

## Step 5 receipt data

The existing OCR date step renames dated cropped images with a leading
`YYYY-MM-DD_` prefix in `data/processed/`. The matching loader reads that date
and retains images without a usable date as unmatched. Optional amount, vendor,
raw OCR text, and explicit receipt dates can be supplied using the version-1
`data/processed/receipt_manifest.json` format documented in the repository
[README](../README.md#receipt-matching-step-5).

Run the date-selection GUI with `py -m src.gui.date_selection`. Receipt
matching reruns automatically whenever a date is selected or cleared, saving
the current selection and result. Selected dates are filled green when their
week has a qualifying receipt and orange when it does not. Use **Recheck
receipts** after receipt files change while the GUI is open. Each selected week is present in the
output even when it has zero matches. The matcher uses the shared week-boundary
helpers in `src/expense_weeks.py`; it does not implement the later missing-week
notification or Excel generation steps. A brief summary, unmatched reasons,
and output path appear below the calendar.

## Current assumptions

- An uploaded image may contain multiple receipts, and a receipt image may be associated with an expense document only when its receipt date is within the expense week or within two calendar days before or after it.
- The later export workflow is expected to require at least one associated receipt for every generated Excel document.
- The later export workflow is expected to embed receipt images in generated documents.
- The missing-receipt notification policy belongs to step 6 and is not implemented in step 5.
- A settings object can store values such as home address, delta distance to work, and vehicle registration.
- The final output is an Excel fuel expense template populated with extracted expense data and receipt images.
