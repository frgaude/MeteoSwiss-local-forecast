#!/bin/sh
# Container entry point (see nas/compose.yaml): update the code, install the
# Python packages into a venv kept in the dataset (fast when nothing changed;
# restart the app after changing requirements.txt), then run the render loop.
set -e
cd "$(dirname "$0")/.."
git pull --ff-only -q || echo "git pull failed, using the code as it is"
[ -x .venv-nas/bin/python ] || python -m venv .venv-nas
.venv-nas/bin/pip install -q --disable-pip-version-check -r requirements.txt \
  || { echo "pip install failed, retrying in 10 min"; sleep 600; exit 1; }
echo "starting the render loop"
exec .venv-nas/bin/python nas/publish.py
