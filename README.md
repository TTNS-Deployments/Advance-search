

# Advance Search

ARM templates and shell scripts that provision the full Azure infrastructure for a small-scale advance search application: Django on App Service, Cosmos DB, Azure AI Search, and Azure OpenAI embeddings for semantic search. The deployment is idempotent, parameterized, and runs with one command.

This repository is a proof-of-concept (POC) deployment. It is meant to get a working search stack running quickly, so treat it as a template you can customize for your own use case. The search returns ranked results with similarity scores. No chat or completion model is deployed, so there is no generated-answer step anywhere in the stack.

A simple front-end page that summarizes the deployment is in [`index.html`](index.html) and can be published with GitHub Pages.

## Overview

Resources are listed in deployment order.

| # | Name | Description | Service | Template |
| - | ---- | ----------- | ------- | -------- |
| 1 | Key Vault | Holds every secret the stack generates | Key Vault | [`01-keyvault.json`](templates/01-keyvault.json) |
| 2 | Storage Account | Document store and backup target | Storage (blob, files) | [`02-storage.json`](templates/02-storage.json) |
| 3 | Monitoring | Logs and application telemetry | Log Analytics, Application Insights | [`03-monitor.json`](templates/03-monitor.json) |
| 4 | Web app | Hosts the Django application | App Service (P1v2, Linux) | [`04-appservice.json`](templates/04-appservice.json) |
| 5 | Database | Structured application data | Cosmos DB for NoSQL (100 RU/s) | [`05-cosmosdb.json`](templates/05-cosmosdb.json) |
| 6 | Search | Indexing and ranked retrieval | Azure AI Search (Standard S1) | [`06-search.json`](templates/06-search.json) |
| 7 | Background processing | Async and background work | Azure Functions (Consumption) | [`07-functions.json`](templates/07-functions.json) |
| 8 | Embeddings | Vectorizes documents and queries | Azure OpenAI `text-embedding-3-large` | [`09-embedding.json`](templates/09-embedding.json) |
| 9 | Backup | Protects the `backupshare` file share | Recovery Services Vault | [`08-backup.json`](templates/08-backup.json) |
| 10 | Security posture | Subscription-wide protection plans | Defender for Cloud | [`09-defender.json`](subscription/09-defender.json) |

Template file numbers differ from deployment order in two places (embedding and backup), and both the embedding and Defender templates use `09`. The table above follows the order `deploy.sh` runs them in.

## Deployed Resources in More Detail

- **Key Vault** (`templates/01-keyvault.json`): Standard tier with soft-delete on and purge protection off, so it is easy to tear down while testing. It is deployed first because later steps push secrets into it.
- **Storage Account** (`templates/02-storage.json`): StorageV2, LRS, Hot tier. Creates a `documents` blob container for source files and a `backupshare` file share that Azure Backup protects.
- **Log Analytics and Application Insights** (`templates/03-monitor.json`): Workspace-based Application Insights, with 30-day Log Analytics retention and 90-day Application Insights retention.
- **App Service** (`templates/04-appservice.json`): A P1v2 Linux plan running the `PYTHON|3.12` runtime for Django, with a system-assigned identity so it can read Key Vault.
- **Cosmos DB** (`templates/05-cosmosdb.json`): NoSQL API with manual throughput at 100 RU/s, a single region, and periodic backup.
- **Azure AI Search** (`templates/06-search.json`): Standard S1 with 1 replica and 1 partition. It is provisioned as `Microsoft.Search/searchServices`, which is what appears as "Foundry IQ" on newer Azure cost sheets.
- **Azure Functions** (`templates/07-functions.json`): Consumption (Y1) plan on Linux and Python. It reuses the Storage Account from step 2 instead of creating a second one.
- **Azure OpenAI embedding** (`templates/09-embedding.json`): `text-embedding-3-large`, deployed to East US 2 in the same resource group (see below).
- **Recovery Services Vault** (`templates/08-backup.json`): A daily backup policy that protects the `backupshare` file share.
- **Defender for Cloud** (`subscription/09-defender.json`): Subscription-scope plans, deployed last and only after a confirmation prompt because it changes security settings for the whole subscription.

### How it fits together

Django runs on the App Service, backed by Cosmos DB for structured data and Azure AI Search for retrieval. Documents are vectorized with the Azure OpenAI embedding deployment, and AI Search returns ranked results with similarity scores directly. Azure Functions handles background processing. Key Vault holds every secret these services generate, and App Service and Functions read them through Key Vault references rather than plaintext app settings. Monitor, Backup, and Defender for Cloud cover observability, resilience, and security posture.

![Advance Search architecture](imgs/architecture.svg)


## Repository Layout

```
Advance_Search/
├── README.md
├── index.html                  # simple front-end page (GitHub Pages)
├── deploy.sh                   # deploys everything, in order
├── deploy-embedding.sh         # standalone: redeploy just the embedding model
├── templates/                  # resource-group-scope ARM templates
│   ├── 01-keyvault.json
│   ├── 02-storage.json
│   ├── 03-monitor.json
│   ├── 04-appservice.json
│   ├── 05-cosmosdb.json
│   ├── 06-search.json
│   ├── 07-functions.json
│   ├── 08-backup.json
│   └── 09-embedding.json
├── subscription/               # subscription-scope ARM templates
│   └── 09-defender.json
├── app/                        # Django application code goes here
├── imgs/                       # banner and architecture diagram
├── LICENSE
├── CODE_OF_CONDUCT.md
├── SECURITY.md
├── SUPPORT.md
└── .gitignore
```

## Prerequisites

