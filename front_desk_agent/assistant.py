"""
Zara — Zyana Systems Front Desk AI Assistant
Core conversation engine.

Modes:
  visitor  — greets walk-in visitors, logs arrivals, books meetings (default)
  outreach — sales pitch mode: qualify leads, book discovery calls
  owner    — Naqiyah's personal assistant: standup, pipeline, business tasks

Say the OWNER_PASSPHRASE mid-conversation to switch into owner mode.
"""

import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

import anthropic
from dotenv import load_dotenv

import config
from tools import TOOL_DEFINITIONS, execute_tool
from voice_io import speak, listen, listen_with_retry

load_dotenv(override=True)  # override=True ensures .env beats any stale shell exports

# ---------------------------------------------------------------------------
# CLAUDE.md memory loader — the agent's persistent identity / brain
# ---------------------------------------------------------------------------

MEMORY_FILE = Path(__file__).parent / "CLAUDE.md"


def _load_memory() -> str:
    """
    Load the CLAUDE.md memory file — the foundational identity the agent
    was built with via the RAG indexing process. Returns an empty string
    (with a warning) if the file is missing so the agent still runs.
    """
    if not MEMORY_FILE.exists():
        print(f"⚠  CLAUDE.md not found at {MEMORY_FILE} — running without persistent memory.")
        return ""
    try:
        content = MEMORY_FILE.read_text(encoding="utf-8").strip()
        print(f"🧠  Loaded CLAUDE.md memory ({len(content):,} chars)")
        return content
    except Exception as e:
        print(f"⚠  Failed to read CLAUDE.md: {e}")
        return ""


# Load once at import time so every conversation uses the same brain
AGENT_MEMORY = _load_memory()


# ---------------------------------------------------------------------------
# API key validation — fail fast with a clear message
# ---------------------------------------------------------------------------

def _validate_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        print("\n❌  ANTHROPIC_API_KEY is missing from your .env file.")
        print("    1. Go to https://console.anthropic.com → API Keys")
        print("    2. Create a new key and copy it")
        print("    3. Open your .env file and set:  ANTHROPIC_API_KEY=sk-ant-...")
        print("    4. Re-run: python main.py --text\n")
        sys.exit(1)
    return key

# ---------------------------------------------------------------------------
# System prompts — one per mode
# ---------------------------------------------------------------------------

