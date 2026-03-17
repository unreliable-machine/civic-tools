"""
title: Civic Intelligence Search
author: ChangeAgent AI
description: Search across all civic intelligence data — federal contracts, grants, foundations, legislators, bills, nonprofits, court records, and demographics.
version: 0.1.0
requirements: httpx
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

SYSTEM_PROMPT_INJECTION = """
### Civic Intelligence Search — Usage Guide
Use this tool for broad, cross-source searches across civic intelligence data.
- `search_all` searches across ALL data sources at once — use when the query spans multiple domains or you're unsure which specific tool to use.
- `data_status` shows what data is available and how fresh it is — use when the user asks what civic data you have.
For domain-specific queries, prefer the specialized civic tools (procurement, funding, legislators, organizations, court) for better results.
"""


class EventEmitter:
    def __init__(self, event_emitter: Callable[[dict], Any] = None):
        self.event_emitter = event_emitter

    async def progress_update(self, description: str):
        await self.emit(description)

    async def error_update(self, description: str):
        await self.emit(description, "error", True)

    async def success_update(self, description: str):
        await self.emit(description, "success", True)

    async def emit(
        self,
        description: str = "Unknown State",
        status: str = "in_progress",
        done: bool = False,
    ):
        if self.event_emitter:
            await self.event_emitter(
                {
                    "type": "status",
                    "data": {
                        "status": status,
                        "description": description,
                        "done": done,
                    },
                }
            )


class Tools:
    class Valves(BaseModel):
        GOVCON_API_URL: str = Field(
            default_factory=lambda: os.getenv(
                "GOVCON_API_URL",
                "https://govcon-api-production.up.railway.app",
            ),
            description="GovCon Civic Intelligence API base URL",
        )
        GOVCON_API_KEY: str = Field(
            default_factory=lambda: os.getenv("GOVCON_API_KEY", ""),
            description="Bearer token for GovCon API authentication",
        )
        TIMEOUT: int = Field(default=30, description="HTTP request timeout in seconds")

    def __init__(self):
        self.valves = self.Valves()

    # ── HTTP helpers ──────────────────────────────────────────────

    def _headers(self) -> Dict[str, str]:
        h = {"Accept": "application/json"}
        if self.valves.GOVCON_API_KEY:
            h["Authorization"] = f"Bearer {self.valves.GOVCON_API_KEY}"
        return h

    async def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        import httpx

        url = f"{self.valves.GOVCON_API_URL.rstrip('/')}/api{path}"
        cleaned = {k: v for k, v in (params or {}).items() if v is not None}
        async with httpx.AsyncClient(timeout=self.valves.TIMEOUT) as client:
            resp = await client.get(url, params=cleaned, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    async def _post(self, path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        import httpx

        url = f"{self.valves.GOVCON_API_URL.rstrip('/')}/api{path}"
        async with httpx.AsyncClient(timeout=self.valves.TIMEOUT) as client:
            resp = await client.post(url, json=body or {}, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    # ── Tool methods ──────────────────────────────────────────────

    async def search_all(
        self,
        query: str,
        sources: Optional[List[str]] = None,
        page: int = 1,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Search across ALL civic intelligence data sources at once — federal contracts, grants, foundations,
        legislators, bills, nonprofits, court records, and demographics. Use this when the user wants a
        broad search across multiple data types, or when you're unsure which specific civic data source
        to query. Returns results grouped by source with relevance scores.

        :param query: The search query (e.g., "climate change", "education funding", "cybersecurity")
        :param sources: Optional list of specific sources to search. Valid values: opportunities, entities, grants, awards, foundations, legislators, bills, nonprofits, census, legislation_bills, legislation_people. If omitted, searches all sources.
        :param page: Page number for paginated results (default: 1)
        :return: Search results organized by data source, with relevance-ranked items from each source.
        """
        emitter = EventEmitter(__event_emitter__)
        await emitter.progress_update(f"Searching civic intelligence for: {query}")

        try:
            body: Dict[str, Any] = {"query": query, "page": page, "page_size": 25}
            if sources:
                body["sources"] = sources
            data = await self._post("/search", body)
        except Exception as e:
            await emitter.error_update(f"Search failed: {e}")
            return f"Error: Failed to search civic intelligence — {e}"

        # Format results grouped by source
        results = data if isinstance(data, dict) else {}
        items = results.get("results", [])
        total = results.get("total_results", len(items))

        if not items:
            await emitter.success_update("Search complete — no results found")
            return f"No results found for '{query}' across civic intelligence data sources."

        # Group by source
        grouped: Dict[str, list] = {}
        for item in items:
            src = item.get("source", "unknown")
            grouped.setdefault(src, []).append(item)

        source_labels = {
            "opportunities": "Federal Contract Opportunities (SAM.gov)",
            "entities": "Registered Entities (SAM.gov)",
            "grants": "Federal Grants (Grants.gov)",
            "awards": "Federal Awards (USAspending)",
            "foundations": "Private Foundations (IRS 990-PF)",
            "legislators": "State Legislators (Open States)",
            "bills": "Legislative Bills",
            "nonprofits": "Nonprofit Organizations",
            "census": "Census Demographics",
            "legislation_bills": "State Legislation (Bulk)",
            "legislation_people": "Legislative People",
        }

        lines = [f"## Civic Intelligence Search Results\n\nFound **{total}** results for \"{query}\"\n"]

        for source, source_items in grouped.items():
            label = source_labels.get(source, source.replace("_", " ").title())
            lines.append(f"### {label} ({len(source_items)} results)\n")
            for i, item in enumerate(source_items[:5], 1):
                title = item.get("title") or item.get("name") or item.get("label", "Untitled")
                snippet = item.get("snippet", "")
                lines.append(f"{i}. **{title}**")
                if snippet:
                    lines.append(f"   {snippet[:200]}")
                lines.append("")
            if len(source_items) > 5:
                lines.append(f"   _...and {len(source_items) - 5} more in {source}_\n")

        page_info = results.get("page", page)
        page_size = results.get("page_size", 25)
        if total > page_info * page_size:
            lines.append(f"\n_Showing page {page_info} of {(total + page_size - 1) // page_size}. Use page={page_info + 1} for more results._")

        await emitter.success_update(f"Found {total} results across {len(grouped)} sources")
        return "\n".join(lines)

    async def data_status(
        self,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Check what civic intelligence data is available and when each data source was last updated.
        Returns sync status for all data connectors including record counts and last sync timestamps.
        Use this when the user asks what data you have access to, how fresh the data is, or whether
        a specific data source is available.

        :return: Status of all data connectors showing last sync time, record counts, and health.
        """
        emitter = EventEmitter(__event_emitter__)
        await emitter.progress_update("Checking civic intelligence data status...")

        try:
            data = await self._get("/sync/status")
        except Exception as e:
            await emitter.error_update(f"Status check failed: {e}")
            return f"Error: Failed to check data status — {e}"

        if not data:
            await emitter.success_update("No data connectors found")
            return "No data connector status available."

        connector_labels = {
            "sam_opportunities": "Federal Contract Opportunities (SAM.gov)",
            "sam_entities": "Registered Entities (SAM.gov)",
            "grants_gov": "Federal Grants (Grants.gov)",
            "usaspending": "Federal Awards (USAspending)",
            "propublica_foundations": "Private Foundations (ProPublica/IRS)",
            "open_states_legislators": "State Legislators (Open States)",
            "census_acs": "Demographics (Census ACS)",
            "court_opinions": "Court Opinions (CourtListener)",
            "court_dockets": "Court Dockets (CourtListener)",
            "court_judges": "Court Judges (CourtListener)",
        }

        lines = ["## Civic Intelligence Data Status\n"]
        lines.append("| Data Source | Records | Last Synced | Status |")
        lines.append("|------------|---------|-------------|--------|")

        for connector in data:
            name = connector.get("connector", "unknown")
            label = connector_labels.get(name, name.replace("_", " ").title())
            records = connector.get("records_synced", 0)
            last_sync = connector.get("last_sync_at")

            if last_sync:
                try:
                    dt = datetime.fromisoformat(last_sync.replace("Z", "+00:00"))
                    age = datetime.now(timezone.utc) - dt
                    if age.days > 7:
                        status = f"Stale ({age.days}d ago)"
                    elif age.days > 0:
                        status = f"OK ({age.days}d ago)"
                    else:
                        hours = age.seconds // 3600
                        status = f"Fresh ({hours}h ago)"
                    sync_str = dt.strftime("%Y-%m-%d %H:%M UTC")
                except Exception:
                    sync_str = last_sync[:19]
                    status = "OK"
            else:
                sync_str = "Never"
                status = "Not synced"

            records_str = f"{records:,}" if records else "0"
            lines.append(f"| {label} | {records_str} | {sync_str} | {status} |")

        await emitter.success_update("Data status retrieved")
        return "\n".join(lines)
