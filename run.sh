#!/bin/bash
uv sync

uv run gunicorn \
    --workers 1 \
    --bind 0.0.0.0:8080 \
    main:app
