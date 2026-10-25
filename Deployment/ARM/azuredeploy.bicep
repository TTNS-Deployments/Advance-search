// Advance Search: every Azure resource in one template.
// Source of Deployment/ARM/azuredeploy.json. After editing, rebuild the JSON:
//   bicep build Deployment/ARM/azuredeploy.bicep --outfile Deployment/ARM/azuredeploy.json
// (or: az bicep build --file Deployment/ARM/azuredeploy.bicep --outfile Deployment/ARM/azuredeploy.json)

metadata description = 'Advance Search: meaning-based search over PDF, Word and Excel documents (web app, Blob Storage, Azure OpenAI embeddings, Azure AI Search, Key Vault, monitoring).'

// ---------------------------------------------------------------------------- naming

@description('Short lowercase alphanumeric prefix for all resource names (3-8 characters).')
@minLength(3)
@maxLength(8)
param solutionPrefix string = 'advsrch'

@description('Environment name, used in resource names and tags.')
@allowed(['demo', 'dev', 'test', 'uat', 'prod'])
param environmentName string = 'dev'

@description('Region for all resources except Azure OpenAI (see openAiLocation). With an existing App Service plan, this must be the plan\'s region.')
param location string = resourceGroup().location

@description('Extra tags applied to every resource.')
param tags object = {}

// ---------------------------------------------------------------------------- storage

@description('Storage redundancy.')
@allowed(['Standard_LRS', 'Standard_ZRS', 'Standard_GRS', 'Standard_RAGRS', 'Standard_GZRS'])
param storageSku string = 'Standard_LRS'

@description('Allow storage account keys (shared key). Needed by Deployment/scripts/deploy_code_arm.sh, which uploads the code package with the account key.')
param allowSharedKeyAccess bool = true

@description('Days that deleted blobs and containers can be restored (soft delete).')
@minValue(1)
@maxValue(365)
param blobSoftDeleteDays int = 7

// ---------------------------------------------------------------------------- monitoring and Key Vault

@description('Log Analytics retention in days.')
@minValue(30)
@maxValue(730)
param logAnalyticsRetentionDays int = 30

@description('Log Analytics daily ingestion cap in GB (-1 = no cap).')
@minValue(-1)
param logAnalyticsDailyQuotaGb int = 1

@description('Key Vault tier.')
@allowed(['standard', 'premium'])
param keyVaultSku string = 'standard'

// ---------------------------------------------------------------------------- Azure OpenAI (embeddings)

@description('Region of the Azure OpenAI resource. Must offer the embedding model and deployment type, with quota in your subscription.')
param openAiLocation string = 'southindia'

@description('Embedding model (for example text-embedding-3-small or text-embedding-3-large).')
param embeddingModelName string = 'text-embedding-3-small'

@description('Embedding model version.')
param embeddingModelVersion string = '1'

@description('Deployment type of the embedding model.')
@allowed(['Standard', 'GlobalStandard', 'DataZoneStandard'])
param embeddingDeploymentSku string = 'GlobalStandard'

@description('Embedding deployment capacity in thousands of tokens per minute.')
@minValue(1)
param embeddingCapacity int = 10

@description('Vector size. 1536 for text-embedding-3-small, 3072 for text-embedding-3-large (or a smaller value; text-embedding-3 models can shorten vectors). Changing it needs an index rebuild.')
@minValue(256)
@maxValue(3072)
param embeddingDimensions int = 1536

@description('Azure OpenAI API version used for embeddings.')
param openAiApiVersion string = '2024-10-21'

// ---------------------------------------------------------------------------- Azure AI Search

@description('Azure AI Search tier. Free: one per subscription, no semantic ranker, no private endpoints, 50 MB.')
@allowed(['free', 'basic', 'standard', 'standard2', 'standard3'])
param searchSku string = 'basic'

@description('Search replicas (free: 1; basic: up to 3).')
@minValue(1)
@maxValue(12)
param searchReplicas int = 1

@description('Search partitions (free and basic: 1).')
@allowed([1, 2, 3, 4, 6, 12])
param searchPartitions int = 1

@description('Semantic ranker plan. free = 1,000 semantic queries per month; ignored on the free search tier.')
@allowed(['disabled', 'free', 'standard'])
param searchSemanticSearch string = 'free'

@description('Name of the search index (created by the web app).')
param searchIndexName string = 'advance-search'

// ---------------------------------------------------------------------------- web app

@description('Resource ID of an existing Linux App Service plan to host the web app. Empty = create a new plan. An existing plan is never modified.')
param existingAppServicePlanId string = ''

