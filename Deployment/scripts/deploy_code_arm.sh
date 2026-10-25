#!/usr/bin/env bash
# Deploys the application code (and optionally the sample documents) using ONLY the Azure management API.
#
#   Deployment/scripts/deploy_code_arm.sh -g <resource-group> -e <environment> [--seed] [--seed-only]
#
# Options
#   -g, --resource-group   resource group of the deployment [required]
#   -e, --environment      environment name; the infrastructure deployment is "advsrch-<env>" [required]
#       --seed             also upload Data/sample_docs/*.pdf|docx|xlsx to the documents container
#       --seed-only        only upload the sample documents (no code deployment)
#   -h, --help             show this help
#
# For Azure Cloud Shell, where tokens for App Service (SCM/Kudu), Storage, Key Vault and Graph cannot be
# obtained. It:
#   1. builds build/webapp.zip with every Python library included (package.sh --vendor; needs python3 + pip)
#      (set PACKAGE_ZIP=<path> to use an existing package instead)
#   2. uploads it to the code-packages container with the storage account key (read through the management API)
#   3. sets WEBSITE_RUN_FROM_PACKAGE to a read-only SAS URL (valid one year), the startup command, and restarts
#   4. --seed: uploads the sample documents with the account key; the web app indexes them on start-up
# Run it after every infrastructure deployment (the template resets the web app settings).
# Needs allowSharedKeyAccess=true on the storage account (demo and dev parameter files).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RG="" ENV="" SEED=0 SEED_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    -g|--resource-group) RG="${2:-}"; shift 2 ;;
    -e|--environment) ENV="${2:-}"; shift 2 ;;
    --seed) SEED=1; shift ;;
    --seed-only) SEED=1; SEED_ONLY=1; shift ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) echo "Unknown option $1 (see --help)" >&2; exit 1 ;;
  esac
done
[[ -n "$RG" && -n "$ENV" ]] || { echo "Usage: $0 -g <resource-group> -e <environment> [--seed]  (see --help)" >&2; exit 1; }

DEPLOYMENT="advsrch-$ENV"
STARTUP="python -m gunicorn --bind=0.0.0.0:8000 --timeout 600 --workers 1 --threads 4 config.wsgi"
out() { az deployment group show -g "$RG" -n "$DEPLOYMENT" --query "properties.outputs.$1.value" -o tsv; }

WEB_APP="$(out webAppName)" || true
STORAGE="$(out storageAccountName)" || true
if [[ -z "$WEB_APP" || -z "$STORAGE" ]]; then
  echo "Could not read the outputs of deployment $DEPLOYMENT in $RG. Run the infrastructure step first:" >&2
  echo "  Deployment/scripts/deploy.sh -e $ENV" >&2
  exit 1
fi

KEY="$(az storage account keys list -g "$RG" -n "$STORAGE" --query "[0].value" -o tsv)" || KEY=""
if [[ -z "$KEY" ]]; then
  echo "Could not read the key of storage account $STORAGE. It needs allowSharedKeyAccess=true (see Deployment/README.md)." >&2
  exit 1
fi

blob_upload() {  # blob_upload <container> <blob name> <file>
  az storage blob upload --account-name "$STORAGE" --account-key "$KEY" -c "$1" -n "$2" -f "$3" --overwrite -o none
}

if [[ $SEED_ONLY -eq 0 ]]; then
  ZIP="${PACKAGE_ZIP:-}"
  if [[ -z "$ZIP" ]]; then
    echo "==> Packaging with all Python libraries included (takes a few minutes)"
    "$ROOT/Deployment/scripts/package.sh" --vendor
    ZIP="$ROOT/build/webapp.zip"
  fi
  [[ -f "$ZIP" ]] || { echo "Package not found: $ZIP" >&2; exit 1; }

  STAMP="$(date -u +%Y%m%d%H%M%S)"
  BLOB="webapp-$STAMP.zip"
  echo "==> Uploading $BLOB to $STORAGE/code-packages (account key)"
  az storage container create --account-name "$STORAGE" --account-key "$KEY" -n code-packages -o none
  blob_upload code-packages "$BLOB" "$ZIP"
  EXPIRY="$(date -u -d '+365 days' '+%Y-%m-%dT%H:%MZ')"
  PACKAGE_URL="$(az storage blob generate-sas --account-name "$STORAGE" --account-key "$KEY" -c code-packages -n "$BLOB" \
    --permissions r --expiry "$EXPIRY" --https-only --full-uri -o tsv)"
  [[ "$PACKAGE_URL" == https://* ]] || { echo "Could not create a SAS URL for the package" >&2; exit 1; }

  echo "==> Configuring web app $WEB_APP to run from the package"
  az webapp config appsettings set -g "$RG" -n "$WEB_APP" -o none --settings \
    WEBSITE_RUN_FROM_PACKAGE="$PACKAGE_URL" SCM_DO_BUILD_DURING_DEPLOYMENT=false \
    PYTHONPATH=/home/site/wwwroot/.packages
  az webapp config set -g "$RG" -n "$WEB_APP" -o none --startup-file "$STARTUP"
fi

if [[ $SEED -eq 1 ]]; then
  echo "==> Uploading the sample documents to the documents container (account key)"
  shopt -s nullglob
  for file in "$ROOT"/Data/sample_docs/*.pdf "$ROOT"/Data/sample_docs/*.docx "$ROOT"/Data/sample_docs/*.xlsx; do
    blob_upload documents "$(basename "$file")" "$file"
    echo "    uploaded $(basename "$file")"
  done
  shopt -u nullglob
fi

# Restart last, so the start-up scan sees the sample documents.
echo "==> Restarting $WEB_APP"
az webapp restart -g "$RG" -n "$WEB_APP" -o none
echo "Code deployed. Web app: https://$(az webapp show -g "$RG" -n "$WEB_APP" --query defaultHostName -o tsv)"
echo "The first page load after a restart can take about a minute."
