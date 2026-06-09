# Freight Rates Agent — Supply Chain Visibility

An interactive Deep Agent that gives supply chain teams a single place to query negotiated freight rates, compare them against live market intelligence, monitor port conditions, and track containers in transit.

## Data Sources

| Source | What it provides |
|--------|-----------------|
| **Excel (FCL V-V CIF)** | Your internally negotiated all-in rates by trade lane and carrier, including 20ft/40ft rates, transit times, free time policies (demurrage/detention), freight conditions, and nominated carriers |
| **FreightPulse** | Live ocean freight market rates, port congestion levels, and active supply chain disruption alerts (strikes, weather, route diversions, geopolitical events) |
| **GoComet** | Container tracking milestones and rate benchmarks for competitive comparison |

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- A DeepSeek API key — [platform.deepseek.com](https://platform.deepseek.com)
- A FreightPulse API key — [freightpulsehq.com](https://freightpulsehq.com)
- _(Optional)_ A GoComet API key and Org ID — GoComet → Settings → API

## Setup

**1. Install dependencies**

```
uv sync
```

**2. Configure environment**

Copy `.env.example` to `.env` and fill in your keys:

```
DEEPSEEK_API_KEY=sk-...
FREIGHTPULSE_API_KEY=fp_live_...
GOCOMET_API_KEY=                   # optional
GOCOMET_ORG_ID=                    # optional
FREIGHT_EXCEL_PATH=C:\path\to\your\Freight Summary.xlsx
```

`FREIGHT_EXCEL_PATH` defaults to `C:\Users\reca\Downloads\Freight Summary - Submission to Exp & Imp (2).xlsx` if not set.

**3. Run**

```
python agent.py
```

## Tools

| Tool | Source | Description |
|------|--------|-------------|
| `list_routes` | Excel | All unique trade lanes with carrier count |
| `query_negotiated_rates` | Excel | All-in rates, transit times, free time, and remarks per carrier on a lane |
| `get_nominated_carriers` | Excel | Every lane where a Final Nominated Carrier has been confirmed |
| `compare_rates` | Excel + FreightPulse | Side-by-side view of your negotiated rates against the live market, with % saving or premium |
| `get_market_rates` | FreightPulse | Live 40ft rate and trend for any trade lane |
| `get_port_congestion` | FreightPulse | Current congestion level and vessel waiting time at any port |
| `get_supply_chain_disruptions` | FreightPulse | Active alerts — port closures, labour strikes, weather events, geopolitical risks |
| `track_container` | GoComet | Live container status, vessel, ETA, and event milestones |
| `get_gocomet_rate_benchmarks` | GoComet | Market average, min/max range, and trend for a lane |

## Sample Prompts

```
> list all trade lanes
> show negotiated rates from Dalian to Laemchabang
> compare our rates vs market for Shanghai to Jakarta
> which carriers are nominated across all lanes?
> get market rates for Haiphong to Port Klang
> any active supply chain disruptions?
> check port congestion at Laemchabang
> track container TCKU1234567
> what is the best carrier for Nhava Sheva to Laemchabang based on rate and free time?
> is our DIMERCO rate for Dalian → Laemchabang competitive vs the market?
```

## Excel Format

The agent reads the **FCL V-V CIF** sheet. Each row represents one carrier option on a trade lane with these key fields:

| Column | Field |
|--------|-------|
| POL / POD | Port of Loading and Port of Discharge |
| Carriers | The forwarder or shipping line quoting the rate |
| Final Nominated Carrier | The confirmed carrier for that lane (marked ✓) |
| Current / New Selling | All-in rates for 20ft and 40ft containers (USD) |
| Freight condition | Surcharge notes, e.g. EFS (Emergency Fuel Surcharge) |
| Transit days | Ocean transit time from POL to POD |
| Transshipment Port | Intermediate hub port, if not direct |
| DEM / DET free time | Free days at origin and POD before charges apply |

> **All-in rates** include base ocean freight plus applicable surcharges. New Selling rates are the latest negotiated values and take precedence over Current Selling rates.

## Key Concepts

- **CIF** — Cost, Insurance, Freight. The seller pays ocean freight to the destination port.
- **FCL** — Full Container Load. The shipper books the entire container.
- **DEM (Demurrage)** — Daily charge for keeping a container at the terminal beyond the free period.
- **DET (Detention)** — Daily charge for keeping a container outside the terminal beyond the free period.
- **EFS** — Emergency Fuel Surcharge. An add-on levy applied when fuel costs spike.
- **Transshipment** — Routing cargo through an intermediate hub port. Usually cheaper but slower than direct.

## Project Structure

```
freight-rates/
├── agent.py        # Deep Agent definition and interactive REPL
├── tools.py        # All LangChain tools (Excel, FreightPulse, GoComet)
├── pyproject.toml
├── .env            # Your API keys (not committed)
└── .env.example    # Key template
```
