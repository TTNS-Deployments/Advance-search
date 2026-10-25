"""Deployment scripts tested against a fake `az` that records every call and returns canned output.

The real Azure CLI cannot sign in from the development environment, so these tests check what the scripts would
run (order, arguments, management-API-only calls) and how they handle failures.
"""
import base64
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / "Deployment" / "scripts"
OID = "11111111-2222-3333-4444-555555555555"

FAKE_AZ = r'''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_AZ_LOG"], "a") as fh:
    fh.write(json.dumps(args) + "\n")
cmd = " ".join(args)
fail = [f for f in os.environ.get("FAKE_AZ_FAIL", "").split("|") if f]
if any(f in cmd for f in fail):
    sys.stderr.write("ERROR: simulated failure\n")
    sys.exit(1)

def query():
    return args[args.index("--query") + 1] if "--query" in args else ""

outputs = {"webAppName": "asrch-demo-abc123-web", "storageAccountName": "asrchdemoabc123st",
           "webAppUrl": "https://asrch-demo-abc123-web.azurewebsites.net"}
if cmd.startswith("account show"):
    print({"name": "Test Subscription", "user.type": os.environ.get("FAKE_AZ_USER_TYPE", "user")}[query()])
elif cmd.startswith("account get-access-token"):
    print(os.environ["FAKE_AZ_TOKEN"])
elif cmd.startswith("group exists"):
    print(os.environ.get("FAKE_AZ_GROUP_EXISTS", "true"))
elif cmd.startswith("group show"):
    print("centralindia")
elif cmd.startswith("provider show"):
    ns = args[args.index("-n") + 1]
    print("NotRegistered" if ns in os.environ.get("FAKE_AZ_UNREGISTERED", "").split(",") else "Registered")
elif cmd.startswith("appservice plan show"):
    rg, name = args[args.index("-g") + 1], args[args.index("-n") + 1]
    print(f"/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/{rg}/providers/Microsoft.Web/serverfarms/{name}")
elif cmd.startswith("deployment group show"):
    q = query()
    if os.environ.get("FAKE_AZ_NO_OUTPUTS"):
        sys.exit(3)
    print(outputs[q.split(".")[2]])
elif cmd.startswith("storage account keys list"):
    print("ZmFrZWtleQ==")
elif cmd.startswith("storage blob generate-sas"):
    name = args[args.index("-n") + 1]
    print(f"https://asrchdemoabc123st.blob.core.windows.net/code-packages/{name}?sv=2022&sig=x")
elif cmd.startswith("webapp show"):
    print("asrch-demo-abc123-web.azurewebsites.net")
'''


