"""
title: Civic Community Intelligence
author: ChangeAgent AI
description: Census demographics, labor/wage data, health indicators, and housing affordability — community intelligence across Census ACS, EPI, CDC PLACES, and HUD data.
version: 0.1.0
requirements: httpx
"""

import asyncio
import os
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

SYSTEM_PROMPT_INJECTION = """
### Civic Community Intelligence Tool

**This tool provides Census demographics, labor/wage data, health indicators, and housing affordability data.**

For targeted queries:
- **Demographics for a place?** → `community_search_demographics` to find geographies, then `community_get_demographic_profile` for full detail
- **Wages, unions, inequality?** → `community_search_labor` for EPI indicators, `community_get_labor_summary` for state snapshot
- **Health conditions in a county?** → `community_search_health` to find measures, `community_get_health_profile` for a county's full health profile
- **Rent costs, affordability?** → `community_search_housing` for HUD Fair Market Rents and income limits
- **Broad community overview** → Combine demographics + health + housing for a geography

**Use the other civic tools for:** campaign finance/lobbying (civic_research), legislation/bills (civic_legislators), grants/foundations (civic_funding), federal contracts (civic_procurement), court records (civic_court), nonprofits by sector (civic_organizations).

**Data coverage:** Census ACS 2024 (states, counties, congressional districts), EPI labor indicators (wages, union rates by state), CDC PLACES 2023 (23 health measures for 3,000+ counties), HUD FMR/Income Limits 2026 (Fair Market Rents and income limits by area).

ANTI-HALLUCINATION (CRITICAL):
- ONLY present data that was returned by a tool call. NEVER invent, estimate, or extrapolate values.
- If a tool returns no results, say "no results found" — do NOT fill in with guesses.
- NEVER fabricate URLs. Only include URLs returned by the tool.
- Use EXACT values from tool output. Do not round, paraphrase, or approximate numerical data.
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
        LABOR_API_URL: str = Field(
            default_factory=lambda: os.getenv(
                "CIVIC_LABOR_URL",
                "https://civic-labor-production.up.railway.app",
            ),
            description="Civic Labor API base URL (EPI wage/union data)",
        )
        HEALTH_API_URL: str = Field(
            default_factory=lambda: os.getenv(
                "CIVIC_HEALTH_URL",
                "https://civic-health-production.up.railway.app",
            ),
            description="Civic Health API base URL (CDC PLACES health indicators)",
        )
        HOUSING_API_URL: str = Field(
            default_factory=lambda: os.getenv(
                "CIVIC_HOUSING_URL",
                "https://civic-housing-production.up.railway.app",
            ),
            description="Civic Housing API base URL (HUD FMR/Income Limits)",
        )
        CENSUS_API_URL: str = Field(
            default_factory=lambda: os.getenv(
                "CIVIC_CENSUS_URL",
                "https://civic-census-production.up.railway.app",
            ),
            description="Civic Census API base URL (ACS demographic profiles)",
        )
        API_KEY: str = Field(
            default_factory=lambda: os.getenv("GOVCON_API_KEY", ""),
            description="Bearer token for API authentication (shared across services)",
        )
        TIMEOUT: int = Field(default=15, description="HTTP request timeout in seconds")

    def __init__(self):
        self.valves = self.Valves()

    # -- HTTP helpers --------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        h = {"Accept": "application/json"}
        if self.valves.API_KEY:
            h["Authorization"] = f"Bearer {self.valves.API_KEY}"
        return h

    @staticmethod
    def _fmt_money(val) -> str:
        if val is None:
            return "N/A"
        try:
            return f"${float(val):,.0f}"
        except (ValueError, TypeError):
            return str(val)

    @staticmethod
    def _fmt_pct(val) -> str:
        if val is None:
            return "N/A"
        try:
            return f"{float(val):.1f}%"
        except (ValueError, TypeError):
            return str(val)

    @staticmethod
    def _fmt_num(val) -> str:
        if val is None:
            return "N/A"
        try:
            return f"{int(val):,}"
        except (ValueError, TypeError):
            return str(val)

    async def _get(
        self,
        base_url: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
    ) -> tuple:
        """Anti-fragile GET: 2 retries on 5xx/connection errors, graceful degradation.

        Returns (data_dict, None) on success or (None, error_string) on failure.
        Never raises.
        """
        import httpx

        url = f"{base_url.rstrip('/')}{path}"
        cleaned = {k: v for k, v in (params or {}).items() if v is not None}
        t = timeout or self.valves.TIMEOUT
        backoffs = [1, 3]

        last_error = ""
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=t) as client:
                    resp = await client.get(url, params=cleaned, headers=self._headers())
                    if resp.status_code >= 500 and attempt < 1:
                        last_error = f"Server error ({resp.status_code})"
                        await asyncio.sleep(backoffs[attempt])
                        continue
                    if resp.status_code == 401:
                        return None, "Authentication failed -- check API key configuration"
                    if resp.status_code == 404:
                        return None, "Resource not found"
                    if resp.status_code >= 400:
                        return None, f"Request error ({resp.status_code})"
                    return resp.json(), None
            except httpx.TimeoutException:
                last_error = f"Request timed out after {t}s"
                if attempt < 1:
                    await asyncio.sleep(backoffs[attempt])
                    continue
            except httpx.ConnectError:
                last_error = "Service unavailable -- connection failed"
                if attempt < 1:
                    await asyncio.sleep(backoffs[attempt])
                    continue
            except Exception as e:
                return None, f"Unexpected error: {str(e)[:200]}"

        return None, last_error

    # -- Labor (EPI) ---------------------------------------------------------

    async def community_search_labor(
        self,
        indicator: Optional[str] = None,
        state: Optional[str] = None,
        year: Optional[int] = None,
        dimension: Optional[str] = None,
        geo_level: Optional[str] = None,
        page: int = 1,
        page_size: int = 25,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Search EPI (Economic Policy Institute) labor and wage indicators. Covers hourly
        wage percentiles, union membership rates, and wage inequality across states
        and nationally. Use this to research wages, labor conditions, and economic
        inequality in specific states or nationwide.

        :param indicator: Filter by indicator ID (e.g. "hourly_wage_percentiles", "union_membership")
        :param state: Two-letter state abbreviation (e.g. "OH", "CA")
        :param year: Filter by year (e.g. 2025)
        :param dimension: Filter by dimension value (e.g. "wage_p50" for median, "wage_p10", "wage_p90")
        :param geo_level: Filter by geo level: "national" or "state"
        :param page: Page number (default: 1)
        :param page_size: Results per page (default: 25, max: 100)
        :return: EPI labor indicators with values, dimensions, and geographic detail.
        """
        emitter = EventEmitter(__event_emitter__)
        desc_parts = [p for p in [indicator, state, str(year) if year else None] if p]
        await emitter.progress_update(f"Searching EPI labor indicators: {', '.join(desc_parts) or 'all'}")

        data, error = await self._get(self.valves.LABOR_API_URL, "/api/epi/indicators", {
            "indicator": indicator, "state": state, "year": year,
            "dimension": dimension, "geo_level": geo_level,
            "page": page, "page_size": page_size,
        })

        if error:
            await emitter.error_update(error)
            return f"Labor data unavailable: {error}. Try again in a moment."

        items = data.get("results", [])
        total = data.get("total_results", len(items))

        if not items:
            await emitter.success_update("Search complete")
            return "No EPI labor indicators found matching your criteria. Try a different state, indicator, or year."

        lines = [f"## EPI Labor Indicators\n\nFound **{total}** results\n"]

        for i, item in enumerate(items[:15], 1):
            ind_id = item.get("indicator_id", "")
            measure = item.get("measure_id", "")
            dim = item.get("dimension_value", "")
            geo = item.get("geo_level", "")
            st = item.get("state_abbr", "")
            yr = item.get("year", "")
            val = item.get("value")

            label = dim or measure or ind_id
            location = st if st else geo

            val_str = f"{float(val):.4f}" if val is not None else "N/A"
            lines.append(f"{i}. **{label}** ({location}, {yr})")
            lines.append(f"   Indicator: {ind_id} | Measure: {measure} | Value: {val_str}")
            lines.append("")

        if total > page * page_size:
            lines.append(f"_Showing page {page} of {(total + page_size - 1) // page_size}. Use page={page + 1} for more._")

        lines.append(f"\n_Tip: Use `community_get_labor_summary(state)` for a quick state-level wage and union snapshot._")
        lines.append("\n---\n**Source:** [Economic Policy Institute](https://www.epi.org/data/)")

        await emitter.success_update(f"Found {total} labor indicators")
        return "\n".join(lines)

    async def community_get_labor_summary(
        self,
        state: str,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Get a state-level wage and union membership summary from EPI data. Returns
        median hourly wage, 10th/90th percentile wages, wage inequality ratio, and
        union membership rate for a state. Quick snapshot for comparing states.

        :param state: Two-letter state abbreviation (e.g. "OH", "CA", "NY")
        :return: State wage summary with median, percentiles, inequality ratio, and union rate.
        """
        emitter = EventEmitter(__event_emitter__)
        await emitter.progress_update(f"Fetching labor summary for {state.upper()}...")

        data, error = await self._get(
            self.valves.LABOR_API_URL, f"/api/epi/states/{state.upper()}"
        )

        if error:
            await emitter.error_update(error)
            return f"Labor summary unavailable for {state.upper()}: {error}."

        st = data.get("state_abbr", state.upper())
        lines = [f"## Labor Summary: {st}\n"]

        median = data.get("median_hourly_wage")
        p10 = data.get("wage_p10")
        p90 = data.get("wage_p90")
        ratio = data.get("wage_ratio_90_10")
        union = data.get("union_membership_rate")
        yr = data.get("latest_year", "")

        if median is not None:
            lines.append(f"- **Median hourly wage:** ${float(median):.2f}")
        if p10 is not None:
            lines.append(f"- **10th percentile wage:** ${float(p10):.2f}")
        if p90 is not None:
            lines.append(f"- **90th percentile wage:** ${float(p90):.2f}")
        if ratio is not None:
            lines.append(f"- **90/10 wage ratio:** {float(ratio):.1f}x")
        if union is not None:
            lines.append(f"- **Union membership rate:** {float(union) * 100:.1f}%")
        if yr:
            lines.append(f"- **Data year:** {yr}")

        lines.append("\n---\n**Source:** [Economic Policy Institute](https://www.epi.org/data/)")

        await emitter.success_update(f"Labor summary for {st}")
        return "\n".join(lines)

    # -- Health (CDC PLACES) -------------------------------------------------

    async def community_search_health(
        self,
        measure: Optional[str] = None,
        category: Optional[str] = None,
        state: Optional[str] = None,
        year: Optional[int] = None,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        page: int = 1,
        page_size: int = 25,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Search CDC PLACES health indicators across US counties. Covers 23 measures
        including diabetes, obesity, depression, asthma, food insecurity, housing
        insecurity, and more. Use this to find counties with specific health conditions
        or compare health outcomes across areas.

        Common measure IDs: DIABETES, OBESITY, DEPRESSION, BPHIGH (high blood pressure),
        CASTHMA (current asthma), CHD (coronary heart disease), COPD, CANCER,
        FOODINSECU (food insecurity), HOUSINSECU (housing insecurity), CSMOKING,
        BINGE (binge drinking), LPA (no leisure physical activity), ACCESS2 (no health insurance).

        :param measure: Filter by measure ID (e.g. "DIABETES", "FOODINSECU", "DEPRESSION")
        :param category: Filter by category (e.g. "Health Outcomes", "Health-Related Social Needs", "Disability")
        :param state: Two-letter state abbreviation (e.g. "OH", "CA")
        :param year: Filter by year (e.g. 2023)
        :param min_value: Minimum data value percentage (e.g. 20 for >= 20%)
        :param max_value: Maximum data value percentage (e.g. 10 for <= 10%)
        :param page: Page number (default: 1)
        :param page_size: Results per page (default: 25, max: 100)
        :return: Health indicators by county with measure name, value, confidence interval, and population.
        """
        emitter = EventEmitter(__event_emitter__)
        desc_parts = [p for p in [measure, category, state] if p]
        await emitter.progress_update(f"Searching CDC PLACES health data: {', '.join(desc_parts) or 'all'}")

        data, error = await self._get(self.valves.HEALTH_API_URL, "/api/health/indicators", {
            "measure": measure, "category": category, "state": state,
            "year": year, "min_value": min_value, "max_value": max_value,
            "page": page, "page_size": page_size,
        })

        if error:
            await emitter.error_update(error)
            return f"Health data unavailable: {error}. Try again in a moment."

        items = data.get("results", [])
        total = data.get("total_results", len(items))

        if not items:
            await emitter.success_update("Search complete")
            return "No CDC PLACES health indicators found matching your criteria. Try a different measure, state, or value range."

        lines = [f"## CDC PLACES Health Indicators\n\nFound **{total}** results\n"]

        # Table format for health data
        lines.append("| # | County | State | Measure | Value | CI (Low-High) | Pop |")
        lines.append("|---|--------|-------|---------|-------|---------------|-----|")

        for i, item in enumerate(items[:15], 1):
            loc_name = item.get("location_name", "Unknown")
            st = item.get("state_abbr", "")
            m_name = item.get("measure_name", item.get("measure_id", ""))
            val = item.get("data_value")
            low_ci = item.get("low_confidence")
            high_ci = item.get("high_confidence")
            pop = item.get("total_population")
            loc_id = item.get("location_id", "")

            val_str = self._fmt_pct(val)
            ci_str = f"{self._fmt_pct(low_ci)}-{self._fmt_pct(high_ci)}" if low_ci is not None else "N/A"
            pop_str = self._fmt_num(pop)

            lines.append(f"| {i} | {loc_name} | {st} | {m_name} | {val_str} | {ci_str} | {pop_str} |")

        lines.append("")

        if total > page * page_size:
            lines.append(f"_Showing page {page} of {(total + page_size - 1) // page_size}. Use page={page + 1} for more._")

        lines.append(f"\n_Tip: Use `community_get_health_profile(location_id)` for all health measures for a specific county (e.g. FIPS code like \"39049\" for Franklin County, OH)._")
        lines.append("\n---\n**Source:** [CDC PLACES](https://www.cdc.gov/places/)")

        await emitter.success_update(f"Found {total} health indicators")
        return "\n".join(lines)

    async def community_get_health_profile(
        self,
        location_id: str,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Get all CDC PLACES health measures for a specific county. Returns a complete
        health profile with 23 measures covering health outcomes, social needs,
        prevention, and disability. Location ID is the county FIPS code.

        :param location_id: County FIPS code (e.g. "39049" for Franklin County OH, "06037" for Los Angeles County CA)
        :return: Full health profile with all available measures, organized by category.
        """
        emitter = EventEmitter(__event_emitter__)
        await emitter.progress_update(f"Fetching health profile for location {location_id}...")

        # Fetch profile and measures list in parallel
        profile_task = self._get(
            self.valves.HEALTH_API_URL, f"/api/health/locations/{location_id}"
        )
        measures_task = self._get(
            self.valves.HEALTH_API_URL, "/api/health/measures"
        )
        (profile_data, profile_err), (measures_data, measures_err) = await asyncio.gather(
            profile_task, measures_task
        )

        if profile_err:
            await emitter.error_update(profile_err)
            return f"Health profile unavailable for location {location_id}: {profile_err}. Verify the FIPS code with `community_search_health(state='XX')`."

        loc_name = profile_data.get("location_name", "Unknown")
        st = profile_data.get("state_abbr", "")
        yr = profile_data.get("year", "")
        measures = profile_data.get("measures", {})

        if not measures:
            await emitter.success_update("Profile retrieved")
            return f"No health measures found for location {location_id} ({loc_name}, {st})."

        # Build a lookup for measure names and categories
        measure_info = {}
        if measures_data and not measures_err:
            if isinstance(measures_data, list):
                for m in measures_data:
                    measure_info[m.get("measure_id", "")] = {
                        "name": m.get("measure_name", ""),
                        "category": m.get("category", ""),
                    }

        lines = [f"## Health Profile: {loc_name}, {st}\n"]
        if yr:
            lines.append(f"**Data year:** {yr}\n")

        # Group measures by category
        categories: Dict[str, list] = {}
        for measure_id, value in measures.items():
            info = measure_info.get(measure_id, {})
            cat = info.get("category", "Other")
            name = info.get("name", measure_id)
            categories.setdefault(cat, []).append((name, measure_id, value))

        for cat in sorted(categories.keys()):
            lines.append(f"\n### {cat}\n")
            lines.append("| Measure | ID | Value |")
            lines.append("|---------|-----|-------|")
            for name, mid, val in sorted(categories[cat]):
                lines.append(f"| {name} | {mid} | {self._fmt_pct(val)} |")

        lines.append(f"\n_Tip: Use `community_search_health(measure='MEASURE_ID', state='{st}')` to compare this county against others in the state._")
        lines.append("\n---\n**Source:** [CDC PLACES](https://www.cdc.gov/places/)")

        await emitter.success_update(f"Health profile for {loc_name}, {st}")
        return "\n".join(lines)

    # -- Housing (HUD) -------------------------------------------------------

    async def community_search_housing(
        self,
        state: Optional[str] = None,
        indicator_type: Optional[str] = None,
        area_type: Optional[str] = None,
        min_2br: Optional[int] = None,
        max_2br: Optional[int] = None,
        page: int = 1,
        page_size: int = 25,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Search HUD housing affordability data -- Fair Market Rents (FMR) and Income
        Limits by area. FMRs determine maximum rents for Housing Choice Vouchers
        (Section 8). Income Limits determine eligibility for HUD programs.
        Use this to research rent costs, housing affordability, and HUD program
        thresholds by state, metro area, or county.

        :param state: Two-letter state abbreviation (e.g. "OH", "CA")
        :param indicator_type: "fmr" for Fair Market Rents or "il" for Income Limits
        :param area_type: "metro", "county", or "state"
        :param min_2br: Minimum 2-bedroom FMR in dollars (e.g. 1500 for >= $1,500/mo)
        :param max_2br: Maximum 2-bedroom FMR in dollars (e.g. 1000 for <= $1,000/mo)
        :param page: Page number (default: 1)
        :param page_size: Results per page (default: 25, max: 100)
        :return: Housing indicators with FMR by bedroom count and income limits.
        """
        emitter = EventEmitter(__event_emitter__)
        desc_parts = [p for p in [state, indicator_type, area_type] if p]
        await emitter.progress_update(f"Searching HUD housing data: {', '.join(desc_parts) or 'all'}")

        data, error = await self._get(self.valves.HOUSING_API_URL, "/api/housing/indicators", {
            "state": state, "indicator_type": indicator_type, "area_type": area_type,
            "min_2br": min_2br, "max_2br": max_2br,
            "page": page, "page_size": page_size,
        })

        if error:
            await emitter.error_update(error)
            return f"Housing data unavailable: {error}. Try again in a moment."

        items = data.get("results", [])
        total = data.get("total_results", len(items))

        if not items:
            await emitter.success_update("Search complete")
            return "No HUD housing data found matching your criteria. Try a different state, indicator type, or rent range."

        lines = [f"## HUD Housing Data\n\nFound **{total}** results\n"]

        for i, item in enumerate(items[:15], 1):
            area_name = item.get("area_name", "Unknown")
            st = item.get("state_abbr", "")
            ind_type = item.get("indicator_type", "")
            a_type = item.get("area_type", "")
            yr = item.get("year", "")

            lines.append(f"{i}. **{area_name}** ({st}, {a_type})")

            parts = [f"Type: {ind_type.upper()}", f"Year: {yr}"]

            # FMR fields
            fmr_eff = item.get("fmr_efficiency")
            fmr_1 = item.get("fmr_1br")
            fmr_2 = item.get("fmr_2br")
            fmr_3 = item.get("fmr_3br")
            fmr_4 = item.get("fmr_4br")

            if any(v is not None for v in [fmr_eff, fmr_1, fmr_2, fmr_3, fmr_4]):
                rent_parts = []
                if fmr_eff is not None:
                    rent_parts.append(f"Eff: {self._fmt_money(fmr_eff)}")
                if fmr_1 is not None:
                    rent_parts.append(f"1BR: {self._fmt_money(fmr_1)}")
                if fmr_2 is not None:
                    rent_parts.append(f"2BR: {self._fmt_money(fmr_2)}")
                if fmr_3 is not None:
                    rent_parts.append(f"3BR: {self._fmt_money(fmr_3)}")
                if fmr_4 is not None:
                    rent_parts.append(f"4BR: {self._fmt_money(fmr_4)}")
                lines.append(f"   FMR: {' | '.join(rent_parts)}")

            # Income limit fields
            mfi = item.get("median_family_income")
            il_vl = item.get("il_very_low_4")
            il_el = item.get("il_extremely_low_4")
            il_low = item.get("il_low_4")

            if any(v is not None for v in [mfi, il_vl, il_el, il_low]):
                il_parts = []
                if mfi is not None:
                    il_parts.append(f"MFI: {self._fmt_money(mfi)}")
                if il_el is not None:
                    il_parts.append(f"Extremely Low: {self._fmt_money(il_el)}")
                if il_vl is not None:
                    il_parts.append(f"Very Low: {self._fmt_money(il_vl)}")
                if il_low is not None:
                    il_parts.append(f"Low: {self._fmt_money(il_low)}")
                lines.append(f"   Income Limits (4-person): {' | '.join(il_parts)}")

            lines.append(f"   {' | '.join(parts)}")
            lines.append("")

        if total > page * page_size:
            lines.append(f"_Showing page {page} of {(total + page_size - 1) // page_size}. Use page={page + 1} for more._")

        lines.append("\n---\n**Source:** [HUD Fair Market Rents](https://www.huduser.gov/portal/datasets/fmr.html) | [HUD Income Limits](https://www.huduser.gov/portal/datasets/il.html)")

        await emitter.success_update(f"Found {total} housing indicators")
        return "\n".join(lines)

    # -- Census (ACS) --------------------------------------------------------

    async def community_search_demographics(
        self,
        search: Optional[str] = None,
        state: Optional[str] = None,
        geo_type: Optional[str] = None,
        min_population: Optional[int] = None,
        min_poverty_rate: Optional[float] = None,
        sort: Optional[str] = None,
        page: int = 1,
        page_size: int = 25,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Search Census American Community Survey (ACS) demographic profiles across
        states, counties, and congressional districts. Covers population, income,
        poverty, employment, education, housing, and racial demographics.
        Use this to find geographies matching criteria or search by name.

        :param search: Full-text search across state/geography names (e.g. "Ohio", "Franklin", "Los Angeles")
        :param state: Two-letter state abbreviation filter (e.g. "OH", "CA")
        :param geo_type: Geography type: "state", "county", or "congressional_district"
        :param min_population: Minimum total population
        :param min_poverty_rate: Minimum poverty rate percentage (e.g. 20 for >= 20%)
        :param sort: Sort by: "relevance" (with search), "population", or "state"
        :param page: Page number (default: 1)
        :param page_size: Results per page (default: 25, max: 100)
        :return: Census profiles with key demographics for matching geographies.
        """
        emitter = EventEmitter(__event_emitter__)
        desc_parts = [p for p in [search, state, geo_type] if p]
        await emitter.progress_update(f"Searching Census demographics: {', '.join(desc_parts) or 'all'}")

        data, error = await self._get(self.valves.CENSUS_API_URL, "/api/census/profiles", {
            "search": search, "state": state, "geo_type": geo_type,
            "min_population": min_population, "min_poverty_rate": min_poverty_rate,
            "sort": sort, "page": page, "page_size": page_size,
        })

        if error:
            await emitter.error_update(error)
            return f"Census data unavailable: {error}. Try again in a moment."

        items = data.get("results", [])
        total = data.get("total_results", len(items))

        if not items:
            await emitter.success_update("Search complete")
            return "No Census profiles found matching your criteria. Try a different search term, state, or geography type."

        lines = [f"## Census ACS Demographic Profiles\n\nFound **{total}** results\n"]

        for i, item in enumerate(items[:10], 1):
            geo_id = item.get("geo_id", "")
            g_type = item.get("geo_type", "")
            state_name = item.get("state_name", "")
            county_name = item.get("county_name", "")
            district = item.get("district_number", "")

            # Build location label
            if g_type == "state":
                label = state_name or geo_id
            elif g_type == "county":
                label = f"{county_name} County, {item.get('state_abbr', '')}" if county_name else geo_id
            elif g_type == "congressional_district":
                label = f"{state_name} District {district}" if district else geo_id
            else:
                label = geo_id

            pop = item.get("total_population")
            income = item.get("median_household_income")
            poverty = item.get("poverty_rate")
            unemp = item.get("unemployment_rate")
            uninsured = item.get("uninsured_rate")

            lines.append(f"{i}. **{label}** (`{geo_id}`)")
            parts = []
            if pop is not None:
                parts.append(f"Pop: {self._fmt_num(pop)}")
            if income is not None:
                parts.append(f"MHI: {self._fmt_money(income)}")
            if poverty is not None:
                parts.append(f"Poverty: {self._fmt_pct(poverty)}")
            if unemp is not None:
                parts.append(f"Unemp: {self._fmt_pct(unemp)}")
            if uninsured is not None:
                parts.append(f"Uninsured: {self._fmt_pct(uninsured)}")
            if parts:
                lines.append(f"   {' | '.join(parts)}")

            # Race/ethnicity summary
            pct_white = item.get("pct_white")
            pct_black = item.get("pct_black")
            pct_hispanic = item.get("pct_hispanic")
            pct_asian = item.get("pct_asian")
            race_parts = []
            if pct_white is not None:
                race_parts.append(f"White: {self._fmt_pct(pct_white)}")
            if pct_black is not None:
                race_parts.append(f"Black: {self._fmt_pct(pct_black)}")
            if pct_hispanic is not None:
                race_parts.append(f"Hispanic: {self._fmt_pct(pct_hispanic)}")
            if pct_asian is not None:
                race_parts.append(f"Asian: {self._fmt_pct(pct_asian)}")
            if race_parts:
                lines.append(f"   {' | '.join(race_parts)}")

            lines.append("")

        if total > page * page_size:
            lines.append(f"_Showing page {page} of {(total + page_size - 1) // page_size}. Use page={page + 1} for more._")

        lines.append(f"\n_Tip: Use `community_get_demographic_profile(geo_id)` for the full profile (e.g. \"ST-OH\", \"CD-OH-03\")._")
        lines.append("\n---\n**Source:** [Census ACS](https://data.census.gov)")

        await emitter.success_update(f"Found {total} Census profiles")
        return "\n".join(lines)

    async def community_get_demographic_profile(
        self,
        geo_id: str,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Get the full Census ACS demographic profile for a specific geography.
        Returns comprehensive data including population, income, poverty, employment,
        education, housing, race/ethnicity, inequality, and social program participation.

        :param geo_id: Geography identifier. Use "ST-XX" for states (e.g. "ST-OH"), "CD-XX-NN" for congressional districts (e.g. "CD-GA-05"), or county geo IDs from search results.
        :return: Full demographic profile with population, income, poverty, housing, education, race, and inequality data.
        """
        emitter = EventEmitter(__event_emitter__)
        await emitter.progress_update(f"Fetching Census profile for {geo_id}...")

        data, error = await self._get(
            self.valves.CENSUS_API_URL, f"/api/census/profiles/{geo_id}"
        )

        if error:
            await emitter.error_update(error)
            return f"Census profile unavailable for {geo_id}: {error}. Verify the geo_id with `community_search_demographics`."

        # Build location label
        g_type = data.get("geo_type", "")
        state_name = data.get("state_name", "")
        county_name = data.get("county_name", "")
        district = data.get("district_number", "")
        acs_year = data.get("acs_year", "")

        if g_type == "state":
            label = state_name or geo_id
        elif g_type == "county":
            label = f"{county_name} County, {data.get('state_abbr', '')}" if county_name else geo_id
        elif g_type == "congressional_district":
            label = f"{state_name} District {district}" if district else geo_id
        else:
            label = geo_id

        lines = [f"## Census Profile: {label}\n"]
        if acs_year:
            lines.append(f"**ACS {acs_year} Data**\n")

        # Population & Households
        lines.append("### Population & Households\n")
        pop = data.get("total_population")
        households = data.get("total_households")
        median_age = data.get("median_age")
        foreign_born = data.get("foreign_born_rate")
        non_english = data.get("non_english_rate")
        veteran = data.get("veteran_rate")

        if pop is not None:
            lines.append(f"- **Total population:** {self._fmt_num(pop)}")
        if households is not None:
            lines.append(f"- **Total households:** {self._fmt_num(households)}")
        if median_age is not None:
            lines.append(f"- **Median age:** {float(median_age):.1f}")
        if foreign_born is not None:
            lines.append(f"- **Foreign-born:** {self._fmt_pct(foreign_born)}")
        if non_english is not None:
            lines.append(f"- **Non-English at home:** {self._fmt_pct(non_english)}")
        if veteran is not None:
            lines.append(f"- **Veterans:** {self._fmt_pct(veteran)}")

        # Race & Ethnicity
        pct_white = data.get("pct_white")
        pct_black = data.get("pct_black")
        pct_hispanic = data.get("pct_hispanic")
        pct_asian = data.get("pct_asian")
        if any(v is not None for v in [pct_white, pct_black, pct_hispanic, pct_asian]):
            lines.append("\n### Race & Ethnicity\n")
            if pct_white is not None:
                lines.append(f"- **White:** {self._fmt_pct(pct_white)}")
            if pct_black is not None:
                lines.append(f"- **Black:** {self._fmt_pct(pct_black)}")
            if pct_hispanic is not None:
                lines.append(f"- **Hispanic/Latino:** {self._fmt_pct(pct_hispanic)}")
            if pct_asian is not None:
                lines.append(f"- **Asian:** {self._fmt_pct(pct_asian)}")

        # Income & Poverty
        lines.append("\n### Income & Poverty\n")
        income = data.get("median_household_income")
        per_capita = data.get("per_capita_income")
        poverty = data.get("poverty_rate")
        deep_poverty = data.get("deep_poverty_rate")
        near_poverty = data.get("near_poverty_rate")
        gini = data.get("gini_index")
        snap = data.get("snap_rate")
        poverty_black = data.get("poverty_rate_black")
        poverty_hispanic = data.get("poverty_rate_hispanic")

        if income is not None:
            lines.append(f"- **Median household income:** {self._fmt_money(income)}")
        if per_capita is not None:
            lines.append(f"- **Per capita income:** {self._fmt_money(per_capita)}")
        if poverty is not None:
            lines.append(f"- **Poverty rate:** {self._fmt_pct(poverty)}")
        if deep_poverty is not None:
            lines.append(f"- **Deep poverty rate:** {self._fmt_pct(deep_poverty)}")
        if near_poverty is not None:
            lines.append(f"- **Near poverty rate:** {self._fmt_pct(near_poverty)}")
        if poverty_black is not None:
            lines.append(f"- **Poverty rate (Black):** {self._fmt_pct(poverty_black)}")
        if poverty_hispanic is not None:
            lines.append(f"- **Poverty rate (Hispanic):** {self._fmt_pct(poverty_hispanic)}")
        if gini is not None:
            lines.append(f"- **Gini index:** {float(gini):.4f}")
        if snap is not None:
            lines.append(f"- **SNAP participation:** {self._fmt_pct(snap)}")

        # Employment & Education
        unemp = data.get("unemployment_rate")
        uninsured = data.get("uninsured_rate")
        bachelors = data.get("bachelors_rate")
        graduate = data.get("graduate_rate")

        if any(v is not None for v in [unemp, uninsured, bachelors, graduate]):
            lines.append("\n### Employment & Education\n")
            if unemp is not None:
                lines.append(f"- **Unemployment rate:** {self._fmt_pct(unemp)}")
            if uninsured is not None:
                lines.append(f"- **Uninsured rate:** {self._fmt_pct(uninsured)}")
            if bachelors is not None:
                lines.append(f"- **Bachelor's degree:** {self._fmt_pct(bachelors)}")
            if graduate is not None:
                lines.append(f"- **Graduate degree:** {self._fmt_pct(graduate)}")

        # Housing
        home_value = data.get("median_home_value")
        rent = data.get("median_gross_rent")
        renter = data.get("renter_rate")
        rent_burden = data.get("rent_burden_pct")

        if any(v is not None for v in [home_value, rent, renter, rent_burden]):
            lines.append("\n### Housing\n")
            if home_value is not None:
                lines.append(f"- **Median home value:** {self._fmt_money(home_value)}")
            if rent is not None:
                lines.append(f"- **Median gross rent:** {self._fmt_money(rent)}")
            if renter is not None:
                lines.append(f"- **Renter-occupied:** {self._fmt_pct(renter)}")
            if rent_burden is not None:
                lines.append(f"- **Rent burden (30%+ income):** {self._fmt_pct(rent_burden)}")

        lines.append("\n---\n**Source:** [Census ACS](https://data.census.gov)")

        await emitter.success_update(f"Census profile for {label}")
        return "\n".join(lines)
