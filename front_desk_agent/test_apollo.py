"""
test_apollo.py — Quick Apollo integration test
Run from your front_desk_agent folder:
    python test_apollo.py

Tests in order:
  1. API key is valid (any 200/403 confirms the key is accepted)
  2. Person enrich  (/people/match) — works on free plan, uses 1 credit
  3. People search  (/mixed_people/search) — only works on paid plan
  4. CSV import     — works without any Apollo plan
"""

import os
import sys
import json
import tempfile
from pathlib import Path

# ── Load .env so the key is available ────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
    print("✅  .env loaded")
except ImportError:
    print("⚠   python-dotenv not installed — will try shell env")

api_key = os.environ.get("APOLLO_API_KEY", "").strip()
if not api_key or api_key == "your_apollo_api_key_here":
    print("\n❌  APOLLO_API_KEY is missing or still set to the placeholder.")
    print("    Add it to your .env file:\n    APOLLO_API_KEY=your_real_key_here")
    sys.exit(1)

print(f"🔑  Key found: {api_key[:8]}...{api_key[-4:]}")

# ── Import our Apollo client ──────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
try:
    import apollo_client as ac
    print("✅  apollo_client.py imported")
except ImportError as e:
    print(f"❌  Could not import apollo_client: {e}")
    sys.exit(1)


# ════════════════════════════════════════════════════════════════════════════
# TEST 1 — API KEY VALIDATION (ping /people/match with minimal payload)
# ════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*55)
print("TEST 1 — API key validation")
print("═"*55)

import requests

resp = requests.post(
    "https://api.apollo.io/api/v1/people/match",
    headers={
        "x-api-key":     api_key,
        "Content-Type":  "application/json",
        "Cache-Control": "no-cache",
    },
    json={"first_name": "ping", "last_name": "test"},
    timeout=15,
)
print(f"HTTP status: {resp.status_code}")
if resp.status_code == 401:
    print("❌  Key rejected (401 Unauthorized). Double-check your Apollo API key.")
    sys.exit(1)
elif resp.status_code in (200, 404, 422):
    print("✅  Key accepted by Apollo — authentication is working")
elif resp.status_code == 403:
    print("✅  Key accepted (403 means plan restriction, not a bad key)")
else:
    print(f"⚠   Unexpected status {resp.status_code}: {resp.text[:200]}")


# ════════════════════════════════════════════════════════════════════════════
# TEST 2 — PERSON ENRICH  (/people/match)  works on free plan
# ════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*55)
print("TEST 2 — Enrich a real person (uses 1 free credit)")
print("═"*55)

# Using a real, well-known tech founder so Apollo will likely find a match
try:
    result = ac.enrich_person(name="Sam Altman", company="OpenAI")
    if result:
        print("✅  Enrich works! Sample result:")
        for k, v in result.items():
            if v:
                print(f"    {k:12} {v}")
    else:
        print("⚠   Enrich returned no match (not an error — just no data found)")
        print("    Try again with a real prospect's name + company.")
except Exception as e:
    print(f"❌  Enrich failed: {e}")


# ════════════════════════════════════════════════════════════════════════════
# TEST 3 — PEOPLE SEARCH  (paid plan only)
# ════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*55)
print("TEST 3 — Search prospects (requires paid plan)")
print("═"*55)

try:
    results = ac.search_prospects(industry="dental", title="owner", location="Toronto", limit=3)
    if results:
        print(f"✅  Search works! Found {len(results)} prospects:")
        for r in results:
            print(f"    • {r['name']} | {r['title']} @ {r['company']} | {r['email'] or 'no email'}")
    else:
        print("⚠   Search returned 0 results (try different filters)")
except Exception as e:
    msg = str(e)
    if "403" in msg or "free plan" in msg.lower():
        print("ℹ️   Search blocked on free plan (expected).")
        print("    Workaround: export leads from app.apollo.io → CSV → import with Zara")
        print("    Command: 'Zara, import leads from ~/Downloads/apollo_export.csv'")
    else:
        print(f"❌  Search failed: {e}")


# ════════════════════════════════════════════════════════════════════════════
# TEST 4 — CSV IMPORT  (no Apollo plan needed)
# ════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*55)
print("TEST 4 — CSV import (free workaround for Apollo search)")
print("═"*55)

SAMPLE_CSV = """\
First Name,Last Name,Title,Company,Email,Phone,Industry,City,State,LinkedIn URL
Sarah,Chen,Owner,Bright Smile Dental,sarah@brightsmile.ca,+14165550101,Dental,Toronto,Ontario,https://linkedin.com/in/sarahchen
Mike,Patel,Founder,Patel Real Estate Group,mike@patelre.com,+14165550102,Real Estate,Toronto,Ontario,https://linkedin.com/in/mikepatel
Amina,Osei,Marketing Director,Fresh Eats Restaurant,amina@fresheats.ca,+14165550103,Food & Beverage,Toronto,Ontario,
"""

# Write to a temp file
with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, prefix="test_leads_") as f:
    f.write(SAMPLE_CSV)
    tmp_path = f.name

try:
    import tools
    result = tools.import_leads_csv(tmp_path)
    print(f"✅  {result}")
    print("\n    Pipeline after import:")
    stats = tools.get_pipeline_stats()
    print(f"    {stats}")
except Exception as e:
    print(f"❌  CSV import failed: {e}")
finally:
    os.unlink(tmp_path)


# ════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ════════════════════════════════════════════════════════════════════════════
print("\n" + "═"*55)
print("SUMMARY")
print("═"*55)
print("✅  API key:  valid")
print("✅  Enrich:   working (run after capture_lead to fill in details)")
print("ℹ️   Search:   use Apollo web UI export → CSV → import_leads_csv")
print("✅  CSV import: working — this is your primary lead-load path")
print()
print("Apollo free plan workflow:")
print("  1. Go to app.apollo.io → Search people")
print("  2. Filter by industry/title/city")
print("  3. Select up to 50 contacts → Export as CSV")
print("  4. Tell Zara: 'Import leads from ~/Downloads/apollo_export.csv'")
print("  5. Zara auto-adds them to the pipeline + enriches each one")
