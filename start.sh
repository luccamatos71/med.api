#!/bin/sh
set -e

echo "Running migrations..."
for i in 1 2 3 4 5; do
  /app/.venv/bin/alembic upgrade head && break
  echo "Migration attempt $i failed, retrying in 5s..."
  sleep 5
done

echo "Starting server..."
exec /app/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
