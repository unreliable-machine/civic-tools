# Change Agent Civic Intelligence Platform

> A distributed civic data infrastructure serving the social sector -- 26 repositories, 14 data services, 8 OpenWebUI tools, and a federated search gateway. ~11.9 million records across 60+ tables, two PostgreSQL databases, hosted on Railway.

## Architecture

```
                        +---------------------------+
                        |      civic-demo           |
                        |   (AI chat interface)     |
                        +------------+--------------+
                                     |
                        +------------v--------------+
                        |    OpenWebUI Tools (8)    |
                        |  community, research,     |
                        |  funding, search, court,  |
                        |  procurement, orgs, legs  |
                        +------------+--------------+
                                     |
                        +------------v--------------+
                        |   civic-intelligence      |
                        |  (entity graph + AI       |
                        |   narration, 23K entities)|
                        +------------+--------------+
                                     |
              +----------------------v----------------------+
              |            civic-gateway                    |
              |  (federated search across 12 sources,      |
              |   3 compose endpoints, relevance ranking)   |
              +---+-----+-----+-----+-----+-----+----+----+
                  |     |     |     |     |     |    |
     +----------+ | +---+ +---+ +---+ +---+ +--++ +--+--------+
     |          | | |   | |   | |   | |   | |   | |          |
+----v---+ +----v-v-v+ +v--+ +v--+ +v--+ +v--+ +v-+ +--------v---+
| census | | labor   | |hlth| |hsg| |fin| |irs| |ct| |legislators |
| 138K   | | 27K     | |70K | |7K | |4.2M| |6.3M| |33K| |1.5M bills |
+--------+ +---------+ +---+ +---+ +---+ +---+ +--+ +------+-----+
                                                        |
     +-----------+ +-----------+ +------------+  +------v-----+
     |procurement| | funding   | | nonprofits |  |    olms    |
     |  1.7M     | | 3.4M      | | (enrichment)|  | 21K (SQLite)|
     +-----------+ +-----------+ +------------+  +------------+
                          |
              +-----------v-----------+
              |  External Data APIs   |
              |  Census, EPI, CDC,    |
              |  HUD, FEC, IRS,       |
              |  CourtListener,       |
              |  OpenStates, SAM.gov, |
              |  Grants.gov, DOL,     |
              |  BLS, LittleSis,      |
              |  Senate LDA, ProPublica|
              +-----------------------+
```

**Data flow:** External APIs feed into 14 FastAPI microservices via scheduled sync jobs and CLI connectors. All services write to a shared PostgreSQL instance (yamanote). civic-gateway federates search across all domains. civic-intelligence resolves entities across sources into a unified graph. OpenWebUI tools expose the platform to AI assistants. civic-demo provides an end-user chat interface.

---

## Databases

| Database | Host | Size | Tables | Records | Services |
|----------|------|------|--------|---------|----------|
| **Main (yamanote)** | yamanote.proxy.rlwy.net:37935 | ~12 GB | 54 | ~9.5M | All except civic-irs |
| **6MOF** (IRS + Congress + OpenStates) | metro.proxy.rlwy.net:40549 | ~61 GB | 6 core + 80 OpenStates replica | ~6.3M core | civic-irs, civic-legislators (federal) |

---

## Services

### Community Intelligence (decomposed 2026-03-24)

Four services covering demographics, labor economics, public health, and housing affordability at every US geography. Decomposed from a single civic-census monolith for independent scaling.

