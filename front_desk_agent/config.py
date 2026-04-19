"""
Front desk configuration — Zyana Systems / Zara AI Agent.

Modes:
  visitor  — in-person front desk (greets walk-ins, logs arrivals, books meetings)
  outreach — Zara is calling a sales lead (sales pitch, qualify, book discovery call)
  owner    — Naqiyah is speaking directly to Zara (standup, pipeline, business tasks)
"""

# ─── AGENT IDENTITY ───────────────────────────────────────────────────────────
AGENT_NAME        = "Zara"
AGENT_DESCRIPTION = "Front Desk AI Representative for Zyana Systems"
DEFAULT_MODE      = "visitor"     # visitor | outreach | owner
OWNER_PASSPHRASE  = "zyana owner" # say this to switch into owner mode mid-conversation

# ─── COMPANY ──────────────────────────────────────────────────────────────────
COMPANY_NAME     = "Zyana Systems"
COMPANY_TAGLINE  = "AI Automation for Modern Businesses"
COMPANY_MISSION  = (
    "We build intelligent AI systems that automate repetitive business operations — "
    "from customer communications and lead generation to backend workflows — "
    "so teams can focus entirely on growth."
)
OFFICE_HOURS     = "Monday to Friday, 9 AM to 6 PM"
OFFICE_ADDRESS   = "Zyana Systems HQ"
GENERAL_PHONE    = "(555) 000-0000"
GENERAL_EMAIL    = "hello@zyanasystems.com"
BOOKING_LINK     = "https://calendly.com/zyanasystems"   # Update with your real link

# ─── STAFF DIRECTORY ──────────────────────────────────────────────────────────
STAFF_DIRECTORY = {
    "naqiyah": {
        "title": "Founder & CEO",
        "email": "naqiyah@zyanasystems.com",
        "phone": "ext. 101",
        "location": "Office 201",
    },
    "sales": {
        "title": "Sales Team",
        "email": "sales@zyanasystems.com",
        "phone": "ext. 200",
        "location": "Second Floor",
    },
    "support": {
        "title": "Support Team",
        "email": "support@zyanasystems.com",
        "phone": "ext. 300",
        "location": "Ground Floor",
    },
}

# ─── SERVICES ─────────────────────────────────────────────────────────────────
SERVICES = {
    "chatbot":    "AI Chatbot Development — custom bots for websites, WhatsApp, or CRM",
    "outreach":   "AI Outreach Systems — automated lead generation and follow-up sequences",
    "automation": "Business Automation — connecting your tools so data flows without manual entry",
}

# ─── FAQS ─────────────────────────────────────────────────────────────────────
FAQS = {
    # Visitor FAQs
    "wifi":     "The guest WiFi name is ZyanaGuest and the password is Welcome2024.",
    "parking":  "Visitor parking is in Lot B, left of the main entrance. Free for up to 2 hours.",
    "bathroom": "Restrooms are down the hall, second door on the right.",
    "water":    "There's a water cooler and refreshments in the waiting area just around the corner.",

    # Business FAQs (used in outreach mode)
    "what is zyana":
        "Zyana Systems is an AI automation company. We build intelligent systems that help "
        "businesses automate their operations so their teams can focus on growth.",
    "how much":
        "Our projects are scoped specifically to your business. The best next step is a free "
        "30-minute discovery call where we give you a transparent quote. No pressure at all.",
    "how long":
        "Depending on complexity, most systems are live within 2 to 6 weeks. "
        "Simple chatbots can be deployed in as little as 5 business days.",
    "technical":
        "No technical knowledge required. We build everything and provide simple training. "
        "If you can send an email, you can run our systems.",
    "data safe":
        "All client data is encrypted in transit and at rest. "
        "We never sell or share your data with third parties.",
    "demo":
        "We offer a free discovery call and a no-obligation demo. "
        "It's completely no pressure — just clarity on what automation could look like for you.",
}

# ─── 90-DAY CHALLENGE TARGETS (update as you progress) ────────────────────────
CHALLENGE_TARGETS = {
    "revenue_goal":      25000,    # $ total for 90 days
    "clients_target":    10,       # number of paying clients
    "daily_calls_target": 20,      # outbound calls per day
    "avg_deal_value":    2500,     # $ per client
}

# ─── TTS SETTINGS ─────────────────────────────────────────────────────────────
# Priority order: Edge TTS (free neural) → gTTS (online) → pyttsx3 (offline)
# No API keys needed. Install edge-tts: pip install edge-tts
TTS_LANGUAGE = "en"
TTS_SLOW     = False

# Edge TTS voice — run `edge-tts --list-voices` for full list
# Good options: en-CA-ClaraNeural, en-US-JennyNeural, en-GB-SoniaNeural
EDGE_TTS_VOICE = "en-CA-ClaraNeural"

# ─── SPEECH RECOGNITION ───────────────────────────────────────────────────────
MIC_ENERGY_THRESHOLD  = 300    # Adjust up in noisy environments
MIC_PAUSE_THRESHOLD   = 1.0   # Seconds of silence before ending capture
MIC_PHRASE_TIME_LIMIT = 15    # Max seconds per spoken phrase
USE_GOOGLE_SPEECH     = True  # True = Google STT (internet), False = offline Sphinx
