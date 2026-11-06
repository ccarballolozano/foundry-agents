import os
from pathlib import Path

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from tools import get_benefit_details

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


def create_agent() -> Agent:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    return Agent(
        client=client,
        name="HRBenefitsAgent",
        instructions=load_instructions(),
        tools=[get_benefit_details],
        default_options={"store": False},
    )
