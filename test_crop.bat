@echo off
setlocal
pushd "%~dp0"
for /f %%i in ('powershell -NoProfile -Command "[guid]::NewGuid().ToString('N')"') do set "RUN_ID=%%i"
set "OUTPUT_DIR=data\uploads\crop_%RUN_ID%"
echo [1_] Running receipt crop/splitting...
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"
py src\crop_receipts.py --input data\test\receipts --output "%OUTPUT_DIR%"
if errorlevel 1 (
    echo [1_] Receipt cropping failed.
    popd
    pause
    exit /b 1
)
echo [1_] Receipt cropping complete.
popd
pause