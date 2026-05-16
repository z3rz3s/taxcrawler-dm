"""
api/main.py
-----------
Aplicacion FastAPI de taxcrawler-dm.
Expone los servicios de core/ a traves de endpoints HTTP.
Todas las rutas llaman a services/ unicamente — nunca a core/ directamente.

Iniciar el servidor:
  uvicorn api.main:app --reload
  uvicorn api.main:app --host 0.0.0.0 --port 8000

Documentacion interactiva:
  http://localhost:8000/docs
  http://localhost:8000/redoc
"""

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Raiz del proyecto — necesaria para resolver imports de core/ y services/
# ---------------------------------------------------------------------------
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# ---------------------------------------------------------------------------
# Dependencias locales — libs/ tiene prioridad sobre el sistema
# ---------------------------------------------------------------------------
_libs = _root / "libs"
if _libs.exists() and str(_libs) not in sys.path:
    sys.path.insert(0, str(_libs))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import cache, download, excel

app = FastAPI(
    title="taxcrawler-dm API",
    description=(
        "API para descarga masiva de CFDI del SAT y generacion de Papel de Trabajo. "
        "Todos los endpoints llaman a services/ — la logica de negocio esta en core/."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# CORS — permite acceso desde la UI local (CustomTkinter no lo necesita,
# pero si se accede desde un browser en desarrollo)
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:8080"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
app.include_router(download.router, prefix="/download", tags=["Download"])
app.include_router(excel.router,    prefix="/excel",    tags=["Excel"])
app.include_router(cache.router,    prefix="/cache",    tags=["Cache"])


@app.get("/", tags=["Health"])
def root():
    """Verificacion rapida de que el servidor esta activo."""
    return {"status": "ok", "service": "taxcrawler-dm API", "version": "1.0.0"}


@app.get("/health", tags=["Health"])
def health():
    """Health check para monitoreo."""
    return {"status": "healthy"}