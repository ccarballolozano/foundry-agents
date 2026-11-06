"""Provision (or update) the knowledge stack behind hr-agent. Safe to run again.

Run from the repo root, signed in with `az login` and `azd auth login`:

    python agents/hr-agent/provision/provision.py              # create or update
    python agents/hr-agent/provision/provision.py --teardown   # remove knowledge objects, toolboxes, connections

Steps, in order (each one checks what exists first and only changes what differs):
  1. Azure resources: search service, storage account + container, embedding deployment.
  2. Roles for the search service's identity (read the handbook blobs, call the models).
  3. Handbook sync: upload changed files, delete blobs that no longer exist locally.
  4. Knowledge source `hr-handbook-ks` and knowledge base `hr-handbook-kb`, then wait for ingestion.
  5. Connections `hr-kb` / `hr-kb-dev` and toolboxes `hr-agent-toolbox` / `hr-agent-toolbox-dev`.
  6. Roles for callers: the developer and, once deployed, hr-agent's own identity.

All names and endpoints come from the azd environment. Authentication is keyless
(your Entra sign-in); no key or connection secret is read, stored or printed.
Role assignments you are not allowed to create are listed at the end as
commands for someone with Owner or User Access Administrator.
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import yaml
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.identity import AzureCliCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient, SearchIndexerClient
from azure.search.documents.indexes.models import AzureBlobKnowledgeSource, KnowledgeBase
from azure.storage.blob import BlobServiceClient, ContentSettings

# --- Pinned versions (also listed in the README) ---------------------------------
SEARCH_API_VERSION = "2026-08-01-preview"  # knowledge sources, knowledge bases, KB MCP endpoint
TOOLBOX_API_VERSION = "v1"  # Foundry toolboxes

# --- Fixed names -----------------------------------------------------------------
HERE = Path(__file__).parent
HANDBOOK_DIR = HERE.parent / "knowledge" / "handbook"
CONTAINER = "hr-handbook"
KNOWLEDGE_SOURCE = "hr-handbook-ks"
KNOWLEDGE_BASE = "hr-handbook-kb"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_MODEL_VERSION = "1"
SEARCH_AUDIENCE = "https://search.azure.com"
TOOLBOXES = {
    # toolbox name: (definition file, connection name, connection auth type)
    "hr-agent-toolbox": ("toolbox.yaml", "hr-kb", "agentic-identity"),
    "hr-agent-toolbox-dev": ("toolbox-dev.yaml", "hr-kb-dev", "user-entra-token"),
}

ROLE_SEARCH_INDEX_DATA_READER = "Search Index Data Reader"
ROLE_STORAGE_BLOB_DATA_READER = "Storage Blob Data Reader"
ROLE_COGNITIVE_SERVICES_USER = "Cognitive Services User"

credential = AzureCliCredential()
pending_roles: list[str] = []  # commands for an admin, printed at the end


# --- Small helpers -----------------------------------------------------------------
def step(title: str) -> None:
    print(f"\n=== {title}")


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def az(*args: str) -> object:
    """Run an az CLI command and return its JSON output (None when empty)."""
    out = run(["az", *args, "-o", "json"]).stdout.strip()
    return json.loads(out) if out else None


def az_exists(*args: str) -> object | None:
    result = run(["az", *args, "-o", "json"], check=False)
    return json.loads(result.stdout) if result.returncode == 0 and result.stdout.strip() else None


def azd(*args: str) -> str:
    result = run(["azd", *args, "--no-prompt"], check=False)
    if result.returncode != 0:
        sys.exit(f"azd {' '.join(args)} failed:\n{result.stderr or result.stdout}")
    return result.stdout


def azd_json(*args: str) -> object:
    # azd may print update notices before the JSON; keep only the JSON part.
    out = azd(*args, "-o", "json")
    start = min(i for i in (out.find("{"), out.find("[")) if i >= 0)
    return json.loads(out[start:])


def load_env() -> dict[str, str]:
    values = azd_json("env", "get-values")
    return {k: str(v) for k, v in values.items()}


def env_set(env: dict[str, str], name: str, value: str) -> None:
    if env.get(name) != value:
        azd("env", "set", name, value)
        env[name] = value
        print(f"  azd env: {name}={value}")


# --- Step 1: Azure resources ------------------------------------------------------
def resolve_names(env: dict[str, str]) -> None:
    """Defaults derive from the azd environment name; resolved values are written back."""
    base = re.sub(r"[^a-z0-9]", "", env["AZURE_ENV_NAME"].lower())
    suffix = hashlib.sha1(env["AZURE_SUBSCRIPTION_ID"].encode()).hexdigest()[:4]
    env_set(env, "HR_AGENT_SEARCH_SERVICE", env.get("HR_AGENT_SEARCH_SERVICE") or f"{base[:50]}-{suffix}-srch")
    env_set(env, "HR_AGENT_STORAGE_ACCOUNT", env.get("HR_AGENT_STORAGE_ACCOUNT") or f"{base[:16]}{suffix}hr")
    env_set(env, "HR_AGENT_EMBEDDING_DEPLOYMENT", env.get("HR_AGENT_EMBEDDING_DEPLOYMENT") or EMBEDDING_MODEL)
    if not env.get("ENVIRONMENT_TIER") and env["AZURE_ENV_NAME"].endswith("-dev"):
        env_set(env, "ENVIRONMENT_TIER", "dev")


def ensure_search_service(env: dict[str, str]) -> dict:
    rg, name = env["AZURE_RESOURCE_GROUP"], env["HR_AGENT_SEARCH_SERVICE"]
    service = az_exists("search", "service", "show", "-g", rg, "-n", name)
    if service is None:
        print(f"  creating search service {name} (basic, semantic ranker, system identity)...")
        service = az("search", "service", "create", "-g", rg, "-n", name, "-l", env["AZURE_LOCATION"],
                     "--sku", "basic", "--semantic-search", "free", "--identity-type", "SystemAssigned",
                     "--auth-options", "aadOrApiKey", "--aad-auth-failure-mode", "http401WithBearerChallenge")
    else:
        print(f"  search service {name} exists")
        if not (service.get("identity") or {}).get("principalId"):
            print("  enabling its system-assigned identity...")
            service = az("search", "service", "update", "-g", rg, "-n", name, "--identity-type", "SystemAssigned")
        if service.get("semanticSearch") in (None, "disabled"):
            print("  enabling the semantic ranker (free plan)...")
            service = az("search", "service", "update", "-g", rg, "-n", name, "--semantic-search", "free")
        if not service.get("authOptions", {}).get("aadOrApiKey"):
            print("  enabling Entra ID (RBAC) data-plane access...")
            service = az("search", "service", "update", "-g", rg, "-n", name, "--auth-options", "aadOrApiKey",
                         "--aad-auth-failure-mode", "http401WithBearerChallenge")
    env_set(env, "HR_AGENT_SEARCH_ENDPOINT", f"https://{name}.search.windows.net")
    return service


def ensure_storage(env: dict[str, str]) -> dict:
    rg, name = env["AZURE_RESOURCE_GROUP"], env["HR_AGENT_STORAGE_ACCOUNT"]
    account = az_exists("storage", "account", "show", "-g", rg, "-n", name)
    if account is None:
        print(f"  creating storage account {name}...")
        account = az("storage", "account", "create", "-g", rg, "-n", name, "-l", env["AZURE_LOCATION"],
                     "--sku", "Standard_LRS", "--kind", "StorageV2", "--allow-blob-public-access", "false",
                     "--allow-shared-key-access", "false", "--min-tls-version", "TLS1_2")
    else:
        print(f"  storage account {name} exists")
    # Control-plane (ARM) container create: needs no data-plane role.
    if az_exists("storage", "container-rm", "show", "-g", rg, "--storage-account", name, "-n", CONTAINER) is None:
        print(f"  creating container {CONTAINER}...")
        az("storage", "container-rm", "create", "-g", rg, "--storage-account", name, "-n", CONTAINER)
    else:
        print(f"  container {CONTAINER} exists")
    return account


def ensure_embedding_deployment(env: dict[str, str]) -> None:
    rg, account, name = env["AZURE_RESOURCE_GROUP"], env["AZURE_AI_ACCOUNT_NAME"], env["HR_AGENT_EMBEDDING_DEPLOYMENT"]
    if az_exists("cognitiveservices", "account", "deployment", "show", "-g", rg, "-n", account,
                 "--deployment-name", name):
        print(f"  embedding deployment {name} exists")
        return
    print(f"  creating embedding deployment {name}...")
    az("cognitiveservices", "account", "deployment", "create", "-g", rg, "-n", account, "--deployment-name", name,
       "--model-name", EMBEDDING_MODEL, "--model-version", EMBEDDING_MODEL_VERSION, "--model-format", "OpenAI",
       "--sku-name", "GlobalStandard", "--sku-capacity", "50")


# --- Role assignments (steps 2 and 6) ---------------------------------------------
def ensure_role(principal_id: str, principal_type: str, role: str, scope: str, who: str) -> None:
    existing = az("role", "assignment", "list", "--assignee", principal_id, "--role", role, "--scope", scope)
    short_scope = scope.split("/providers/")[-1]
    if existing:
        print(f"  {who}: {role} on {short_scope} already assigned")
        return
    cmd = ["az", "role", "assignment", "create", "--assignee-object-id", principal_id,
           "--assignee-principal-type", principal_type, "--role", role, "--scope", scope]
    result = run(cmd, check=False)
    if result.returncode == 0:
        print(f"  {who}: {role} on {short_scope} assigned")
    elif "AuthorizationFailed" in result.stderr or "does not have authorization" in result.stderr:
        print(f"  {who}: {role} on {short_scope} PENDING (you may not assign this role)")
        pending_roles.append(" ".join(f'"{c}"' if " " in c else c for c in cmd))
    else:
        sys.exit(f"Role assignment failed: {result.stderr}")


def search_service_roles(env: dict[str, str], search: dict, storage: dict) -> None:
    principal = search["identity"]["principalId"]
    ensure_role(principal, "ServicePrincipal", ROLE_STORAGE_BLOB_DATA_READER, storage["id"], "search identity")
    foundry_id = env["AZURE_AI_PROJECT_ID"].split("/projects/")[0]
    ensure_role(principal, "ServicePrincipal", ROLE_COGNITIVE_SERVICES_USER, foundry_id, "search identity")


def caller_roles(env: dict[str, str], search: dict) -> None:
    developer = az("ad", "signed-in-user", "show")["id"]
    ensure_role(developer, "User", ROLE_SEARCH_INDEX_DATA_READER, search["id"], "developer")
    agent = env.get("AGENT_HR_AGENT_INSTANCE_IDENTITY_PRINCIPAL_ID")
    if agent:
        ensure_role(agent, "ServicePrincipal", ROLE_SEARCH_INDEX_DATA_READER, search["id"], "hr-agent identity")
    else:
        print("  hr-agent identity: pending, run this script again after `azd deploy hr-agent`")


# --- Step 3: handbook sync --------------------------------------------------------
def sync_handbook(env: dict[str, str]) -> bool:
    """Upload new or changed files and delete blobs that are gone locally. Returns True if anything changed."""
    service = BlobServiceClient(f"https://{env['HR_AGENT_STORAGE_ACCOUNT']}.blob.core.windows.net", credential)
    container = service.get_container_client(CONTAINER)
    remote = {b.name: bytes(b.content_settings.content_md5 or b"") for b in container.list_blobs()}
    local = {p.name: p for p in sorted(HANDBOOK_DIR.glob("*.md"))}
    changed = False

    for name, path in local.items():
        data = path.read_bytes()
        md5 = hashlib.md5(data).digest()  # noqa: S324 - content fingerprint, not security
        if remote.get(name) == md5:
            continue
        container.upload_blob(name, data, overwrite=True,
                              content_settings=ContentSettings(content_type="text/markdown", content_md5=md5))
        print(f"  uploaded {name}")
        changed = True

    for name in remote.keys() - local.keys():
        container.delete_blob(name)
        print(f"  deleted {name} (no longer in the repo)")
        changed = True

    if not changed:
        print(f"  {len(local)} handbook files already in sync")
    return changed


# --- Step 4: knowledge source and knowledge base ----------------------------------
def search_clients(env: dict[str, str]) -> tuple[SearchIndexClient, SearchIndexerClient]:
    endpoint = env["HR_AGENT_SEARCH_ENDPOINT"]
    return (SearchIndexClient(endpoint, credential, api_version=SEARCH_API_VERSION),
            SearchIndexerClient(endpoint, credential, api_version=SEARCH_API_VERSION))


def knowledge_source_definition(env: dict[str, str], storage: dict) -> dict:
    openai_endpoint = env["AZURE_OPENAI_ENDPOINT"].rstrip("/")
    return {
        "name": KNOWLEDGE_SOURCE,
        "kind": "azureBlob",
        "description": "MyConcepts HR handbook (Markdown files synced from the repo).",
        "azureBlobParameters": {
            # Keyless: the search service reads the container with its managed identity.
            "connectionString": f"ResourceId={storage['id']};",
            "containerName": CONTAINER,
            "ingestionParameters": {
                "contentExtractionMode": "minimal",
                "embeddingModel": {
                    "kind": "azureOpenAI",
                    "azureOpenAIParameters": {
                        "resourceUri": openai_endpoint,
                        "deploymentId": env["HR_AGENT_EMBEDDING_DEPLOYMENT"],
                        "modelName": EMBEDDING_MODEL,
                    },
                },
            },
        },
    }


def knowledge_base_definition(env: dict[str, str]) -> dict:
    deployment = env["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
    return {
        "name": KNOWLEDGE_BASE,
        "description": "MyConcepts HR handbook for hr-agent.",
        "knowledgeSources": [{"name": KNOWLEDGE_SOURCE}],
        # Return passages with references; hr-agent's own model writes the answer and citations.
        "outputMode": "extractiveData",
        "retrievalReasoningEffort": {"kind": "low"},
        "models": [{
            "kind": "azureOpenAI",
            "azureOpenAIParameters": {
                "resourceUri": env["AZURE_OPENAI_ENDPOINT"].rstrip("/"),
                "deploymentId": deployment,
                "modelName": deployment,
            },
        }],
    }


def ensure_knowledge_objects(env: dict[str, str], storage: dict, handbook_changed: bool) -> None:
    index_client, indexer_client = search_clients(env)

    if stale_documents(env):
        # A plain re-run of the indexer does not remove documents whose blobs were
        # deleted, so rebuild the knowledge source (and the index it owns) instead.
        # The knowledge base references the source, so it goes first and is recreated below.
        # Retrieval is unavailable for the minute or two this takes.
        print(f"  a handbook file was removed: rebuilding {KNOWLEDGE_BASE} and {KNOWLEDGE_SOURCE}")
        delete_knowledge_base(index_client)
        delete_knowledge_source(index_client)

    try:
        current = index_client.get_knowledge_source(KNOWLEDGE_SOURCE).as_dict()
    except ResourceNotFoundError:
        current = None
    desired = knowledge_source_definition(env, storage)
    if current is None or _differs(desired, current):
        index_client.create_or_update_knowledge_source(AzureBlobKnowledgeSource(desired))
        print(f"  knowledge source {KNOWLEDGE_SOURCE} {'created' if current is None else 'updated'}")
        handbook_changed = True
    else:
        print(f"  knowledge source {KNOWLEDGE_SOURCE} up to date")

    try:
        current_kb = index_client.get_knowledge_base(KNOWLEDGE_BASE).as_dict()
    except ResourceNotFoundError:
        current_kb = None
    desired_kb = knowledge_base_definition(env)
    if current_kb is None or _differs(desired_kb, current_kb):
        index_client.create_or_update_knowledge_base(KnowledgeBase(desired_kb))
        print(f"  knowledge base {KNOWLEDGE_BASE} {'created' if current_kb is None else 'updated'}")
    else:
        print(f"  knowledge base {KNOWLEDGE_BASE} up to date")

    if handbook_changed:
        run_ingestion(index_client, indexer_client)
    env_set(env, "HR_AGENT_KB_MCP_ENDPOINT",
            f"{env['HR_AGENT_SEARCH_ENDPOINT']}/knowledgebases/{KNOWLEDGE_BASE}/mcp?api-version={SEARCH_API_VERSION}")


def _differs(desired: object, current: object) -> bool:
    """True when any value we set differs from the service's copy (extra service fields are ignored)."""
    if isinstance(desired, dict):
        return not isinstance(current, dict) or any(_differs(v, current.get(k)) for k, v in desired.items())
    if isinstance(desired, list):
        return not isinstance(current, list) or len(desired) != len(current) or any(
            _differs(d, c) for d, c in zip(desired, current))
    if current == "<redacted>":  # the service never returns connection strings; can't compare
        return False
    return desired != current


