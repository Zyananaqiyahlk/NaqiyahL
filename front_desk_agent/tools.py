"""
Front desk tools that Claude (Zara) can invoke during a conversation.

Original tools (visitor mode):
  log_visitor, take_message, lookup_staff, check_appointment, book_appointment, get_faq_answer

New tools (outreach + owner mode):
  capture_lead         — save a prospect's info to the leads file
  book_discovery_call  — log a booked discovery call
  get_pipeline_stats   — summarise current lead pipeline
  get_daily_standup    — return today's priority tasks across the 5 pillars
  draft_followup_email — compose a follow-up email draft for a prospect
"""

import json
import os
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import config

# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

VISITORS_FILE     = DATA_DIR / "visitors.json"
MESSAGES_FILE     = DATA_DIR / "messages.json"
APPOINTMENTS_FILE = DATA_DIR / "appointments.json"
LEADS_FILE        = DATA_DIR / "leads.json"
STANDUP_FILE      = DATA_DIR / "standup_tasks.json"
CALENDAR_FILE     = DATA_DIR / "calendar.json"


def _load(path: Path) -> list:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return []


def _save(path: Path, data: list) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ===========================================================================
# VISITOR MODE TOOLS (unchanged from original)
# ===========================================================================

def log_visitor(name: str, purpose: str, host: str = "") -> str:
    """Record a visitor's arrival at the front desk."""
    record = {
        "id":         len(_load(VISITORS_FILE)) + 1,
        "name":       name,
        "purpose":    purpose,
        "host":       host,
        "arrived_at": datetime.now().isoformat(),
    }
    visitors = _load(VISITORS_FILE)
    visitors.append(record)
    _save(VISITORS_FILE, visitors)
    return (
        f"Visitor '{name}' logged (#{record['id']}). Purpose: {purpose}. "
        + (f"Host notified: {host}." if host else "")
    )


def take_message(sender_name: str, sender_contact: str, recipient: str, message_body: str) -> str:
    """Record a message for a staff member who is unavailable."""
    record = {
        "id":           len(_load(MESSAGES_FILE)) + 1,
        "from_name":    sender_name,
        "from_contact": sender_contact,
        "for":          recipient,
        "message":      message_body,
        "received_at":  datetime.now().isoformat(),
        "delivered":    False,
    }
    messages = _load(MESSAGES_FILE)
    messages.append(record)
    _save(MESSAGES_FILE, messages)
    return (
        f"Message from {sender_name} recorded for {recipient}. "
        f"They'll be notified shortly. Message ID: #{record['id']}."
    )


def lookup_staff(name_or_role: str) -> str:
    """Look up a staff member or department by name or role."""
    query = name_or_role.lower().strip()
    for key, info in config.STAFF_DIRECTORY.items():
        if query in key or query in info["title"].lower():
            return (
                f"{info['title']}: located at {info['location']}, "
                f"phone {info['phone']}, email {info['email']}."
            )
    return (
        f"I don't have '{name_or_role}' in our directory. "
        f"Main line: {config.GENERAL_PHONE} | email: {config.GENERAL_EMAIL}."
    )


def check_appointment(visitor_name: str, date: str = "") -> str:
    """Check whether a visitor has a scheduled appointment."""
    target_date  = date if date else datetime.now().strftime("%Y-%m-%d")
    appointments = _load(APPOINTMENTS_FILE)
    matches = [
        a for a in appointments
        if visitor_name.lower() in a.get("visitor_name", "").lower()
        and a.get("date", "").startswith(target_date)
    ]
    if matches:
        lines = [
            f"{a['time']} with {a.get('host', 'unknown')} ({a.get('purpose', 'no details')})"
            for a in matches
        ]
        return f"Appointment(s) found for {visitor_name}: " + "; ".join(lines) + "."
    return (
        f"No appointment found for {visitor_name} on {target_date}. "
        "They may be a walk-in, or booked under a different name."
    )


def book_appointment(visitor_name: str, host: str, date: str, time: str, purpose: str = "") -> str:
    """Book an in-person appointment for a visitor."""
    record = {
        "id":           len(_load(APPOINTMENTS_FILE)) + 1,
        "visitor_name": visitor_name,
        "host":         host,
        "date":         date,
        "time":         time,
        "purpose":      purpose,
        "booked_at":    datetime.now().isoformat(),
    }
    appts = _load(APPOINTMENTS_FILE)
    appts.append(record)
    _save(APPOINTMENTS_FILE, appts)
    return (
        f"Appointment booked for {visitor_name} with {host} on {date} at {time}. "
        f"Appointment ID: #{record['id']}."
    )