def _token():
    payload = base64.urlsafe_b64encode(json.dumps({"oid": OID}).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJub25lIn0.{payload}.sig"


@pytest.fixture
def fake_az(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    az = bin_dir / "az"
    az.write_text(FAKE_AZ)
    az.chmod(0o755)
    package = tmp_path / "webapp.zip"
    with zipfile.ZipFile(package, "w") as zf:
        zf.writestr("manage.py", "")
    log = tmp_path / "az.log"
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "FAKE_AZ_LOG": str(log),
           "FAKE_AZ_TOKEN": _token(), "PACKAGE_ZIP": str(package)}

    def run(script, *args, **extra_env):
        result = subprocess.run([str(SCRIPTS / script), *args], capture_output=True, text=True,
                                env={**env, **extra_env}, cwd=tmp_path, timeout=120)
        calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        log.unlink(missing_ok=True)
        return result, calls

    return run


def joined(calls):
    return [" ".join(c) for c in calls]


def find(calls, prefix):
    return [c for c in joined(calls) if c.startswith(prefix)]


def test_shellcheck_and_syntax():
    scripts = sorted(SCRIPTS.glob("*.sh"))
    assert {p.name for p in scripts} == {"deploy.sh", "deploy_code_arm.sh", "package.sh"}
    for path in scripts:
        assert os.access(path, os.X_OK), f"{path.name} is not executable"
        subprocess.run(["bash", "-n", str(path)], check=True)
    import sys

    local = Path(sys.executable).parent / "shellcheck"
    shellcheck = shutil.which("shellcheck") or (str(local) if local.exists() else None)
    if not shellcheck:
        pytest.skip("shellcheck not installed (pip install shellcheck-py)")
    subprocess.run([shellcheck, *map(str, scripts)], check=True)


@pytest.mark.parametrize("script", ["deploy.sh", "deploy_code_arm.sh", "package.sh"])
def test_help(script, fake_az):
    result, calls = fake_az(script, "--help")
    assert result.returncode == 0
    assert "Usage" in result.stdout or "Deployment/scripts/" in result.stdout
    assert calls == []


def test_demo_deployment_uses_management_api_only(fake_az):
    result, calls = fake_az("deploy.sh", "-e", "demo", "--param", "demoPassword=s3cret-Pass")
    assert result.returncode == 0, result.stderr
    cmds = joined(calls)
    # Existing resource group reused, never created.
    assert not find(calls, "group create")
    # The shared plan is looked up by name from demo.env and passed by ID; nothing changes the plan.
    assert find(calls, "appservice plan show -g Vaibhav.Chaudhary -n ccai-demo-gqausd-web-plan --query id -o tsv")
    assert not [c for c in cmds if c.startswith(("appservice plan update", "appservice plan create"))]
    create = find(calls, "deployment group create")[0]
    assert "-n advancesearch-demo" in create
    assert "@" + str(REPO / "Deployment/ARM/parameters/demo.parameters.json") in create
    assert f"deployerPrincipalId={OID}" in create and "deployerPrincipalType=User" in create
    assert "existingAppServicePlanId=/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/" \
           "Vaibhav.Chaudhary/providers/Microsoft.Web/serverfarms/ccai-demo-gqausd-web-plan" in create
    assert "demoPassword=s3cret-Pass" in create
    # Code step after the infrastructure step.
    i_create = cmds.index(create)
    settings = find(calls, "webapp config appsettings set")[0]
    assert cmds.index(settings) > i_create
    assert "WEBSITE_RUN_FROM_PACKAGE=https://asrchdemoabc123st.blob.core.windows.net/code-packages/webapp-" in settings
    assert "SCM_DO_BUILD_DURING_DEPLOYMENT=false" in settings and "PYTHONPATH=/home/site/wwwroot/.packages" in settings
    startup = find(calls, "webapp config set")[0]
    assert "--workers 1 --threads 4" in startup and "python -m gunicorn" in startup
    sas = find(calls, "storage blob generate-sas")[0]
    assert "--permissions r" in sas and "--https-only" in sas and "--account-key ZmFrZWtleQ==" in sas
    # demo.env sets SEED=1: the sample documents are uploaded with the account key, before the restart.
    seeds = [c for c in find(calls, "storage blob upload") if "-c documents" in c]
    assert len(seeds) == 13
    assert all("--account-key" in c for c in find(calls, "storage blob upload"))
    assert cmds.index(find(calls, "webapp restart")[0]) > cmds.index(seeds[-1])
    # Never uses data-plane tokens, Kudu or Graph.
    forbidden = ("ad ", "webapp deploy", "functionapp", "keyvault secret", "webapp up")
    assert not [c for c in cmds if c.startswith(forbidden) or "--auth-mode login" in c]
    assert "Done. Web app: https://asrch-demo-abc123-web.azurewebsites.net" in result.stdout
    assert "demo password" in result.stdout


def test_missing_shared_plan_stops_before_deploying(fake_az):
    result, calls = fake_az("deploy.sh", "-e", "demo", FAKE_AZ_FAIL="appservice plan show")
    assert result.returncode == 1
    assert "App Service plan 'ccai-demo-gqausd-web-plan' was not found" in result.stderr
    assert not find(calls, "deployment group create")


def test_unregistered_providers_are_registered(fake_az):
    result, calls = fake_az("deploy.sh", "-e", "demo", FAKE_AZ_UNREGISTERED="Microsoft.Search,Microsoft.Insights")
    assert result.returncode == 0, result.stderr
    assert find(calls, "provider register -n Microsoft.Search --wait")
    assert find(calls, "provider register -n Microsoft.Insights --wait")
    assert not find(calls, "provider register -n Microsoft.Web")
    assert not [c for c in joined(calls) if "Microsoft.Network" in c]  # only checked for private networking


def test_failed_provider_registration_warns_and_continues(fake_az):
    result, calls = fake_az("deploy.sh", "-e", "demo", FAKE_AZ_UNREGISTERED="Microsoft.Search",
                            FAKE_AZ_FAIL="provider register")
    assert result.returncode == 0
    assert "could not be registered: Microsoft.Search" in result.stderr
    assert "az provider register -n <namespace> --wait" in result.stderr
    assert find(calls, "deployment group create")


def test_private_networking_checks_network_provider(fake_az):
    result, calls = fake_az("deploy.sh", "-e", "prod", "-g", "rg-prod")
    assert result.returncode == 0, result.stderr
    assert find(calls, "provider show -n Microsoft.Network")
    assert not find(calls, "appservice plan show")  # prod creates its own plan
    assert "existingAppServicePlanId" not in find(calls, "deployment group create")[0]


def test_new_resource_group_is_created_when_missing(fake_az):
    result, calls = fake_az("deploy.sh", "-e", "dev", "-g", "rg-new", "-l", "southindia", FAKE_AZ_GROUP_EXISTS="false")
    assert result.returncode == 0, result.stderr
    assert find(calls, "group create -n rg-new -l southindia")
    assert not [c for c in find(calls, "storage blob upload") if "-c documents" in c]  # dev: no seed by default


def test_skip_infra_only_deploys_code(fake_az):
    result, calls = fake_az("deploy.sh", "-e", "demo", "--skip-infra", "--no-seed")
    assert result.returncode == 0, result.stderr
    assert not find(calls, "deployment group create")
    assert not find(calls, "provider")
    assert find(calls, "webapp config appsettings set")
    assert not [c for c in find(calls, "storage blob upload") if "-c documents" in c]


def test_skip_code_warns(fake_az):
    result, calls = fake_az("deploy.sh", "-e", "demo", "--skip-code")
    assert result.returncode == 0
    assert "has no code package" in result.stderr
    assert find(calls, "deployment group create")
    assert not find(calls, "webapp config appsettings set")


def test_service_principal_deployer(fake_az):
    result, calls = fake_az("deploy.sh", "-e", "demo", "--skip-code", FAKE_AZ_USER_TYPE="servicePrincipal")
    assert "deployerPrincipalType=ServicePrincipal" in find(calls, "deployment group create")[0]


@pytest.mark.parametrize("args,message", [
    ([], "Usage"), (["-e", "staging", "-g", "x"], "Parameters file not found"), (["-e", "dev"], "No resource group"),
    (["-e", "demo", "--bogus"], "Unknown option"),
])
def test_argument_errors(fake_az, args, message):
    result, calls = fake_az("deploy.sh", *args)
    assert result.returncode == 1
    assert message in result.stderr
    assert not find(calls, "deployment group create")


def test_code_step_without_infrastructure_outputs(fake_az):
    result, calls = fake_az("deploy_code_arm.sh", "-g", "rg", "-e", "demo", FAKE_AZ_NO_OUTPUTS="1")
    assert result.returncode == 1
    assert "Run the infrastructure step first" in result.stderr


def test_code_step_without_shared_key_access(fake_az):
    result, calls = fake_az("deploy_code_arm.sh", "-g", "rg", "-e", "demo", FAKE_AZ_FAIL="storage account keys list")
    assert result.returncode == 1
    assert "allowSharedKeyAccess=true" in result.stderr
    assert not find(calls, "webapp config appsettings set")


def test_seed_only(fake_az):
    result, calls = fake_az("deploy_code_arm.sh", "-g", "rg", "-e", "demo", "--seed-only")
    assert result.returncode == 0, result.stderr
    assert not find(calls, "webapp config appsettings set")
    uploads = [c for c in find(calls, "storage blob upload") if "-c documents" in c]
    assert len(uploads) == 13 and not [c for c in uploads if "queries.yaml" in c or "generate.py" in c]
    assert find(calls, "webapp restart")


def test_failed_deployment_stops_the_script(fake_az):
    result, calls = fake_az("deploy.sh", "-e", "demo", FAKE_AZ_FAIL="deployment group create")
    assert result.returncode != 0
    assert not find(calls, "webapp config appsettings set")
