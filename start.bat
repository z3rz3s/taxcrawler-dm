@echo off
REM =============================================================================
REM taxcrawler-dm — Start Script (Windows)
REM =============================================================================
REM Usage:
REM   start.bat          <- starts API server + desktop UI
REM   start.bat --api    <- starts API server only
REM   start.bat --cli    <- starts CLI interactive mode
REM =============================================================================

set API_HOST=127.0.0.1
set API_PORT=8000

echo.
echo =============================================
echo  taxcrawler-dm
echo =============================================
echo.

REM -----------------------------------------------------------------------------
REM CLI mode
REM -----------------------------------------------------------------------------
if "%1"=="--cli" (
    echo Starting CLI interactive mode...
    python cli\main.py
    exit /b 0
)

REM -----------------------------------------------------------------------------
REM Start API server in background
REM -----------------------------------------------------------------------------
echo Starting API server on http://%API_HOST%:%API_PORT% ...
start /b python -m uvicorn api.main:app --host %API_HOST% --port %API_PORT% --log-level warning

REM Wait for server to be ready
echo   Waiting for server...
timeout /t 3 /nobreak >nul
echo   Server should be ready.
echo.

REM -----------------------------------------------------------------------------
REM API only mode
REM -----------------------------------------------------------------------------
if "%1"=="--api" (
    echo API running at http://%API_HOST%:%API_PORT%
    echo Docs at http://%API_HOST%:%API_PORT%/docs
    echo.
    echo Press Ctrl+C to stop.
    pause
    exit /b 0
)

REM -----------------------------------------------------------------------------
REM Start desktop UI
REM -----------------------------------------------------------------------------
echo Starting desktop UI...
python ui\main.py

echo.
echo UI closed.
echo Stopping server...
taskkill /f /im python.exe /fi "WINDOWTITLE eq uvicorn*" >nul 2>&1
echo Done.
pause