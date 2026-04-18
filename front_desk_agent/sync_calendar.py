"""
sync_calendar.py
----------------
Fetches the next 7 days of Google Calendar events and writes them to
data/calendar.json so Zara can answer "what's on my calendar today?".

Run this manually any time:
    python sync_calendar.py

Or schedule it (runs every morning at 7am):
    # Add to crontab:  0 7 * * * /path/to/python /path/to/sync_calendar.py

Setup (one time only):
    1. Go to https://console.cloud.google.com
    2. Select your project → Enable "Google Calendar API"
    3. Go to Credentials → Create OAuth 2.0 Client ID → Desktop App
    4. Download the JSON → save as credentials_oauth.json in this folder
    5. Run this script once — it opens a browser for you to approve access
    6. A token.json file is saved — future runs are automatic

Dependencies (already in requirements.txt):
    pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_DIR      = Path(__file__).parent / "data"
CALENDAR_FILE = DATA_DIR / "calendar.json"
CREDS_FILE    = Path(__file__).parent / "credentials_oauth.json"
TOKEN_FILE    = Path(__file__).parent / "token.json"
SCOPES        = ["https://www.googleapis.com/auth/calendar.readonly"]
LOOKAHEAD_DAYS = 7


def authenticate():
    """Authenticate with Google Calendar API using OAuth 2.0."""
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    creds = None

    # Load saved token
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    # Refresh or get new token
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDS_FILE.exists():
                print(f"\n❌  credentials_oauth.json not found.")
                print("    Setup steps:")
                print("    1. Go to https://console.cloud.google.com")
                print("    2. Enable Google Calendar API")
                print("    3. Create OAuth 2.0 credentials (Desktop App)")
                print("    4. Download JSON → save as credentials_oauth.json here")
                print("    5. Re-run: python sync_calendar.py\n")
                sys.exit(1)
            flow  = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save token for next run
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return creds


def fetch_events(creds) -> list[dict]:
    """Fetch events from Google Calendar for the next LOOKAHEAD_DAYS days."""
    from googleapiclient.discovery import build

    service  = build("calendar", "v3", credentials=creds)
    now      = datetime.now(timezone.utc)
    end_time = now + timedelta(days=LOOKAHEAD_DAYS)

    result = service.events().list(
        calendarId="primary",
        timeMin=now.isoformat(),
        timeMax=end_time.isoformat(),
        maxResults=50,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    raw_events = result.get("items", [])
    events     = []

    for e in raw_events:
        start = e["start"].get("dateTime", e["start"].get("date", ""))
        end   = e["end"].get("dateTime", e["end"].get("date", ""))

        # Parse date and time
        if "T" in start:
            dt       = datetime.fromisoformat(start)
            ev_date  = dt.strftime("%Y-%m-%d")
            ev_time  = dt.strftime("%-I:%M %p")
        else:
            ev_date  = start
            ev_time  = "All day"

        if "T" in end:
            end_dt   = datetime.fromisoformat(end)
            ev_end   = end_dt.strftime("%-I:%M %p")
        else:
            ev_end   = ""

        events.append({
            "date":        ev_date,
            "time":        ev_time,
            "end_time":    ev_end,
            "title":       e.get("summary", "(no title)"),
            "description": e.get("description", ""),
            "location":    e.get("location", ""),
            "meet_link":   e.get("hangoutLink", ""),
            "type":        "recurring" if e.get("recurringEventId") else "single",
        })

    return events


def sync():
    print("\n🔄  Syncing Google Calendar → Zara...")

    try:
        creds  = authenticate()
        events = fetch_events(creds)
    except ImportError:
        print("❌  Missing packages. Run:  pip install google-api-python-client google-auth-oauthlib")
        sys.exit(1)
    except Exception as e:
        print(f"❌  Error fetching calendar: {e}")
        sys.exit(1)

    DATA_DIR.mkdir(exist_ok=True)
    data = {
        "last_synced": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "timezone":    "America/Toronto",
        "events":      events,
    }
    with open(CALENDAR_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print(f"✅  Synced {len(events)} events → data/calendar.json")
    if events:
        for e in events[:5]:
            print(f"   {e['date']} {e['time']:>10}  {e['title']}")
        if len(events) > 5:
            print(f"   … and {len(events)-5} more")
    else:
        print("   Calendar is clear for the next 7 days.")
    print()


if __name__ == "__main__":
    sync()
