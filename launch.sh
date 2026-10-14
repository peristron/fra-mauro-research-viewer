#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
exec streamlit run streamlit_app.py
