import logging

from agent_framework_foundry_hosting import ResponsesHostServer

from agent import create_agent


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    # Pass the factory, not an agent: the server builds a fresh agent (credential,
    # toolbox session, request headers) for every request and closes it afterwards.
    server = ResponsesHostServer(create_agent)
    server.run()


if __name__ == "__main__":
    main()
