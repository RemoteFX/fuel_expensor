@echo off
echo Running receipt crop/splitting test...
py src\crop_receipts.py --input data\test\receipts --output data\processed
pause