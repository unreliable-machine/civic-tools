"""
title: Civic Organizations Intelligence
author: ChangeAgent AI
description: Search nonprofit organizations, get IRS filing data, and discover coalition partners for advocacy and organizing.
version: 0.1.0
requirements: httpx
"""

import json
import os
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

SYSTEM_PROMPT_INJECTION = """
### Civic Organizations Intelligence — Usage Guide
Use this tool for nonprofit and civil society data:
- `search_nonprofits` — Find 501(c)(3) organizations by name, state, or NTEE category
- `get_nonprofit` — Detailed IRS filing data for a specific nonprofit
- `find_partners` — Coalition partner discovery: cross-references nonprofits + demographics + legislators + litigation risk
For foundations (philanthropic funders), use the Civic Funding tool instead.
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

    async def emit(self, description="Unknown State", status="in_progress", done=False):
        if self.event_emitter:
            await self.event_emitter(
                {"type": "status", "data": {"status": status, "description": description, "done": done}}
            )


class Tools:
    class Valves(BaseModel):
        GOVCON_API_URL: str = Field(
            default_factory=lambda: os.getenv("GOVCON_API_URL", "https://govcon-api-production.up.railway.app"),
            description="GovCon Civic Intelligence API base URL",
        )
        GOVCON_API_KEY: str = Field(
            default_factory=lambda: os.getenv("GOVCON_API_KEY", ""),
            description="Bearer token for GovCon API authentication",
        )
        TIMEOUT: int = Field(default=30, description="HTTP request timeout in seconds")

    def __init__(self):
        self.valves = self.Valves()

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

    @staticmethod
    def _fmt_money(val) -> str:
        if val is None:
            return "N/A"
        try:
            return f"${float(val):,.0f}"
        except (ValueError, TypeError):
            return str(val)

    # ── Tool methods ──────────────────────────────────────────────

    async def search_nonprofits(
        self,
        query: str,
        state: Optional[str] = None,
        ntee_code: Optional[str] = None,
        page: int = 1,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Search nonprofit organizations (501(c)(3) public charities) by name, state, or NTEE category.
        Use this when the user asks about nonprofits, charitable organizations, NGOs, or wants to find
        organizations working on a specific issue in a specific area. This searches the ProPublica
        Nonprofit Explorer database.

        :param query: Search text — organization name or keyword (e.g., "Planned Parenthood", "food bank")
        :param state: Two-letter state code filter (e.g., "GA", "OH")
        :param ntee_code: NTEE major category code (e.g., "P" for Human Services, "R" for Civil Rights, "S" for Community Improvement, "J" for Employment, "W" for Public Benefit)
        :param page: Page number (default: 1)
        :return: List of nonprofits with name, EIN, state, NTEE classification, revenue, and assets.
        """
        emitter = EventEmitter(__event_emitter__)
        await emitter.progress_update(f"Searching nonprofits: {query}")

        try:
            # Nonprofits endpoint is 0-indexed; convert 1-indexed user page
            api_page = max(0, page - 1)
            data = await self._get("/nonprofits", {
                "q": query,
                "state": state,
                "ntee": ntee_code,
                "page": api_page,
            })
        except Exception as e:
            await emitter.error_update(f"Search failed: {e}")
            return f"Error: Failed to search nonprofits — {e}"

        items = data.get("results", [])
        total = data.get("total_results", len(items))
        has_next = data.get("has_next", False)

        if not items:
            await emitter.success_update("No nonprofits found")
            return f"No nonprofit organizations found for '{query}'."

        lines = [f"## Nonprofit Organizations\n\nFound **{total}** results for \"{query}\"\n"]
        for i, org in enumerate(items, 1):
            name = org.get("name", "Unknown")
            ein = org.get("ein", "N/A")
            org_state = org.get("state", "")
            org_city = org.get("city", "")
            ntee = org.get("ntee_code", "")
            ntee_desc = org.get("ntee_description", "")
            revenue = org.get("revenue")
            assets = org.get("assets")

            lines.append(f"{i}. **{name}** (EIN: {ein})")
            detail_parts = []
            if org_city and org_state:
                detail_parts.append(f"{org_city}, {org_state}")
            elif org_state:
                detail_parts.append(org_state)
            if ntee_desc:
                detail_parts.append(ntee_desc)
            elif ntee:
                detail_parts.append(f"NTEE: {ntee}")
            if detail_parts:
                lines.append(f"   {' | '.join(detail_parts)}")

            money_parts = []
            if revenue:
                money_parts.append(f"Revenue: {self._fmt_money(revenue)}")
            if assets:
                money_parts.append(f"Assets: {self._fmt_money(assets)}")
            if money_parts:
                lines.append(f"   {' | '.join(money_parts)}")

            lines.append(f"   _Use get_nonprofit(\"{ein}\") for full details_")
            lines.append("")

        if has_next:
            lines.append(f"_Page {page} — more results available. Use page={page + 1} for next page._")

        await emitter.success_update(f"Found {total} nonprofits")
        return "\n".join(lines)

    async def get_nonprofit(
        self,
        ein: str,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Get full details for a specific nonprofit organization by its EIN. Use this after search_nonprofits
        to see an organization's complete IRS filing data including revenue, expenses, and leadership.

        :param ein: The nonprofit's EIN, with or without dash (e.g., "13-1837418")
        :return: Nonprofit profile with name, address, mission, revenue, expenses, assets, and key personnel from latest IRS filing.
        """
        emitter = EventEmitter(__event_emitter__)
        await emitter.progress_update(f"Fetching nonprofit {ein}...")

        try:
            org = await self._get(f"/nonprofits/{ein}")
        except Exception as e:
            await emitter.error_update(f"Fetch failed: {e}")
            return f"Error: Failed to fetch nonprofit {ein} — {e}"

        lines = [f"## Nonprofit Profile\n"]
        lines.append(f"**{org.get('name', 'Unknown')}**\n")

        fields = [
            ("EIN", org.get("ein")),
            ("Location", f"{org.get('city', '')}, {org.get('state', '')}" if org.get("city") else org.get("state")),
            ("NTEE Code", org.get("ntee_code")),
            ("NTEE Description", org.get("ntee_description")),
            ("Subsection", org.get("subsection_code")),
            ("Ruling Date", org.get("ruling_date")),
            ("Tax Period", org.get("tax_period")),
            ("Filing Year", org.get("filing_year")),
            ("Revenue", self._fmt_money(org.get("revenue")) if org.get("revenue") else None),
            ("Expenses", self._fmt_money(org.get("expenses")) if org.get("expenses") else None),
            ("Assets", self._fmt_money(org.get("assets")) if org.get("assets") else None),
            ("Income", self._fmt_money(org.get("income")) if org.get("income") else None),
        ]
        for label, val in fields:
            if val:
                lines.append(f"- **{label}:** {val}")

        await emitter.success_update("Nonprofit details retrieved")
        return "\n".join(lines)

    async def find_partners(
        self,
        topic: str,
        state: str,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Discover potential coalition partners for advocacy or organizing around a specific topic in a
        specific state. This is a COMPOUND intelligence query that cross-references nonprofits working
        on the topic, state demographics, and relevant legislators. Use this when the user asks about
        "finding partners", "coalition building", "who's working on [issue] in [state]", or
        "organizations we could partner with."

        :param topic: The advocacy or organizing topic (e.g., "education equity", "healthcare access", "voting rights")
        :param state: Two-letter state code (e.g., "GA", "AZ")
        :return: Multi-source intelligence brief with: relevant nonprofits in the state, state demographic context, state legislators working on related issues, and potential litigation risk from court dockets.
        """
        emitter = EventEmitter(__event_emitter__)
        await emitter.progress_update(f"Discovering coalition partners for '{topic}' in {state}...")

        try:
            data = await self._post("/compose/partners", {
                "topic": topic,
                "state": state,
            })
        except Exception as e:
            await emitter.error_update(f"Partner discovery failed: {e}")
            return f"Error: Failed to find partners — {e}"

        lines = [f"## Coalition Partner Discovery: \"{topic}\" in {state}\n"]

        # Nonprofits section
        np_section = data.get("nonprofits", {})
        if np_section.get("status") == "ok":
            np_data = np_section.get("data", {})
            np_results = np_data.get("results", []) if isinstance(np_data, dict) else np_data
            if np_results:
                lines.append(f"### Relevant Organizations ({len(np_results)} found)\n")
                for i, org in enumerate(np_results[:10], 1):
                    name = org.get("name", "Unknown")
                    city = org.get("city", "")
                    org_state = org.get("state", "")
                    ntee_desc = org.get("ntee_description", "")
                    revenue = org.get("revenue")

                    loc = f"{city}, {org_state}" if city else org_state
                    lines.append(f"{i}. **{name}** ({loc})")
                    detail_parts = []
                    if ntee_desc:
                        detail_parts.append(ntee_desc)
                    if revenue:
                        detail_parts.append(f"Revenue: {self._fmt_money(revenue)}")
                    if detail_parts:
                        lines.append(f"   {' | '.join(detail_parts)}")
                    lines.append("")
                if len(np_results) > 10:
                    lines.append(f"_...and {len(np_results) - 10} more organizations_\n")
            else:
                lines.append("### Organizations\n\nNo nonprofits found for this topic in this state.\n")
        else:
            error = np_section.get("error", "unknown error")
            lines.append(f"### Organizations\n\n_Could not search nonprofits: {error}_\n")

        # Demographics section
        demo_section = data.get("demographics", {})
        if demo_section.get("status") == "ok":
            demo = demo_section.get("data", {})
            if demo:
                lines.append("### State Demographics\n")
                pop = demo.get("total_population")
                income = demo.get("median_household_income")
                poverty = demo.get("poverty_rate")
                if pop:
                    try:
                        lines.append(f"- Population: {int(float(pop)):,}")
                    except (ValueError, TypeError):
                        pass
                if income:
                    lines.append(f"- Median Income: {self._fmt_money(income)}")
                if poverty is not None:
                    try:
                        lines.append(f"- Poverty Rate: {float(poverty):.1f}%")
                    except (ValueError, TypeError):
                        pass
                lines.append("")

        # Legislators section
        leg_section = data.get("legislators", {})
        if leg_section.get("status") == "ok":
            leg_data = leg_section.get("data", {})
            leg_results = leg_data.get("results", []) if isinstance(leg_data, dict) else leg_data
            if leg_results:
                lines.append(f"### Relevant Legislators ({len(leg_results)} found)\n")
                for leg in leg_results[:8]:
                    name = leg.get("name", "Unknown")
                    party = leg.get("party", "")
                    chamber = {"upper": "Senate", "lower": "House"}.get(leg.get("chamber", ""), leg.get("chamber", ""))
                    district = leg.get("district", "")
                    lines.append(f"- **{name}** ({party}) — {chamber} District {district}")
                lines.append("")

        # Litigation risk section
        lit_section = data.get("litigation_risk", {})
        if lit_section.get("status") == "ok":
            lit_data = lit_section.get("data", {})
            if lit_data:
                lines.append("### Litigation Landscape\n")
                dockets = lit_data.get("dockets", []) if isinstance(lit_data, dict) else []
                if dockets:
                    for d in dockets[:5]:
                        case_name = d.get("case_name", "Unknown case")
                        court = d.get("court", "")
                        lines.append(f"- {case_name} ({court})")
                    lines.append("")
                else:
                    summary = lit_data.get("summary", "")
                    if summary:
                        lines.append(f"{summary}\n")
                    else:
                        lines.append("No relevant litigation found.\n")

        await emitter.success_update("Partner discovery complete")
        return "\n".join(lines)
