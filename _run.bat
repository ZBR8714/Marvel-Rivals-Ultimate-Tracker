@echo off
setlocal

echo ============================================
echo  Marvel Rivals Ult Tracker - Launcher
echo ============================================

REM 1. Check if Python is installed
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python from https://www.python.org/downloads/
    echo IMPORTANT: During install, check "Add python.exe to PATH"
    pause
    exit /b 1
)

echo [OK] Python found.
python --version

REM 2. Check and install dependencies
echo.
echo Checking dependencies...
python -m pip show opencv-python >nul 2>nul || set MISSING=1
python -m pip show mss >nul 2>nul || set MISSING=1
python -m pip show easyocr >nul 2>nul || set MISSING=1
python -m pip show numpy >nul 2>nul || set MISSING=1
python -m pip show Pillow >nul 2>nul || set MISSING=1
python -m pip show pywin32 >nul 2>nul || set MISSING=1

if defined MISSING (
    echo Installing missing dependencies...
    python -m pip install --upgrade pip
    python -m pip install opencv-python mss easyocr numpy Pillow pywin32
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed.
        pause
        exit /b 1
    )
) else (
    echo [OK] All dependencies already installed.
)

REM 3. Run the script
echo.
echo Starting Ult Tracker...
python "%~dp0ult_tracker.py"

pause
endlocal