@description('App Service plan SKU (only when a new plan is created).')
@allowed(['B1', 'B2', 'B3', 'S1', 'S2', 'S3', 'P0v3', 'P1v3', 'P2v3', 'P3v3'])
param webAppSku string = 'B1'

@description('Number of plan instances (only when a new plan is created).')
@minValue(1)
@maxValue(10)
param webAppInstanceCount int = 1

@description('Largest upload in MB.')
@minValue(1)
@maxValue(100)
param maxUploadMb int = 20

@description('Time zone for dates shown in the web app.')
param displayTimeZone string = 'Asia/Kolkata'

@description('Sign-in mode. password = one shared demo password plus a role choice (Admin or User).')
@allowed(['password'])
param authMode string = 'password'

@description('Shared demo password, stored in Key Vault as demo-password. Leave empty on redeploys to keep the current one.')
@secure()
param demoPassword string = ''

@description('Django secret key. Generated on every deployment unless given (a new key signs everyone out).')
@secure()
param djangoSecretKey string = newGuid()

// ---------------------------------------------------------------------------- identity of the deployer

@description('Object ID of the identity running the deployment; gets Storage Blob Data Contributor and Key Vault Secrets Officer. Empty = skip.')
param deployerPrincipalId string = ''

@description('Type of deployerPrincipalId.')
@allowed(['User', 'ServicePrincipal', 'Group'])
param deployerPrincipalType string = 'User'

// ---------------------------------------------------------------------------- private networking

@description('Private endpoints for Blob Storage, AI Search, Azure OpenAI and Key Vault; the web app reaches them through VNet integration and they refuse public traffic. Needs a Basic or higher search tier.')
param privateNetworking bool = false

@description('VNet address range (private networking only).')
param vnetAddressPrefix string = '10.60.0.0/16'

@description('Subnet for the web app\'s VNet integration (private networking only).')
param appSubnetPrefix string = '10.60.1.0/24'

@description('Subnet for the private endpoints (private networking only).')
param privateEndpointSubnetPrefix string = '10.60.2.0/24'

// ============================================================================ variables

var suffix = take(uniqueString(resourceGroup().id, solutionPrefix, environmentName), 6)
var prefix = toLower(solutionPrefix)
var baseName = '${prefix}-${environmentName}-${suffix}'
var names = {
  keyVault: '${baseName}-kv'
  storage: take('${prefix}${environmentName}${suffix}st', 24)
  logs: '${baseName}-log'
  appInsights: '${baseName}-appi'
  openAi: '${baseName}-openai'
  search: '${baseName}-search'
  plan: '${baseName}-plan'
  web: '${baseName}-web'
  vnet: '${baseName}-vnet'
}
var allTags = union(tags, { solution: 'advance-search', environment: environmentName })
var containers = ['documents', 'config', 'code-packages']
var createPlan = empty(existingAppServicePlanId)
var planTiers = {
  B1: 'Basic'
  B2: 'Basic'
  B3: 'Basic'
  S1: 'Standard'
  S2: 'Standard'
  S3: 'Standard'
  P0v3: 'Premium0V3'
  P1v3: 'PremiumV3'
  P2v3: 'PremiumV3'
  P3v3: 'PremiumV3'
}
var startupCommand = 'python -m gunicorn --bind=0.0.0.0:8000 --timeout 600 --workers 1 --threads 4 config.wsgi'
var roles = {
  blobDataContributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  openAiUser: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
  searchIndexDataContributor: '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
  searchServiceContributor: '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
  keyVaultSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6'
  keyVaultSecretsOfficer: 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'
}
var publicAccess = privateNetworking ? 'Disabled' : 'Enabled'
var semanticSetting = searchSku == 'free' ? {} : { semanticSearch: searchSemanticSearch }

// ============================================================================ 1. Key Vault

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: names.keyVault
  location: location
  tags: allTags
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: keyVaultSku }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    publicNetworkAccess: publicAccess
    networkAcls: { defaultAction: privateNetworking ? 'Deny' : 'Allow', bypass: 'AzureServices' }
  }
}

resource secretDjango 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'django-secret-key'
  properties: { value: djangoSecretKey }
}

// Created only when a password is given, so a redeploy without --param demoPassword keeps the current one.
resource secretDemoPassword 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(demoPassword)) {
  parent: keyVault
  name: 'demo-password'
  properties: { value: demoPassword }
}

