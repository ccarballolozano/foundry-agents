"""Call a hosted agent directly over A2A v1.0, the way another agent would.

Usage (from the repo root, after `az login`):
    uv run python scripts/a2a_call.py                                   # it-agent, default question
    uv run python scripts/a2a_call.py "Which accounts does a sales person get?"
    uv run python scripts/a2a_call.py --agent it-agent "What laptop does a consultant get?"

It fetches the agent's v1.0 card (Entra token required, anonymous calls are
rejected), prints its skills, then sends one text message with a non-streaming
A2A client, as in Learn's "Enable incoming A2A on a Foundry agent" example.
Reading the v1.0 card makes the SDK use A2A v1.0 for the call, instead of the
v0.3 preview that Foundry serves when no version is selected.

Your identity needs Foundry Agent Consumer (or a broader Foundry role) on the
project or on the agent.
"""

import argparse
import asyncio
import json
import subprocess

import httpx
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import get_artifact_text, get_message_text, new_text_message
from a2a.types.a2a_pb2 import Role, SendMessageRequest
from azure.identity import AzureCliCredential

AGENT_CARD_PATH = "agentCard/v1.0"


def project_endpoint() -> str:
    out = subprocess.run(["azd", "env", "get-values", "-o", "json", "--no-prompt"],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out[out.find("{"):])["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")


def answer_text(response: object) -> str:
    """Text of a completed task (its artifacts or status message) or of a direct message."""
    if response.HasField("message"):
        return get_message_text(response.message)
    task = response.task
    texts = [get_artifact_text(a) for a in task.artifacts]
    if not any(texts) and task.status.HasField("message"):
        texts = [get_message_text(task.status.message)]
    return "\n".join(t for t in texts if t)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("question", nargs="?", default="What laptop does a software engineer get?")
    parser.add_argument("--agent", default="it-agent")
    args = parser.parse_args()

    base_url = f"{project_endpoint()}/agents/{args.agent}/endpoint/protocols/a2a"
    token = AzureCliCredential().get_token("https://ai.azure.com/.default").token

    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"},
                                 timeout=httpx.Timeout(120.0)) as http:
        card = await A2ACardResolver(httpx_client=http, base_url=base_url,
                                     agent_card_path=AGENT_CARD_PATH).get_agent_card()
        versions = sorted({i.protocol_version for i in card.supported_interfaces})
        print(f"Agent card: {card.name} (A2A {', '.join(versions)})")
        for skill in card.skills:
            print(f"  skill {skill.id}: {skill.description}")

        client = await create_client(agent=card, client_config=ClientConfig(streaming=False, httpx_client=http))
        try:
            request = SendMessageRequest(message=new_text_message(args.question, role=Role.ROLE_USER))
            print(f"\nQ: {args.question}")
            async for response in client.send_message(request):
                print(f"A: {answer_text(response)}")
        finally:
            await client.close()


if __name__ == "__main__":
    asyncio.run(main())
