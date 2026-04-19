"""
apollo_client.py
----------------
Thin wrapper around Apollo.io's REST API for two tasks:
  1. search_prospects()  — find leads by industry, title, location
  2. enrich_person()     — look up a captured lead and return enriched data

Setup:
  1. Go to https://app.apollo.io → Settings → Integrations → API Keys
  2. Create a key and copy it
  3. Add to your .env:  APOLLO_API_KEY=your_key_here

Apollo free tier: 50 email credits + 5 export credits/month.
Paid plans start at $49/mo for unlimited exports.
"""

import os
import requests
from typing import Optional

APOLLO_BASE     = "https://api.apollo.io/api/v1"  # note: /api/v1 not /v1
REQUEST_TIMEOUT = 15  # seconds


def _get_key() -> str:
    """Read Apollo API key from environment — raises clearly if missing."""
    key = os.environ.get("APOLLO_API_KEY", "").strip()
    if not key:
        raise ValueError(
            "APOLLO_API_KEY is not set. "
            "Add it to your .env file: APOLLO_API_KEY=your_key_here"
        )
    return key


def _headers() -> dict:
    """Apollo now requires the key in the header, not the request body."""
    return {
        "x-api-key":    _get_key(),
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
    }


def search_prospects(
    industry: str   = "",
    title: str      = "",
    location: str   = "",
    limit: int      = 10,
) -> list[dict]:
    """
    Search Apollo for people matching the given criteria.

    Args:
        industry:  e.g. "dental", "real estate", "e-commerce"
        title:     e.g. "owner", "founder", "operations manager"
        location:  e.g. "Toronto", "Ontario", "Canada"
        limit:     max results (1–25 per Apollo's API)

    Returns:
        List of prospect dicts with name, title, company, email, phone, linkedin, location.
    """
    payload = {
        "per_page":         min(limit, 25),
        "page":             1,
        "person_titles":    [title]    if title    else [],
        "person_locations": [location] if location else [],
    }
    # Use q_keywords for industry — it's a free-text search across org fields
    if industry:
        payload["q_keywords"] = industry

    resp = requests.post(
        f"{APOLLO_BASE}/mixed_people/search",
        headers=_headers(),
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )

    if not resp.ok:
        raise Exception(f"{resp.status_code} {resp.reason}: {resp.text[:300]}")

    data   = resp.json()
    people = data.get("people", [])

    results = []
    for p in people:
        org      = p.get("organization") or {}
        phones   = p.get("phone_numbers") or []
        location_parts = [p.get("city", ""), p.get("state", "")]
        loc      = ", ".join(x for x in location_parts if x)

        results.append({
            "name":      f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
            "title":     p.get("title", ""),
            "company":   org.get("name", ""),
            "industry":  org.get("industry", industry),
            "email":     p.get("email", ""),
            "phone":     phones[0].get("raw_number", "") if phones else "",
            "linkedin":  p.get("linkedin_url", ""),
            "location":  loc,
            "employees": org.get("estimated_num_employees", ""),
            "website":   org.get("website_url", ""),
            "seniority": p.get("seniority", ""),
        })

    return results


def enrich_person(
    name:    str = "",
    email:   str = "",
    company: str = "",
    domain:  str = "",
) -> dict:
    """
    Enrich a contact using Apollo's /people/match endpoint.

    Pass whatever you have — Apollo fills in the rest.
    Returns a dict with all the data Apollo finds, or an empty dict if no match.
    """
    first, *rest = name.split() if name else ("", [])
    last         = " ".join(rest) if rest else ""

    payload = {
        "first_name":             first,
        "last_name":              last,
        "email":                  email,
        "organization_name":      company,
        "domain":                 domain,
        "reveal_personal_emails": True,
        "reveal_phone_number":    True,
    }

    resp = requests.post(
        f"{APOLLO_BASE}/people/match",
        headers=_headers(),
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )

    if not resp.ok:
        raise Exception(f"{resp.status_code} {resp.reason}: {resp.text[:300]}")
    data   = resp.json()
    person = data.get("person") or {}

    if not person:
        return {}

    org    = person.get("organization") or {}
    phones = person.get("phone_numbers") or []
    location_parts = [person.get("city", ""), person.get("state", "")]
    loc    = ", ".join(x for x in location_parts if x)

    return {
        "name":        f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
        "title":       person.get("title", ""),
        "email":       person.get("email", email),
        "phone":       phones[0].get("raw_number", "") if phones else "",
        "linkedin":    person.get("linkedin_url", ""),
        "company":     org.get("name", company),
        "industry":    org.get("industry", ""),
        "employees":   org.get("estimated_num_employees", ""),
        "website":     org.get("website_url", ""),
        "location":    loc,
        "seniority":   person.get("seniority", ""),
        "departments": person.get("departments", []),
    }
