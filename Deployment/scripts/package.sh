#!/usr/bin/env bash
# Builds the deployable web app package: build/webapp.zip
#
#   Deployment/scripts/package.sh            app code only (dependencies installed by the platform)
#   Deployment/scripts/package.sh --vendor   app code + every Python library (Linux x64, Python 3.12) in .packages
#   Deployment/scripts/package.sh --help
#
# The package contains the Django app (Code/webapp), the `advancesearch` package (Code/core), the default
# configuration (Config/) and the collected static files (run-from-package is read-only, so nothing can be
# built on the server). With --vendor no remote build is needed (Deployment/scripts/deploy_code_arm.sh).
# Uses tar and Python only (no rsync), so it runs in Azure Cloud Shell and in a Codespace.
# Environment: PYTHON (default python3).
set -euo pipefail

VENDOR=0
case "${1:-}" in
  --vendor) VENDOR=1 ;;
  -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
  "") ;;
  *) echo "Unknown option $1 (see --help)" >&2; exit 1 ;;
esac

PY="$(command -v "${PYTHON:-python3}")" || { echo "Python not found: ${PYTHON:-python3}" >&2; exit 1; }
PY="$(cd "$(dirname "$PY")" && pwd)/$(basename "$PY")"
PIP_TARGET_FLAGS=(--quiet --disable-pip-version-check --only-binary=:all: --implementation cp --python-version 3.12
  --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 --upgrade)

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD="$ROOT/build"
STAGE="$BUILD/webapp"
rm -rf "$BUILD" && mkdir -p "$STAGE"

# tar instead of rsync so this also runs in Azure Cloud Shell and minimal images
tar -C "$ROOT/Code/webapp" --exclude='__pycache__' --exclude='*.pyc' --exclude='staticfiles' --exclude='tests.py' \
    -cf - . | tar -C "$STAGE" -xf -
tar -C "$ROOT/Code/core" --exclude='__pycache__' --exclude='*.pyc' -cf - advancesearch | tar -C "$STAGE" -xf -
tar -C "$ROOT" -cf - Config | tar -C "$STAGE" -xf -

COLLECT_PATH=""
if [[ $VENDOR -eq 1 ]]; then
  echo "Installing Python libraries for Linux x64 / Python 3.12 into .packages"
  "$PY" -m pip install "${PIP_TARGET_FLAGS[@]}" --target "$STAGE/.packages" -r "$STAGE/requirements.txt"
  COLLECT_PATH="$STAGE/.packages"
fi

# Static files must exist in the package (run-from-package is read-only; there is no build step on the server).
if [[ -n "$COLLECT_PATH" ]] || "$PY" -c "import django, whitenoise" 2>/dev/null; then
  (cd "$STAGE" && PYTHONPATH="${COLLECT_PATH}" ADVSEARCH_MODE=local DJANGO_DEBUG=false \
    "$PY" manage.py collectstatic --noinput -v 0)
else
  echo "Note: Django is not installed here, so static files were not collected (use --vendor)." >&2
fi

"$PY" - "$STAGE" "$BUILD/webapp.zip" <<'PYCODE'
import os, sys, zipfile
src, dst = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
    for folder, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            if name.endswith(".pyc"):
                continue
            path = os.path.join(folder, name)
            zf.write(path, os.path.relpath(path, src))
PYCODE
echo "Built $BUILD/webapp.zip ($(du -h "$BUILD/webapp.zip" | cut -f1))"
