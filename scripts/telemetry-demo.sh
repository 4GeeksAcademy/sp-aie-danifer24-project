#!/bin/bash

# Script para arrancar stack de telemetría: Backend + Backoffice
# Abre DevTools Network y verifica que los eventos llegan a /api/telemetry/events

set -e

echo "🚀 Iniciando stack de telemetría..."
echo ""
echo "Servicios:"
echo "  • Backend FastAPI: http://127.0.0.1:8000"
echo "  • Backoffice: http://127.0.0.1:3001"
echo ""
echo "Instrucciones:"
echo "  1. En Backoffice, abre DevTools (F12) → Network"
echo "  2. Filtra por 'telemetry' o 'api'"
echo "  3. Navega entre secciones para ver page_view events"
echo "  4. Consulta /inventory/products para ver api_request_completed"
echo ""

# Comprobar que PostgreSQL está disponible
if ! nc -z localhost 5432 2>/dev/null; then
  echo "⚠️  PostgreSQL no está disponible en localhost:5432"
  echo "   Asegúrate de que la base de datos esté corriendo antes de continuar"
  echo ""
fi

# Comprobar dependencias
if ! command -v npm &> /dev/null; then
  echo "❌ npm no encontrado. Instala Node.js."
  exit 1
fi

if ! command -v uv &> /dev/null; then
  echo "❌ uv no encontrado. Instala uv para ejecutar FastAPI."
  exit 1
fi

# Limpiar procesos anteriores
pkill -f "next.*dev.*3001" || true
pkill -f "uvicorn" || true
sleep 1

# Iniciar Backend FastAPI en terminal 1
echo "Starting FastAPI backend..."
uv run --with-requirements services/api/requirements.txt \
  uvicorn services.api.main:app \
  --host 127.0.0.1 \
  --port 8000 \
  --reload &
BACKEND_PID=$!

# Esperar a que FastAPI esté listo
sleep 3

# Iniciar Backoffice en terminal 2
echo "Starting Backoffice..."
npm --prefix uis/backoffice run dev -- --port 3001 &
BACKOFFICE_PID=$!

# Mantener vivos los procesos
trap "kill $BACKEND_PID $BACKOFFICE_PID" EXIT

echo ""
echo "✅ Stack iniciado:"
echo "   Backend PID: $BACKEND_PID"
echo "   Backoffice PID: $BACKOFFICE_PID"
echo ""
echo "Presiona CTRL+C para detener."
echo ""

wait
