# Civic Intelligence Tool — Method Docstrings

> LLM-facing interface definitions for 6 OpenWebUI tools wrapping the GovCon Civic Intelligence API.
> Each docstring is optimized for tool selection accuracy.

---

## civic_search (2 methods)

### search_all
```
Search across ALL civic intelligence data sources at once — federal contracts, grants, foundations,
legislators, bills, nonprofits, court records, and demographics. Use this when the user wants a
broad search across multiple data types, or when you're unsure which specific civic data source
to query. Returns results grouped by source with relevance scores.

:param query: The search query (e.g., "climate change", "education funding", "cybersecurity")
:param sources: Optional list of specific sources to search. Valid values: opportunities, entities, grants, awards, foundations, legislators, bills, nonprofits, census, legislation_bills, legislation_people. If omitted, searches all sources.
:param page: Page number for paginated results (default: 1)
:return: Search results organized by data source, with relevance-ranked items from each source.
```

### data_status
```
Check what civic intelligence data is available and when each data source was last updated.
Returns sync status for all data connectors including record counts and last sync timestamps.
Use this when the user asks what data you have access to, how fresh the data is, or whether
a specific data source is available.

:return: Status of all data connectors showing last sync time, record counts, and health.
```

---

## civic_procurement (5 methods)

### search_opportunities
```
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
```

### get_opportunity
```
Get full details for a specific federal contract opportunity from SAM.gov by its opportunity ID.
Use this after search_opportunities to get complete information about a specific solicitation,
including full description, contact info, and attachments.

:param opportunity_id: The opportunity ID (integer) from search results
:return: Complete opportunity details including description, agency, contacts, dates, set-aside info, and NAICS code.
```

### search_awards
```
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
```

### search_entities
```
Search SAM.gov REGISTERED ENTITIES — companies and organizations that are registered to do
business with the federal government. Use this when the user wants to find government contractors,
look up a company's SAM registration, or find businesses by NAICS code or state.

:param query: Search text — business name, DBA name, or CAGE code
:param state: Two-letter state code filter (e.g., "VA", "DC")
:param naics_code: Primary NAICS code filter (e.g., "541611")
:param page: Page number (default: 1)
:return: List of registered entities with business name, UEI, state, NAICS codes, and registration status.
```

### get_entity
```
Get full details for a specific SAM.gov registered entity by its UEI (Unique Entity Identifier),
including their federal contract award history. Use this after search_entities to get a company's
complete registration profile and their past government contracts.

:param uei: The entity's Unique Entity Identifier (e.g., "JF1NFKM3HNE7")
:return: Entity profile with business name, address, NAICS codes, registration dates, and recent contract awards.
```

---

## civic_funding (5 methods)

### search_grants
```
Search federal GRANT OPPORTUNITIES from Grants.gov — these are government funding opportunities
for organizations to apply for (NOT contracts for services). Use this when the user asks about
federal grants, government funding, grant opportunities, or "grants for [topic]." Grants fund
projects and programs; contracts (use civic_procurement) pay for services delivered.

:param query: Search text (e.g., "education", "STEM workforce development")
:param agency: Agency code filter (e.g., "HHS", "DOE", "NSF")
:param status: Grant status filter — P=Posted (open), F=Forecasted (upcoming), C=Closed, A=Archived
:param page: Page number (default: 1)
:return: List of federal grant opportunities with title, agency, funding amount, close date, and status.
```

### get_grant
```
Get full details for a specific federal grant opportunity from Grants.gov. Use this after
search_grants to get the complete grant announcement including eligibility, funding details,
and application instructions.

:param grant_id: The grant ID (integer) from search results
:return: Complete grant details including description, eligibility, funding range, application deadline, and agency contact.
```

### search_foundations
```
Search PRIVATE FOUNDATIONS from IRS 990-PF filings — these are philanthropic foundations that
give money to nonprofits and causes. Use this when the user asks about private foundations,
philanthropic funders, "foundations that fund [topic]", or foundation giving in a specific state.
This is about the FUNDERS themselves, not their individual grants (use search_foundation_grants for that).

:param query: Search text — foundation name (e.g., "Ford Foundation", "Gates")
:param state: Two-letter state code filter (e.g., "NY", "CA")
:param min_giving: Minimum total giving amount in USD (e.g., 1000000 for $1M+)
:param page: Page number (default: 1)
:return: List of private foundations with name, EIN, state, total assets, total giving, and NTEE classification.
```

