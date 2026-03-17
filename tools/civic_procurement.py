"""
title: Civic Procurement Intelligence
author: ChangeAgent AI
description: Search federal contract opportunities (SAM.gov), registered entities, and contract awards (USAspending) — the full federal procurement landscape.
version: 0.1.0
requirements: httpx
"""

import json
import os
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

SYSTEM_PROMPT_INJECTION = """
### Civic Procurement Intelligence — Usage Guide
Use this tool for federal contracting and procurement data:
- `search_opportunities` — Open solicitations/RFPs from SAM.gov (what the government wants to buy)
- `search_awards` — Completed contract awards from USAspending (what the government already bought)
- `search_entities` — Companies registered to do business with the government (SAM.gov)
- `get_opportunity` / `get_entity` — Detailed views of specific records
Do NOT use this tool for grants or foundation funding — use the Civic Funding tool instead.
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

    @staticmethod
    def _fmt_money(val) -> str:
        if val is None:
            return "N/A"
        try:
            return f"${float(val):,.0f}"
        except (ValueError, TypeError):
            return str(val)

    # ── Tool methods ──────────────────────────────────────────────

    async def search_opportunities(
        self,
        query: str,
        agency: Optional[str] = None,
        naics_code: Optional[str] = None,
        set_aside: Optional[str] = None,
        active_only: bool = True,
        posted_from: Optional[str] = None,
        posted_to: Optional[str] = None,
        page: int = 1,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Search federal CONTRACT OPPORTUNITIES from SAM.gov — these are active solicitations where the
        government is seeking bids from contractors. Use this when the user asks about government RFPs,
        solicitations, contract opportunities, or "what contracts is [agency] offering." This is about
        contracts the government wants to AWARD, not contracts already awarded (use search_awards for that).

        :param query: Search text (e.g., "cybersecurity", "IT support services")
        :param agency: Agency code filter (e.g., "7013" for Army, "7500" for HHS)
        :param naics_code: 6-digit NAICS industry code filter (e.g., "541611" for management consulting)
        :param set_aside: Set-aside type filter (e.g., "SBA" for small business, "HZC" for HUBZone)
        :param active_only: If true, show only currently open opportunities (default: true)
        :param posted_from: Only show opportunities posted on or after this date (YYYY-MM-DD)
        :param posted_to: Only show opportunities posted on or before this date (YYYY-MM-DD)
        :param page: Page number (default: 1)
        :return: List of federal contract opportunities with title, solicitation number, agency, set-aside type, posting date, and response deadline.
        """
        emitter = EventEmitter(__event_emitter__)
        await emitter.progress_update(f"Searching federal contract opportunities: {query}")

        try:
            data = await self._get("/opportunities", {
                "search": query,
                "agency_code": agency,
                "naics_code": naics_code,
                "set_aside": set_aside,
                "active": active_only if active_only else None,
                "posted_from": posted_from,
                "posted_to": posted_to,
                "page": page,
                "page_size": 25,
            })
        except Exception as e:
            await emitter.error_update(f"Search failed: {e}")
            return f"Error: Failed to search contract opportunities — {e}"

        items = data.get("results", [])
        total = data.get("total_results", len(items))

        if not items:
            await emitter.success_update("No opportunities found")
            return f"No federal contract opportunities found for '{query}'."

        lines = [f"## Federal Contract Opportunities\n\nFound **{total}** results for \"{query}\"\n"]
        for i, opp in enumerate(items, 1):
            title = opp.get("title", "Untitled")
            sol_num = opp.get("solicitation_number") or ""
            agency_name = opp.get("agency_name") or opp.get("agency_code", "N/A")
            notice_type = opp.get("notice_type", "")
            set_aside_val = opp.get("set_aside_description") or opp.get("set_aside", "")
            posted = (opp.get("posted_date") or "")[:10]
            response_due = (opp.get("response_deadline") or "")[:10]
            opp_id = opp.get("opportunity_id", "")

            title_line = f"{i}. **{title}**"
            if sol_num:
                title_line += f" ({sol_num})"
            lines.append(title_line)
            detail_parts = []
            if agency_name:
                detail_parts.append(f"Agency: {agency_name}")
            if notice_type:
                detail_parts.append(f"Type: {notice_type}")
            if set_aside_val:
                detail_parts.append(f"Set-aside: {set_aside_val}")
            lines.append(f"   {' | '.join(detail_parts)}")
            date_parts = []
            if posted:
                date_parts.append(f"Posted: {posted}")
            if response_due:
                date_parts.append(f"Response due: {response_due}")
            if date_parts:
                lines.append(f"   {' | '.join(date_parts)}")
            if opp_id:
                lines.append(f"   _ID: {opp_id} — use get_opportunity({opp_id}) for details_")
            lines.append("")

        if total > page * 25:
            lines.append(f"_Showing page {page} of {(total + 24) // 25}. Use page={page + 1} for more._")

        await emitter.success_update(f"Found {total} contract opportunities")
        return "\n".join(lines)

    async def get_opportunity(
        self,
        opportunity_id: str,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Get full details for a specific federal contract opportunity from SAM.gov by its opportunity ID.
        Use this after search_opportunities to get complete information about a specific solicitation,
        including full description, contact info, and attachments.

        :param opportunity_id: The opportunity ID (string) from search results
        :return: Complete opportunity details including description, agency, contacts, dates, set-aside info, and NAICS code.
        """
        emitter = EventEmitter(__event_emitter__)
        await emitter.progress_update(f"Fetching opportunity {opportunity_id}...")

        try:
            opp = await self._get(f"/opportunities/{opportunity_id}")
        except Exception as e:
            await emitter.error_update(f"Fetch failed: {e}")
            return f"Error: Failed to fetch opportunity {opportunity_id} — {e}"

        lines = [f"## Contract Opportunity Detail\n"]
        lines.append(f"**{opp.get('title', 'Untitled')}**\n")

        fields = [
            ("Solicitation Number", opp.get("solicitation_number")),
            ("Agency", opp.get("agency_name") or opp.get("agency_code")),
            ("Notice Type", opp.get("notice_type")),
            ("Set-Aside", opp.get("set_aside_description") or opp.get("set_aside")),
            ("NAICS Code", opp.get("naics_code")),
            ("Posted Date", (opp.get("posted_date") or "")[:10]),
            ("Response Deadline", (opp.get("response_deadline") or "")[:10]),
            ("Archive Date", (opp.get("archive_date") or "")[:10]),
            ("Place of Performance", opp.get("place_of_performance")),
            ("Classification Code", opp.get("classification_code")),
        ]
        for label, val in fields:
            if val:
                lines.append(f"- **{label}:** {val}")

        desc = opp.get("description", "")
        if desc:
            lines.append(f"\n### Description\n\n{desc[:3000]}")
            if len(desc) > 3000:
                lines.append("\n_[Description truncated — full text available on SAM.gov]_")

        contact = opp.get("point_of_contact") or opp.get("contact_info")
        if contact:
            lines.append(f"\n### Point of Contact\n\n{contact}")

        await emitter.success_update("Opportunity details retrieved")
        return "\n".join(lines)

    async def search_awards(
        self,
        query: str,
        recipient: Optional[str] = None,
        agency: Optional[str] = None,
        naics_code: Optional[str] = None,
        fiscal_year: Optional[int] = None,
        page: int = 1,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Search federal CONTRACT AWARDS from USAspending.gov — these are contracts that have ALREADY been
        awarded to specific companies. Use this when the user asks about government spending, awarded
        contracts, "what awards went to [company]", or "how much did [agency] spend." This is about
        completed awards, not open solicitations (use search_opportunities for those).

        :param query: Search text (e.g., "Deloitte", "cloud migration")
        :param recipient: Recipient company name filter (case-insensitive substring match)
        :param agency: Awarding agency code filter (e.g., "7500" for HHS)
        :param naics_code: 6-digit NAICS code filter
        :param fiscal_year: Federal fiscal year filter (Oct-Sep cycle, e.g., 2026)
        :param page: Page number (default: 1)
        :return: List of federal contract awards with description, recipient, award amount, agency, and award date.
        """
        emitter = EventEmitter(__event_emitter__)
        await emitter.progress_update(f"Searching federal contract awards: {query}")

        try:
            data = await self._get("/awards", {
                "search": query,
                "recipient_name": recipient,
                "awarding_agency_code": agency,
                "naics_code": naics_code,
                "fiscal_year": fiscal_year,
                "page": page,
                "page_size": 25,
            })
        except Exception as e:
            await emitter.error_update(f"Search failed: {e}")
            return f"Error: Failed to search contract awards — {e}"

        items = data.get("results", [])
        total = data.get("total_results", len(items))

        if not items:
            await emitter.success_update("No awards found")
            return f"No federal contract awards found for '{query}'."

        lines = [f"## Federal Contract Awards\n\nFound **{total}** results for \"{query}\"\n"]
        for i, award in enumerate(items, 1):
            desc = award.get("description", "Untitled")
            recipient_name = award.get("recipient_name", "Unknown")
            amount = award.get("total_obligation")
            agency_name = award.get("awarding_agency_name") or award.get("awarding_agency_code", "")
            award_date = (award.get("award_date") or "")[:10]
            award_id = award.get("award_id", "")

            amount_str = self._fmt_money(amount)
            lines.append(f"{i}. **{desc[:120]}**")
            lines.append(f"   Recipient: {recipient_name} | Amount: {amount_str}")
            detail_parts = []
            if agency_name:
                detail_parts.append(f"Agency: {agency_name}")
            if award_date:
                detail_parts.append(f"Awarded: {award_date}")
            if detail_parts:
                lines.append(f"   {' | '.join(detail_parts)}")
            lines.append("")

        if total > page * 25:
            lines.append(f"_Showing page {page} of {(total + 24) // 25}. Use page={page + 1} for more._")

        await emitter.success_update(f"Found {total} contract awards")
        return "\n".join(lines)

    async def search_entities(
        self,
        query: str,
        state: Optional[str] = None,
        naics_code: Optional[str] = None,
        page: int = 1,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Search SAM.gov REGISTERED ENTITIES — companies and organizations that are registered to do
        business with the federal government. Use this when the user wants to find government contractors,
        look up a company's SAM registration, or find businesses by NAICS code or state.

        :param query: Search text — business name, DBA name, or CAGE code
        :param state: Two-letter state code filter (e.g., "VA", "DC")
        :param naics_code: Primary NAICS code filter (e.g., "541611")
        :param page: Page number (default: 1)
        :return: List of registered entities with business name, UEI, state, NAICS codes, and registration status.
        """
        emitter = EventEmitter(__event_emitter__)
        await emitter.progress_update(f"Searching SAM.gov registered entities: {query}")

        try:
            data = await self._get("/entities", {
                "search": query,
                "state": state,
                "primary_naics": naics_code,
                "page": page,
                "page_size": 25,
            })
        except Exception as e:
            await emitter.error_update(f"Search failed: {e}")
            return f"Error: Failed to search registered entities — {e}"

        items = data.get("results", [])
        total = data.get("total_results", len(items))

        if not items:
            await emitter.success_update("No entities found")
            return f"No SAM.gov registered entities found for '{query}'."

        lines = [f"## SAM.gov Registered Entities\n\nFound **{total}** results for \"{query}\"\n"]
        for i, ent in enumerate(items, 1):
            name = ent.get("legal_business_name", "Unknown")
            uei = ent.get("uei", "N/A")
            ent_state = ent.get("physical_address_state", "")
            naics = ent.get("primary_naics", "")
            active = ent.get("active_registration", False)
            status = "Active" if active else "Inactive"

            lines.append(f"{i}. **{name}** (UEI: {uei})")
            detail_parts = [f"Status: {status}"]
            if ent_state:
                detail_parts.append(f"State: {ent_state}")
            if naics:
                detail_parts.append(f"NAICS: {naics}")
            lines.append(f"   {' | '.join(detail_parts)}")
            lines.append(f"   _Use get_entity(\"{uei}\") for full profile + award history_")
            lines.append("")

        if total > page * 25:
            lines.append(f"_Showing page {page} of {(total + 24) // 25}. Use page={page + 1} for more._")

        await emitter.success_update(f"Found {total} registered entities")
        return "\n".join(lines)

    async def get_entity(
        self,
        uei: str,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Get full details for a specific SAM.gov registered entity by its UEI (Unique Entity Identifier),
        including their federal contract award history. Use this after search_entities to get a company's
        complete registration profile and their past government contracts.

        :param uei: The entity's Unique Entity Identifier (e.g., "JF1NFKM3HNE7")
        :return: Entity profile with business name, address, NAICS codes, registration dates, and recent contract awards.
        """
        emitter = EventEmitter(__event_emitter__)
        await emitter.progress_update(f"Fetching entity {uei}...")

        try:
            ent = await self._get(f"/entities/{uei}")
        except Exception as e:
            await emitter.error_update(f"Fetch failed: {e}")
            return f"Error: Failed to fetch entity {uei} — {e}"

        lines = [f"## Entity Profile\n"]
        lines.append(f"**{ent.get('legal_business_name', 'Unknown')}**\n")

        fields = [
            ("UEI", ent.get("uei")),
            ("DBA Name", ent.get("dba_name")),
            ("CAGE Code", ent.get("cage_code")),
            ("State", ent.get("physical_address_state")),
            ("City", ent.get("physical_address_city")),
            ("Primary NAICS", ent.get("primary_naics")),
            ("Entity Type", ent.get("entity_type")),
            ("Registration Status", "Active" if ent.get("active_registration") else "Inactive"),
            ("Registration Date", (ent.get("registration_date") or "")[:10]),
            ("Expiration Date", (ent.get("expiration_date") or "")[:10]),
        ]
        for label, val in fields:
            if val:
                lines.append(f"- **{label}:** {val}")

        # Fetch awards for this entity
        lines.append("\n### Recent Contract Awards\n")
        try:
            awards_data = await self._get(f"/entities/{uei}/awards", {"page": 1, "page_size": 10})
            awards = awards_data.get("results", [])
            if awards:
                for j, award in enumerate(awards[:10], 1):
                    desc = award.get("description", "N/A")[:100]
                    amount = award.get("total_obligation")
                    amount_str = self._fmt_money(amount)
                    date = (award.get("award_date") or "")[:10]
                    lines.append(f"{j}. {desc} — {amount_str} ({date})")
                total_awards = awards_data.get("total_results", len(awards))
                if total_awards > 10:
                    lines.append(f"\n_Showing 10 of {total_awards} awards._")
            else:
                lines.append("No contract awards on record.")
        except Exception:
            lines.append("_Could not retrieve award history._")

        await emitter.success_update("Entity details retrieved")
        return "\n".join(lines)