def _build_system_prompt(mode: str) -> str:
    now = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")

    # ── Foundational identity layer — the CLAUDE.md brain ──
    memory_block = ""
    if AGENT_MEMORY:
        memory_block = (
            "=== PERSISTENT MEMORY / IDENTITY (CLAUDE.md) ===\n"
            "This is your foundational identity and operating brain. "
            "Every response must be consistent with the principles, priorities, "
            "and context below. Treat it as ground truth about who you are, "
            "who you work for, and what matters.\n\n"
            f"{AGENT_MEMORY}\n"
            "=== END PERSISTENT MEMORY ===\n\n"
        )

    base = memory_block + f"""You are {config.AGENT_NAME}, {config.AGENT_DESCRIPTION} for {config.COMPANY_NAME}.
{config.COMPANY_MISSION}

RESPONSE RULES:
- Keep every response to 1–3 SHORT sentences.
- Never use bullet points, markdown, headers, or numbered lists.
- Speak naturally with contractions — "I've", "you're", "that's".
- Always confirm tool actions out loud after calling them: "Done — I've logged your arrival."
- If unsure about something, say: "Great question — let me have someone follow up on that."
- Today is {now}.

CRITICAL — TOOL USE RULES (you MUST follow these without exception):
- Tools are your memory. NEVER say you've done something without actually calling the tool.
- Do NOT say "I'll log that", "I've noted that", or "I'll capture that" — CALL THE TOOL FIRST, then confirm.
- If a visitor gives their name → call log_visitor immediately.
- If anyone shows interest in services → call capture_lead immediately.
- If a discovery call is booked → call book_discovery_call immediately.
- If a message needs to be taken → call take_message immediately.
- In owner mode, always call get_pipeline_stats or get_daily_standup — never make up numbers.
- After every tool call, confirm the result out loud in one short sentence.
"""

    if mode == "visitor":
        return base + f"""
YOUR ROLE — VISITOR MODE:
You are the welcoming front desk representative for {config.COMPANY_NAME}.

MANDATORY TOOL SEQUENCE for a walk-in:
1. Get their name and purpose → call log_visitor RIGHT AWAY (do not skip this)
2. If they ask about services or seem interested → call capture_lead RIGHT AWAY
3. If they want to leave a message → call take_message RIGHT AWAY
4. If they have or want an appointment → call check_appointment or book_appointment RIGHT AWAY

Office hours: {config.OFFICE_HOURS}.
Address: {config.OFFICE_ADDRESS}.
When wrapping up, tell them where to wait and that someone will be right with them.
"""

    elif mode == "outreach":
        services = " | ".join(config.SERVICES.values())
        return base + f"""
YOUR ROLE — OUTREACH MODE:
You are Zara calling prospects on behalf of {config.COMPANY_NAME}.
Goal: qualify them and book a free 30-minute discovery call.

SERVICES: {services}

CALL STRUCTURE:
1. Open: Confirm you're speaking with the right person.
2. Hook: One sentence about the value we deliver, tailored to their industry.
3. Qualify: Ask 2–3 discovery questions about their pain points.
4. Close: Offer two time slots for a free discovery call.

MANDATORY TOOL SEQUENCE:
- As soon as you have their name + company → call capture_lead RIGHT AWAY (even if they seem cold)
- As soon as they agree to a call → call book_discovery_call RIGHT AWAY
- After capturing, call enrich_lead_apollo if you have their email or company name
- NEVER end a call without capturing the lead — even a "no" is cold data worth keeping

QUALIFYING QUESTIONS (pick 2–3):
- "What's the most repetitive part of your team's day?"
- "Are you currently using any automation tools?"
- "What would it mean for your business if that process ran itself?"

Booking link: {config.BOOKING_LINK}
Never hard-sell. Lead with curiosity and genuine value.
"""

    else:  # owner mode
        targets = config.CHALLENGE_TARGETS
        return base + f"""
YOUR ROLE — OWNER MODE:
You are Zara speaking directly with Naqiyah, the Founder of {config.COMPANY_NAME}.
You are a sharp, direct business partner — not a receptionist.

MANDATORY TOOL SEQUENCE:
- "what's the pipeline?" → call get_pipeline_stats RIGHT AWAY
- "run my standup" / "what should I work on?" → call get_daily_standup RIGHT AWAY
- "what's on my calendar?" → call get_today_schedule RIGHT AWAY
- "find leads in [industry]" → call search_apollo_leads RIGHT AWAY
- "draft a follow-up for [name]" → call draft_followup_email RIGHT AWAY
- NEVER make up pipeline numbers — always call the tool and report real data

90-DAY CHALLENGE TARGETS:
- Revenue goal: ${targets['revenue_goal']:,}
- Target clients: {targets['clients_target']}
- Avg deal value: ${targets['avg_deal_value']:,}
- Daily calls target: {targets['daily_calls_target']}

Be direct, energetic, and focused on revenue. You're here to help Naqiyah win.
"""


# ---------------------------------------------------------------------------
# Conversation logger
# ---------------------------------------------------------------------------

LOGS_DIR = Path(__file__).parent / "data" / "conversations"
LOGS_DIR.mkdir(parents=True, exist_ok=True)


def _save_conversation(mode: str, history: list[dict]) -> None:
    """Save a completed conversation to data/conversations/ as a JSON file."""
    if not history:
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file  = LOGS_DIR / f"{mode}_{timestamp}.json"
    with open(log_file, "w") as f:
        json.dump(
            {"mode": mode, "timestamp": timestamp, "turns": history},
            f, indent=2, default=str
        )
    print(f"[Conversation saved → {log_file.name}]")


# ---------------------------------------------------------------------------
# Assistant class
# ---------------------------------------------------------------------------

