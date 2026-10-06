# Application code

Place the Django application for the advance search solution in this folder.
The infrastructure in `templates/` provisions the App Service (Python 3.12,
Linux) that hosts it, and `deploy.sh` wires its settings to Key Vault.

Settings the app can read from the environment once deployed:

| Setting | Source |
|---|---|
| `COSMOS_CONNECTION_STRING` | Key Vault secret `CosmosDbConnectionString` |
| `SEARCH_ADMIN_KEY` | Key Vault secret `SearchAdminKey` |
| `SEARCH_SERVICE_NAME` | App setting |
| `EMBEDDING_ENDPOINT` | Key Vault secret `EmbeddingEndpoint` |
| `EMBEDDING_API_KEY` | Key Vault secret `EmbeddingApiKey` |
| `EMBEDDING_DEPLOYMENT_NAME` | App setting (`embedding-large`) |
