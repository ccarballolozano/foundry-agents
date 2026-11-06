import asyncio

from agent import create_agent


async def main() -> None:
    agent = create_agent()

    result = await agent.run("What benefits are available for remote employees?")

    print(result.text)


if __name__ == "__main__":
    asyncio.run(main())
