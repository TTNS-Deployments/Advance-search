# Deployment

| File | Purpose |
|---|---|
| `ARM/azuredeploy.bicep` | Source of the template. After editing: `bicep build ARM/azuredeploy.bicep --outfile ARM/azuredeploy.json` (CI checks that the two match) |
| `ARM/azuredeploy.json` | The ARM template for every Azure resource, role assignment and app setting |
| `ARM/parameters/demo.parameters.json`, `dev.parameters.json`, `prod.parameters.json` | **The SKU files.** Pick the tier and size of every service per environment. Copy one to add an environment (`test`, `uat`) |
| `ARM/createUiDefinition.json` | Portal form used by the *Deploy to Azure* button (a dropdown per SKU) |
| `environments/<env>.env` | Optional deployment variables per environment (subscription, resource group, region, shared plan, seeding) read by `deploy.sh` |
| `scripts/deploy.sh` | Infrastructure, then code, in one command (`-e <env> [-g <rg>] [--param name=value] [--seed] [--skip-infra] [--skip-code]`) |
| `scripts/deploy_code_arm.sh` | Code (and sample documents) through the management API only: package upload with the account key, run-from-package SAS URL, startup command, restart |
| `scripts/package.sh` | Builds `build/webapp.zip` (`--vendor`: every Python library included, static files collected) |

Every script has `--help`. Step-by-step instructions are in [Documents/deployment-guide.md](../Documents/deployment-guide.md).

> Verified locally only: the template compiles with Bicep and passes the consistency tests, `package.sh --vendor`
> builds a package that runs under gunicorn, and the scripts were run against a fake `az`. No ARM deployment has
> been run yet; dev and prod are untested.

## Demo environment

For a demo or proof of concept, use the `demo` files. They pick the cheapest settings that still run the whole system:

| File | Contents |
|---|---|
| `ARM/parameters/demo.parameters.json` | No new App Service plan (the web app joins an existing B1 Linux plan); Storage Standard_LRS; AI Search **Basic** (1 replica, 1 partition, semantic ranker free plan); Azure OpenAI `text-embedding-3-small` (1536 dimensions, GlobalStandard, 10K TPM) in **South India**; Log Analytics 30 days and 1 GB/day; Key Vault standard; demo password sign-in; public endpoints; tags `owner: TTNS`, `project: advance-search`, `purpose: demo` |
| `environments/demo.env` | Resource group `Vaibhav.Chaudhary` (reused, never recreated), region `centralindia`, the shared plan `ccai-demo-gqausd-web-plan` (its resource ID is looked up at deployment time, so no subscription ID is stored), `SEED=1` (upload the sample documents) |

```bash
Deployment/scripts/deploy.sh -e demo --param demoPassword='<choose-a-password>'
```

The web app is a **separate app** on the shared plan, with its own name, settings, managed identity, startup command
and logs. The template never modifies the plan. Because the plan's 1.75 GB of memory is shared with other apps, the
web app runs gunicorn with 1 worker and 4 threads and ingests one file at a time.

Sign-in uses one shared password (`authMode=password`) stored in Key Vault as `demo-password`. It is created only
when `demoPassword` is passed, so later deployments keep it. Remove the demo by deleting the resources named
`advsrch-demo-*` and `advsrchdemo*st`; leave the resource group and the shared plan.

## SKU and sizing parameters

Values in the three parameter files; "Options" are the values the template accepts.