def stale_documents(env: dict[str, str]) -> set[str]:
    """Handbook files that are still in the index but no longer in the repo."""
    client = SearchClient(env["HR_AGENT_SEARCH_ENDPOINT"], f"{KNOWLEDGE_SOURCE}-index", credential,
                          api_version=SEARCH_API_VERSION)
    try:
        indexed = {doc["blob_url"].rsplit("/", 1)[-1] for doc in client.search("*", select=["blob_url"], top=1000)}
    except (ResourceNotFoundError, HttpResponseError):
        return set()  # no index yet, or no data access yet on a first run: nothing stale to remove
    stale = indexed - {p.name for p in HANDBOOK_DIR.glob("*.md")}
    if stale:
        print(f"  still indexed but removed from the repo: {', '.join(sorted(stale))}")
    return stale


def run_ingestion(index_client: SearchIndexClient, indexer_client: SearchIndexerClient) -> None:
    """Start a sync now (instead of waiting for the daily schedule) and wait until it finishes.

    Progress is read from the knowledge source status: a sync is done when no
    synchronization is running and the last one ended after we started waiting.
    """
    started = datetime.now(timezone.utc) - timedelta(seconds=5)
    source = index_client.get_knowledge_source(KNOWLEDGE_SOURCE).as_dict()
    indexer = (source["azureBlobParameters"].get("createdResources") or {}).get("indexer")
    if indexer:
        try:
            indexer_client.run_indexer(indexer)
        except HttpResponseError:  # a sync is already running (e.g. right after creation): just wait for it
            pass
    print("  waiting for ingestion", end="", flush=True)
    deadline = time.time() + 900
    while time.time() < deadline:
        time.sleep(10)
        print(".", end="", flush=True)
        status = index_client.get_knowledge_source_status(KNOWLEDGE_SOURCE).as_dict()
        last = status.get("lastSynchronizationState") or {}
        end_time = last.get("endTime")
        if status.get("currentSynchronizationState") or not end_time:
            continue
        if datetime.fromisoformat(str(end_time).replace("Z", "+00:00")) < started:
            continue
        print(f" done: {last.get('itemsUpdatesProcessed', 0)} processed, {last.get('itemsUpdatesFailed', 0)} failed")
        if last.get("itemsUpdatesFailed"):
            for error in last.get("errors") or []:
                print(f"    error: {error}")
            sys.exit("Ingestion had failures (see above). Check the search identity's roles.")
        return
    sys.exit("\nIngestion did not finish within 15 minutes.")


