import sys
from pathlib import Path

from agent_framework_foundry_hosting import ResponsesHostServer

from agent import create_agent


def main() -> None:
    agent = create_agent()

    server = ResponsesHostServer(agent)
    server.run()


if __name__ == "__main__":
    main()
