"""Static checks that the ARM template, parameter files, portal form, scripts, app code and docs agree."""
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
ARM = REPO / "Deployment" / "ARM"
TEMPLATE = json.loads((ARM / "azuredeploy.json").read_text())
PARAM_FILES = sorted((ARM / "parameters").glob("*.parameters.json"))
TYPES = {"string": str, "securestring": str, "int": int, "bool": bool, "object": dict, "array": list}


def web_app():
    return next(r for r in TEMPLATE["resources"].values() if r["type"] == "Microsoft.Web/sites") \
        if isinstance(TEMPLATE["resources"], dict) else \
        next(r for r in TEMPLATE["resources"] if r["type"] == "Microsoft.Web/sites")


def resources():
    res = TEMPLATE["resources"]
    return list(res.values()) if isinstance(res, dict) else res


def template_app_settings() -> dict:
    return {s["name"]: s["value"] for s in web_app()["properties"]["siteConfig"]["appSettings"]}


def test_template_is_compiled_from_bicep_source():
    assert (ARM / "azuredeploy.bicep").is_file()
    assert TEMPLATE["$schema"].endswith("deploymentTemplate.json#")


def test_parameter_files_exist():
    assert [p.name for p in PARAM_FILES] == ["demo.parameters.json", "dev.parameters.json", "prod.parameters.json"]


@pytest.mark.parametrize("path", PARAM_FILES, ids=lambda p: p.name)
def test_parameter_files_match_template(path):
    values = json.loads(path.read_text())["parameters"]
    for name, item in values.items():
        assert name in TEMPLATE["parameters"], f"{name} is not a template parameter"
        spec = TEMPLATE["parameters"][name]
        value = item["value"]
        assert isinstance(value, TYPES[spec["type"].lower()]), f"{name} has the wrong type"
        if "allowedValues" in spec:
            assert value in spec["allowedValues"], f"{name}={value} not in {spec['allowedValues']}"
        if "minValue" in spec:
            assert value >= spec["minValue"], f"{name}={value} < {spec['minValue']}"
        if "maxValue" in spec:
            assert value <= spec["maxValue"], f"{name}={value} > {spec['maxValue']}"
        if "maxLength" in spec:
            assert len(value) <= spec["maxLength"]
    assert "demoPassword" not in values and "djangoSecretKey" not in values  # secrets never in files


def test_demo_parameters_are_the_cheapest_working_set():
    v = {k: i["value"] for k, i in json.loads((ARM / "parameters/demo.parameters.json").read_text())["parameters"].items()}
    assert v["environmentName"] == "demo" and v["storageSku"] == "Standard_LRS"
    assert (v["searchSku"], v["searchReplicas"], v["searchPartitions"], v["searchSemanticSearch"]) == ("basic", 1, 1, "free")
    assert (v["embeddingModelName"], v["embeddingCapacity"], v["embeddingDimensions"]) == ("text-embedding-3-small", 10, 1536)
    assert v["openAiLocation"] == "southindia" and v["location"] == "centralindia"
    assert (v["logAnalyticsRetentionDays"], v["logAnalyticsDailyQuotaGb"]) == (30, 1)
    assert v["keyVaultSku"] == "standard" and v["authMode"] == "password" and v["privateNetworking"] is False
    assert v["existingAppServicePlanId"] == ""  # filled in by deploy.sh from demo.env
    assert v["tags"] == {"owner": "TTNS", "project": "advance-search", "purpose": "demo"}


def test_prod_parameters():
    v = {k: i["value"] for k, i in json.loads((ARM / "parameters/prod.parameters.json").read_text())["parameters"].items()}
    assert v["privateNetworking"] is True and v["allowSharedKeyAccess"] is False
    assert (v["searchSku"], v["searchReplicas"], v["searchSemanticSearch"]) == ("standard", 2, "standard")
    assert v["webAppSku"] in ("P0v3", "S1")


def test_ui_definition_outputs_are_parameters_and_values_allowed():
    ui = json.loads((ARM / "createUiDefinition.json").read_text())
    outputs = ui["parameters"]["outputs"]
    for name in outputs:
        assert name in TEMPLATE["parameters"], f"createUiDefinition output {name} is not a template parameter"
    elements = list(ui["parameters"]["basics"])
    for step in ui["parameters"]["steps"]:
        elements += step["elements"]
    for el in elements:
        if el["type"] != "Microsoft.Common.DropDown" or el["name"] not in TEMPLATE["parameters"]:
            continue
        spec = TEMPLATE["parameters"][el["name"]]
        for option in el["constraints"]["allowedValues"]:
            value = option["value"]
            typed = {"int": lambda x: int(x), "bool": lambda x: x == "true"}.get(spec["type"], lambda x: x)(value)
            if "allowedValues" in spec:
                assert typed in spec["allowedValues"], f"{el['name']} option {value}"
            if "minValue" in spec:
                assert typed >= spec["minValue"]


def test_outputs():
    assert set(TEMPLATE["outputs"]) == {"webAppName", "webAppUrl", "storageAccountName", "keyVaultName",
                                        "searchServiceName", "searchEndpoint", "openAiEndpoint"}


