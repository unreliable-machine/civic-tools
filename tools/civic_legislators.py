"""
title: Civic Legislators & Legislation
author: ChangeAgent AI
description: Search state legislators, legislative bills, census demographics, and generate intelligence briefs — the full state-level political landscape.
version: 0.1.0
requirements: httpx
"""

import json
import os
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

SYSTEM_PROMPT_INJECTION = """
### Civic Legislators & Legislation — Usage Guide
Use this tool for state-level political intelligence:
- `search_legislators` / `get_legislator` — Find and profile state legislators
- `find_legislators_by_address` — Who represents a specific address (geocodes automatically)
- `search_bills` / `get_bill` — Search and drill into state legislative bills
- `brief_on_bill` — Multi-source intelligence brief (bill + sponsors + demographics + orgs)
- `get_demographics` — Census ACS data for states and congressional districts
This covers STATE-level legislators (not federal Congress). For nonprofits, use Civic Organizations. For court data, use Civic Court.
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
        TIMEOUT: int = Field(default=45, description="HTTP request timeout in seconds")

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

    # ── Tool methods ──────────────────────────────────────────────

    async def search_legislators(
        self,
        query: Optional[str] = None,
        state: Optional[str] = None,
        party: Optional[str] = None,
        chamber: Optional[str] = None,
        page: int = 1,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Search state legislators (state representatives and state senators) across all US states.
        Use this when the user asks about state legislators, state representatives, state senators,
        or wants to find elected officials by name, state, party, or chamber. This covers STATE-level
        officials only — not federal Congress members.

        :param query: Search text — legislator name (e.g., "Sherrod Brown")
        :param state: Two-letter state code (e.g., "OH", "GA")
        :param party: Party filter (e.g., "Democratic", "Republican")
        :param chamber: Chamber filter — "upper" (senate), "lower" (house/assembly), "legislature"
        :param page: Page number (default: 1)
        :return: List of state legislators with name, party, state, chamber, district, and contact info.
        """
        emitter = EventEmitter(__event_emitter__)
        search_desc = query or state or "all states"
        await emitter.progress_update(f"Searching state legislators: {search_desc}")

        try:
            data = await self._get("/legislators", {
                "search": query,
                "state": state,
                "party": party,
                "chamber": chamber,
                "page": page,
                "page_size": 25,
            })
        except Exception as e:
            await emitter.error_update(f"Search failed: {e}")
            return f"Error: Failed to search legislators — {e}"

        items = data.get("results", [])
        total = data.get("total_results", len(items))

        if not items:
            await emitter.success_update("No legislators found")
            return f"No state legislators found for '{search_desc}'."

        lines = [f"## State Legislators\n\nFound **{total}** results\n"]
        for i, leg in enumerate(items, 1):
            name = leg.get("name", "Unknown")
            leg_party = leg.get("party", "")
            leg_state = leg.get("jurisdiction_name") or leg.get("state", "")
            leg_chamber = leg.get("chamber", "")
            district = leg.get("district", "")
            openstates_id = leg.get("openstates_id", "")

            chamber_label = {"upper": "Senate", "lower": "House"}.get(leg_chamber, leg_chamber)
            lines.append(f"{i}. **{name}** ({leg_party})")
            detail_parts = []
            if leg_state:
                detail_parts.append(leg_state)
            if chamber_label:
                detail_parts.append(chamber_label)
            if district:
                detail_parts.append(f"District {district}")
            lines.append(f"   {' | '.join(detail_parts)}")
            if openstates_id:
                lines.append(f"   _Use get_legislator(\"{openstates_id}\") for full profile_")
            lines.append("")

        if total > page * 25:
            lines.append(f"_Showing page {page} of {(total + 24) // 25}. Use page={page + 1} for more._")

        await emitter.success_update(f"Found {total} legislators")
        return "\n".join(lines)

    async def get_legislator(
        self,
        openstates_id: str,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Get full details for a specific state legislator by their Open States ID. Use this after
        search_legislators to get a legislator's complete profile including committee memberships,
        sponsored bills, and contact information.

        :param openstates_id: The legislator's Open States ID (e.g., "ocd-person/12345678-abcd-...")
        :return: Complete legislator profile with name, party, district, committees, sponsored legislation, and contact details.
        """
        emitter = EventEmitter(__event_emitter__)
        await emitter.progress_update(f"Fetching legislator profile...")

        try:
            leg = await self._get(f"/legislators/{openstates_id}")
        except Exception as e:
            await emitter.error_update(f"Fetch failed: {e}")
            return f"Error: Failed to fetch legislator — {e}"

        lines = [f"## Legislator Profile\n"]
        name = leg.get("name", "Unknown")
        party = leg.get("party", "")
        lines.append(f"**{name}** ({party})\n")

        chamber_label = {"upper": "Senate", "lower": "House"}.get(leg.get("chamber", ""), leg.get("chamber", ""))
        fields = [
            ("State", leg.get("jurisdiction_name") or leg.get("state")),
            ("Chamber", chamber_label),
            ("District", leg.get("district")),
            ("Email", leg.get("email")),
            ("Image", leg.get("image")),
        ]
        for label, val in fields:
            if val:
                lines.append(f"- **{label}:** {val}")

        # Contact info
        offices = leg.get("offices") or []
        if offices:
            lines.append("\n### Offices")
            for office in offices:
                office_name = office.get("name", "Office")
                addr = office.get("address", "")
                phone = office.get("voice", "")
                lines.append(f"- **{office_name}:** {addr}")
                if phone:
                    lines.append(f"  Phone: {phone}")

        # Committee memberships
        committees = leg.get("committees") or leg.get("memberships") or []
        if committees:
            lines.append("\n### Committee Memberships")
            for c in committees[:10]:
                c_name = c.get("name") or c.get("organization_name", "Unknown")
                role = c.get("role", "member")
                lines.append(f"- {c_name} ({role})")

        # Sponsored bills
        bills = leg.get("sponsored_bills") or []
        if bills:
            lines.append("\n### Sponsored Bills")
            for b in bills[:10]:
                b_title = b.get("title", "Untitled")
                b_id = b.get("identifier", "")
                lines.append(f"- {b_id}: {b_title[:100]}")

        await emitter.success_update("Legislator profile retrieved")
        return "\n".join(lines)

    async def find_legislators_by_address(
        self,
        address: str,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Find which state legislators represent a specific street address. Use this when the user asks
        "who represents [address]?", "who is my state rep?", or "find legislators for [location]."
        Handles geocoding internally — just pass the street address.

        :param address: Full US street address (e.g., "123 Main St, Columbus, OH 43215")
        :return: List of state legislators (state senator and state representative) who represent the given address, with their name, party, district, and contact info.
        """
        emitter = EventEmitter(__event_emitter__)
        await emitter.progress_update(f"Finding legislators for: {address}")

        try:
            data = await self._post("/compose/representatives", {"address": address})
        except Exception as e:
            await emitter.error_update(f"Lookup failed: {e}")
            return f"Error: Failed to find legislators for that address — {e}"

        lines = [f"## Legislators for: {address}\n"]

        # Representatives section
        reps = data.get("representatives", {})
        rep_status = reps.get("status", "error")
        if rep_status == "ok":
            legislators = reps.get("data", {}).get("legislators") or reps.get("data", [])
            if isinstance(legislators, dict):
                legislators = legislators.get("results", [])

            if legislators:
                lines.append(f"Found **{len(legislators)}** representing legislators:\n")
                for i, leg in enumerate(legislators, 1):
                    name = leg.get("name", "Unknown")
                    party = leg.get("party", "")
                    chamber = {"upper": "State Senate", "lower": "State House"}.get(
                        leg.get("chamber", ""), leg.get("chamber", "")
                    )
                    district = leg.get("district", "")
                    email = leg.get("email", "")

                    lines.append(f"{i}. **{name}** ({party})")
                    detail_parts = []
                    if chamber:
                        detail_parts.append(chamber)
                    if district:
                        detail_parts.append(f"District {district}")
                    if email:
                        detail_parts.append(email)
                    if detail_parts:
                        lines.append(f"   {' | '.join(detail_parts)}")
                    lines.append("")
            else:
                lines.append("No legislators found for this address.\n")
        else:
            error_msg = reps.get("error", "Unknown error")
            lines.append(f"_Could not look up representatives: {error_msg}_\n")

        # Bills section (if topic was included and returned)
        bills = data.get("bills", {})
        if bills.get("status") == "ok" and bills.get("data"):
            bill_list = bills["data"] if isinstance(bills["data"], list) else bills["data"].get("results", [])
            if bill_list:
                lines.append("### Related Bills\n")
                for b in bill_list[:5]:
                    b_title = b.get("title", "Untitled")
                    b_id = b.get("identifier", "")
                    lines.append(f"- {b_id}: {b_title[:100]}")
                lines.append("")

        lines.append("_Note: This returns state legislators only. Federal representatives are not available through this endpoint._")

        await emitter.success_update("Legislator lookup complete")
        return "\n".join(lines)

    async def search_bills(
        self,
        query: str,
        state: Optional[str] = None,
        session: Optional[str] = None,
        subject: Optional[str] = None,
        page: int = 1,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Search state legislative bills across all US state legislatures. Use this when the user asks
        about state legislation, bills, proposed laws, or "bills about [topic] in [state]." Returns
        bill summaries from bulk legislative data with sponsors and latest actions.

        :param query: Search text (e.g., "voting rights", "renewable energy")
        :param state: State jurisdiction filter — state name (e.g., "Ohio") or OCD ID
        :param session: Legislative session filter (e.g., "2025")
        :param subject: Subject category filter
        :param page: Page number (default: 1)
        :return: List of bills with title, bill number, jurisdiction, session, latest action, and sponsor names.
        """
        emitter = EventEmitter(__event_emitter__)
        await emitter.progress_update(f"Searching state bills: {query}")

        try:
            # Try bulk legislation endpoint first, fall back to cached bills
            try:
                data = await self._get("/legislation/bills", {
                    "search": query,
                    "jurisdiction": state,
                    "session": session,
                    "subject": subject,
                    "page": page,
                    "page_size": 25,
                })
            except Exception:
                data = await self._get("/bills", {
                    "q": query,
                    "jurisdiction": state,
                    "session_name": session,
                    "search": query if not state else None,
                    "page": page,
                    "page_size": 25,
                })
        except Exception as e:
            await emitter.error_update(f"Search failed: {e}")
            return f"Error: Failed to search bills — {e}"

        items = data.get("results", [])
        total = data.get("total_results", len(items))

        if not items:
            await emitter.success_update("No bills found")
            return f"No legislative bills found for '{query}'."

        lines = [f"## State Legislative Bills\n\nFound **{total}** results for \"{query}\"\n"]
        for i, bill in enumerate(items, 1):
            title = bill.get("title", "Untitled")
            identifier = bill.get("identifier", "")
            jurisdiction = bill.get("jurisdiction_name") or bill.get("jurisdiction", "")
            bill_session = bill.get("session_name") or bill.get("session", "")
            ocd_id = bill.get("ocd_id", "")

            # Latest action
            actions = bill.get("actions") or []
            latest_action = ""
            if actions:
                last = actions[-1] if isinstance(actions, list) else None
                if last:
                    latest_action = last.get("description", "")[:80]
                    action_date = (last.get("date") or "")[:10]
                    if action_date:
                        latest_action = f"{latest_action} ({action_date})"

            # Sponsors
            sponsors = bill.get("sponsors") or []
            sponsor_names = [s.get("name", "") for s in sponsors[:3] if s.get("name")]

            lines.append(f"{i}. **{identifier}: {title[:120]}**")
            detail_parts = []
            if jurisdiction:
                detail_parts.append(jurisdiction)
            if bill_session:
                detail_parts.append(f"Session: {bill_session}")
            if detail_parts:
                lines.append(f"   {' | '.join(detail_parts)}")
            if sponsor_names:
                lines.append(f"   Sponsors: {', '.join(sponsor_names)}")
            if latest_action:
                lines.append(f"   Latest: {latest_action}")
            if ocd_id:
                lines.append(f"   _Use get_bill(\"{ocd_id}\") for full details_")
            lines.append("")

        if total > page * 25:
            lines.append(f"_Showing page {page} of {(total + 24) // 25}. Use page={page + 1} for more._")

        await emitter.success_update(f"Found {total} bills")
        return "\n".join(lines)

    async def get_bill(
        self,
        bill_ocd_id: str,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Get full details for a specific state legislative bill including all actions (history),
        sponsors, document versions, and vote records. Use this after search_bills to see a bill's
        complete legislative history.

        :param bill_ocd_id: The bill's OCD ID from search results (e.g., "ocd-bill/...")
        :return: Complete bill details with title, full text link, all actions with dates, sponsors, committee referrals, and vote tallies.
        """
        emitter = EventEmitter(__event_emitter__)
        await emitter.progress_update("Fetching bill details...")

        try:
            try:
                bill = await self._get(f"/legislation/bills/{bill_ocd_id}")
            except Exception:
                bill = await self._get(f"/bills/{bill_ocd_id}")
        except Exception as e:
            await emitter.error_update(f"Fetch failed: {e}")
            return f"Error: Failed to fetch bill — {e}"

        lines = [f"## Bill Detail\n"]
        identifier = bill.get("identifier", "")
        title = bill.get("title", "Untitled")
        lines.append(f"**{identifier}: {title}**\n")

        fields = [
            ("Jurisdiction", bill.get("jurisdiction_name") or bill.get("jurisdiction")),
            ("Session", bill.get("session_name") or bill.get("session")),
            ("Classification", ", ".join(bill.get("classification", [])) if bill.get("classification") else None),
            ("Subjects", ", ".join(bill.get("subject", [])[:5]) if bill.get("subject") else None),
        ]
        for label, val in fields:
            if val:
                lines.append(f"- **{label}:** {val}")

        # Abstracts
        abstracts = bill.get("abstracts") or []
        if abstracts:
            lines.append(f"\n### Summary\n\n{abstracts[0].get('abstract', '')[:2000]}")

        # Sponsors
        sponsors = bill.get("sponsors") or []
        if sponsors:
            lines.append("\n### Sponsors\n")
            for s in sponsors:
                name = s.get("name", "Unknown")
                classification = s.get("classification", "")
                primary = " (primary)" if s.get("primary") else ""
                lines.append(f"- {name} — {classification}{primary}")

        # Actions (legislative history)
        actions = bill.get("actions") or []
        if actions:
            lines.append("\n### Legislative History\n")
            for a in actions[-15:]:  # Show last 15 actions
                date = (a.get("date") or "")[:10]
                desc = a.get("description", "")
                org = a.get("organization_name", "")
                org_str = f" [{org}]" if org else ""
                lines.append(f"- {date}: {desc}{org_str}")

        # Vote events
        votes = bill.get("vote_events") or bill.get("votes") or []
        if votes:
            lines.append("\n### Votes\n")
            for v in votes[:5]:
                motion = v.get("motion_text", "Vote")
                result = v.get("result", "")
                date = (v.get("start_date") or v.get("date", ""))[:10]
                counts = v.get("counts") or []
                count_str = ", ".join(f"{c.get('option', '')}: {c.get('value', 0)}" for c in counts)
                lines.append(f"- {date}: {motion} — **{result}** ({count_str})")

        # Documents/versions
        versions = bill.get("versions") or []
        if versions:
            lines.append("\n### Document Versions\n")
            for v in versions[:5]:
                note = v.get("note", "Version")
                links = v.get("links") or []
                url = links[0].get("url", "") if links else ""
                lines.append(f"- {note}" + (f" — [Link]({url})" if url else ""))

        await emitter.success_update("Bill details retrieved")
        return "\n".join(lines)

    async def brief_on_bill(
        self,
        jurisdiction: str,
        session_name: str,
        bill_id: str,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Generate a comprehensive intelligence brief about a specific state bill. This goes beyond
        get_bill by cross-referencing the bill with sponsor profiles, state demographics, and related
        organizations. Use this when the user wants a deep analysis of a bill — who introduced it, what
        district they represent, and what the political landscape looks like.

        :param jurisdiction: State name (e.g., "Ohio")
        :param session_name: Legislative session (e.g., "2025")
        :param bill_id: Bill identifier (e.g., "HB 247")
        :return: Multi-source intelligence brief with bill details, sponsor profiles with their districts, district demographics, and related nonprofit organizations.
        """
        emitter = EventEmitter(__event_emitter__)
        await emitter.progress_update(f"Generating intelligence brief for {jurisdiction} {bill_id}...")

        try:
            data = await self._post("/compose/brief", {
                "jurisdiction": jurisdiction,
                "session_name": session_name,
                "bill_id": bill_id,
            })
        except Exception as e:
            await emitter.error_update(f"Brief generation failed: {e}")
            return f"Error: Failed to generate bill brief — {e}"

        lines = [f"## Intelligence Brief: {jurisdiction} {bill_id} ({session_name})\n"]

        # Bill section
        bill_section = data.get("bill", {})
        if bill_section.get("status") == "ok":
            bill_data = bill_section.get("data", {})
            title = bill_data.get("title", "Untitled")
            lines.append(f"### Bill Overview\n\n**{bill_id}: {title}**\n")

            abstracts = bill_data.get("abstracts") or []
            if abstracts:
                lines.append(f"{abstracts[0].get('abstract', '')[:1500]}\n")

            actions = bill_data.get("actions") or []
            if actions:
                last = actions[-1]
                lines.append(f"**Latest action:** {last.get('description', '')} ({(last.get('date') or '')[:10]})\n")
        else:
            lines.append(f"_Bill data unavailable: {bill_section.get('error', 'unknown error')}_\n")

        # Sponsors section
        sponsors_section = data.get("sponsors", {})
        if sponsors_section.get("status") == "ok":
            sponsors_data = sponsors_section.get("data", [])
            if sponsors_data:
                lines.append("### Sponsor Profiles\n")
                for s in sponsors_data:
                    name = s.get("name", "Unknown")
                    party = s.get("party", "")
                    chamber = {"upper": "Senate", "lower": "House"}.get(s.get("chamber", ""), s.get("chamber", ""))
                    district = s.get("district", "")
                    lines.append(f"- **{name}** ({party}) — {chamber} District {district}")
                lines.append("")

        # Demographics section
        demographics_section = data.get("demographics", {})
        if demographics_section.get("status") == "ok":
            demo_data = demographics_section.get("data", {})
            if demo_data:
                lines.append("### District Demographics\n")
                pop = demo_data.get("total_population")
                income = demo_data.get("median_household_income")
                poverty = demo_data.get("poverty_rate")
                if pop:
                    lines.append(f"- Population: {pop:,}")
                if income:
                    lines.append(f"- Median Income: ${income:,.0f}")
                if poverty:
                    lines.append(f"- Poverty Rate: {poverty:.1f}%")
                lines.append("")

        # Related orgs section
        orgs_section = data.get("organizations", {}) or data.get("nonprofits", {})
        if orgs_section.get("status") == "ok":
            org_data = orgs_section.get("data", [])
            if isinstance(org_data, dict):
                org_data = org_data.get("results", [])
            if org_data:
                lines.append("### Related Organizations\n")
                for org in org_data[:5]:
                    org_name = org.get("name", "Unknown")
                    org_state = org.get("state", "")
                    lines.append(f"- {org_name} ({org_state})")
                lines.append("")

        await emitter.success_update("Intelligence brief generated")
        return "\n".join(lines)

    async def get_demographics(
        self,
        state: str,
        district: Optional[str] = None,
        page: int = 1,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Get Census Bureau demographic data for a US state or congressional district. Includes population,
        income, poverty rate, education levels, race/ethnicity, housing, and employment data from the
        American Community Survey (ACS) 5-year estimates. Use this when the user asks about demographics,
        population data, poverty rates, or socioeconomic characteristics of a state or district.

        :param state: Two-letter state code (e.g., "OH", "GA")
        :param district: Congressional district number (e.g., "03"). If omitted, returns state-level data.
        :param page: Page number for listing multiple profiles (default: 1)
        :return: Demographic profile with population, median income, poverty rate, education attainment, race/ethnicity breakdown, and housing statistics.
        """
        emitter = EventEmitter(__event_emitter__)
        desc = f"{state}" + (f" District {district}" if district else "")
        await emitter.progress_update(f"Fetching demographics for {desc}...")

        try:
            if district:
                # Specific district
                geo_id = f"CD-{state.upper()}-{district.zfill(2)}"
                data = await self._get(f"/census/profiles/{geo_id}")
            else:
                # State-level: try specific geo_id first
                geo_id = f"ST-{state.upper()}"
                try:
                    data = await self._get(f"/census/profiles/{geo_id}")
                except Exception:
                    # Fallback to search
                    data = await self._get("/census/profiles", {
                        "state": state,
                        "geo_type": "state" if not district else "congressional_district",
                        "page": page,
                        "page_size": 25,
                    })
        except Exception as e:
            await emitter.error_update(f"Fetch failed: {e}")
            return f"Error: Failed to fetch demographics — {e}"

        # Handle list response vs single profile
        if "items" in data:
            items = data.get("results", [])
            if not items:
                await emitter.success_update("No demographics found")
                return f"No demographic data found for {desc}."
            # Format as a list
            lines = [f"## Census Demographics\n\nFound **{data.get('total_results', len(items))}** profiles\n"]
            for i, profile in enumerate(items, 1):
                name = profile.get("state_name") or profile.get("geo_name") or "Unknown"
                dn = profile.get("district_number")
                if dn:
                    name = f"{name} CD-{dn}"
                pop = profile.get("total_population")
                income = profile.get("median_household_income")
                poverty = profile.get("poverty_rate")
                try:
                    pop_str = f"{int(float(pop)):,}" if pop else "N/A"
                except (ValueError, TypeError):
                    pop_str = "N/A"
                try:
                    income_str = f"${float(income):,.0f}" if income else "N/A"
                except (ValueError, TypeError):
                    income_str = "N/A"
                try:
                    poverty_str = f"{float(poverty):.1f}%" if poverty is not None else "N/A"
                except (ValueError, TypeError):
                    poverty_str = "N/A"
                lines.append(f"{i}. **{name}** — Pop: {pop_str} | Income: {income_str} | Poverty: {poverty_str}")
            await emitter.success_update(f"Demographics retrieved for {len(items)} areas")
            return "\n".join(lines)

        # Single profile response
        profile = data
        name = profile.get("state_name") or profile.get("geo_name") or desc
        district_num = profile.get("district_number")
        if district_num:
            name = f"{name} — Congressional District {district_num}"
        lines = [f"## Demographics: {name}\n"]

        def _pct(val):
            if val is None:
                return None
            try:
                return f"{float(val):.1f}%"
            except (ValueError, TypeError):
                return str(val)

        def _money(val):
            if val is None:
                return None
            try:
                return f"${float(val):,.0f}"
            except (ValueError, TypeError):
                return str(val)

        def _num(val):
            if val is None:
                return None
            try:
                return f"{int(float(val)):,}"
            except (ValueError, TypeError):
                return str(val)

        # Core stats
        sections = [
            ("Population & Income", [
                ("Total Population", _num(profile.get("total_population"))),
                ("Median Household Income", _money(profile.get("median_household_income"))),
                ("Per Capita Income", _money(profile.get("per_capita_income"))),
                ("Median Age", profile.get("median_age")),
                ("Poverty Rate", _pct(profile.get("poverty_rate"))),
                ("Unemployment Rate", _pct(profile.get("unemployment_rate"))),
                ("Uninsured Rate", _pct(profile.get("uninsured_rate"))),
                ("SNAP Recipients", _pct(profile.get("snap_rate"))),
            ]),
            ("Education", [
                ("Bachelor's Degree+", _pct(profile.get("bachelors_rate"))),
                ("Graduate Degree+", _pct(profile.get("graduate_rate"))),
            ]),
            ("Race & Ethnicity", [
                ("White", _pct(profile.get("pct_white"))),
                ("Black/African American", _pct(profile.get("pct_black"))),
                ("Hispanic/Latino", _pct(profile.get("pct_hispanic"))),
                ("Asian", _pct(profile.get("pct_asian"))),
                ("Foreign Born", _pct(profile.get("foreign_born_rate"))),
                ("Non-English at Home", _pct(profile.get("non_english_rate"))),
            ]),
            ("Housing", [
                ("Total Households", _num(profile.get("total_households"))),
                ("Renter Rate", _pct(profile.get("renter_rate"))),
                ("Median Home Value", _money(profile.get("median_home_value"))),
                ("Veteran Rate", _pct(profile.get("veteran_rate"))),
            ]),
        ]

        for section_name, fields in sections:
            visible = [(l, v) for l, v in fields if v]
            if visible:
                lines.append(f"\n### {section_name}\n")
                for label, val in visible:
                    lines.append(f"- **{label}:** {val}")

        lines.append("\n_Source: U.S. Census Bureau, American Community Survey 5-Year Estimates_")

        await emitter.success_update("Demographics retrieved")
        return "\n".join(lines)
