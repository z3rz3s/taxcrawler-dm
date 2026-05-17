@echo off
REM =============================================================================
REM taxcrawler-dm — Installation Script (Windows)
REM =============================================================================
REM Usage:
REM   Double-click install.bat
REM   OR run from Command Prompt: install.bat
REM
REM What this does:
REM   1. Checks Python is available
REM   2. Installs all dependencies into .\libs (no virtualenv required)
REM   3. Installs uvicorn system-wide (needed to run the server)
REM   4. Creates .env from .env.example with a placeholder SAT_CACHE_SALT
REM =============================================================================

echo.
echo =============================================
echo  taxcrawler-dm -- Installation
echo =============================================
echo.

REM -----------------------------------------------------------------------------
REM Check Python
REM -----------------------------------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Download it from: https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('python --version') do echo Python: %%v
echo.

REM -----------------------------------------------------------------------------
REM Install dependencies into .\libs
REM -----------------------------------------------------------------------------
echo Installing dependencies into .\libs ...
python -m pip install ^
    cfdiclient ^
    openpyxl ^
    python-dotenv ^
    cryptography ^
    fastapi ^
    uvicorn ^
    customtkinter ^
    requests ^
    --target .\libs ^
    --quiet

if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)
echo   Dependencies installed.
echo.

REM -----------------------------------------------------------------------------
REM Install uvicorn system-wide
REM -----------------------------------------------------------------------------
echo Installing uvicorn system-wide ...
python -m pip install uvicorn --quiet
echo   uvicorn installed.
echo.

REM -----------------------------------------------------------------------------
REM Create .env from .env.example
REM -----------------------------------------------------------------------------
if not exist .env (
    if exist .env.example (
        copy .env.example .env >nul
        echo Created .env from .env.example
    ) else (
        type nul > .env
        echo Created empty .env
    )
    echo.
    echo   IMPORTANT: Open .env and set SAT_CACHE_SALT to a random secret value.
    echo   Example: SAT_CACHE_SALT=my_very_secret_random_value_here
    echo   You can generate one at: https://www.random.org/strings/
    echo.
) else (
    echo .env already exists -- skipping.
)
echo.

REM -----------------------------------------------------------------------------
REM Done
REM -----------------------------------------------------------------------------
echo =============================================
echo  Installation complete.
echo =============================================
echo.
echo To start the application:
echo   start.bat
echo.
echo To use the CLI directly:
echo   python cli\main.py --help
echo.
pause