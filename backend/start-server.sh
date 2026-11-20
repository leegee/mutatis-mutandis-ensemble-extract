#!/usr/bin/env bash

uv run --directory backend uvicorn mutatis_mutandis.fast_api.api:app --app-dir src --port 8000 --reload --reload-dir src
