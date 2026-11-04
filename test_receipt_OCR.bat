@echo off
setlocal
pushd "%~dp0"
echo [2_] Running receipt date extraction...
py src\process_receipt_dates.py --input data\processed
if errorlevel 1 (
    echo [2_] Receipt date extraction failed.
    popd
    pause
    exit /b 1
)
echo [2_] Receipt date extraction complete.
popd
pause