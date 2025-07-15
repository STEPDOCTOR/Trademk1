#!/bin/bash
set -e

echo "Waiting for PostgreSQL to be ready..."
/app/docker/wait-for-it.sh db:5432 -t 30 -s -- echo "PostgreSQL is ready!"

echo "Running database migrations..."
alembic upgrade head

echo "Starting FastAPI application..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload