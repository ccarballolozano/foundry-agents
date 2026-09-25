import os

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from dotenv import load_dotenv


load_dotenv()


def main() -> None:
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    agent_name = "hr-benefits-agent"

    project_client = AIProjectClient(
        endpoint=project_endpoint,
        credential=DefaultAzureCredential(),
    )

    responses_client = project_client.get_openai_client(
        agent_name=agent_name,
    ).responses

    print("=== Turno 1 ===")

    first = responses_client.create(
        input="Mi nombre es Christian.",
        store=True,
    )

    session_id = first.model_extra.get("agent_session_id")

    print(f"Response ID: {first.id}")
    print(f"Session ID: {session_id}")
    print(f"Respuesta: {first.output_text}")

    print()
    print("=== Turno 2 ===")

    second = responses_client.create(
        input="¿Cómo me llamo?",
        previous_response_id=first.id,
        extra_body={
            "agent_session_id": session_id,
        },
        store=True,
    )

    print(f"Response ID: {second.id}")
    print(f"Session ID: {second.model_extra.get('agent_session_id')}")
    print(f"Respuesta: {second.output_text}")


if __name__ == "__main__":
    main()