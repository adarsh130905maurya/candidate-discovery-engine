@echo off
title Candidate Discovery Engine
cd /d "%~dp0"
cls

echo ============================================================
echo   INTELLIGENT CANDIDATE DISCOVERY ENGINE
echo ============================================================
echo.

REM --- Check if CSV already exists ---
if exist "output\team_ai_rankers.csv" (
    echo [OK] Found existing results: output\team_ai_rankers.csv
    echo      Skipping backend pipeline. To re-run it manually:
    echo      python src/main.py
    echo.
) else (
    echo [!] No results CSV found. Running the backend pipeline...
    echo     This will take a few minutes on CPU.
    echo.
    python src/main.py
    if %errorlevel% neq 0 (
        echo.
        echo [ERROR] Pipeline failed. Make sure you ran:
        echo         pip install -r requirements.txt
        pause
        exit /b 1
    )
)

REM --- Kill any stale server on port 8000 ---
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000.*LISTENING" 2^>nul') do (
    taskkill /PID %%a /F >nul 2>&1
)

echo Starting local web server on port 8000...
start /b python -m http.server 8000 >nul 2>&1
timeout /t 2 >nul

echo Opening dashboard in browser...
start http://localhost:8000/dashboard.html

echo.
echo ============================================================
echo   Dashboard is live at:
echo   http://localhost:8000/dashboard.html
echo.
echo   Data loads automatically from output\team_ai_rankers.csv
echo   Keep this window open. Press Ctrl+C to stop.
echo ============================================================
pause
