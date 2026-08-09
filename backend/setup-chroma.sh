#!/bin/bash

# Prepare the local Chroma vector store used when VECTOR_BACKEND=chroma.
# Chroma runs embedded inside the backend process (no separate server), so
# "starting" it means making sure the store exists and passes verification.
# Safe to re-run: a healthy store is left untouched.

cd "$(dirname "$0")/chroma"

# dedicated venv, kept separate from the sciscigpt conda env
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
    ./.venv/bin/pip install --upgrade pip
    ./.venv/bin/pip install -r requirements.txt
fi

# build the collections from HuggingFace only if verification fails
if ! ./.venv/bin/python build_index.py --verify-only; then
    ./.venv/bin/python build_index.py --reset
fi

echo "Chroma store ready. Set VECTOR_BACKEND=chroma in backend/.env and restart the backend."
