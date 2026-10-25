# Deployment Guide

> **Status:** the template, scripts and app were tested in a development environment that cannot sign in to
> Azure: the app in local mode and as the built package under gunicorn, Blob code against the Azurite emulator,
> the scripts against a fake `az`, and the template with the Bicep compiler and consistency tests. **No ARM
> deployment has been run yet.** dev and prod are untested.

## Prerequisites

- **Azure Cloud Shell (Bash)**. It has the Azure CLI, Python 3.12, pip, zip and git. The scripts use only
  management-API (ARM) requests and storage account keys, because Cloud Shell cannot get tokens for App Service
  (Kudu), Microsoft Graph, Storage (Entra ID) or the Key Vault data plane.
- **Owner** on the resource group (or Contributor + User Access Administrator), because the template creates role
  assignments. For the demo: resource group `Vaibhav.Chaudhary` (Central India), which already exists.
- Quota for the embedding model in the Azure OpenAI region (`openAiLocation`, South India by default).

## 1. Check the embedding model, quota and providers (once)

Run in Cloud Shell before the first deployment:

```bash
az cognitiveservices model list -l southindia --query "[?contains(model.name,'embedding')].{n:model.name,v:model.version,s:model.skus[].name}" -o table
az cognitiveservices usage list -l southindia -o table
az provider register -n Microsoft.Search --wait
```

- The first command lists the embedding models offered in South India, with versions and deployment types (SKUs).
  The default is `text-embedding-3-small`, version `1`, deployment type `GlobalStandard`, 1536 dimensions.
- The second shows quota (limit and current use). The demo needs 10 (thousand tokens per minute) of the matching
  line, for example `OpenAI.GlobalStandard.text-embedding-3-small`.
- If the output differs (another version, only `Standard`, or no quota), change **only the parameters** in
  `Deployment/ARM/parameters/demo.parameters.json`: `embeddingModelVersion`, `embeddingDeploymentSku`,
  `embeddingCapacity`, or `embeddingModelName` with `embeddingDimensions` (3072 for `text-embedding-3-large`).
  No code change is needed.
- `deploy.sh` also checks Microsoft.Web, Storage, KeyVault, CognitiveServices, Search, Insights,
  OperationalInsights (and Network with private networking) and registers missing ones.

## 2. Deploy the demo

```bash
cd ~ && git clone https://github.com/TTNS-Deployments/Advance-search.git ; cd ~/Advance-search && git pull && Deployment/scripts/deploy.sh -e demo --param demoPassword='<choose-a-password>'
```

Replace `<choose-a-password>` with a password you choose (at least 8 characters; keep the single quotes). It is
stored in Key Vault as `demo-password`. On later runs leave `--param demoPassword` out to keep it, or pass a new one
to change it. The clone step prints an error when the folder already exists; that is expected, `git pull` updates it.

What the command does (about 10–15 minutes the first time):

1. Reads `Deployment/environments/demo.env`: resource group `Vaibhav.Chaudhary`, region `centralindia`, the shared
   App Service plan `ccai-demo-gqausd-web-plan` and `SEED=1`.
2. Reuses the resource group, checks and registers resource providers.
3. Reads your object ID from the ARM token (no Microsoft Graph) for your data roles.
4. Looks up the shared plan's resource ID (`az appservice plan show ... --query id -o tsv`) and passes it as
   `existingAppServicePlanId`. If the plan is not found it stops. The plan is never modified.
5. Deploys `azuredeploy.json` with `demo.parameters.json` (deployment name `advancesearch-demo`).
6. Always runs the code step next (`deploy_code_arm.sh`), because an infrastructure deployment resets the web
   app's settings: builds `build/webapp.zip` with every library, uploads it to `code-packages` with the storage
   account key, sets `WEBSITE_RUN_FROM_PACKAGE` to a one-year read-only SAS URL and the startup command
   (`python -m gunicorn ... --workers 1 --threads 4 config.wsgi`), uploads the 13 sample documents, and restarts
   the app.
7. Prints the web app URL and the sign-in hint.

Resources created (names end in a 6-character suffix from the resource group, so they never collide with other
resources in it): `asrch-demo-<suffix>-kv`, storage `asrchdemo<suffix>st`, `-log`, `-appi`, `-openai` (South
India), `-search`, and the web app `asrch-demo-<suffix>-web` on the shared plan.

## 3. After deployment

1. Open the URL. The first load after a restart can take a minute on B1.
2. Choose **Admin**, enter the password, sign in.
3. On **Documents**, the sample documents move from *Queued* to *Indexed* within a few minutes (the
   *Scanned-Delivery-Note.pdf* sample shows *No text* on purpose). If nothing appears after 5 minutes, select
   **Sync from storage**.
4. Search for `how many days off do I get`. The 10-minute walkthrough is in the [user guide](user-guide.md).

Redeploy code only (after a `git pull`): `Deployment/scripts/deploy.sh -e demo --skip-infra --no-seed`.
Re-upload the samples only: `Deployment/scripts/deploy_code_arm.sh -g Vaibhav.Chaudhary -e demo --seed-only`.

## 4. Other environments

- **dev**: `Deployment/scripts/deploy.sh -e dev -g <resource-group> -l centralindia --param demoPassword='...'`
  creates its own B1 plan. Add `--seed` for the sample documents.
- **prod**: `Deployment/scripts/deploy.sh -e prod -g <resource-group> --param demoPassword='...'`. P0v3 plan with 2
  instances, Search Standard with 2 replicas and the standard semantic ranker, ZRS storage,
  `privateNetworking=true` and `allowSharedKeyAccess=false`.

