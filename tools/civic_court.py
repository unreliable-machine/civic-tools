"""
title: Civic Court Intelligence
author: ChangeAgent AI
description: Search federal court opinions, dockets (cases), and judges from CourtListener — the full federal court landscape.
version: 0.1.0
requirements: httpx
"""

import json
import os
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

SYSTEM_PROMPT_INJECTION = """
### Civic Court Intelligence — Usage Guide
Use this tool for federal court data from CourtListener:
- `search_opinions` — Written court decisions and rulings (legal precedent)
- `search_dockets` — Active and closed court cases (litigation tracking)
- `search_judges` — Federal judge profiles and appointments
- `get_court_detail` — Full details for a specific opinion, docket, or judge
Note: Court data may be limited depending on sync status. Use civic_search.data_status() to check.
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

    # ── Tool methods ──────────────────────────────────────────────

    async def search_opinions(
        self,
        query: str,
        court: Optional[str] = None,
        after_date: Optional[str] = None,
        page: int = 1,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Search federal court OPINIONS — written decisions issued by federal courts. Use this when the
        user asks about court rulings, judicial decisions, legal precedents, case law, or "what has
        the court said about [topic]." Covers all federal courts including the Supreme Court.

        :param query: Search text (e.g., "first amendment", "voting rights", "redistricting")
        :param court: Court identifier filter (e.g., "scotus" for Supreme Court, "cacd" for Central District of California)
        :param after_date: Only return opinions filed on or after this date (YYYY-MM-DD)
        :param page: Page number (default: 1)
        :return: List of court opinions with case name, court, date filed, citation, and summary.
        """
        emitter = EventEmitter(__event_emitter__)
        await emitter.progress_update(f"Searching court opinions: {query}")

        try:
            data = await self._get("/court/opinions", {
                "q": query,
                "court": court,
                "after": after_date,
                "page": page,
                "page_size": 25,
            })
        except Exception as e:
            await emitter.error_update(f"Search failed: {e}")
            return f"Error: Failed to search court opinions — {e}"

        items = data.get("results", [])
        total = data.get("total_results", len(items))

        if not items:
            await emitter.success_update("No opinions found")
            msg = f"No court opinions found for '{query}'."
            if total == 0:
                msg += " Court opinion data may not be synced yet — use data_status() in civic_search to check."
            return msg

        lines = [f"## Federal Court Opinions\n\nFound **{total}** results for \"{query}\"\n"]
        for i, op in enumerate(items, 1):
            case_name = op.get("case_name", "Unknown Case")
            court_name = op.get("court", "")
            date_filed = (op.get("date_filed") or "")[:10]
            citation_count = op.get("citation_count", 0)
            snippet = op.get("snippet", "")
            cl_id = op.get("courtlistener_id", "")

            lines.append(f"{i}. **{case_name}**")
            detail_parts = []
            if court_name:
                detail_parts.append(f"Court: {court_name}")
            if date_filed:
                detail_parts.append(f"Filed: {date_filed}")
            if citation_count:
                detail_parts.append(f"Citations: {citation_count}")
            if detail_parts:
                lines.append(f"   {' | '.join(detail_parts)}")
            if snippet:
                lines.append(f"   {snippet[:250]}")
            if cl_id:
                lines.append(f"   _Use get_court_detail({cl_id}, \"opinion\") for full text_")
            lines.append("")

        if total > page * 25:
            lines.append(f"_Showing page {page} of {(total + 24) // 25}. Use page={page + 1} for more._")

        await emitter.success_update(f"Found {total} court opinions")
        return "\n".join(lines)

    async def search_dockets(
        self,
        query: str,
        court: Optional[str] = None,
        nature_of_suit: Optional[str] = None,
        page: int = 1,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Search federal court DOCKETS — active and closed court cases with their procedural history.
        Use this when the user asks about court cases, lawsuits, litigation, pending cases, or
        "cases about [topic]." Dockets track the lifecycle of a case from filing to resolution.

        :param query: Search text (e.g., "patent infringement", "employment discrimination")
        :param court: Court identifier filter (e.g., "cacd", "nysd")
        :param nature_of_suit: Nature of suit filter (e.g., "Civil Rights", "Labor")
        :param page: Page number (default: 1)
        :return: List of court dockets with case name, court, docket number, date filed, nature of suit, and status.
        """
        emitter = EventEmitter(__event_emitter__)
        await emitter.progress_update(f"Searching court dockets: {query}")

        try:
            data = await self._get("/court/dockets", {
                "q": query,
                "court": court,
                "nature_of_suit": nature_of_suit,
                "page": page,
                "page_size": 25,
            })
        except Exception as e:
            await emitter.error_update(f"Search failed: {e}")
            return f"Error: Failed to search court dockets — {e}"

        items = data.get("results", [])
        total = data.get("total_results", len(items))

        if not items:
            await emitter.success_update("No dockets found")
            msg = f"No court dockets found for '{query}'."
            if total == 0:
                msg += " Court docket data may not be synced yet — use data_status() in civic_search to check."
            return msg

        lines = [f"## Federal Court Dockets\n\nFound **{total}** results for \"{query}\"\n"]
        for i, dkt in enumerate(items, 1):
            case_name = dkt.get("case_name", "Unknown Case")
            court_name = dkt.get("court", "")
            docket_number = dkt.get("docket_number", "")
            date_filed = (dkt.get("date_filed") or "")[:10]
            nos = dkt.get("nature_of_suit", "")
            cl_id = dkt.get("courtlistener_id", "")

            lines.append(f"{i}. **{case_name}**")
            detail_parts = []
            if docket_number:
                detail_parts.append(f"Docket: {docket_number}")
            if court_name:
                detail_parts.append(f"Court: {court_name}")
            if date_filed:
                detail_parts.append(f"Filed: {date_filed}")
            if nos:
                detail_parts.append(f"Nature: {nos}")
            if detail_parts:
                lines.append(f"   {' | '.join(detail_parts)}")
            if cl_id:
                lines.append(f"   _Use get_court_detail({cl_id}, \"docket\") for full details_")
            lines.append("")

        if total > page * 25:
            lines.append(f"_Showing page {page} of {(total + 24) // 25}. Use page={page + 1} for more._")

        await emitter.success_update(f"Found {total} court dockets")
        return "\n".join(lines)

    async def search_judges(
        self,
        query: str,
        court: Optional[str] = None,
        page: int = 1,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Search federal judges — current and former judges across all federal courts. Use this when
        the user asks about specific judges, judicial appointments, or "who are the judges on [court]."

        :param query: Search text — judge name (e.g., "Sotomayor", "Kavanaugh")
        :param court: Court identifier filter (e.g., "scotus")
        :param page: Page number (default: 1)
        :return: List of judges with name, court, appointing president, political affiliation, and service dates.
        """
        emitter = EventEmitter(__event_emitter__)
        await emitter.progress_update(f"Searching federal judges: {query}")

        try:
            data = await self._get("/court/judges", {
                "q": query,
                "court": court,
                "page": page,
                "page_size": 25,
            })
        except Exception as e:
            await emitter.error_update(f"Search failed: {e}")
            return f"Error: Failed to search judges — {e}"

        items = data.get("results", [])
        total = data.get("total_results", len(items))

        if not items:
            await emitter.success_update("No judges found")
            msg = f"No federal judges found for '{query}'."
            if total == 0:
                msg += " Judge data may not be synced yet — use data_status() in civic_search to check."
            return msg

        lines = [f"## Federal Judges\n\nFound **{total}** results for \"{query}\"\n"]
        for i, judge in enumerate(items, 1):
            name = judge.get("name") or judge.get("name_full", "Unknown")
            court_name = judge.get("court", "")
            appointer = judge.get("appointing_president", "")
            political = judge.get("political_affiliation", "")
            cl_id = judge.get("courtlistener_id", "")

            lines.append(f"{i}. **{name}**")
            detail_parts = []
            if court_name:
                detail_parts.append(f"Court: {court_name}")
            if appointer:
                detail_parts.append(f"Appointed by: {appointer}")
            if political:
                detail_parts.append(f"Affiliation: {political}")
            if detail_parts:
                lines.append(f"   {' | '.join(detail_parts)}")
            if cl_id:
                lines.append(f"   _Use get_court_detail({cl_id}, \"judge\") for full profile_")
            lines.append("")

        if total > page * 25:
            lines.append(f"_Showing page {page} of {(total + 24) // 25}. Use page={page + 1} for more._")

        await emitter.success_update(f"Found {total} judges")
        return "\n".join(lines)

    async def get_court_detail(
        self,
        courtlistener_id: int,
        record_type: str,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Get full details for a specific court record — an opinion, docket, or judge — by its
        CourtListener ID. Use this after any search method to get the complete record.

        :param courtlistener_id: The CourtListener ID from search results (integer)
        :param record_type: Type of record — "opinion", "docket", or "judge"
        :return: Complete record details. For opinions: full text and citations. For dockets: party information and filing history. For judges: career history, education, and political affiliations.
        """
        emitter = EventEmitter(__event_emitter__)
        await emitter.progress_update(f"Fetching {record_type} {courtlistener_id}...")

        type_to_path = {
            "opinion": "opinions",
            "docket": "dockets",
            "judge": "judges",
        }
        path_segment = type_to_path.get(record_type)
        if not path_segment:
            await emitter.error_update(f"Invalid record type: {record_type}")
            return f"Error: Invalid record_type '{record_type}'. Must be 'opinion', 'docket', or 'judge'."

        try:
            record = await self._get(f"/court/{path_segment}/{courtlistener_id}")
        except Exception as e:
            await emitter.error_update(f"Fetch failed: {e}")
            return f"Error: Failed to fetch {record_type} {courtlistener_id} — {e}"

        if record_type == "opinion":
            return self._format_opinion(record)
        elif record_type == "docket":
            return self._format_docket(record)
        else:
            return self._format_judge(record)

    def _format_opinion(self, op: dict) -> str:
        lines = [f"## Court Opinion Detail\n"]
        lines.append(f"**{op.get('case_name', 'Unknown Case')}**\n")

        fields = [
            ("Court", op.get("court")),
            ("Date Filed", (op.get("date_filed") or "")[:10]),
            ("Citation Count", op.get("citation_count")),
            ("Judges", op.get("judges")),
        ]
        for label, val in fields:
            if val:
                lines.append(f"- **{label}:** {val}")

        snippet = op.get("snippet") or op.get("plain_text") or op.get("html", "")
        if snippet:
            # Clean HTML tags if present
            import re
            clean = re.sub(r"<[^>]+>", "", snippet)
            lines.append(f"\n### Text\n\n{clean[:4000]}")
            if len(clean) > 4000:
                lines.append("\n_[Text truncated]_")

        url = op.get("full_text_url") or op.get("absolute_url")
        if url:
            lines.append(f"\n[Full text on CourtListener]({url})")

        return "\n".join(lines)

    def _format_docket(self, dkt: dict) -> str:
        lines = [f"## Court Docket Detail\n"]
        lines.append(f"**{dkt.get('case_name', 'Unknown Case')}**\n")

        fields = [
            ("Docket Number", dkt.get("docket_number")),
            ("Court", dkt.get("court")),
            ("Date Filed", (dkt.get("date_filed") or "")[:10]),
            ("Date Terminated", (dkt.get("date_terminated") or "")[:10]),
            ("Nature of Suit", dkt.get("nature_of_suit")),
            ("Cause", dkt.get("cause")),
            ("Jury Demand", dkt.get("jury_demand")),
        ]
        for label, val in fields:
            if val:
                lines.append(f"- **{label}:** {val}")

        # Parties
        parties = dkt.get("parties") or []
        if parties:
            lines.append("\n### Parties\n")
            for p in parties[:10]:
                if isinstance(p, dict):
                    name = p.get("name", "Unknown")
                    role = p.get("type", "")
                    lines.append(f"- {name} ({role})")
                else:
                    lines.append(f"- {p}")

        url = dkt.get("absolute_url")
        if url:
            lines.append(f"\n[View on CourtListener]({url})")

        return "\n".join(lines)

    def _format_judge(self, judge: dict) -> str:
        lines = [f"## Judge Profile\n"]
        name = judge.get("name") or judge.get("name_full", "Unknown")
        lines.append(f"**{name}**\n")

        fields = [
            ("Court", judge.get("court")),
            ("Appointing President", judge.get("appointing_president")),
            ("Political Affiliation", judge.get("political_affiliation")),
            ("Date of Birth", (judge.get("date_dob") or "")[:10]),
            ("Race", judge.get("race")),
            ("Gender", judge.get("gender")),
        ]
        for label, val in fields:
            if val:
                lines.append(f"- **{label}:** {val}")

        # Education
        education = judge.get("education") or []
        if education:
            lines.append("\n### Education\n")
            for edu in education:
                if isinstance(edu, dict):
                    school = edu.get("school", "")
                    degree = edu.get("degree_level", "")
                    year = edu.get("degree_year", "")
                    lines.append(f"- {school} — {degree} ({year})" if year else f"- {school} — {degree}")
                else:
                    lines.append(f"- {edu}")

        # Positions
        positions = judge.get("positions") or []
        if positions:
            lines.append("\n### Positions\n")
            for pos in positions:
                if isinstance(pos, dict):
                    court = pos.get("court", "")
                    title = pos.get("position_type", "")
                    start = (pos.get("date_start") or "")[:10]
                    end = (pos.get("date_termination") or "present")[:10]
                    lines.append(f"- {title} at {court} ({start} – {end})")
                else:
                    lines.append(f"- {pos}")

        url = judge.get("absolute_url")
        if url:
            lines.append(f"\n[View on CourtListener]({url})")

        return "\n".join(lines)
