#!/usr/bin/env bash

echo ---------------------------------------------------------------------
echo Shall use Bun and Concurrently to start Vite and Uvicorn dev servers.
echo CTRL+C to quit both.
echo ---------------------------------------------------------------------

bunx concurrently -k -n api,web -c blue,green \
  "uv run --directory backend uvicorn mutatis_mutandis.api:app --app-dir src --port 8000 --reload --reload-dir src" \
  "cd frontend && bun run dev"
  