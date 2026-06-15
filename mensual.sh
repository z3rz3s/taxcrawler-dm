#!/bin/bash
# mensual.sh — Flujo mensual automatizado para taxcrawler-dm
# Ejecuta clients.py run-all para el mes anterior, copia Excels a reportes/
# y registra todo en un log.
#
# Llamado por n8n el día 5 de cada mes a las 8:00 AM.
# También se puede ejecutar manualmente: ./mensual.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Calcular mes anterior (funciona en macOS y Linux)
MES=$(date -v-1m '+%Y-%m' 2>/dev/null || date -d '1 month ago' '+%Y-%m')

LOG_DIR="$HOME/despacho-roy/logs"
REPORTES_DIR="$HOME/despacho-roy/reportes"
LOG_FILE="$LOG_DIR/n8n_${MES}.log"

mkdir -p "$LOG_DIR" "$REPORTES_DIR"

{
    echo "=============================================="
    echo "INICIO: $(date '+%Y-%m-%d %H:%M:%S') — Mes: $MES"
    echo "=============================================="
    echo ""

    # ── Ejecutar flujo completo ──
    python3.13 clients.py run-all --mes "$MES" --intervalo 30
    EXIT=$?

    echo ""
    echo "--- Copiando Excels a reportes/ ---"
    echo ""

    # Buscar y copiar Excels generados (técnico y cliente)
    COPIADOS=0
    for excel in results_*/*_${MES}.xlsx results_*/*_${MES}_cliente.xlsx; do
        [ -f "$excel" ] || continue
        RFC=$(basename "$(dirname "$excel")" | sed 's/results_//')
        DEST="$REPORTES_DIR/$RFC/$MES"
        mkdir -p "$DEST"
        cp "$excel" "$DEST/"
        echo "  ✅ $RFC → $DEST/$(basename "$excel")"
        COPIADOS=$((COPIADOS + 1))
    done

    # Buscar y copiar PDFs de documentos SAT (CSF, Opinión)
    DOCS_COPIADOS=0
    for pdf in results_*/documentos_sat/*.pdf; do
        [ -f "$pdf" ] || continue
        RFC=$(basename "$(dirname "$(dirname "$pdf")")" | sed 's/results_//')
        DEST="$REPORTES_DIR/$RFC/$MES"
        mkdir -p "$DEST"
        cp "$pdf" "$DEST/"
        echo "  📄 $RFC → $DEST/$(basename "$pdf")"
        DOCS_COPIADOS=$((DOCS_COPIADOS + 1))
    done

    if [ $COPIADOS -eq 0 ] && [ $DOCS_COPIADOS -eq 0 ]; then
        echo "  ⚠️  No se encontraron Excels ni PDFs para copiar."
    fi

    echo ""
    echo "=============================================="
    echo "FIN: $(date '+%Y-%m-%d %H:%M:%S') — exit=$EXIT, excels=$COPIADOS, docs=$DOCS_COPIADOS"
    echo "=============================================="
} >> "$LOG_FILE" 2>&1

echo "✅ Flujo mensual completado. Log: $LOG_FILE"
exit 0