1. **An Azure subscription** with permission to create resources. Contributor is the minimum; you also need Security Admin or Owner if you want the Defender for Cloud step.
2. **Azure CLI.** Check with `az --version`. Install: <https://learn.microsoft.com/en-us/cli/azure/install-azure-cli>
3. **jq**, used to parse deployment outputs. Check with `jq --version`. Install with `sudo apt install jq` (Debian/Ubuntu), `brew install jq` (macOS), or see <https://jqlang.org/download/>
4. **Bash.** The scripts use `set -euo pipefail`. On Windows, run them through WSL or Git Bash rather than PowerShell or cmd.

## Step-by-Step: Deploying from Scratch

1. **Clone the repository**

   ```bash
   git clone https://github.com/TTNS-Deployments/Advance_Search.git
   cd Advance_Search
   ```

2. **Log in to Azure**

   ```bash
   az login
   ```

   If you have more than one subscription, pick the right one:

   ```bash
   az account list -o table
   az account set --subscription "<subscription-id-or-name>"
   ```

3. **Review the configuration block at the top of `deploy.sh`.** The defaults are:

   ```bash
   RESOURCE_GROUP="rg-advsearch-dev"
   LOCATION="centralindia"
   EMBEDDING_LOCATION="eastus2"
   NAME_PREFIX="advsearch"
   ENVIRONMENT="dev"
   ```

   Edit these for different naming, a different primary region, or a different resource group. Resource names are generated from `NAME_PREFIX`, `ENVIRONMENT`, and a uniqueness suffix, so re-running with the same values updates existing resources instead of colliding with them.

4. **Make the script executable and run it**

   ```bash
   chmod +x deploy.sh
   ./deploy.sh
   ```

5. **Follow the prompts.** Resources 1 to 9 deploy automatically. Before step 10 (Defender for Cloud) the script asks for confirmation, because that step changes security settings for the entire subscription, not just this resource group:

   ```
   Continue enabling Defender plans on subscription <id>? [y/N]
   ```

   Type `y` to proceed or `n` to skip it and enable it later.

6. **Read the summary at the end.** It lists every resource name, the App Service URL, and the secrets stored in Key Vault.

A full run typically takes 10 to 20 minutes. Cosmos DB and Azure OpenAI account creation are usually the slowest steps.

## After Deployment

- **Deploy your Django code** to the App Service (`WEB_APP_NAME` in the summary), for example with `az webapp deploy` or a CI/CD pipeline. This repository provisions infrastructure only; application code goes in [`app/`](app/).
- **Configure the AI Search vectorizer** to use the embedding deployment. You need the `endpoint`, the `deploymentName` (`embedding-large`), and the API key. The key is in Key Vault as `EmbeddingApiKey`, and the rest print in the deployment summary.
- **Upload documents** to the `documents` blob container in the Storage Account, or have your Functions app do it.

## Redeploying a Single Piece

Every resource has its own template, so you can redeploy one without touching the rest. To redeploy only the embedding model:

```bash
./deploy-embedding.sh
```

To also store the endpoint and key in Key Vault:

```bash
KEY_VAULT_NAME=<your-keyvault-name> ./deploy-embedding.sh
```

Any other single template can be redeployed directly:

```bash
az deployment group create \
  --resource-group rg-advsearch-dev \
  --template-file templates/06-search.json \
  --parameters namePrefix=advsearch environment=dev location=centralindia
```

ARM deployments are idempotent: re-running a template against an existing resource updates it in place.

## Enabling Defender for Cloud Later

If you skipped step 10 or want to run it again:

```bash
az deployment sub create \
  --location centralindia \
  --template-file subscription/09-defender.json
```

## Tearing Everything Down

```bash
az group delete --name rg-advsearch-dev --yes --no-wait
```

This removes every resource-group-scoped resource (steps 1 to 9). Defender for Cloud plans (step 10) are subscription-scoped and are not removed by deleting the resource group. Reset them individually if needed, for example:

```bash
az security pricing create --name KeyVaults --tier Free
```

## Assumptions

- Resource group `rg-advsearch-dev` in `centralindia`, embedding resource in `eastus2`, prefix `advsearch`, environment `dev`. All are overridable at the top of `deploy.sh`.
- Functions reuse the single Storage Account rather than getting a dedicated one, since this runs at small scale.
- Backup protects only the `backupshare` file share, not blob data or the App Service. Add more `Microsoft.RecoveryServices` resources if you need that.
- No chat or completion model is deployed, only the embedding model. If you later want generated answers instead of ranked results with similarity scores, that is an intentional gap rather than an oversight.

## Cost Note

The Premium V2 App Service plan and Standard S1 AI Search are the bulk of the monthly cost, and both bill continuously regardless of traffic. Everything else is low-cost or near-free at this scale: Functions on Consumption, Cosmos DB at 100 RU/s, Key Vault, small Storage, Log Analytics at this volume, and the embedding model, which bills per token. Review current pricing before deploying: <https://azure.microsoft.com/en-us/pricing/calculator/>

## Troubleshooting

- **`az: command not found`**: Azure CLI is not installed or not on your PATH. See Prerequisites.
- **`jq: command not found`**: install `jq`. See Prerequisites.
- **`Run 'az login' first.`**: you are not authenticated. Run `az login` and retry.
- **A deployment fails partway through**: `deploy.sh` does not roll back earlier steps. Fix the reported error and re-run `./deploy.sh`; resources that already deployed update in place instead of failing or duplicating.
- **Region or quota errors on the embedding model or App Service**: some subscriptions have per-region quota limits on Azure OpenAI or compute SKUs. Check your quota in the Azure portal for that resource type, or try a different region by editing the relevant location variable.

## Contributing and Support

See [SUPPORT.md](SUPPORT.md) for questions and bug reports, [SECURITY.md](SECURITY.md) for reporting vulnerabilities, and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for community expectations.

## License

Released under the [MIT License](LICENSE).
