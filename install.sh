#!/bin/bash
# =============================================================================
# taxcrawler-dm — Installation Script (Mac/Linux)
# =============================================================================
# Usage:
#   chmod +x install.sh
#   ./install.sh
#
# What this does:
#   1. Checks Python 3 is available
#   2. Installs all dependencies into ./libs (no virtualenv required)
#   3. Installs uvicorn system-wide (needed to run the server)
#   4. Installs tkinter if missing (required for the desktop UI)
#   5. Creates .env from .env.example with a generated SAT_CACHE_SALT
# =============================================================================

set -e

echo ""
echo "============================================="
echo " taxcrawler-dm — Installation"
echo "============================================="
echo ""

# -----------------------------------------------------------------------------
# Check Python 3
# -----------------------------------------------------------------------------
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed."
    echo "Download it from: https://www.python.org/downloads/"
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo "Python: $PYTHON_VERSION"
echo ""

# -----------------------------------------------------------------------------
# Install dependencies into ./libs
# -----------------------------------------------------------------------------
echo "Installing dependencies into ./libs ..."
python3 -m pip install \
    cfdiclient \
    openpyxl \
    python-dotenv \
    cryptography \
    fastapi \
    uvicorn \
    customtkinter \
    requests \
    --target ./libs \
    --break-system-packages \
    --quiet

echo "  Dependencies installed."
echo ""

# -----------------------------------------------------------------------------
# Install uvicorn system-wide (needed for python3 -m uvicorn)
# -----------------------------------------------------------------------------
echo "Installing uvicorn system-wide ..."
python3 -m pip install uvicorn --break-system-packages --quiet
echo "  uvicorn installed."
echo ""

# -----------------------------------------------------------------------------
# Check tkinter (required for desktop UI)
# -----------------------------------------------------------------------------
if ! python3 -c "import tkinter" 2>/dev/null; then
    echo "tkinter not found. Installing ..."
    if command -v brew &> /dev/null; then
        PYTHON_MINOR=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        brew install python-tk@${PYTHON_MINOR} 2>/dev/null || brew install python-tk
        echo "  tkinter installed via Homebrew."
    else
        echo ""
        echo "  WARNING: Homebrew not found. Install it first:"
        echo "  https://brew.sh"
        echo "  Then run: brew install python-tk"
        echo ""
        echo "  The CLI and API will work without tkinter."
        echo "  The desktop UI (ui/main.py) requires tkinter."
    fi
else
    echo "tkinter: already available."
fi
echo ""

# -----------------------------------------------------------------------------
# Create .env from .env.example
# -----------------------------------------------------------------------------
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "Created .env from .env.example"
    else
        touch .env
        echo "Created empty .env"
    fi

    # Generate a random SAT_CACHE_SALT
    if command -v openssl &> /dev/null; then
        SALT=$(openssl rand -base64 32)
        echo "SAT_CACHE_SALT=$SALT" >> .env
        echo "  SAT_CACHE_SALT generated automatically."
    else
        echo "  WARNING: openssl not found. Set SAT_CACHE_SALT manually in .env"
        echo "  SAT_CACHE_SALT=" >> .env
    fi
else
    echo ".env already exists — skipping."
fi
echo ""

# -----------------------------------------------------------------------------
# Done
# -----------------------------------------------------------------------------
echo "============================================="
echo " Installation complete."
echo "============================================="
echo ""
echo "To start the application:"
echo "  ./start.sh"
echo ""
echo "To use the CLI directly:"
echo "  python3 cli/main.py --help"
echo ""