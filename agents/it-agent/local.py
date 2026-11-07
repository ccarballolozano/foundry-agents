"""Quick local check: build it-agent's graph outside the server and ask one or more questions.

Usage (from the repo root, after `az login`):
    python agents/it-agent/local.py
    python agents/it-agent/local.py "What laptop does a sales person get?"
"""

import sys

from agent import create_credential, create_graph

DEFAULT_QUESTIONS = [
    "What laptop does a software engineer get?",
    "Which accounts does a consultant get and how do I set them up?",
]


def main() -> None:
    graph = create_graph(create_credential())
    for question in sys.argv[1:] or DEFAULT_QUESTIONS:
        result = graph.invoke({"messages": [{"role": "user", "content": question}]})
        tools = [m.name for m in result["messages"] if m.type == "tool"]
        print(f"\nQ: {question}\nTools: {', '.join(tools) or 'none'}\nA: {result['messages'][-1].text}\n")


if __name__ == "__main__":
    main()
