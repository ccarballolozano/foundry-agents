"""hr-agent: benefit catalog tool + MyConcepts handbook through a Foundry toolbox.

`create_agent()` is a factory: the hosting server calls it once per request, so
each request gets its own credential and toolbox (MCP) session, which are closed
together with the agent. The same code runs hosted and locally; it chooses the
credential and the toolbox from the hosting environment, never from code edits.
"""

import logging
import os
from pathlib import Path

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import FoundryToolbox
from azure.ai.agentserver.core import AgentConfig
from azure.core.credentials import TokenCredential
from azure.identity import AzureCliCredential, ManagedIdentityCredential
from dotenv import load_dotenv

from tools import get_benefit_details

load_dotenv()

logger = logging.getLogger("hr_agent")

PROMPTS_DIR = Path(__file__).parent / "prompts"
DEFAULT_PROMPT = "baseline"

DEFAULT_HOSTED_TOOLBOX = "hr-agent-toolbox"
DEFAULT_DEV_TOOLBOX = "hr-agent-toolbox-dev"
# Toolbox consumer endpoints are GA ("v1"). The unversioned endpoint always
# serves the toolbox's default version, so promoting a new version needs no redeploy.
TOOLBOX_API_VERSION = "v1"


def load_instructions() -> str:
    """Load the system prompt variant named by AGENT_PROMPT (default: baseline).

    Only names that match a file in prompts/ are accepted, so the value can
    never point at a file outside that folder.
    """
    available = sorted(p.stem for p in PROMPTS_DIR.glob("*.md"))
    name = os.environ.get("AGENT_PROMPT") or DEFAULT_PROMPT
    if name not in available:
        raise ValueError(
            f"Unknown AGENT_PROMPT '{name}'. Available variants: {', '.join(available)}"
        )
    text = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    return " ".join(text.split())


# Read at import time so a bad AGENT_PROMPT fails at startup, not on the first request.
INSTRUCTIONS = load_instructions()


def is_hosted() -> bool:
    return AgentConfig.from_env().is_hosted


def create_credential() -> TokenCredential:
    """The agent's own managed identity when hosted, the developer's az login locally.

    No credential chain is used on purpose: trying credential types one after
    another hides misconfiguration.
    """
    if is_hosted():
        return ManagedIdentityCredential(client_id=os.environ["FOUNDRY_AGENT_INSTANCE_CLIENT_ID"])
    return AzureCliCredential()


def toolbox_name() -> str:
    if is_hosted():
        return os.environ.get("HR_AGENT_TOOLBOX") or DEFAULT_HOSTED_TOOLBOX
    return os.environ.get("HR_AGENT_DEV_TOOLBOX") or DEFAULT_DEV_TOOLBOX


def toolbox_endpoint(name: str) -> str:
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    return f"{project_endpoint}/toolboxes/{name}/mcp?api-version={TOOLBOX_API_VERSION}"


def create_agent() -> Agent:
    credential = create_credential()
    name = toolbox_name()
    logger.info("hr-agent using toolbox '%s' (hosted=%s)", name, is_hosted())

    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )

    # Works with or without a server request context: outside a request (local.py)
    # there are simply no platform headers to forward.
    toolbox = FoundryToolbox(credential, url=toolbox_endpoint(name), name="hr_toolbox")

    return Agent(
        client=client,
        name="HRAgent",
        instructions=INSTRUCTIONS,
        tools=[get_benefit_details, toolbox],
        default_options={"store": False},
    )
