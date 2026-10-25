#!/usr/bin/env bash
# One-command deployment of Advance Search: infrastructure (ARM) and then application code.
#
#   Deployment/scripts/deploy.sh -e <environment> [options]
#
# Options
#   -e, --environment   environment: uses Deployment/ARM/parameters/<env>.parameters.json [required]
#                       and Deployment/environments/<env>.env (optional) for defaults of -g/-l/-s and flags
#   -g, --resource-group  resource group (an existing one is reused, never recreated); default RESOURCE_GROUP
#   -l, --location      region for a new resource group (default: centralindia)
#   -s, --subscription  subscription ID or name (default: the current az account)
#       --param name=value  extra ARM parameter (repeatable), e.g. --param demoPassword='...'
#       --seed          upload the sample documents (Data/sample_docs) after the code deployment
#       --no-seed       do not upload them even if the env file sets SEED=1
#       --skip-infra    only deploy the code
#       --skip-code     only deploy the infrastructure (WARNING: this resets the web app's settings, including
#                       WEBSITE_RUN_FROM_PACKAGE; the app stops working until the code step runs again)
#   -h, --help          show this help
#
# Uses only management-API (ARM) calls, so it runs in Azure Cloud Shell. Needs Owner (or Contributor + User
# Access Administrator) on the resource group, plus python3, pip and zip (all in Cloud Shell).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPTS="$ROOT/Deployment/scripts"
RG="" ENV="" LOCATION="centralindia" LOCATION_SET=0 SUBSCRIPTION="" SEED=0 NO_SEED=0 SKIP_INFRA=0 SKIP_CODE=0
EXTRA_PARAMS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    -e|--environment) ENV="${2:-}"; shift 2 ;;
    -g|--resource-group) RG="${2:-}"; shift 2 ;;
    -l|--location) LOCATION="${2:-}"; LOCATION_SET=1; shift 2 ;;
    -s|--subscription) SUBSCRIPTION="${2:-}"; shift 2 ;;
    --param) EXTRA_PARAMS+=("${2:-}"); shift 2 ;;
    --seed) SEED=1; shift ;;
    --no-seed) NO_SEED=1; shift ;;
    --skip-infra) SKIP_INFRA=1; shift ;;
    --skip-code) SKIP_CODE=1; shift ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) echo "Unknown option $1 (see --help)" >&2; exit 1 ;;
  esac
done
[[ -n "$ENV" ]] || { echo "Usage: $0 -e <environment> [-g <resource-group>]  (see --help)" >&2; exit 1; }

PARAMS="$ROOT/Deployment/ARM/parameters/$ENV.parameters.json"
[[ -f "$PARAMS" ]] || { echo "Parameters file not found: $PARAMS" >&2; exit 1; }

# Optional per-environment variables. Command-line options win.
ENV_FILE="$ROOT/Deployment/environments/$ENV.env"
EXISTING_PLAN_NAME="" EXISTING_PLAN_RESOURCE_GROUP=""
if [[ -f "$ENV_FILE" ]]; then
  echo "Using variables from Deployment/environments/$(basename "$ENV_FILE")"
  CLI_LOCATION="$LOCATION" CLI_SEED="$SEED"
  # shellcheck disable=SC1090
  source "$ENV_FILE"   # may set RESOURCE_GROUP, LOCATION, AZURE_SUBSCRIPTION, SEED, EXISTING_PLAN_*
  [[ -z "$RG" ]] && RG="${RESOURCE_GROUP:-}"
  [[ "$LOCATION_SET" -eq 1 || -z "${LOCATION:-}" ]] && LOCATION="$CLI_LOCATION"
  [[ -z "$SUBSCRIPTION" ]] && SUBSCRIPTION="${AZURE_SUBSCRIPTION:-}"
  [[ "$CLI_SEED" == "1" ]] && SEED=1
fi
[[ "$NO_SEED" -eq 1 ]] && SEED=0
[[ -n "$RG" ]] || { echo "No resource group: pass -g or set RESOURCE_GROUP in Deployment/environments/$ENV.env" >&2; exit 1; }

command -v az >/dev/null || { echo "The Azure CLI (az) is not installed. Use Azure Cloud Shell (Bash)." >&2; exit 1; }
[[ -n "$SUBSCRIPTION" ]] && az account set --subscription "$SUBSCRIPTION"
echo "Subscription: $(az account show --query name -o tsv)"

# Object ID of the signed-in identity without Microsoft Graph (refused in Cloud Shell):
# read the "oid" claim from the Azure Resource Manager access token.
oid_from_token() {
  az account get-access-token --query accessToken -o tsv 2>/dev/null | python3 -c '
import base64, json, sys
part = sys.stdin.read().strip().split(".")[1]
part += "=" * (-len(part) % 4)
print(json.loads(base64.urlsafe_b64decode(part)).get("oid", ""))' 2>/dev/null || true
}