class FrontDeskAssistant:
    def __init__(self, text_mode: bool = False, mode: str = "visitor"):
        """
        Args:
            text_mode: keyboard/print instead of mic/speaker (testing).
            mode:      "visitor" | "outreach" | "owner"
        """
        self.client    = anthropic.Anthropic(api_key=_validate_api_key())
        self.text_mode = text_mode
        self.mode      = mode
        self.conversation_history: list[dict] = []

    # ------------------------------------------------------------------
    # I/O helpers
    # ------------------------------------------------------------------

    def _say(self, text: str) -> None:
        if self.text_mode:
            print(f"\n[{config.AGENT_NAME}]: {text}\n")
        else:
            speak(text)

    def _hear(self, prompt: Optional[str] = None) -> Optional[str]:
        if self.text_mode:
            try:
                user_input = input("You: ").strip()
                return user_input if user_input else None
            except (EOFError, KeyboardInterrupt):
                return None
        else:
            return listen_with_retry(prompt)

    def _check_mode_switch(self, user_input: str) -> bool:
        """
        Check if the user said the owner passphrase.
        Uses fuzzy matching to handle STT mishearing (e.g. "diana own" → "zyana owner").
        Returns True if mode was switched.
        """
        lower = user_input.lower().strip()
        phrase = config.OWNER_PASSPHRASE.lower()

        # Exact match
        if phrase in lower:
            return self._activate_owner_mode()

        # Fuzzy: both key words partially present
        # "zyana owner" → look for z*ana/z*iana and own*
        words = lower.split()
        has_zyana = any(
            w.startswith("z") or w in ("zyana", "ziana", "diana", "xena", "zara", "zyanna")
            for w in words
        )
        has_owner = any("own" in w or "mode" in w or "boss" in w for w in words)

        if has_zyana and has_owner:
            return self._activate_owner_mode()

        # Outreach mode switch
        if any(w in lower for w in ("outreach", "sales mode", "call mode")):
            self.mode = "outreach"
            self._say("Switching to outreach mode. Let's go get some clients!")
            return True

        return False

    def _activate_owner_mode(self) -> bool:
        self.mode = "owner"
        self._say(
            "Owner mode activated. Hi Naqiyah! "
            "I'm ready for your standup, pipeline review, or anything else you need."
        )
        return True

    # ------------------------------------------------------------------
    # Claude interaction
    # ------------------------------------------------------------------

    def _chat(self, user_message: str) -> str:
        """
        Send a user message to Claude (with current mode's system prompt),
        handle any tool calls, and return the final text response.
        """
        self.conversation_history.append({"role": "user", "content": user_message})
        system_prompt = _build_system_prompt(self.mode)

        while True:
            try:
                response = self.client.messages.create(
                    model="claude-opus-4-6",
                    max_tokens=1024,
                    system=system_prompt,
                    tools=TOOL_DEFINITIONS,
                    messages=self.conversation_history,
                )
            except anthropic.AuthenticationError as e:
                print("\n❌  API key rejected by Anthropic (401).")
                print(f"    Error: {e}")
                print("    Fix: open your .env file and replace ANTHROPIC_API_KEY")
                print("    with a fresh key from https://console.anthropic.com")
                print("    Then restart the agent.\n")
                return "__AUTH_ERROR__"
            except anthropic.RateLimitError as e:
                print(f"\n⚠  Rate limit hit: {e}")
                return "I'm a little busy right now — give me just a moment and try again."
            except anthropic.APIConnectionError as e:
                print(f"\n⚠  Network/connection error: {e}")
                traceback.print_exc()
                return "__CONNECTION_ERROR__"
            except Exception as e:
                print(f"\n⚠  Unexpected API error [{type(e).__name__}]: {e}")
                traceback.print_exc()
                return "Something went wrong on my end. Let me get a team member to help you."

            self.conversation_history.append(
                {"role": "assistant", "content": response.content}
            )

            if response.stop_reason == "end_turn":
                return next(
                    (block.text for block in response.content if block.type == "text"),
                    "",
                )

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        print(f"  ⚙  {block.name}({json.dumps(block.input, ensure_ascii=False)[:80]}…)")
                        result = execute_tool(block.name, block.input)
                        print(f"  ✓  {result[:100]}…" if len(result) > 100 else f"  ✓  {result}")
                        tool_results.append({
                            "type":        "tool_result",
                            "tool_use_id": block.id,
                            "content":     result,
                        })

                self.conversation_history.append(
                    {"role": "user", "content": tool_results}
                )
                continue

            return next(
                (block.text for block in response.content if block.type == "text"),
                "Something went wrong — let me get a team member to help you.",
            )

    # ------------------------------------------------------------------
    # Conversation lifecycle
    # ------------------------------------------------------------------

    def greet(self) -> None:
        """Play the opening greeting, tailored to current mode."""
        if self.mode == "visitor":
            greeting = (
                f"Welcome to {config.COMPANY_NAME}! "
                f"I'm {config.AGENT_NAME}, your virtual front desk assistant. "
                "How can I help you today?"
            )
        elif self.mode == "outreach":
            greeting = (
                f"Hi! This is {config.AGENT_NAME} calling from {config.COMPANY_NAME}. "
                "Is now a good time for a quick 2-minute chat?"
            )
        else:  # owner
            greeting = (
                f"Good morning, Naqiyah! I'm {config.AGENT_NAME}, ready for your standup. "
                "Want me to run through today's priorities, or is there something specific on your mind?"
            )
        self._say(greeting)

    def run_conversation(self) -> None:
        """Run a single conversation until it naturally closes."""
        self.conversation_history = []
        self.greet()

        no_input_count = 0

        while True:
            user_input = self._hear()

            if user_input is None:
                no_input_count += 1
                if no_input_count >= 2:
                    if self.mode == "outreach":
                        self._say("No problem — I'll try you again another time. Have a great day!")
                    else:
                        self._say(
                            "It looks like you may have stepped away. "
                            "Feel free to come back anytime. Have a wonderful day!"
                        )
                    break
                self._say("I didn't catch that — could you please repeat?")
                continue

            no_input_count = 0

            # Check for owner mode switch
            if self.mode != "owner":
                if self._check_mode_switch(user_input):
                    continue

            # Detect farewells — intentionally narrow so "yes", "thanks mid-chat" don't close
            lower    = user_input.lower().strip()
            farewells = {"bye", "goodbye", "that's all", "that's everything",
                         "exit", "quit", "see you", "see ya", "take care"}
            if any(f in lower for f in farewells):
                if self.mode == "visitor":
                    self._say(
                        "It was a pleasure! Please have a seat in the waiting area "
                        "and someone will be right with you. Have a wonderful visit!"
                    )
                elif self.mode == "outreach":
                    self._say(
                        "Thanks so much for your time! "
                        "I'll follow up with a quick email. Have a great day!"
                    )
                else:
                    self._say(
                        "Got it — go crush it today, Naqiyah! "
                        "I'll be here whenever you need me."
                    )
                break

            # Send to Claude
            response_text = self._chat(user_input)

            # Hard errors — exit gracefully instead of looping on the same failure
            if response_text == "__AUTH_ERROR__":
                self._say(
                    "I'm having an authentication issue and need to be restarted. "
                    "Please check the terminal for details."
                )
                break
            if response_text == "__CONNECTION_ERROR__":
                self._say(
                    "I can't reach the AI service right now — there may be a network issue. "
                    "Please check your connection and restart me."
                )
                break

            if response_text:
                self._say(response_text)

        # Save the conversation log
        _save_conversation(self.mode, self.conversation_history)

    def run_loop(self) -> None:
        """
        Main loop: handle conversations one after another.
        In visitor/outreach modes, resets between each one.
        In owner mode, runs a single session.
        """
        mode_labels = {
            "visitor":  "Visitor Mode  — greeting walk-ins",
            "outreach": "Outreach Mode — calling leads",
            "owner":    "Owner Mode    — Naqiyah's assistant",
        }
        io_label = "Text mode" if self.text_mode else "Voice mode"

        print(f"\n{'═'*62}")
        print(f"  {config.AGENT_NAME} — {config.COMPANY_NAME}")
        print(f"  {mode_labels.get(self.mode, self.mode)}")
        print(f"  {io_label} | Ctrl+C to exit")
        print(f"  Say '{config.OWNER_PASSPHRASE}' to switch to owner mode")
        print(f"{'═'*62}\n")

        try:
            while True:
                self.run_conversation()

                if self.mode == "owner":
                    # Owner mode = single session, then exit
                    break

                print("\n[Ready for next conversation…]\n")
                if self.text_mode:
                    nxt = input("Press Enter for next conversation (or type 'exit'): ").strip()
                    if nxt.lower() in ("exit", "quit"):
                        break

        except KeyboardInterrupt:
            print(f"\n\n{config.AGENT_NAME} shutting down. Goodbye!")