def get_faq_answer(topic: str) -> str:
    """Answer common visitor or business FAQs."""
    query = topic.lower()
    for key, answer in config.FAQS.items():
        if key in query or query in key:
            return answer
    return "I don't have a specific answer for that. Let me check with a team member."


# ===========================================================================
# OUTREACH MODE TOOLS (new — sales & lead management)
# ===========================================================================

def capture_lead(
    name: str,
    company: str,
    phone: str,
    email: str = "",
    industry: str = "",
    interest_level: str = "warm",
    notes: str = "",
) -> str:
    """
    Save a prospect's contact details to the leads file.
    Called when Zara qualifies someone as a potential client during a conversation.
    interest_level: hot | warm | cold
    """
    record = {
        "id":             len(_load(LEADS_FILE)) + 1,
        "name":           name,
        "company":        company,
        "phone":          phone,
        "email":          email,
        "industry":       industry,
        "interest_level": interest_level,
        "status":         "New",
        "notes":          notes,
        "captured_at":    datetime.now().isoformat(),
    }
    leads = _load(LEADS_FILE)
    leads.append(record)
    _save(LEADS_FILE, leads)
    return (
        f"Lead captured: {name} from {company} (#{record['id']}). "
        f"Interest: {interest_level}. "
        + (f"Notes: {notes}" if notes else "")
    )


def book_discovery_call(
    prospect_name: str,
    company: str,
    phone: str,
    preferred_date: str,
    preferred_time: str,
    notes: str = "",
) -> str:
    """
    Log a booked discovery call with a prospect.
    Called when someone agrees to a free discovery call during outreach.
    """
    record = {
        "id":             len(_load(APPOINTMENTS_FILE)) + 1,
        "visitor_name":   prospect_name,
        "company":        company,
        "phone":          phone,
        "host":           "Naqiyah (Founder, Zyana Systems)",
        "date":           preferred_date,
        "time":           preferred_time,
        "purpose":        "Discovery call — AI automation consultation",
        "type":           "discovery_call",
        "notes":          notes,
        "booked_at":      datetime.now().isoformat(),
    }
    appts = _load(APPOINTMENTS_FILE)
    appts.append(record)
    _save(APPOINTMENTS_FILE, appts)

    # Also capture as a lead if not already there
    leads   = _load(LEADS_FILE)
    already = any(
        l.get("phone", "") == phone or l.get("name", "").lower() == prospect_name.lower()
        for l in leads
    )
    if not already:
        leads.append({
            "id": len(leads) + 1, "name": prospect_name, "company": company,
            "phone": phone, "status": "Booked", "captured_at": datetime.now().isoformat(),
        })
        _save(LEADS_FILE, leads)

    return (
        f"Discovery call booked! {prospect_name} from {company} — "
        f"{preferred_date} at {preferred_time}. "
        f"Booking ID: #{record['id']}. "
        f"Booking link also sent: {config.BOOKING_LINK}"
    )


def get_pipeline_stats() -> str:
    """
    Return a quick summary of the current lead pipeline.
    Used by owner mode so Naqiyah can ask 'what's the pipeline looking like?'
    """
    leads = _load(LEADS_FILE)
    appts = _load(APPOINTMENTS_FILE)
    if not leads:
        return "No leads captured yet. Time to get those outreach calls going!"

    total     = len(leads)
    new_leads = sum(1 for l in leads if l.get("status", "New") == "New")
    booked    = sum(1 for l in leads if l.get("status") == "Booked")
    discovery = sum(1 for a in appts if a.get("type") == "discovery_call")
    hot       = sum(1 for l in leads if l.get("interest_level") == "hot")

    targets = config.CHALLENGE_TARGETS
    return (
        f"Pipeline snapshot: {total} total leads. "
        f"{new_leads} new, {booked} booked for discovery call, {hot} hot leads. "
        f"{discovery} discovery calls scheduled so far. "
        f"Revenue goal: ${targets['revenue_goal']:,} | "
        f"Target clients: {targets['clients_target']}."
    )