// ============================================================================ 2. Storage

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: names.storage
  location: location
  tags: allTags
  kind: 'StorageV2'
  sku: { name: storageSku }
  properties: {
    accessTier: 'Hot'
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    allowSharedKeyAccess: allowSharedKeyAccess
    publicNetworkAccess: publicAccess
    networkAcls: { defaultAction: privateNetworking ? 'Deny' : 'Allow', bypass: 'AzureServices' }
    encryption: {
      keySource: 'Microsoft.Storage'
      services: { blob: { enabled: true } }
    }
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    deleteRetentionPolicy: { enabled: true, days: blobSoftDeleteDays }
    containerDeleteRetentionPolicy: { enabled: true, days: blobSoftDeleteDays }
  }
}

resource blobContainers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [for c in containers: {
  parent: blobService
  name: c
  properties: { publicAccess: 'None' }
}]

// ============================================================================ 3. Monitoring

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: names.logs
  location: location
  tags: allTags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: logAnalyticsRetentionDays
    workspaceCapping: { dailyQuotaGb: logAnalyticsDailyQuotaGb }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: names.appInsights
  location: location
  tags: allTags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
  }
}

// ============================================================================ 4. Azure OpenAI (embeddings only)

resource openAi 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: names.openAi
  location: openAiLocation
  tags: allTags
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: names.openAi
    publicNetworkAccess: publicAccess
    networkAcls: { defaultAction: privateNetworking ? 'Deny' : 'Allow' }
  }
}

resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openAi
  name: embeddingModelName
  sku: { name: embeddingDeploymentSku, capacity: embeddingCapacity }
  properties: {
    model: { format: 'OpenAI', name: embeddingModelName, version: embeddingModelVersion }
  }
}

// ============================================================================ 5. Azure AI Search

resource search 'Microsoft.Search/searchServices@2023-11-01' = {
  name: names.search
  location: location
  tags: allTags
  sku: { name: searchSku }
  properties: union({
    replicaCount: searchReplicas
    partitionCount: searchPartitions
    hostingMode: 'default'
    publicNetworkAccess: privateNetworking ? 'disabled' : 'enabled'
    authOptions: { aadOrApiKey: { aadAuthFailureMode: 'http401WithBearerChallenge' } }
  }, semanticSetting)
}

// ============================================================================ 6. App Service plan (only without an existing plan)

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = if (createPlan) {
  name: names.plan
  location: location
  tags: allTags
  kind: 'linux'
  sku: { name: webAppSku, tier: planTiers[webAppSku], capacity: webAppInstanceCount }
  properties: { reserved: true }
}

// ============================================================================ 9a. Network (private networking only)

resource vnet 'Microsoft.Network/virtualNetworks@2024-01-01' = if (privateNetworking) {
  name: names.vnet
  location: location
  tags: allTags
  properties: {
    addressSpace: { addressPrefixes: [vnetAddressPrefix] }
    subnets: [
      {
        name: 'app'
        properties: {
          addressPrefix: appSubnetPrefix
          delegations: [{ name: 'web', properties: { serviceName: 'Microsoft.Web/serverFarms' } }]
        }
      }
      {
        name: 'private-endpoints'
        properties: { addressPrefix: privateEndpointSubnetPrefix, privateEndpointNetworkPolicies: 'Disabled' }
      }
    ]
  }
}

// ============================================================================ 7. Web app

resource web 'Microsoft.Web/sites@2024-04-01' = {
  name: names.web
  location: location
  tags: union(allTags, { 'azd-service-name': 'web' })
  kind: 'app,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: createPlan ? plan.id : existingAppServicePlanId
    httpsOnly: true
    clientAffinityEnabled: false
    keyVaultReferenceIdentity: 'SystemAssigned'
    virtualNetworkSubnetId: privateNetworking ? '${vnet.id}/subnets/app' : null
    vnetRouteAllEnabled: privateNetworking
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.12'
      appCommandLine: startupCommand
      alwaysOn: true
      http20Enabled: true
      minTlsVersion: '1.2'
      scmMinTlsVersion: '1.2'
      ftpsState: 'Disabled'
      healthCheckPath: '/healthz'
      vnetRouteAllEnabled: privateNetworking
      appSettings: [
        { name: 'ADVSEARCH_MODE', value: 'azure' }
        { name: 'ENVIRONMENT_NAME', value: environmentName }
        { name: 'DJANGO_SECRET_KEY', value: '@Microsoft.KeyVault(VaultName=${names.keyVault};SecretName=django-secret-key)' }
        { name: 'AUTH_MODE', value: authMode }
        { name: 'DEMO_PASSWORD', value: '@Microsoft.KeyVault(VaultName=${names.keyVault};SecretName=demo-password)' }
        { name: 'AZURE_STORAGE_ACCOUNT_URL', value: storage.properties.primaryEndpoints.blob }
        { name: 'CONTAINER_DOCUMENTS', value: 'documents' }
        { name: 'CONTAINER_CONFIG', value: 'config' }
        { name: 'SEARCH_ENDPOINT', value: 'https://${names.search}.search.windows.net' }
        { name: 'SEARCH_INDEX_NAME', value: searchIndexName }
        { name: 'AZURE_OPENAI_ENDPOINT', value: openAi.properties.endpoint }
        { name: 'AZURE_OPENAI_API_VERSION', value: openAiApiVersion }
        { name: 'EMBEDDING_DEPLOYMENT', value: embeddingDeployment.name }
        { name: 'EMBEDDING_DIMENSIONS', value: string(embeddingDimensions) }
        { name: 'MAX_UPLOAD_MB', value: string(maxUploadMb) }
        { name: 'DISPLAY_TIME_ZONE', value: displayTimeZone }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'false' }
        { name: 'PYTHONPATH', value: '/home/site/wwwroot/.packages' }
      ]
    }
  }
}

