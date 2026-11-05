@echo off
setlocal
pushd "%~dp0"
for /f %%i in ('powershell -NoProfile -Command "[guid]::NewGuid().ToString('N')"') do set "RUN_ID=%%i"
set "RUN_DIR=data\processed\workflow_%RUN_ID%"

echo [1_] Cropping receipts from data\test\receipts into %RUN_DIR%...
mkdir "%RUN_DIR%"
echo Processing has not completed.>"%RUN_DIR%\.incomplete"
py src\crop_receipts.py --input data\test\receipts --output "%RUN_DIR%"
if errorlevel 1 goto workflow_failed
echo [1_] Receipt cropping complete.
echo.

echo [2_] Extracting receipt dates from %RUN_DIR%...
py src\process_receipt_dates.py --input-dir "%RUN_DIR%"
if errorlevel 1 goto workflow_failed
del "%RUN_DIR%\.incomplete"
echo [2_] Receipt date extraction complete.
echo.

echo [3_] Starting the date-selection GUI...
py -m src.gui.date_selection --receipts-dir "%RUN_DIR%"
if errorlevel 1 goto workflow_failed
echo [3_] Date-selection GUI closed.
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