def get_daily_standup() -> str:
    """
    Return today's priority checklist across the 5 business pillars.
    Used when Naqiyah asks Zara 'what should I work on today?' or 'run my standup'.
    """
    today = date.today().strftime("%A, %B %d")

    # Check pipeline for any leads needing follow-up
    leads      = _load(LEADS_FILE)
    follow_ups = [l["name"] for l in leads if l.get("status") in ("Follow-Up", "Called")]
    appts      = _load(APPOINTMENTS_FILE)
    today_calls = [
        f"{a['visitor_name']} at {a['time']}"
        for a in appts
        if a.get("date") == date.today().strftime("%Y-%m-%d") and a.get("type") == "discovery_call"
    ]

    standup = f"Good morning! Here's your standup for {today}.\n"

    standup += "\n🌐 WEBSITE: Review your homepage CTA — is the booking link working on mobile?"
    standup += "\n🔍 SEO: Draft or publish one piece of content today. Target: AI automation keywords."
    standup += "\n💼 LINKEDIN: Post a client result or AI insight. Engage with 10 comments in your ICP."

    if follow_ups:
        standup += f"\n📧 LEAD EMAILS: Follow up with: {', '.join(follow_ups[:5])}."
    else:
        standup += "\n📧 LEAD EMAILS: Add 5 new leads to the tracker and queue outreach emails."

    standup += "\n🤖 AGENT/CHATBOT: Review yesterday's call transcripts. Update any FAQ answers."

    if today_calls:
        standup += f"\n\n📞 CALLS TODAY: {'; '.join(today_calls)}."
    else:
        standup += "\n\n📞 No discovery calls scheduled yet today — good time to trigger outbound."

    targets = config.CHALLENGE_TARGETS
    standup += (
        f"\n\n🎯 90-DAY TARGET: ${targets['revenue_goal']:,} revenue | "
        f"{targets['clients_target']} clients | "
        f"{targets['daily_calls_target']} calls/day. Stay consistent!"
    )

    return standup


def get_today_schedule(lookahead_days: int = 1) -> str:
    """
    Return today's (and optionally tomorrow's) calendar events from the
    local calendar cache. Run sync_calendar.py to refresh the cache.
    lookahead_days: 1 = today only, 2 = today + tomorrow, 7 = full week
    """
    if not CALENDAR_FILE.exists():
        return (
            "No calendar data found. Run sync_calendar.py to connect your Google Calendar, "
            "or add events manually to data/calendar.json."
        )

    try:
        with open(CALENDAR_FILE) as f:
            cal = json.load(f)
    except Exception as e:
        return f"Could not read calendar file: {e}"

    events    = cal.get("events", [])
    synced    = cal.get("last_synced", "unknown")
    today     = date.today()
    cutoff    = today + __import__("datetime").timedelta(days=lookahead_days)

    upcoming = [
        e for e in events
        if today <= date.fromisoformat(e["date"]) < cutoff
    ]

    if not upcoming:
        label = "today" if lookahead_days == 1 else f"the next {lookahead_days} days"
        return f"Your calendar is clear for {label}. Good time to focus on outreach."

    lines = []
    for e in sorted(upcoming, key=lambda x: (x["date"], x.get("time", ""))):
        day   = "Today" if e["date"] == str(today) else "Tomorrow" if e["date"] == str(today + __import__("datetime").timedelta(days=1)) else e["date"]
        desc  = f" — {e['description'][:120]}…" if e.get("description") else ""
        lines.append(f"{day} {e.get('time','')}: {e['title']}{desc}")

    result = f"Calendar ({len(upcoming)} event{'s' if len(upcoming)!=1 else ''}, synced {synced[:10]}):\n"
    result += "\n".join(lines)
    return result


def draft_followup_email(
    prospect_name: str,
    company: str,
    call_outcome: str,
    next_step: str = "book a discovery call",
) -> str:
    """
    Compose a personalised follow-up email draft for a prospect after a call.
    Returns the full email text that Zara reads out or saves.
    """
    today = date.today().strftime("%B %d, %Y")
    email = f"""Subject: Following up — AI automation for {company}

Hi {prospect_name.split()[0]},

It was great connecting with you today. {call_outcome}

At Zyana Systems, we specialize in helping businesses like {company} automate the repetitive parts of their operations — so your team can focus on what actually moves the needle.

The next step I'd suggest is a free 30-minute discovery call where we look at your specific workflows and show you exactly what automation could look like for you. No pressure, no commitment — just clarity.

You can book directly here: {config.BOOKING_LINK}

Or just reply to this email and we'll sort a time.

Looking forward to connecting,

Naqiyah
Founder, Zyana Systems
{config.GENERAL_EMAIL} | {config.GENERAL_PHONE}
"""
    return f"Email draft ready for {prospect_name} at {company}:\n\n{email}"


# ===========================================================================
# TOOL DEFINITIONS FOR CLAUDE API
# ===========================================================================

