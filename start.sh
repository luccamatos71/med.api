#!/bin/sh

echo "Running migrations..."
MIGRATED=0
for i in 1 2 3 4 5; do
  if /app/.venv/bin/alembic upgrade head; then
    MIGRATED=1
    break
  fi
  echo "Migration attempt $i failed, retrying in 5s..."
  sleep 5
done

if [ "$MIGRATED" = "0" ]; then
  echo "Migrations failed after 5 attempts, starting server anyway..."
fi

echo "Starting server..."
exec /app/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
