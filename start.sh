#!/bin/bash
PORT=${PORT:-8501}
echo "Starting Polymarket Scanner on 0.0.0.0:${PORT}"
exec gunicorn --bind "0.0.0.0:${PORT}" --workers 1 --timeout 120 app:app