DEPLOYMENT="advancesearch-$ENV"
if [[ $SKIP_INFRA -eq 0 ]]; then
  # Reuse an existing resource group; create it only if missing.
  if [[ "$(az group exists -n "$RG")" == "true" ]]; then
    echo "==> Using existing resource group $RG ($(az group show -n "$RG" --query location -o tsv))"
  else
    echo "==> Creating resource group $RG ($LOCATION)"
    az group create -n "$RG" -l "$LOCATION" -o none
  fi

  # Resource providers must be registered in the subscription. Try to register missing ones; warn if that fails.
  PROVIDERS=(Microsoft.Web Microsoft.Storage Microsoft.KeyVault Microsoft.CognitiveServices Microsoft.Search
             Microsoft.Insights Microsoft.OperationalInsights)
  if python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1]))["parameters"].get("privateNetworking",{}).get("value") else 1)' "$PARAMS" \
     || printf '%s\n' "${EXTRA_PARAMS[@]+"${EXTRA_PARAMS[@]}"}" | grep -qx 'privateNetworking=true'; then
    PROVIDERS+=(Microsoft.Network)
  fi
  MISSING=""
  for ns in "${PROVIDERS[@]}"; do
    state="$(az provider show -n "$ns" --query registrationState -o tsv 2>/dev/null || echo unknown)"
    if [[ "$state" != "Registered" ]]; then
      echo "==> Registering resource provider $ns (was: $state)"
      az provider register -n "$ns" --wait -o none 2>/dev/null || MISSING="$MISSING $ns"
    fi
  done
  if [[ -n "$MISSING" ]]; then
    echo "WARNING: these resource providers could not be registered:$MISSING" >&2
    echo "         Ask a subscription Owner or Contributor to run: az provider register -n <namespace> --wait" >&2
  fi

  # Identity running the deployment gets Storage Blob Data Contributor and Key Vault Secrets Officer.
  if [[ "$(az account show --query user.type -o tsv)" == "servicePrincipal" ]]; then
    DEPLOYER_TYPE="ServicePrincipal"
  else
    DEPLOYER_TYPE="User"
  fi
  DEPLOYER_ID="$(oid_from_token)"
  if [[ -n "$DEPLOYER_ID" ]]; then
    echo "Deploying identity: $DEPLOYER_ID ($DEPLOYER_TYPE)"
  else
    echo "Note: could not read the deploying identity; skipping its data-access role assignments."
  fi

  PLAN_PARAMS=()
  if [[ -n "$EXISTING_PLAN_NAME" ]]; then
    PLAN_RG="${EXISTING_PLAN_RESOURCE_GROUP:-$RG}"
    PLAN_ID="$(az appservice plan show -g "$PLAN_RG" -n "$EXISTING_PLAN_NAME" --query id -o tsv 2>/dev/null || true)"
    if [[ -z "$PLAN_ID" ]]; then
      echo "ERROR: App Service plan '$EXISTING_PLAN_NAME' was not found in resource group '$PLAN_RG'." >&2
      echo "       Check EXISTING_PLAN_NAME and EXISTING_PLAN_RESOURCE_GROUP in Deployment/environments/$ENV.env," >&2
      echo "       or remove both lines to create a new plan." >&2
      exit 1
    fi
    echo "==> Using existing App Service plan $EXISTING_PLAN_NAME (it is not modified)"
    PLAN_PARAMS=(existingAppServicePlanId="$PLAN_ID")
  fi

  echo "==> Deploying infrastructure with $(basename "$PARAMS") (deployment $DEPLOYMENT, about 5-10 minutes)"
  az deployment group create -g "$RG" -n "$DEPLOYMENT" \
    --template-file "$ROOT/Deployment/ARM/azuredeploy.json" \
    --parameters @"$PARAMS" \
    --parameters deployerPrincipalId="$DEPLOYER_ID" deployerPrincipalType="$DEPLOYER_TYPE" \
    ${PLAN_PARAMS[@]+--parameters "${PLAN_PARAMS[@]}"} \
    ${EXTRA_PARAMS[@]+--parameters "${EXTRA_PARAMS[@]}"} \
    -o none
fi

# The infrastructure step resets the web app settings (WEBSITE_RUN_FROM_PACKAGE included), so the code step
# always follows it.
CODE_ARGS=(-g "$RG" -e "$ENV")
[[ $SEED -eq 1 ]] && CODE_ARGS+=(--seed)
if [[ $SKIP_CODE -eq 0 ]]; then
  "$SCRIPTS/deploy_code_arm.sh" "${CODE_ARGS[@]}"
else
  echo "WARNING: --skip-code: the web app has no code package until you run: $0 -e $ENV --skip-infra" >&2
fi

WEB_URL="$(az deployment group show -g "$RG" -n "$DEPLOYMENT" --query properties.outputs.webAppUrl.value -o tsv)"
echo
echo "Done. Web app: $WEB_URL"
AUTH_MODE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["parameters"].get("authMode",{}).get("value","password"))' "$PARAMS")"
if [[ "$AUTH_MODE" == "password" ]]; then
  echo "Sign in: choose Admin or User and enter the demo password you set with --param demoPassword='...'."
  echo "         (Set it once; later runs without --param keep it.)"
fi
