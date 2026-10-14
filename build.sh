#!/usr/bin/env bash
# Render build: install, collect static files. Migrations run at start, when the
# database is reachable and the disk is mounted.
set -euo pipefail
pip install --upgrade pip
pip install -r requirements.txt
python manage.py collectstatic --noinput
