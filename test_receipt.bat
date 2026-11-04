@echo off
echo Running receipt date extraction...
py src\process_receipt_dates.py --input-dir data\processed
pause