def delete_knowledge_base(index_client: SearchIndexClient) -> bool:
    try:
        index_client.delete_knowledge_base(KNOWLEDGE_BASE)
        return True
    except ResourceNotFoundError:
        return False


def delete_knowledge_source(index_client: SearchIndexClient) -> None:
    try:
        index_client.delete_knowledge_source(KNOWLEDGE_SOURCE)
    except ResourceNotFoundError:
        return
    for _ in range(60):  # deletion is asynchronous
        try:
            index_client.get_knowledge_source(KNOWLEDGE_SOURCE)
        except ResourceNotFoundError:
            return
        time.sleep(5)


# --- Step 5: connections and toolboxes --------------------------------------------
def ensure_connections_and_toolboxes(env: dict[str, str]) -> None:
    kb_mcp = env["HR_AGENT_KB_MCP_ENDPOINT"]
    connections = {c["name"]: c for c in azd_json("ai", "connection", "list")}
    expected_auth = {"agentic-identity": "AgenticIdentityToken", "user-entra-token": "UserEntraToken",
                     "project-managed-identity": "ProjectManagedIdentity"}

    for toolbox, (definition_file, connection, auth_type) in TOOLBOXES.items():
        existing = connections.get(connection)
        if existing and existing.get("target") == kb_mcp and existing.get("authType") == expected_auth[auth_type]:
            print(f"  connection {connection} up to date")
        else:
            azd("ai", "connection", "create", connection, "--kind", "remote-tool", "--force", "--target", kb_mcp,
                "--auth-type", auth_type, "--audience", SEARCH_AUDIENCE, "--metadata", "ApiType=Azure")
            print(f"  connection {connection} {'updated' if existing else 'created'} ({auth_type})")

        text = (HERE / definition_file).read_text(encoding="utf-8").replace("${KB_MCP_ENDPOINT}", kb_mcp)
        ensure_toolbox(env, toolbox, yaml.safe_load(text))