### get_foundation
```
Get full details for a specific private foundation by its EIN (Employer Identification Number).
Use this after search_foundations to see a foundation's complete profile including financial
details from their IRS 990-PF filing.

:param ein: The foundation's EIN, with or without dash (e.g., "13-1837418" or "131837418")
:return: Foundation profile with name, address, total assets, total giving, fiscal details, and officer information.
```

### search_foundation_grants
```
Search grants MADE BY a specific private foundation — these are donations and grants the
foundation has given to other organizations. Use this when the user asks "what has [foundation]
funded?", "who does [foundation] give to?", or wants to see a foundation's grantmaking history.

:param ein: The foundation's EIN (e.g., "13-1837418")
:param search: Search text to filter grant recipients or purposes
:param min_amount: Minimum grant amount in USD
:param page: Page number (default: 1)
:return: List of grants made by the foundation with recipient name, amount, purpose, and tax year.
```

---

## civic_legislators (7 methods)

### search_legislators
```
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
```

### get_legislator
```
Get full details for a specific state legislator by their Open States ID. Use this after
search_legislators to get a legislator's complete profile including committee memberships,
sponsored bills, and contact information.

:param openstates_id: The legislator's Open States ID (e.g., "ocd-person/12345678-abcd-...")
:return: Complete legislator profile with name, party, district, committees, sponsored legislation, and contact details.
```

### find_legislators_by_address
```
Find which state legislators represent a specific street address. Use this when the user asks
"who represents [address]?", "who is my state rep?", or "find legislators for [location]."
Handles geocoding internally — just pass the street address.

:param address: Full US street address (e.g., "123 Main St, Columbus, OH 43215")
:return: List of state legislators (state senator and state representative) who represent the given address, with their name, party, district, and contact info.
```

### search_bills
```
Search state legislative bills across all US state legislatures. Use this when the user asks
about state legislation, bills, proposed laws, or "bills about [topic] in [state]." Returns
bill summaries from bulk legislative data with sponsors and latest actions.

:param query: Search text (e.g., "voting rights", "renewable energy")
:param state: State jurisdiction filter — state name (e.g., "Ohio") or OCD ID
:param session: Legislative session filter (e.g., "2025")
:param subject: Subject category filter
:param page: Page number (default: 1)
:return: List of bills with title, bill number, jurisdiction, session, latest action, and sponsor names.
```

### get_bill
```
Get full details for a specific state legislative bill including all actions (history),
sponsors, document versions, and vote records. Use this after search_bills to see a bill's
complete legislative history.

:param bill_ocd_id: The bill's OCD ID from search results (e.g., "ocd-bill/...")
:return: Complete bill details with title, full text link, all actions with dates, sponsors, committee referrals, and vote tallies.
```

### brief_on_bill
```
Generate a comprehensive intelligence brief about a specific state bill. This goes beyond
get_bill by cross-referencing the bill with sponsor profiles, state demographics, and related
organizations. Use this when the user wants a deep analysis of a bill — who introduced it, what
district they represent, and what the political landscape looks like.

:param jurisdiction: State name (e.g., "Ohio")
:param session_name: Legislative session (e.g., "2025")
:param bill_id: Bill identifier (e.g., "HB 247")
:return: Multi-source intelligence brief with bill details, sponsor profiles with their districts, district demographics, and related nonprofit organizations.
```

### get_demographics
```
Get Census Bureau demographic data for a US state or congressional district. Includes population,
income, poverty rate, education levels, race/ethnicity, housing, and employment data from the
American Community Survey (ACS) 5-year estimates. Use this when the user asks about demographics,
population data, poverty rates, or socioeconomic characteristics of a state or district.

:param state: Two-letter state code (e.g., "OH", "GA")
:param district: Congressional district number (e.g., "03"). If omitted, returns state-level data.
:param page: Page number for listing multiple profiles (default: 1)
:return: Demographic profile with population, median income, poverty rate, education attainment, race/ethnicity breakdown, and housing statistics.
```