def test_names_follow_the_convention():
    text = (ARM / "azuredeploy.bicep").read_text()
    assert "uniqueString(resourceGroup().id" in text
    assert "var baseName = '${prefix}-${environmentName}-${suffix}'" in text
    assert "storage: take('${prefix}${environmentName}${suffix}st', 24)" in text


SECTION_5 = ["ADVSEARCH_MODE", "DJANGO_SECRET_KEY", "AUTH_MODE", "DEMO_PASSWORD", "AZURE_STORAGE_ACCOUNT_URL",
             "CONTAINER_DOCUMENTS", "CONTAINER_CONFIG", "CONTAINER_IMAGES", "SEARCH_ENDPOINT", "SEARCH_INDEX_NAME", "AZURE_OPENAI_ENDPOINT",
             "AZURE_OPENAI_API_VERSION", "EMBEDDING_DEPLOYMENT", "EMBEDDING_DIMENSIONS", "MAX_UPLOAD_MB",
             "DISPLAY_TIME_ZONE", "APPLICATIONINSIGHTS_CONNECTION_STRING", "SCM_DO_BUILD_DURING_DEPLOYMENT",
             "ENVIRONMENT_NAME"]

# Read by the code but deliberately not set by the template: local development, optional overrides, or set by
# the App Service platform itself. Every one is documented in Documents/configuration.md.
NOT_IN_TEMPLATE = {
    "LOCAL_DATA_DIR", "STORAGE_BACKEND", "SEARCH_BACKEND", "EMBEDDING_BACKEND", "AZURE_STORAGE_CONNECTION_STRING",
    "SEARCH_API_KEY", "AZURE_OPENAI_KEY", "ADVSEARCH_CONFIG_DIR", "ADVSEARCH_SAMPLE_DATA_DIR", "INGEST_WORKER",
    "SYNC_INTERVAL_SECONDS", "PROCESSING_STALE_MINUTES", "AZURE_CLIENT_ID", "DJANGO_DEBUG", "DJANGO_ALLOWED_HOSTS",
    "DJANGO_CSRF_TRUSTED_ORIGINS", "DJANGO_SSL_REDIRECT", "CONTENT_SECURITY_POLICY", "LOG_LEVEL",
    "WEBSITE_HOSTNAME", "WEBSITE_INSTANCE_ID", "SEARCH_MIN_MATCH_PERCENT", "SEARCH_RELATIVE_CUTOFF_PERCENT",
    "IMAGE_EXTRACTION", "IMAGE_OCR",
}


def env_vars_read_by_code() -> set[str]:
    pattern = re.compile(r"""\b_?env(?:_int|_bool|_list)?\(\s*["']([A-Z][A-Z0-9_]+)["']""")
    names = set()
    for path in [REPO / "Code/core/advancesearch/config.py", REPO / "Code/webapp/config/settings.py",
                 REPO / "Code/core/advancesearch/ingest.py"]:
        names |= set(pattern.findall(path.read_text()))
    names |= set(re.findall(r'os\.environ\.get\("([A-Z_]+)"', (REPO / "Code/core/advancesearch/ingest.py").read_text()))
    return names


def test_template_sets_every_required_app_setting():
    settings = template_app_settings()
    missing = [n for n in SECTION_5 if n not in settings]
    assert not missing, missing
    assert settings["ADVSEARCH_MODE"] == "azure"
    assert settings["SCM_DO_BUILD_DURING_DEPLOYMENT"] == "false"
    for secret in ("DJANGO_SECRET_KEY", "DEMO_PASSWORD"):
        assert settings[secret].startswith("[format('@Microsoft.KeyVault(VaultName={0};SecretName=")


def test_every_setting_the_code_reads_is_set_or_known_optional():
    read = env_vars_read_by_code()
    assert "SEARCH_ENDPOINT" in read and "DEMO_PASSWORD" in read  # the scan works
    settings = set(template_app_settings())
    unexplained = sorted(read - settings - NOT_IN_TEMPLATE)
    assert not unexplained, f"read by the code but neither set by the template nor listed as optional: {unexplained}"
    unused = sorted(settings - read - {"SCM_DO_BUILD_DURING_DEPLOYMENT", "PYTHONPATH", "APPLICATIONINSIGHTS_CONNECTION_STRING"})
    assert not unused, f"set by the template but not read by the code: {unused}"


def test_every_setting_is_documented():
    doc = (REPO / "Documents/configuration.md").read_text()
    missing = sorted(n for n in env_vars_read_by_code() | set(SECTION_5) if f"`{n}`" not in doc)
    assert not missing, missing


def test_no_keys_in_app_settings():
    for name, value in template_app_settings().items():
        assert not re.search(r"(?i)key|password|secret", name) or "Microsoft.KeyVault" in value, name
        assert "listKeys" not in value


