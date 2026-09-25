#!/usr/bin/env bash
set -e
pip install -r requirements.txt
exec gunicorn main:app --workers 2 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8000}