| Parameter | demo | dev | prod | Options / notes |
|---|---|---|---|---|
| `solutionPrefix` | advsrch | advsrch | advsrch | 3–8 lowercase letters or digits; part of every name |
| `environmentName` | demo | dev | prod | `demo`, `dev`, `test`, `uat`, `prod` |
| `location` | centralindia | centralindia | centralindia | Region of everything except Azure OpenAI. With an existing plan, the plan's region |
| **Storage** | | | | |
| `storageSku` | Standard_LRS | Standard_LRS | Standard_ZRS | `Standard_LRS`, `Standard_ZRS`, `Standard_GRS`, `Standard_RAGRS`, `Standard_GZRS` |
| `allowSharedKeyAccess` | true | true | false | `true` is needed by `deploy_code_arm.sh` (account-key upload) |
| `blobSoftDeleteDays` | 7 | 7 | 30 | 1–365, blobs and containers |
| **Embeddings (Azure OpenAI)** | | | | |
| `openAiLocation` | southindia | southindia | southindia | Any region that offers the model with quota |
| `embeddingModelName` | text-embedding-3-small | text-embedding-3-small | text-embedding-3-small | Also `text-embedding-3-large` |
| `embeddingModelVersion` | 1 | 1 | 1 | As listed by `az cognitiveservices model list` |
| `embeddingDeploymentSku` | GlobalStandard | GlobalStandard | GlobalStandard | `Standard`, `GlobalStandard`, `DataZoneStandard` |
| `embeddingCapacity` | 10 | 10 | 50 | Thousands of tokens per minute; quota is shared per subscription and region |
| `embeddingDimensions` | 1536 | 1536 | 1536 | 256–3072; 3072 for `text-embedding-3-large`. A change needs *Rebuild index* |
| `openAiApiVersion` | 2024-10-21 | 2024-10-21 | 2024-10-21 | An embeddings-capable API version |
| **Search (Azure AI Search)** | | | | |
| `searchSku` | basic | basic | standard | `free` (one per subscription, no semantic ranker or private endpoints), `basic`, `standard`, `standard2`, `standard3` |
| `searchReplicas` | 1 | 1 | 2 | 1–12 (free: 1, basic: up to 3); 2+ for the read SLA |
| `searchPartitions` | 1 | 1 | 1 | `1`, `2`, `3`, `4`, `6`, `12` (free and basic: 1) |
| `searchSemanticSearch` | free | free | standard | `disabled`, `free` (1,000 queries/month), `standard` (pay per query) |
| `searchIndexName` | advance-search | advance-search | advance-search | Created by the app |
| **Web app** | | | | |
| `existingAppServicePlanId` | (set by `deploy.sh` from `demo.env`) | "" | "" | Resource ID of an existing Linux plan; empty = create a plan |
| `webAppSku` | B1 (unused) | B1 | P0v3 | `B1`–`B3`, `S1`–`S3`, `P0v3`–`P3v3` (new plan only) |
| `webAppInstanceCount` | 1 (unused) | 1 | 2 | 1–10 (new plan only) |
| `maxUploadMb` | 20 | 20 | 20 | 1–100 |
| `displayTimeZone` | Asia/Kolkata | Asia/Kolkata | Asia/Kolkata | |
| `authMode` | password | password | password | `password` (Entra ID is planned) |
| **Operations** | | | | |
| `logAnalyticsRetentionDays` | 30 | 30 | 90 | 30–730 |
| `logAnalyticsDailyQuotaGb` | 1 | 1 | -1 | Daily cap; -1 = none |
| `keyVaultSku` | standard | standard | standard | `standard`, `premium` |
| **Network** | | | | |
| `privateNetworking` | false | false | true | Private endpoints for Blob, AI Search, Azure OpenAI, Key Vault; VNet integration |
| `vnetAddressPrefix` / `appSubnetPrefix` / `privateEndpointSubnetPrefix` | – | – | 10.60.0.0/16, 10.60.1.0/24, 10.60.2.0/24 | Must not overlap your other networks |
| `tags` | owner, project, purpose | owner, project, purpose | owner, project, purpose | Added to every resource |

Not in the parameter files: `demoPassword` (pass `--param demoPassword='...'`), `djangoSecretKey` (generated on
every deployment), `deployerPrincipalId` / `deployerPrincipalType` (set by `deploy.sh`).

> dev and prod are **untested**. prod uses private endpoints and disables storage account keys, so its code
> deployment must run from inside the network (see the deployment guide).
