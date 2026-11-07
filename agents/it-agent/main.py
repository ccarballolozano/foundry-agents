import logging
import os

from langchain_azure_ai.agents.hosting import ResponsesHostServer
from langchain_azure_ai.callbacks.tracers import enable_auto_tracing

from agent import create_credential, create_graph

CONTENT_RECORDING_VAR = "AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED"


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    credential = create_credential()

    # One switch for message content in traces, off unless set to "true". The
    # LangChain tracer reads CONTENT_RECORDING_VAR; the hosting server records
    # content unless OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT is "false",
    # so it is set here from the same switch.
    record_content = os.environ.get(CONTENT_RECORDING_VAR, "").lower() == "true"
    os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = str(record_content).lower()

    # Exactly one exporter. Hosted, the platform injects APPLICATIONINSIGHTS_CONNECTION_STRING
    # and the hosting server already exports every span to that Application Insights, so the
    # LangChain tracer only adds its spans to that pipeline. Without it (locally), the tracer
    # configures Azure Monitor itself from the project endpoint with the same credential, and
    # the agent still runs if no destination can be resolved.
    host_exports = bool(os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"))
    enable_auto_tracing(
        auto_configure_azure_monitor=not host_exports,
        agent_id="it-agent",
        credential=credential,
        enable_content_recording=record_content,
    )

    graph = create_graph(credential)
    ResponsesHostServer(graph).run()


if __name__ == "__main__":
    main()
