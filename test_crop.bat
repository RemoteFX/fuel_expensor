@echo off
setlocal
pushd "%~dp0"
echo [1_] Running receipt crop/splitting...
if not exist data\processed mkdir data\processed
py src\crop_receipts.py --input data\test\receipts --output data\processed
if errorlevel 1 (
    echo [1_] Receipt cropping failed.
    popd
    pause
    exit /b 1
)
echo [1_] Receipt cropping complete.
popd
pause