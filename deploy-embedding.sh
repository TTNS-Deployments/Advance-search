#!/usr/bin/env bash
# deploy-embedding.sh - deploys (or redeploys) only the Azure OpenAI
# text-embedding-3-large resource. Same resource group as the rest of the stack.
#
# Optional: KEY_VAULT_NAME=<vault> ./deploy-embedding.sh
#   also stores EmbeddingEndpoint and EmbeddingApiKey in that Key Vault.
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-rg-advsearch-dev}"
EMBEDDING_LOCATION="${EMBEDDING_LOCATION:-eastus2}"
NAME_PREFIX="${NAME_PREFIX:-advsearch}"
ENVIRONMENT="${ENVIRONMENT:-dev}"
TEMPLATE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/templates/09-embedding.json"

log()  { echo -e "\n\033[1;36m==> $1\033[0m"; }
warn() { echo -e "\033[1;33m! $1\033[0m"; }

command -v az >/dev/null 2>&1 || { echo "Azure CLI not found. Install it first."; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "jq not found. Install it first."; exit 1; }
az account show >/dev/null 2>&1 || { echo "Run 'az login' first."; exit 1; }

log "Deploying text-embedding-3-large to $EMBEDDING_LOCATION (resource group: $RESOURCE_GROUP)"
OUT=$(az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --template-file "$TEMPLATE" \
  --parameters namePrefix="$NAME_PREFIX" environment="$ENVIRONMENT" location="$EMBEDDING_LOCATION" \
  --query properties.outputs -o json)

OAI_ACCOUNT_NAME=$(echo "$OUT" | jq -r .accountName.value)
OAI_ENDPOINT=$(echo "$OUT" | jq -r .endpoint.value)
OAI_DEPLOYMENT_NAME=$(echo "$OUT" | jq -r .deploymentName.value)
OAI_API_KEY=$(echo "$OUT" | jq -r .apiKey.value)

if [[ -n "${KEY_VAULT_NAME:-}" ]]; then
  log "Storing endpoint and key in Key Vault $KEY_VAULT_NAME"
  az keyvault secret set --vault-name "$KEY_VAULT_NAME" --name "EmbeddingEndpoint" --value "$OAI_ENDPOINT" -o none
  az keyvault secret set --vault-name "$KEY_VAULT_NAME" --name "EmbeddingApiKey" --value "$OAI_API_KEY" -o none
else
  warn "KEY_VAULT_NAME not set, so nothing was stored in Key Vault."
  warn "Re-run as: KEY_VAULT_NAME=<your-keyvault-name> ./deploy-embedding.sh"
  echo "apiKey: $OAI_API_KEY"
fi

log "Done"
cat <<SUMMARY

Use these when configuring the Azure OpenAI vectorizer on your AI Search index:
  account:         $OAI_ACCOUNT_NAME
  endpoint:        $OAI_ENDPOINT
  deploymentId:    $OAI_DEPLOYMENT_NAME
  modelName:       text-embedding-3-large
  apiKey:          (in Key Vault as "EmbeddingApiKey" if KEY_VAULT_NAME was set)

SUMMARY
