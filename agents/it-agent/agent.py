"""it-agent: IT onboarding answers, built with LangChain/LangGraph.

The IT team owns this agent and chose LangGraph. It is hosted on Foundry the
same way as the Agent Framework agents, and keeps the repo's conventions: the
same folder skeleton, prompt variants through AGENT_PROMPT, and its own managed
identity when hosted or the developer's `az login` locally.
"""

import os
from pathlib import Path

from azure.ai.agentserver.core import AgentConfig
from azure.ai.projects import AIProjectClient
from azure.core.credentials import TokenCredential
from azure.identity import AzureCliCredential, ManagedIdentityCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.graph.state import CompiledStateGraph

from tools import get_access_setup, get_standard_equipment

load_dotenv()

PROMPTS_DIR = Path(__file__).parent / "prompts"
DEFAULT_PROMPT = "baseline"


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


def create_graph(credential: TokenCredential) -> CompiledStateGraph:
    """Build the LangGraph agent. No checkpointer: the Responses host passes the history."""
    project = AIProjectClient(endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=credential)
    model = ChatOpenAI(
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        base_url=str(project.get_openai_client().base_url),
        api_key=get_bearer_token_provider(credential, "https://ai.azure.com/.default"),
        use_responses_api=True,
        output_version="responses/v1",
    )
    return create_agent(
        model,
        tools=[get_standard_equipment, get_access_setup],
        system_prompt=INSTRUCTIONS,
        name="it-agent",
    )