TOOL_DEFINITIONS = [
    # ── Visitor tools ──────────────────────────────────────────────────────
    {
        "name": "log_visitor",
        "description": "Log a visitor's arrival at the front desk.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name":    {"type": "string", "description": "Full name of the visitor"},
                "purpose": {"type": "string", "description": "Reason for the visit"},
                "host":    {"type": "string", "description": "Staff member they're here to see (if known)"},
            },
            "required": ["name", "purpose"],
        },
    },
    {
        "name": "take_message",
        "description": "Record a message for a staff member who is unavailable.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sender_name":    {"type": "string"},
                "sender_contact": {"type": "string", "description": "Phone or email of the sender"},
                "recipient":      {"type": "string", "description": "Staff member the message is for"},
                "message_body":   {"type": "string"},
            },
            "required": ["sender_name", "sender_contact", "recipient", "message_body"],
        },
    },
    {
        "name": "lookup_staff",
        "description": "Look up a staff member or department by name or role.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name_or_role": {"type": "string"},
            },
            "required": ["name_or_role"],
        },
    },
    {
        "name": "check_appointment",
        "description": "Check whether a visitor has a scheduled appointment for today or a given date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "visitor_name": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD. Leave blank for today."},
            },
            "required": ["visitor_name"],
        },
    },
    {
        "name": "book_appointment",
        "description": "Book an in-person appointment for a visitor with a staff member.",
        "input_schema": {
            "type": "object",
            "properties": {
                "visitor_name": {"type": "string"},
                "host":         {"type": "string"},
                "date":         {"type": "string", "description": "YYYY-MM-DD"},
                "time":         {"type": "string", "description": "HH:MM"},
                "purpose":      {"type": "string"},
            },
            "required": ["visitor_name", "host", "date", "time"],
        },
    },
    {
        "name": "get_faq_answer",
        "description": "Answer common questions about WiFi, parking, services, pricing, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic: wifi, parking, pricing, demo, etc."},
            },
            "required": ["topic"],
        },
    },
    # ── Outreach / sales tools ─────────────────────────────────────────────
    {
        "name": "capture_lead",
        "description": (
            "Save a prospect's contact info as a new lead. "
            "Call this when a visitor or caller is interested in Zyana Systems' services."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name":           {"type": "string", "description": "Full name"},
                "company":        {"type": "string"},
                "phone":          {"type": "string"},
                "email":          {"type": "string"},
                "industry":       {"type": "string"},
                "interest_level": {"type": "string", "description": "hot | warm | cold"},
                "notes":          {"type": "string", "description": "Pain points, context, anything useful"},
            },
            "required": ["name", "company", "phone"],
        },
    },
    {
        "name": "book_discovery_call",
        "description": (
            "Log a booked discovery call when a prospect agrees to a free 30-minute consultation. "
            "This is the primary conversion goal in outreach mode."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "prospect_name":  {"type": "string"},
                "company":        {"type": "string"},
                "phone":          {"type": "string"},
                "preferred_date": {"type": "string", "description": "YYYY-MM-DD"},
                "preferred_time": {"type": "string", "description": "e.g. 10:00 AM"},
                "notes":          {"type": "string"},
            },
            "required": ["prospect_name", "company", "phone", "preferred_date", "preferred_time"],
        },
    },
    {
        "name": "get_pipeline_stats",
        "description": (
            "Return a summary of the current lead pipeline — total leads, bookings, hot leads, "
            "and progress toward the 90-day revenue target. Use in owner mode."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_daily_standup",
        "description": (
            "Return today's priority checklist across the 5 business pillars "
            "(Website, SEO, LinkedIn, Lead Emails, Agent). "
            "Use when the owner asks 'what should I work on today?' or 'run my standup'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_today_schedule",
        "description": (
            "Return today's calendar events from the synced Google Calendar cache. "
            "Use whenever the owner asks about their schedule, meetings, calendar, or what's on today."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lookahead_days": {
                    "type": "integer",
                    "description": "1 = today only, 2 = today + tomorrow, 7 = full week. Default 2.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "draft_followup_email",
        "description": "Compose a personalised follow-up email draft for a prospect after a call or visit.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prospect_name": {"type": "string"},
                "company":       {"type": "string"},
                "call_outcome":  {"type": "string", "description": "1-2 sentence summary of what was discussed"},
                "next_step":     {"type": "string", "description": "Agreed next action, e.g. 'book a discovery call'"},
            },
            "required": ["prospect_name", "company", "call_outcome"],
        },
    },
]

# Tool name → function mapping
TOOL_REGISTRY = {
    "log_visitor":         log_visitor,
    "take_message":        take_message,
    "lookup_staff":        lookup_staff,
    "check_appointment":   check_appointment,
    "book_appointment":    book_appointment,
    "get_faq_answer":      get_faq_answer,
    "capture_lead":        capture_lead,
    "book_discovery_call": book_discovery_call,
    "get_pipeline_stats":  get_pipeline_stats,
    "get_daily_standup":   get_daily_standup,
    "draft_followup_email": draft_followup_email,
    "get_today_schedule":   get_today_schedule,
}


def execute_tool(name: str, tool_input: dict) -> str:
    """Dispatch a tool call by name and return the result as a string."""
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return f"Unknown tool: {name}"
    try:
        return fn(**tool_input)
    except Exception as exc:
        return f"Tool error ({name}): {exc}"
