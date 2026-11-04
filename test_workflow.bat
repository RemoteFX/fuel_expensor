@echo off
setlocal
pushd "%~dp0"

echo [1_] Cropping receipts from data\test\receipts...
if not exist data\processed mkdir data\processed
py src\crop_receipts.py --input data\test\receipts --output data\processed
if errorlevel 1 goto workflow_failed
echo [1_] Receipt cropping complete.
echo.

echo [2_] Extracting receipt dates from data\processed...
py src\process_receipt_dates.py --input data\processed
if errorlevel 1 goto workflow_failed
echo [2_] Receipt date extraction complete.
echo.
echo Workflow completed successfully.
popd
pause
exit /b 0

:workflow_failed
echo Workflow failed. See the error above.
popd
pause
exit /b 1