### Private networking (prod)

With `privateNetworking=true` the template creates a VNet (`vnetAddressPrefix`, default `10.60.0.0/16`) with an
app-integration subnet and a private-endpoint subnet, private endpoints for Blob, AI Search, Azure OpenAI and Key
Vault, the four private DNS zones linked to the VNet, and VNet integration for the web app with all outbound traffic
routed through the VNet. Public network access is disabled on the four services; the web app stays public over HTTPS.

Consequences:

- `deploy_code_arm.sh` cannot upload the package from Cloud Shell (storage refuses public traffic and account
  keys). Run the code deployment from a machine inside the VNet (or a peered network) with identity-based upload,
  or temporarily allow your address on the storage firewall. **This path is untested.**
- The free search tier does not support private endpoints; use Basic or higher.
- Pick address ranges that do not overlap your other networks (`vnetAddressPrefix`, `appSubnetPrefix`,
  `privateEndpointSubnetPrefix`).

## 5. Deploy with the button

The **Deploy to Azure** button in the README opens the portal form (`createUiDefinition.json`) with a dropdown per
SKU and a demo password field. It deploys the infrastructure only, with a new App Service plan. Then deploy the
code from Cloud Shell: `Deployment/scripts/deploy.sh -e <env> -g <resource-group> --skip-infra`. The form's
environment name must match the `-e` value, because the scripts read the deployment `advancesearch-<env>`; if the
portal names the deployment differently, run the full `deploy.sh` instead.

## 6. Deploy with GitHub Actions (untested)

`.github/workflows/deploy.yml` runs `deploy.sh` manually per environment with OpenID Connect:

1. Create an app registration (or user-assigned identity) with a federated credential for
   `repo:TTNS-Deployments/Advance-search:environment:<env>`, and give it Owner on the resource group.
2. In the repository, create a GitHub environment named `demo`, `dev` or `prod` with the variables
   `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`, and optionally the secret
   `DEMO_PASSWORD`.
3. Run *Actions → Deploy* and choose the environment and scope.

The CI workflow (`ci.yml`) runs every test, checks that `azuredeploy.json` matches the Bicep source and builds
the package as an artifact.

## 7. Change SKUs later

Edit the parameters file and run `deploy.sh` again (infrastructure and code). Notes:

- **Search tier** cannot be changed on an existing service. Set the new `searchSku`, delete the old search service
  (or use another `solutionPrefix`), deploy, then select **Rebuild index** (or **Sync from storage**): the app
  recreates the index and re-indexes every document from storage. Replicas and partitions change in place.
- Free tier: one per subscription, no semantic ranker (match % then always comes from vector similarity), 50 MB,
  3 indexes. Basic: up to 3 replicas, 1 partition per service in most regions.
- **Embedding model or dimensions**: deploy, then **Rebuild index** (the app warns Admins while the index has the
  old vector size).

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `InsufficientQuota` on the embedding deployment | No quota for that model and deployment type in `openAiLocation`. Run the two checks in step 1, then lower `embeddingCapacity`, switch `embeddingDeploymentSku`, or use another `openAiLocation` with quota |
| `The subscription is not registered to use namespace 'Microsoft.Search'` | Run `az provider register -n Microsoft.Search --wait` (needs subscription Contributor) |
| `App Service plan 'ccai-demo-gqausd-web-plan' was not found` | Check `EXISTING_PLAN_NAME` / `EXISTING_PLAN_RESOURCE_GROUP` in `demo.env`, or remove both lines to create a plan |
| `ServiceQuotaExceeded` / free search service already exists | Only one free search service per subscription: use `basic` |
| Key Vault `VaultAlreadyExists` / soft-deleted vault after deleting the demo | Purge it: `az keyvault purge -n <vault-name>` (or wait 7 days), then deploy again |
| Sign-in page says "Sign-in is not configured" | No `demo-password` secret yet, or the Key Vault reference is not resolved. Run `deploy.sh -e demo --skip-code --param demoPassword='...'` followed by `deploy.sh -e demo --skip-infra`; a restart picks up role assignments that were still propagating |
| Site shows "Application Error" or 503 | `WEBSITE_RUN_FROM_PACKAGE` is missing (infrastructure was deployed without the code step): run `deploy.sh -e demo --skip-infra`. Check *Log stream* in the portal |
| Documents stay *Queued* | The worker starts on the first request; open the site. Then use **Sync from storage**. Check Application Insights for `Ingestion of ... failed` |
| Documents *Failed* with `HTTP 401/403` | Role assignments take a few minutes; select **Re-index** later |
| Documents *Failed* with `returned N dimensions` | `embeddingDimensions` does not match the model; fix the parameter, deploy, **Rebuild index** |
| Warning "The search index was built with N-dimension vectors" | The model or dimensions changed: **Rebuild index** |
| Match % always says "vector similarity" | Semantic ranker free quota (1,000 queries/month) used up, semantic search disabled, or the free search tier. Results still work |
| `Could not read the key of storage account` | `allowSharedKeyAccess` is false (prod); see private networking above |

## Remove the demo

Delete the resources whose names start with `asrch-demo-` and the storage account `asrchdemo...st` in the
resource group (portal, filter by tag `project: advance-search`). Do **not** delete the resource group or the shared
App Service plan. Purge the soft-deleted Key Vault if you redeploy with the same name.
