import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from orchastrator import agent_fun


async def main() -> None:
    queries = [
        "show me a dog photo and tell me the weather, but don't mention any weather",
        "find books on clean code",
        "hello, how does this work?",
    ]

    async with agent_fun.open_mcp_session() as session:
        agent_fun._mcp_session = session
        try:
            for query in queries:
                result = await agent_fun.process_user_query(query)
                print(f"\nUser: {query}")
                print(f"Tools: {result['executable_tools']}")
                print(f"Banned: {result['banned_tools']}")
                print(f"Reply:\n{result['reply']}")
        finally:
            agent_fun._mcp_session = None


if __name__ == "__main__":
    asyncio.run(main())