# Workflow notes

This project follows a simple receipt-to-claim workflow:

1. User uploads an image containing multiple receipts.
2. System detects each receipt in the image and isolates it.
3. OCR reads receipt metadata such as date and amount.
4. User selects travel dates and workdays.
5. The expense data is inserted into the Excel template and a claim is generated.

## Current assumptions

- The app may process multiple receipts from a single uploaded image.
- A settings object can store values such as home address, delta distance to work, and vehicle registration.
- The final output is an Excel fuel expense template populated using the extracted receipt data.