| Service | Data Source | Tables | Records | Production URL | Repo |
|---------|-----------|--------|---------|----------------|------|
| civic-census | Census ACS 2024 (5-year) | `census_profiles` | 138,294 | civic-census-production.up.railway.app | [civic-census](https://github.com/unreliable-machine/civic-census) |
| civic-labor | EPI SWADL + BLS OES/LAUS | `epi_indicators`, `bls_occupational_wages` | 26,775 | civic-labor-production.up.railway.app | [civic-labor](https://github.com/unreliable-machine/civic-labor) |
| civic-health | CDC PLACES (2023) | `health_indicators` | 70,357 | civic-health-production.up.railway.app | [civic-health](https://github.com/unreliable-machine/civic-health) |
| civic-housing | HUD FMR + Income Limits | `housing_indicators` | 6,977 | civic-housing-production.up.railway.app | [civic-housing](https://github.com/unreliable-machine/civic-housing) |

**Crosswalk keys:** State level via `state_abbr` (universal). County level via `state_fips || county_fips` = CDC `location_id`.

### Core Data Services

| Service | Data Source | Key Tables | Records | Repo |
|---------|-----------|------------|---------|------|
| civic-finance | FEC, Senate LDA, LittleSis | `cf_influence_relationships`, `cf_contribution_aggregates`, `cf_influence_entities`, +9 more | 4,177,470 | [civic-finance](https://github.com/unreliable-machine/civic-finance) |
| civic-irs | IRS BMF bulk (6MOF DB) | `irs_filings`, `irs_organizations`, `foundations`, `foundation_grants` | 9,676,235 | [civic-irs](https://github.com/unreliable-machine/civic-irs) |
| civic-court | CourtListener | `court_judges`, `court_dockets`, `court_opinions` | 32,759 | [civic-court](https://github.com/unreliable-machine/civic-court) |
| civic-funding | Grants.gov + IRS 990-PF Schedule I | `foundation_grants`, `foundations`, `foundation_rfps` | 3,425,080 | [civic-funding](https://github.com/unreliable-machine/civic-funding) |
| civic-procurement | SAM.gov + USAspending + state portals | `state_awards`, `awards`, `opportunities`, `state_grants` | 1,717,930 | [civic-procurement](https://github.com/unreliable-machine/civic-procurement) |
| civic-nonprofits | ProPublica + IRS enrichment | Enrichment layer on civic-irs data | -- | [civic-nonprofits](https://github.com/unreliable-machine/civic-nonprofits) |
| civic-legislators | OpenStates + GovTrack | `os_bill`, `legislators`, `govtrack_persons`, `govtrack_votes` | 1,528,033 | [civic-legislators](https://github.com/unreliable-machine/civic-legislators) |
| civic-olms | DOL OLMS website | `audit_letters`, `findings` (SQLite, not Railway) | 20,612 | [civic-olms](https://github.com/unreliable-machine/civic-olms) |

### OpenWebUI Tools

Eight tools that expose the platform to AI assistants running in OpenWebUI.

| Tool | Covers | Repo |
|------|--------|------|
| civic-community | Census, labor, health, housing (all 4 community services) | Built into [civic-tools](https://github.com/unreliable-machine/civic-tools) |
| civic-research | Campaign finance, lobbying, influence networks | [civic-research-tool](https://github.com/unreliable-machine/civic-research-tool) |
| civic-funding | Grants, foundations, 990-PF giving | [civic-funding-tool](https://github.com/unreliable-machine/civic-funding-tool) |
| civic-search | Cross-source federated search | [civic-search-tool](https://github.com/unreliable-machine/civic-search-tool) |
| civic-procurement | Federal + state contracts and opportunities | [civic-procurement-tool](https://github.com/unreliable-machine/civic-procurement-tool) |
| civic-organizations | Nonprofit discovery and profiles | [civic-organizations-tool](https://github.com/unreliable-machine/civic-organizations-tool) |
| civic-legislators | State legislators, bills, voting records | [civic-legislators-tool](https://github.com/unreliable-machine/civic-legislators-tool) |
| civic-court | Federal court opinions, dockets, judges | [civic-court-tool](https://github.com/unreliable-machine/civic-court-tool) |

### Infrastructure

| Service | Purpose | Key Numbers | Repo |
|---------|---------|-------------|------|
| civic-gateway | Federated search (12 sources), 3 compose endpoints, relevance ranking | 5 API endpoints, 16 models, 50 tests | [civic-gateway](https://github.com/unreliable-machine/civic-gateway) |
| civic-intelligence | Entity graph -- unified entities, aliases, relationships, cross-source ID resolution | 23,179 entities, 25,679 source IDs, 582 aliases, 392 relationships | [civic-intelligence](https://github.com/unreliable-machine/civic-intelligence) |
| civic-tools | Tool aggregator + shared utilities (geocoding, FIPS lookups, data quality) | Houses civic-community tool | [civic-tools](https://github.com/unreliable-machine/civic-tools) |
| civic-demo | AI chat demo interface | -- | [civic-demo](https://github.com/unreliable-machine/civic-demo) |
| civic-intelligence-explorer | React frontend for entity graph exploration (WIP) | -- | [civic-intelligence-explorer](https://github.com/unreliable-machine/civic-intelligence-explorer) |

### Data Quality

| Table | Records | Purpose |
|-------|---------|---------|
| `sentinel_audit_log` | 46,198 | All data operations logged |
| `sentinel_checks` | 16,984 | Data quality check results |
| `sentinel_findings` | 1,001 | Issues found and tracked |

### Legacy

| Service | Purpose | Repo |
|---------|---------|------|
| govcon-intelligence | Original monolith (all 12 services before decomposition) | [govcon-intelligence](https://github.com/unreliable-machine/govcon-intelligence) |

---

## Repository Index (26 repos)

| # | Repo | Type | Description |
|---|------|------|-------------|
| 1 | civic-census | Data service | Census ACS demographics |
| 2 | civic-labor | Data service | EPI wages + BLS employment |
| 3 | civic-health | Data service | CDC PLACES public health |
| 4 | civic-housing | Data service | HUD fair market rents + income limits |
| 5 | civic-finance | Data service | FEC, Senate LDA, LittleSis influence |
| 6 | civic-irs | Data service | IRS 990 filings + exempt orgs |
| 7 | civic-court | Data service | CourtListener opinions, dockets, judges |
| 8 | civic-funding | Data service | Grants.gov + 990-PF foundation grants |
| 9 | civic-procurement | Data service | SAM.gov + USAspending + state procurement |
| 10 | civic-nonprofits | Data service | ProPublica nonprofit enrichment |
| 11 | civic-legislators | Data service | OpenStates + GovTrack legislators and bills |
| 12 | civic-olms | Data service | DOL audit letters (SQLite) |
| 13 | civic-gateway | Infrastructure | Federated search + compose endpoints |
| 14 | civic-intelligence | Infrastructure | Entity graph + AI narration |
| 15 | civic-tools | Infrastructure | Shared utilities + tool aggregator |
| 16 | civic-demo | Infrastructure | AI chat demo interface |
| 17 | civic-intelligence-explorer | Infrastructure | React entity graph frontend (WIP) |
| 18 | civic-community (tool) | OpenWebUI tool | Community intelligence (in civic-tools) |
| 19 | civic-research-tool | OpenWebUI tool | Campaign finance research |
| 20 | civic-funding-tool | OpenWebUI tool | Grant + foundation search |
| 21 | civic-search-tool | OpenWebUI tool | Cross-source federated search |
| 22 | civic-procurement-tool | OpenWebUI tool | Federal + state contracts |
| 23 | civic-organizations-tool | OpenWebUI tool | Nonprofit discovery |
| 24 | civic-legislators-tool | OpenWebUI tool | Legislators + bills |
| 25 | civic-court-tool | OpenWebUI tool | Court opinions |
| 26 | govcon-intelligence | Legacy | Original monolith |

All repos live under **github.com/unreliable-machine/**.

---

## External Data Sources

| Source | API | Auth | Services Using It |
|--------|-----|------|-------------------|
| Census ACS | api.census.gov | API key | civic-census |
| EPI SWADL | epi.org (public) | None | civic-labor |
| BLS OES/LAUS | data.bls.gov | API key | civic-labor |
| CDC PLACES | dev.socrata.com | Socrata token | civic-health |
| HUD FMR/IL | huduser.gov | API token | civic-housing |
| FEC/OpenFEC | api.open.fec.gov | API key | civic-finance |
| Senate LDA | lda.senate.gov | Token (sunsets 2026-06-30) | civic-finance |
| LittleSis | littlesis.org | None (bulk) | civic-finance |
| IRS BMF | irs.gov (bulk) | None | civic-irs |
| CourtListener | courtlistener.com | API token | civic-court |
| Grants.gov | grants.gov | None | civic-funding |
| SAM.gov | sam.gov | API key | civic-procurement |
| USAspending | usaspending.gov | None | civic-procurement |
| OpenStates | openstates.org | API key | civic-legislators |
| Congress.gov | api.congress.gov | API key | civic-irs (bills) |
| GovTrack | govtrack.us | None | civic-irs (legislators) |
| ProPublica | propublica.org | None | civic-nonprofits |
| DOL OLMS | dol.gov | None (scraped) | civic-olms |

---

## Infrastructure

| Component | Detail |
|-----------|--------|
| **Hosting** | Railway (project: govcon-intelligence, ID: `1434fdb0-d403-487b-839a-446df66bd2b9`) |
| **Databases** | PostgreSQL -- yamanote (main, 12 GB) + 6MOF (IRS/Congress, 61 GB) |
| **Auth** | `GOVCON_API_KEY` bearer token on all `/api/*` endpoints (disabled in dev) |
| **Auto-deploy** | Push to `main` triggers Railway build (most services) |
| **Service framework** | FastAPI (Python 3.13) + SQLAlchemy + PostgreSQL full-text search |
| **Container** | `python:3.13.2-slim`, non-root user, uvicorn workers |
| **Connection pooling** | Per-service: `DB_POOL_SIZE` + `DB_MAX_OVERFLOW` (typically 5+2 per worker) |
| **Health checks** | `GET /health` on each service (120s timeout) |
| **Search** | PostgreSQL FTS with `tsvector` triggers, federated through civic-gateway |

---

## Not Yet Integrated (Keys Ready)

| API | Priority | Status |
|-----|----------|--------|
| CDC SVI (Social Vulnerability) | P2 | Socrata token works |
| Census CRE (Community Resilience) | P2 | Census key works |
| Congress.gov expansion (CRS reports, hearings) | P2 | Key exists |
| EPA Air Quality (AQS) | P3 | Key registered |
| FBI Crime Data Explorer | P3 | Key available |
| College Scorecard | P4 | Key available |
| Urban Institute Education | P4 | No auth needed |

---

## Quick Start

```bash
# 1. Clone any service
git clone https://github.com/unreliable-machine/civic-finance.git
cd civic-finance

# 2. Set up Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 3. Configure environment
cp .env.example .env
# Required in .env:
#   DATABASE_URL=postgresql://...  (yamanote connection string)
#   GOVCON_API_KEY=                (leave empty for dev -- auth disabled)
#   <service-specific API keys>

# 4. Initialize database (creates tables + FTS triggers)
# Each service has its own init command, e.g.:
civic-finance init-db

# 5. Run the service
uvicorn civic_finance.api.app:app --host 0.0.0.0 --port 8419 --reload

# Swagger docs at http://localhost:<port>/docs
```

All services follow this same pattern: clone, venv, install, configure `.env`, init-db, uvicorn. Port assignments vary by service. Each repo's README has the exact commands and required environment variables.

**To run the full platform locally,** you need the shared PostgreSQL database (yamanote) accessible. All services except civic-irs and civic-olms connect to the same database instance. civic-irs uses the 6MOF database. civic-olms uses a local SQLite file.
