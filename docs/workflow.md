# Workflow notes

This project follows a receipt-to-claim workflow:

1. User uploads an image containing one or more receipts.
2. System detects and isolates each receipt in the image.
3. OCR reads receipt metadata such as date and amount.
4. User selects the travel dates and workdays for each expense week.
5. For each Excel document to be generated, the system associates at least one receipt dated within that expense week, including a two-calendar-day margin before and after the week.
6. The system notifies the user if any document has no qualifying receipt.
7. The expense data is inserted into the Excel template, and the associated receipt image(s) are embedded in the generated Excel document.
8. The claim is generated.

## Current assumptions

- An uploaded image may contain multiple receipts, and a receipt image may be associated with an expense document only when its receipt date is within the expense week or within two calendar days before or after it.
- Every generated Excel document must have at least one associated receipt.
- Receipt images associated with a document are embedded in that Excel document, not merely referenced or stored separately.
- The user must be notified whenever a document is missing a qualifying receipt.
- A settings object can store values such as home address, delta distance to work, and vehicle registration.
- The final output is an Excel fuel expense template populated with extracted expense data and receipt images.