def foundry_request(env: dict[str, str], method: str, path: str, body: dict | None = None) -> httpx.Response:
    token = credential.get_token("https://ai.azure.com/.default").token
    url = f"{env['FOUNDRY_PROJECT_ENDPOINT'].rstrip('/')}/{path}?api-version={TOOLBOX_API_VERSION}"
    return httpx.request(method, url, json=body, timeout=60, headers={"Authorization": f"Bearer {token}"})


def ensure_toolbox(env: dict[str, str], name: str, definition: dict) -> None:
    """Create a new toolbox version only when the definition changed, then promote it."""
    response = foundry_request(env, "GET", f"toolboxes/{name}")
    if response.status_code == 200:
        default = response.json()["default_version"]
        current = foundry_request(env, "GET", f"toolboxes/{name}/versions/{default}").json()
        if not _differs(definition, {"description": current.get("description"), "tools": current.get("tools")}):
            print(f"  toolbox {name} up to date (version {default})")
            return
    elif response.status_code != 404:
        sys.exit(f"Reading toolbox {name} failed: {response.status_code} {response.text}")

    created = foundry_request(env, "POST", f"toolboxes/{name}/versions", definition)
    if created.status_code not in (200, 201):
        sys.exit(f"Creating toolbox {name} failed: {created.status_code} {created.text}")
    version = created.json()["version"]
    promoted = foundry_request(env, "PATCH", f"toolboxes/{name}", {"default_version": version})
    if promoted.status_code != 200:
        sys.exit(f"Promoting toolbox {name} v{version} failed: {promoted.status_code} {promoted.text}")
    print(f"  toolbox {name}: version {version} created and promoted")


