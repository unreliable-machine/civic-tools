# Civic Intelligence Tools

Open WebUI tools for querying 60GB of civic intelligence data — federal contracts, grants, campaign finance, lobbying, court records, influence networks, and IRS nonprofit filings. Built for [Change Agent AI](https://thechange.ai).

## Overview

Seven tools give conversational AI (Qwen, GPT, etc.) direct access to civic data across 12 microservices. Each tool covers a domain, returns markdown, and degrades gracefully when a service is down.

```
User: "Any pay-to-play with Lockheed Martin?"
Qwen: → pay_to_play_analysis("Lockheed Martin")
      → Overlap Score: 100% — contributions + lobbying + $440M in contracts
```

## Tools

| Tool | Domain | Methods | Backend API |
|------|--------|---------|-------------|
| **civic_research** | Campaign finance, lobbying, influence networks, pay-to-play, IRS 990 | 12 | civic-finance, civic-irs |
| **civic_search** | Cross-source search, data freshness status | 2 | govcon-api |
| **civic_legislators** | Legislators, bills, demographics, bill briefs | 5 | govcon-api |
| **civic_funding** | Federal grants, private foundations, foundation grants | 5 | govcon-api |
| **civic_procurement** | Contract opportunities, awards, SAM entities | 5 | govcon-api |
| **civic_court** | Court opinions, dockets, judges | 5 | govcon-api |
| **civic_organizations** | Nonprofits, partner discovery | 3 | govcon-api |

### civic_research (the headliner)

The newest and most capable tool — calls civic-finance and civic-irs microservices directly (no monolith routing).

| Method | What It Does |
|--------|-------------|
| `search_campaign_finance` | FEC candidates, committees, contribution aggregates |
| `search_lobbying` | Senate LDA filings and lobbyist contributions |
| `search_influence_network` | LittleSis power network (437K entities, 1.8M relationships) |
| `get_entity_network` | Full relationship map for a specific entity |
| `crosswalk_legislator` | Map between bioguide, FEC, Open States, OpenSecrets IDs |
| `legislator_funding_profile` | Complete money profile — FEC + committees + expenditures + lobbying + influence |
| `org_influence_map` | Organization's full political footprint |
| `pay_to_play_analysis` | Cross-reference donations, lobbying, and contracts |
| `search_expenditures` | Super PAC independent expenditures for/against candidates |
| `generate_briefing` | Multi-source intelligence briefing (lobbying + influence + candidates) |
| `search_irs_organizations` | 2.9M IRS tax-exempt organizations |
| `search_irs_filings` | 990 filing history by EIN — revenue, expenses, assets over time |

## Architecture

```
┌─────────────────────┐
│  Open WebUI (Qwen)  │
│  chat.thechange.ai  │
└────────┬────────────┘
         │ tool calls
    ┌────┴────────────────────────────────┐
    │                                     │
    ▼                                     ▼
┌──────────────────┐          ┌─────────────────────┐
│  civic_research  │          │  civic_search        │
│  civic-finance ──┤          │  civic_legislators   │
│  civic-irs ──────┤          │  civic_funding       │
└──────────────────┘          │  civic_procurement   │
    │           │             │  civic_court          │
    ▼           ▼             │  civic_organizations  │
┌────────┐ ┌───────┐         └──────────┬────────────┘
│ civic  │ │ civic │                    │
│finance │ │  irs  │                    ▼
│Railway │ │Railway│              ┌───────────┐
└────────┘ └───────┘              │ govcon-api │
                                  │  Railway   │
                                  └────────────┘
```

Each microservice runs independently on Railway. If civic-irs is down, campaign finance still works. If govcon-api is down, civic_research still works.

## Data Coverage

| Source | Records | Service |
|--------|---------|---------|
| FEC Candidates | ~10K | civic-finance |
| FEC Committees | ~15K | civic-finance |
| Contribution Aggregates | 1.4M | civic-finance |
| Independent Expenditures | ~200K | civic-finance |
| Senate LDA Lobbying Filings | ~50K | civic-finance |
| LittleSis Influence Entities | 437K | civic-finance |
| LittleSis Relationships | 1.8M | civic-finance |
| Legislator ID Crosswalk | ~7K | civic-finance |
| IRS Exempt Organizations | 2.9M | civic-irs |
| IRS 990 Filings | 2.9M | civic-irs |
| Federal Contract Opportunities | ~90K | govcon-api |
| Federal Awards | ~500K | govcon-api |
| Federal Grants | ~80K | govcon-api |
| Private Foundations | ~100K | govcon-api |
| State Legislators | ~7K | govcon-api |
| Court Opinions/Dockets | ~1M | govcon-api |

## Installation

### Option 1: Paste into Open WebUI (quickest)

1. Open your Open WebUI instance → **Admin Panel** → **Tools** → **+**
2. Paste the contents of any `tools/*.py` file
3. Save → configure Valves (gear icon)

### Option 2: Clone and push via sync script

```bash
git clone https://github.com/unreliable-machine/civic-tools.git
cd civic-tools
pip install -r requirements.txt
```

## Configuration

### Valves (per-tool settings in Open WebUI)

**civic_research:**
| Valve | Value |
|-------|-------|
| `CIVIC_FINANCE_URL` | `https://civic-finance-production.up.railway.app` |
| `CIVIC_IRS_URL` | `https://civic-irs-production.up.railway.app` |
| `API_KEY` | Your GOVCON API key |
| `TIMEOUT` | `30` |
| `COMPOSE_TIMEOUT` | `60` |

**All other civic tools:**
| Valve | Value |
|-------|-------|
| `GOVCON_API_URL` | `https://govcon-api-production.up.railway.app` |
| `GOVCON_API_KEY` | Your GOVCON API key |
| `TIMEOUT` | `30` |

### Environment Variables

If you prefer env vars over Valves:

```bash
export GOVCON_API_KEY="your-key-here"
export GOVCON_API_URL="https://govcon-api-production.up.railway.app"
export CIVIC_FINANCE_URL="https://civic-finance-production.up.railway.app"
export CIVIC_IRS_URL="https://civic-irs-production.up.railway.app"
```

## Project Structure

```
civic-tools/
├── tools/                      # Open WebUI tool files (.py)
│   ├── civic_research.py       # Campaign finance, lobbying, influence, IRS 990
│   ├── civic_search.py         # Cross-source search, data status
│   ├── civic_legislators.py    # Legislators, bills, demographics
│   ├── civic_funding.py        # Federal grants, private foundations
│   ├── civic_procurement.py    # Contract opportunities, awards, SAM
│   ├── civic_court.py          # Court opinions, dockets, judges
│   └── civic_organizations.py  # Nonprofits, partner discovery
├── docs/                       # Documentation
│   └── civic-tool-docstrings.md
├── .env.example                # Environment variable template
├── .gitignore
├── requirements.txt
└── README.md
```

## Tool Patterns

All tools follow the same conventions:

- **EventEmitter** class for progress/error/success status updates
- **Valves(BaseModel)** with URL, API key, and timeout configuration
- **`_get()` / `_post()`** async HTTP helpers (civic_research adds retry/backoff)
- **Markdown output** — every method returns formatted markdown, never raw JSON
- **Graceful degradation** — errors return helpful messages, never stack traces
- **Pagination hints** — results include "use page=2 for more" guidance
- **Drill-down hints** — results suggest next methods to call

### Anti-Fragile Pattern (civic_research)

```python
async def _get(self, base_url, path, params=None, timeout=None):
    """2 retries with 1s/3s backoff on 5xx/connection errors.
    Returns (data, None) on success or (None, error_string) on failure.
    Never raises."""
```

## Demo Queries

Test these after installation:

1. **"Search lobbying around homelessness"** → Vectis DC lobbying for LAHSA
2. **"Any pay-to-play with Lockheed Martin?"** → 100% overlap score, $440M in contracts
3. **"Look up Bernie Sanders' bioguide ID"** → S000033 with all cross-referenced IDs
4. **"Search IRS records for Red Cross"** → 180 exempt organizations
5. **"What's ExxonMobil's political influence?"** → lobbying, PACs, LittleSis network

## Related Repositories

| Repo | What |
|------|------|
| [civic-finance](https://github.com/unreliable-machine/civic-finance) | Campaign finance microservice (FEC, lobbying, LittleSis) |
| [civic-irs](https://github.com/unreliable-machine/civic-irs) | IRS 990 filings microservice |
| [govcon-intelligence](https://github.com/unreliable-machine/govcon-intelligence) | Monolith API (procurement, grants, legislators, courts) |
| [civic-intelligence](https://github.com/unreliable-machine/civic-intelligence) | Graph engine for entity resolution |

## Contributing

1. Clone the repo
2. Create a branch (`git checkout -b feat/my-tool`)
3. Make changes to `tools/*.py`
4. Test locally against production APIs
5. Open a PR

## License

MIT
