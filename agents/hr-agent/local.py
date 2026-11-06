"""Quick local check: build hr-agent outside the server and ask one or more questions.

Usage (from the repo root, after `az login`):
    python agents/hr-agent/local.py
    python agents/hr-agent/local.py "How many holiday days can I carry over?"
"""

import asyncio
import logging
import sys

from agent_framework.exceptions import ToolExecutionException

from agent import create_agent, toolbox_name

DEFAULT_QUESTIONS = [
    "How many days of carry-over holiday are allowed?",
    "Am I eligible for the learning budget, and how do I get a course reimbursed?",
]


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    questions = sys.argv[1:] or DEFAULT_QUESTIONS

    for question in questions:
        # The agent owns its toolbox session; `async with` connects and closes it.
        try:
            async with create_agent() as agent:
                result = await agent.run(question)
        except ToolExecutionException as ex:
            sys.exit(
                f"Could not connect to toolbox '{toolbox_name()}' ({ex}).\n"
                "Does it exist? Run: python agents/hr-agent/provision/provision.py"
            )
        print(f"\nQ: {question}\nA: {result.text}\n")


if __name__ == "__main__":
    asyncio.run(main())