def test_existing_plan_is_never_modified():
    plans = [r for r in resources() if r["type"] == "Microsoft.Web/serverfarms"]
    assert len(plans) == 1
    assert plans[0]["condition"] == "[variables('createPlan')]"
    assert TEMPLATE["variables"]["createPlan"] == "[empty(parameters('existingAppServicePlanId'))]"
    assert "existingAppServicePlanId" in web_app()["properties"]["serverFarmId"]
    assert web_app()["kind"] == "app,linux"
    assert web_app()["properties"]["siteConfig"]["linuxFxVersion"] == "PYTHON|3.12"


def test_role_assignments():
    roles = {"ba92f5b4-2d11-453d-a403-e96b0029c9fe": "Storage Blob Data Contributor",
             "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd": "Cognitive Services OpenAI User",
             "8ebe5a00-799e-43f5-93ac-243d3dce84a7": "Search Index Data Contributor",
             "7ca78c08-252a-4471-8644-bb5ff32d4ba0": "Search Service Contributor",
             "4633458b-17de-408a-b874-0445c86b69e6": "Key Vault Secrets User",
             "b86a8fe4-44ce-4948-aee5-eccb2c155cd7": "Key Vault Secrets Officer"}
    text = json.dumps(TEMPLATE)
    for role_id in roles:
        assert role_id in text, roles[role_id]
    assigned = [r for r in resources() if r["type"] == "Microsoft.Authorization/roleAssignments"]
    assert len(assigned) == 7


def test_private_networking_resources():
    types = {r["type"] for r in resources() if "privateNetworking" in r.get("condition", "")}
    assert {"Microsoft.Network/virtualNetworks", "Microsoft.Network/privateEndpoints",
            "Microsoft.Network/privateDnsZones", "Microsoft.Network/privateDnsZones/virtualNetworkLinks",
            "Microsoft.Network/privateEndpoints/privateDnsZoneGroups"} <= types
    bicep = (ARM / "azuredeploy.bicep").read_text()
    for group in ("'blob'", "'searchService'", "'account'", "'vault'"):
        assert f"group: {group}" in bicep


def test_startup_command_matches_code_script():
    startup = web_app()["properties"]["siteConfig"]["appCommandLine"]
    script = (REPO / "Deployment/scripts/deploy_code_arm.sh").read_text()
    command = re.search(r'STARTUP="([^"]+)"', script).group(1)
    assert command in json.dumps(TEMPLATE)
    assert "--workers 1 --threads 4" in command and command.startswith("python -m gunicorn")
    assert startup  # variable reference to the same command


def test_demo_env_and_no_secrets_in_repository():
    env = (REPO / "Deployment/environments/demo.env").read_text()
    assert 'EXISTING_PLAN_NAME="ccai-demo-gqausd-web-plan"' in env
    assert 'EXISTING_PLAN_RESOURCE_GROUP="Vaibhav.Chaudhary"' in env
    assert 'RESOURCE_GROUP="Vaibhav.Chaudhary"' in env
    guid = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
    allowed = {  # Azure built-in role definition IDs (public, the same in every tenant) and test placeholders
        "ba92f5b4-2d11-453d-a403-e96b0029c9fe", "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd",
        "8ebe5a00-799e-43f5-93ac-243d3dce84a7", "7ca78c08-252a-4471-8644-bb5ff32d4ba0",
        "4633458b-17de-408a-b874-0445c86b69e6", "b86a8fe4-44ce-4948-aee5-eccb2c155cd7",
        "00000000-0000-0000-0000-000000000000", "11111111-2222-3333-4444-555555555555",
    }
    email = re.compile(r"[\w.+-]+@(?!meridian-infra\.example)[A-Za-z][\w-]*\.[A-Za-z]{2,}\b")
    import subprocess

    files = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=REPO,
                           capture_output=True, text=True, check=True).stdout.splitlines()
    for rel in files:
        path = REPO / rel
        if not path.is_file() or path.suffix in {".pdf", ".docx", ".xlsx", ".png", ".js"}:
            continue
        text = path.read_text(errors="ignore")
        found = set(m.lower() for m in guid.findall(text)) - allowed
        assert not found, f"{path}: {found}"
        mails = [m for m in email.findall(text) if not m.startswith(("noreply@", "git@"))]
        assert not mails, f"{path}: {mails}"


def test_every_resource_name_carries_the_solution_prefix():
    """Several apps share one resource group: every resource this template names starts with the prefix
    (default advsrch). Exceptions: child resources, role assignments (GUIDs), and private DNS zones, whose names
    Azure fixes (privatelink.*)."""
    assert TEMPLATE["parameters"]["solutionPrefix"]["defaultValue"] == "advsrch"
    for path in PARAM_FILES:
        assert json.loads(path.read_text())["parameters"]["solutionPrefix"]["value"] == "advsrch"
    names = TEMPLATE["variables"]["names"]
    for role, expression in names.items():
        assert "variables('baseName')" in expression or "variables('prefix')" in expression, role
    for r in resources():
        if "/" in r["type"].split("/", 1)[1] or r["type"] in ("Microsoft.Authorization/roleAssignments",
                                                                "Microsoft.Network/privateDnsZones"):
            continue
        assert "variables('names')" in r["name"] or "variables('baseName')" in r["name"], (r["type"], r["name"])
