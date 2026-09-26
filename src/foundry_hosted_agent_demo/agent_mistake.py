import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from tools import get_benefit_details

load_dotenv()


def create_agent() -> Agent:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    return Agent(
        client=client,
        name="HRBenefitsAgent",
        instructions=(
            "You are an HR benefits assistant. "
            "Answer questions about employee benefits accurately. "
            "Do not use get_benefit_details tool."
            "If the benefit is not available, say so clearly. "
            "Do not invent benefit information. "
        ),
        tools=[get_benefit_details],
        default_options={"store": False},
    )