// No FTP or basic-auth publishing; code is deployed from a package URL (Deployment/scripts/deploy_code_arm.sh).
resource webFtp 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2024-04-01' = {
  parent: web
  name: 'ftp'
  properties: { allow: false }
}

// ============================================================================ 8. Role assignments (ARM only, no Graph)

resource webBlob 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, 'web', roles.blobDataContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.blobDataContributor)
    principalId: web.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource webOpenAi 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: openAi
  name: guid(openAi.id, 'web', roles.openAiUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.openAiUser)
    principalId: web.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource webSearchData 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: search
  name: guid(search.id, 'web', roles.searchIndexDataContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.searchIndexDataContributor)
    principalId: web.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource webSearchService 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: search
  name: guid(search.id, 'web', roles.searchServiceContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.searchServiceContributor)
    principalId: web.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource webKeyVault 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: keyVault
  name: guid(keyVault.id, 'web', roles.keyVaultSecretsUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.keyVaultSecretsUser)
    principalId: web.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource deployerBlob 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(deployerPrincipalId)) {
  scope: storage
  name: guid(storage.id, 'deployer', deployerPrincipalId, roles.blobDataContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.blobDataContributor)
    principalId: deployerPrincipalId
    principalType: deployerPrincipalType
  }
}

resource deployerKeyVault 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(deployerPrincipalId)) {
  scope: keyVault
  name: guid(keyVault.id, 'deployer', deployerPrincipalId, roles.keyVaultSecretsOfficer)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.keyVaultSecretsOfficer)
    principalId: deployerPrincipalId
    principalType: deployerPrincipalType
  }
}

// ============================================================================ 9b. Private endpoints and DNS (private networking only)

var privateLinks = [
  { name: 'blob', id: storage.id, group: 'blob', zone: 'privatelink.blob.${environment().suffixes.storage}' }
  { name: 'search', id: search.id, group: 'searchService', zone: 'privatelink.search.windows.net' }
  { name: 'openai', id: openAi.id, group: 'account', zone: 'privatelink.openai.azure.com' }
  { name: 'vault', id: keyVault.id, group: 'vault', zone: 'privatelink.vaultcore.azure.net' }
]

resource dnsZones 'Microsoft.Network/privateDnsZones@2020-06-01' = [for link in privateLinks: if (privateNetworking) {
  name: link.zone
  location: 'global'
  tags: allTags
}]

resource dnsLinks 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = [for (link, i) in privateLinks: if (privateNetworking) {
  parent: dnsZones[i]
  name: '${names.vnet}-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: { id: vnet.id }
  }
}]

resource privateEndpoints 'Microsoft.Network/privateEndpoints@2024-01-01' = [for link in privateLinks: if (privateNetworking) {
  name: '${baseName}-pe-${link.name}'
  location: location
  tags: allTags
  properties: {
    subnet: { id: '${vnet.id}/subnets/private-endpoints' }
    privateLinkServiceConnections: [
      {
        name: link.name
        properties: { privateLinkServiceId: link.id, groupIds: [link.group] }
      }
    ]
  }
}]

resource dnsZoneGroups 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-01-01' = [for (link, i) in privateLinks: if (privateNetworking) {
  parent: privateEndpoints[i]
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [{ name: link.name, properties: { privateDnsZoneId: dnsZones[i].id } }]
  }
}]

// ============================================================================ outputs

output webAppName string = web.name
output webAppUrl string = 'https://${web.properties.defaultHostName}'
output storageAccountName string = storage.name
output keyVaultName string = keyVault.name
output searchServiceName string = search.name
output searchEndpoint string = 'https://${names.search}.search.windows.net'
output openAiEndpoint string = openAi.properties.endpoint