---

## civic_organizations (3 methods)

### search_nonprofits
```
Search nonprofit organizations (501(c)(3) public charities) by name, state, or NTEE category.
Use this when the user asks about nonprofits, charitable organizations, NGOs, or wants to find
organizations working on a specific issue in a specific area. This searches the ProPublica
Nonprofit Explorer database.

:param query: Search text — organization name or keyword (e.g., "Planned Parenthood", "food bank")
:param state: Two-letter state code filter (e.g., "GA", "OH")
:param ntee_code: NTEE major category code (e.g., "P" for Human Services, "R" for Civil Rights, "S" for Community Improvement, "J" for Employment, "W" for Public Benefit)
:param page: Page number (default: 1)
:return: List of nonprofits with name, EIN, state, NTEE classification, revenue, and assets.
```

### get_nonprofit
```
Get full details for a specific nonprofit organization by its EIN. Use this after search_nonprofits
to see an organization's complete IRS filing data including revenue, expenses, and leadership.

:param ein: The nonprofit's EIN, with or without dash (e.g., "13-1837418")
:return: Nonprofit profile with name, address, mission, revenue, expenses, assets, and key personnel from latest IRS filing.
```

### find_partners
```
Discover potential coalition partners for advocacy or organizing around a specific topic in a
specific state. This is a COMPOUND intelligence query that cross-references nonprofits working
on the topic, state demographics, and relevant legislators. Use this when the user asks about
"finding partners", "coalition building", "who's working on [issue] in [state]", or
"organizations we could partner with."

:param topic: The advocacy or organizing topic (e.g., "education equity", "healthcare access", "voting rights")
:param state: Two-letter state code (e.g., "GA", "AZ")
:return: Multi-source intelligence brief with: relevant nonprofits in the state, state demographic context, state legislators working on related issues, and potential litigation risk from court dockets.
```

---

## civic_court (4 methods)

### search_opinions
```
Search federal court OPINIONS — written decisions issued by federal courts. Use this when the
user asks about court rulings, judicial decisions, legal precedents, case law, or "what has
the court said about [topic]." Covers all federal courts including the Supreme Court.

:param query: Search text (e.g., "first amendment", "voting rights", "redistricting")
:param court: Court identifier filter (e.g., "scotus" for Supreme Court, "cacd" for Central District of California)
:param after_date: Only return opinions filed on or after this date (YYYY-MM-DD)
:param page: Page number (default: 1)
:return: List of court opinions with case name, court, date filed, citation, and summary.
```

### search_dockets
```
Search federal court DOCKETS — active and closed court cases with their procedural history.
Use this when the user asks about court cases, lawsuits, litigation, pending cases, or
"cases about [topic]." Dockets track the lifecycle of a case from filing to resolution.

:param query: Search text (e.g., "patent infringement", "employment discrimination")
:param court: Court identifier filter (e.g., "cacd", "nysd")
:param nature_of_suit: Nature of suit filter (e.g., "Civil Rights", "Labor")
:param page: Page number (default: 1)
:return: List of court dockets with case name, court, docket number, date filed, nature of suit, and status.
```

### search_judges
```
Search federal judges — current and former judges across all federal courts. Use this when
the user asks about specific judges, judicial appointments, or "who are the judges on [court]."

:param query: Search text — judge name (e.g., "Sotomayor", "Kavanaugh")
:param court: Court identifier filter (e.g., "scotus")
:param page: Page number (default: 1)
:return: List of judges with name, court, appointing president, political affiliation, and service dates.
```

### get_court_detail
```
Get full details for a specific court record — an opinion, docket, or judge — by its
CourtListener ID. Use this after any search method to get the complete record.

:param courtlistener_id: The CourtListener ID from search results (integer)
:param record_type: Type of record — "opinion", "docket", or "judge"
:return: Complete record details. For opinions: full text and citations. For dockets: party information and filing history. For judges: career history, education, and political affiliations.
```
