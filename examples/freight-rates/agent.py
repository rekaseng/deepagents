"""Freight Rates Agent — Supply Chain Visibility REPL.

Interactive assistant that combines:
  - Negotiated FCL rates from your Excel freight summary (FCL V-V CIF)
  - Live market rates and port intelligence from FreightPulse
  - Container tracking and rate benchmarks from GoComet

Usage:
    python agent.py

Sample prompts:
    > list all trade lanes
    > show negotiated rates from Dalian to Laemchabang
    > compare our rates vs market for Shanghai to Jakarta
    > which carriers are nominated across all lanes?
    > get FreightPulse market rates for Haiphong to Port Klang
    > any active supply chain disruptions?
    > check port congestion at Laemchabang
    > track container TCKU1234567
    > show me the best carrier for Nhava Sheva to Laemchabang
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
    compare_rates,
    get_gocomet_rate_benchmarks,
    get_market_rates,
    get_nominated_carriers,
    get_port_congestion,
    get_supply_chain_disruptions,
    list_routes,
    query_negotiated_rates,
    track_container,
)

load_dotenv(Path(__file__).parent / ".env")

SYSTEM_PROMPT = """You are a supply chain visibility analyst specialising in FCL (Full Container Load) ocean freight.

You have access to three data sources:

1. **Internal negotiated rates** (Excel — FCL V-V CIF sheet)
   All-in rates by trade lane and carrier, including 20ft/40ft rates, transit times,
   free time (demurrage/detention), freight conditions, and final nominated carriers.

2. **FreightPulse** (live market intelligence)
   Real-time ocean freight market rates, port congestion levels, and supply chain
   disruption alerts (strikes, weather, route diversions, geopolitical events).

3. **GoComet** (freight procurement & tracking)
   Container tracking milestones and rate benchmarks for competitive comparison.

Your role is to help logistics and supply chain teams:
- **Rate competitiveness**: Compare negotiated rates against the live market — are we getting a good deal?
- **Carrier selection**: Which carrier offers the best combination of rate, transit time, and free time?
- **Route visibility**: What trade lanes do we cover? Who are the nominated carriers?
- **Market monitoring**: Port congestion, disruptions, and rate trends affecting our lanes.
- **Container visibility**: Live status and ETA of shipments in transit.
- **Decision support**: Should we ship 20ft or 40ft? Is direct routing worth the premium?

Key concepts in the data:
- **Current vs New rates**: New Selling rates are the latest negotiated rates — prefer these.
- **All-in rates**: Include base freight + surcharges (e.g. EFS — Emergency Fuel Surcharge).
- **Final Nominated Carrier** (✓): The agreed carrier for that lane.
- **DEM/DET free time**: Free days before demurrage/detention charges begin at origin or POD.
- **CIF**: Cost Insurance Freight — seller pays ocean freight to destination.
- **Transshipment**: Via an intermediate hub port (e.g. Qingdao, Singapore) — longer transit.

When presenting rates:
- Always show both 20ft and 40ft rates when available.
- Highlight the nominated carrier with ✓.
- Flag surcharge conditions (EFS, etc.) from the freight condition field.
- Calculate % savings vs market when both are available.
- Note free time differences — they materially affect total landed cost.
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
        list_routes,
        query_negotiated_rates,
        get_market_rates,
        get_port_congestion,
        get_supply_chain_disruptions,
        compare_rates,
        get_nominated_carriers,
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
    print("  • Excel:        FCL V-V CIF negotiated rates")
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