# --- Teardown ---------------------------------------------------------------------
def teardown(env: dict[str, str]) -> None:
    step("Teardown: toolboxes and connections")
    for toolbox, (_, connection, _) in TOOLBOXES.items():
        response = foundry_request(env, "DELETE", f"toolboxes/{toolbox}")
        print(f"  toolbox {toolbox}: {'deleted' if response.status_code in (200, 204) else 'not found'}")
        result = run(["azd", "ai", "connection", "delete", connection, "--force", "--no-prompt"], check=False)
        print(f"  connection {connection}: {'deleted' if result.returncode == 0 else 'not found'}")

    if env.get("HR_AGENT_SEARCH_ENDPOINT"):
        step("Teardown: knowledge base and knowledge source")
        index_client, _ = search_clients(env)
        found = delete_knowledge_base(index_client)
        print(f"  knowledge base {KNOWLEDGE_BASE} {'deleted' if found else 'not found'}")
        delete_knowledge_source(index_client)
        print(f"  knowledge source {KNOWLEDGE_SOURCE} deleted (with the index it created)")

    step("Left in place (they cost money while they exist)")
    rg = env["AZURE_RESOURCE_GROUP"]
    print("  The search service, storage account and embedding deployment were kept, because they may be")
    print("  shared with other workloads. If they were created only for hr-agent, delete them with:")
    print(f"    az search service delete -g {rg} -n {env.get('HR_AGENT_SEARCH_SERVICE')} --yes")
    print(f"    az storage account delete -g {rg} -n {env.get('HR_AGENT_STORAGE_ACCOUNT')} --yes")
    print(f"    az cognitiveservices account deployment delete -g {rg} -n {env['AZURE_AI_ACCOUNT_NAME']} "
          f"--deployment-name {env.get('HR_AGENT_EMBEDDING_DEPLOYMENT')}")


