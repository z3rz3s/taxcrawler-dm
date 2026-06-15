#!/bin/bash
# mensual-docs.sh — Descarga documentos SAT (CSF) para todos los clientes
# Ejecuta clients.py docs, copia PDFs a reportes/ y registra en log.
#
# Llamado por n8n el día 1 de cada mes a las 7:00 AM.
# También se puede ejecutar manualmente: ./mensual-docs.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Mes actual (los documentos se descargan ahora, no del mes anterior)
MES=$(date '+%Y-%m' 2>/dev/null || date -d 'now' '+%Y-%m')

LOG_DIR="$HOME/despacho-roy/logs"
REPORTES_DIR="$HOME/despacho-roy/reportes"
LOG_FILE="$LOG_DIR/n8n_docs_${MES}.log"

mkdir -p "$LOG_DIR" "$REPORTES_DIR"

{
    echo "=============================================="
    echo "INICIO DOCS: $(date '+%Y-%m-%d %H:%M:%S') — $MES"
    echo "=============================================="
    echo ""

    # ── Descargar documentos para todos los clientes ──
    python3.13 clients.py docs
    EXIT=$?

    echo ""
    echo "--- Copiando PDFs a reportes/ ---"
    echo ""

    # Copiar PDFs de documentos SAT
    COPIADOS=0
    for pdf in results_*/documentos_sat/*.pdf; do
        [ -f "$pdf" ] || continue
        RFC=$(basename "$(dirname "$(dirname "$pdf")")" | sed 's/results_//')
        DEST="$REPORTES_DIR/$RFC/$MES"
        mkdir -p "$DEST"
        cp "$pdf" "$DEST/"
        echo "  📄 $RFC → $DEST/$(basename "$pdf")"
        COPIADOS=$((COPIADOS + 1))
    done

    if [ $COPIADOS -eq 0 ]; then
        echo "  ⚠️  No se encontraron PDFs para copiar."
    fi

    echo ""
    echo "=============================================="
    echo "FIN DOCS: $(date '+%Y-%m-%d %H:%M:%S') — exit=$EXIT, pdfs=$COPIADOS"
    echo "=============================================="
} >> "$LOG_FILE" 2>&1

echo "✅ Documentos SAT descargados. Log: $LOG_FILE"
exit 0
