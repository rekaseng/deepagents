"""Freight Rates Agent — Supply Chain Visibility REPL.

Interactive assistant powered by FreightPulse live market intelligence.

Usage:
    python agent.py

Sample prompts:
    > get market rates for Shanghai to Los Angeles
    > any active supply chain disruptions?
    > check port congestion at Singapore
    > what are rates from Rotterdam to New York?
"""

from __future__ import annotations

import asyncio
import logging
import os
import traceback
import uuid
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver

from deepagents import create_deep_agent
from tools import (
    get_market_rates,
    get_port_congestion,
    get_supply_chain_disruptions,
)

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

SYSTEM_PROMPT = """You are a supply chain visibility analyst specialising in FCL (Full Container Load) ocean freight.

You have access to FreightPulse (live market intelligence):
- Real-time ocean freight market rates
- Port congestion levels
- Supply chain disruption alerts (strikes, weather, route diversions, geopolitical events)

Your role is to help logistics and supply chain teams:
- **Market rates**: Fetch live FreightPulse rates for any trade lane.
- **Market monitoring**: Port congestion, disruptions, and rate trends affecting relevant lanes.
- **Decision support**: Which lane offers the best rate and transit combination?

Key concepts:
- **All-in rates**: Include base freight + surcharges (e.g. EFS — Emergency Fuel Surcharge).
- **CIF**: Cost Insurance Freight — seller pays ocean freight to destination.
- **Transshipment**: Via an intermediate hub port — longer transit but sometimes cheaper.
- **Rate trend**: Rising/falling/stable indicator from FreightPulse to guide timing decisions.

When presenting rates:
- Always show 40ft rates; include 20ft and 40HC when available.
- Note port congestion or active disruptions that may affect the quoted lane.

When you want to offer the user a set of clickable follow-up options (e.g. after showing rates, or when the user's intent is ambiguous), respond with ONLY the following JSON — no extra text:
{
  "type": "options",
  "message": "<short message to display above the buttons>",
  "choices": [
    {"title": "<button label>", "value": "<query to run when clicked>"},
    ...
  ]
}
Use this sparingly: only when 2–5 distinct follow-up actions make sense.
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
            traceback.print_exc()
            print(f"Error: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
