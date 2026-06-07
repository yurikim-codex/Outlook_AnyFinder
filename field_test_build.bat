@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo OutLook AnyFinder field-test release build
echo ============================================================
echo.
echo Build mode : onedir package recommended for internal testing
echo Output     : release\OutLookAnyFinder_v0.9.1_YYYYMMDD_HHMM.zip
echo.

set PY_CMD=
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py -3 --version >nul 2>nul
    if %ERRORLEVEL% EQU 0 set PY_CMD=py -3
)

if "%PY_CMD%"=="" (
    where python >nul 2>nul
    if %ERRORLEVEL% EQU 0 set PY_CMD=python
)

if "%PY_CMD%"=="" (
    echo Python was not found.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo Make sure to check "Add python.exe to PATH" during installation.
    pause
    exit /b 1
)

echo Using Python command: %PY_CMD%
%PY_CMD% build_exe.py

if errorlevel 1 (
    echo.
    echo ============================================================
    echo BUILD FAILED
    echo If the log shows "No module named pip", run:
    echo   py -3 -m ensurepip --upgrade
    echo   py -3 -m pip install --upgrade pip
    echo   py -3 -m pip install -r requirements.txt pyinstaller
    echo Then run this file again.
    echo ============================================================
    pause
    exit /b 1
)

echo.
echo ============================================================
echo BUILD COMPLETED
echo Send the generated ZIP file in the release folder to testers.
echo ============================================================
pause
endlocal