# --- Main -------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--teardown", action="store_true", help="remove knowledge objects, toolboxes and connections")
    args = parser.parse_args()
    for tool in ("az", "azd"):
        if not shutil.which(tool):
            sys.exit(f"'{tool}' is required on PATH.")

    env = load_env()
    print(f"azd environment: {env['AZURE_ENV_NAME']}  (resource group {env['AZURE_RESOURCE_GROUP']})")
    if args.teardown:
        teardown(env)
        return

    step("1. Azure resources")
    resolve_names(env)
    search = ensure_search_service(env)
    storage = ensure_storage(env)
    ensure_embedding_deployment(env)

    step("2. Roles for the search service's identity")
    search_service_roles(env, search, storage)

    step("3. Handbook sync")
    handbook_changed = sync_handbook(env)

    step("4. Knowledge source and knowledge base")
    ensure_knowledge_objects(env, storage, handbook_changed)

    step("5. Connections and toolboxes")
    ensure_connections_and_toolboxes(env)

    step("6. Roles for callers")
    caller_roles(env, search)

    if pending_roles:
        step("ACTION NEEDED: role assignments you are not allowed to create")
        print("Ask someone with Owner or User Access Administrator on these resources to run:\n")
        for command in pending_roles:
            print(f"  {command}")
        print("\nThen run this script again.")
        sys.exit(2)
    print("\nDone.")


if __name__ == "__main__":
    main()
