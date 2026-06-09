"""Freight Rates Agent — Supply Chain Visibility REPL.

Interactive assistant that combines:
  - Live market rates and port intelligence from FreightPulse
  - Container tracking and rate benchmarks from GoComet

Usage:
    python agent.py

Sample prompts:
    > get FreightPulse market rates for Haiphong to Port Klang
    > compare FreightPulse vs GoComet rates for Shanghai to Jakarta
    > any active supply chain disruptions?
    > check port congestion at Laemchabang
    > track container TCKU1234567
    > show GoComet rate benchmarks for Nhava Sheva to Laemchabang
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver

from deepagents import create_deep_agent
from tools import (
    get_gocomet_rate_benchmarks,
    get_market_rates,
    get_port_congestion,
    get_supply_chain_disruptions,
    track_container,
)

load_dotenv(Path(__file__).parent / ".env")

SYSTEM_PROMPT = """You are a supply chain visibility analyst specialising in FCL (Full Container Load) ocean freight.

You have access to two data sources:

1. **FreightPulse** (live market intelligence)
   Real-time ocean freight market rates, port congestion levels, and supply chain
   disruption alerts (strikes, weather, route diversions, geopolitical events).

2. **GoComet** (freight procurement & tracking)
   Container tracking milestones and rate benchmarks for competitive comparison.

Your role is to help logistics and supply chain teams:
- **Market rates**: Fetch live FreightPulse rates and GoComet benchmarks for any trade lane.
- **Rate comparison**: Cross-reference FreightPulse market rates against GoComet benchmarks.
- **Market monitoring**: Port congestion, disruptions, and rate trends affecting relevant lanes.
- **Container visibility**: Live status and ETA of shipments in transit via GoComet.
- **Decision support**: Which lane offers the best rate and transit combination?

Key concepts:
- **All-in rates**: Include base freight + surcharges (e.g. EFS — Emergency Fuel Surcharge).
- **CIF**: Cost Insurance Freight — seller pays ocean freight to destination.
- **Transshipment**: Via an intermediate hub port — longer transit but sometimes cheaper.
- **Rate trend**: Rising/falling/stable indicator from FreightPulse to guide timing decisions.

When presenting rates:
- Always show 40ft rates; include 20ft when available.
- Compare FreightPulse market rate vs GoComet benchmark range when both are available.
- Note port congestion or active disruptions that may affect the quoted lane.
"""

_model = ChatOpenAI(
    model="deepseek-chat",
    openai_api_base="https://api.deepseek.com",
    openai_api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
)

agent = create_deep_agent(
    model=_model,
    system_prompt=SYSTEM_PROMPT,
    checkpointer=MemorySaver(),
    tools=[
        get_market_rates,
        get_port_congestion,
        get_supply_chain_disruptions,
        track_container,
        get_gocomet_rate_benchmarks,
    ],
)


async def chat(user_input: str, thread_id: str) -> None:
    result = await agent.ainvoke(
        {"messages": [HumanMessage(user_input)]},
        config={"configurable": {"thread_id": thread_id}},
    )
    last = result["messages"][-1]
    content = last.content
    print(
        "\n"
        + (content if isinstance(content, str) else __import__("json").dumps(content, indent=2))
        + "\n"
    )


async def main() -> None:
    thread_id = str(uuid.uuid4())
    print("╔══════════════════════════════════════════════════════════╗")
    print("║     Freight Rates Agent — Supply Chain Visibility        ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print("\nData sources:")
    print("  • FreightPulse: live market rates, port congestion, disruptions")
    print("  • GoComet:      container tracking, rate benchmarks")
    print("\nType a question and press Enter.  Ctrl+C or Ctrl+D to exit.")
    print("─" * 60 + "\n")

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break
        if not user_input:
            continue
        try:
            await chat(user_input, thread_id)
        except Exception as exc:  # noqa: BLE001
            print(f"Error: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
