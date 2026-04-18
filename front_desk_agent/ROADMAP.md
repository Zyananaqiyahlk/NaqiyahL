# Zara — Live Deployment Roadmap

**Goal:** Zara operates as a 24/7 business machine driving Zyana Systems to $10k/month.
**Model:** Phone-first (Twilio) + Split autonomy + Apollo/Hunter/LinkedIn for lead firepower.

---

## Phase 1 — Inbound Phone (build now, ship this week)

**What you get:** A real phone number. Anyone calls → Zara answers in the right mode → handles the conversation using CLAUDE.md + her tools → logs everything.

**Deliverables in this repo:**
- [x] `phone_server.py` — Flask webhook server that Twilio talks to
- [x] `requirements.txt` updated with `flask` + `twilio`
- [x] `.env.example` updated with Twilio vars
- [x] Wired to existing `assistant.py` — same brain, same tools, same CLAUDE.md

**What you do (one-time setup, ~30 min):**
1. Create a Twilio account → buy a number (~$1/mo). [twilio.com/console](https://console.twilio.com)
2. Install new deps: `pip install -r requirements.txt`
3. Copy `.env.example` → `.env`, fill in `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`
4. Run locally: `python phone_server.py`
5. Expose to internet with ngrok: `ngrok http 5001`
6. In Twilio console → your number → "A call comes in" → Webhook → paste `https://<your-ngrok>.ngrok-free.app/voice`
7. Call your Twilio number. Zara answers.

**Production deployment (after testing):** Railway, Render, or Fly.io. One-click deploy, swap ngrok URL for the public one.

---

## Phase 2 — Outbound Calling + Split Autonomy (week 2)

Zara makes outbound calls. Split-autonomy rules:

| Scenario | Behavior |
|---|---|
| Generic cold lead (no name match in CRM) | Auto-call during business hours |
| Named target (Fortune 500, key prospect, marked "VIP" in leads.json) | SMS Naqiyah first — needs "yes" to proceed |
| Follow-up on existing conversation | Auto |
| Pricing / proposal discussion | Auto-book meeting, don't quote numbers |
| Discovery call booking | Auto |
| Commitments > $1k | Escalate immediately |

**New tools:**
- `call_lead(phone, goal)` — places outbound call
- `request_approval(reason, target)` — SMS to Naqiyah, waits for yes/no
- `schedule_call_for_later(lead_id, time)` — queue for off-hours

---

## Phase 3 — Apollo + Hunter + LinkedIn (week 3)

Zara fills her own pipeline.

- **Apollo API:** `find_leads(industry, title, company_size)` → returns 25 enriched contacts
- **Hunter API:** `find_email(domain, name)` → returns verified email
- **LinkedIn:** Sales Nav search via Phantombuster or similar (hardest — defer if time-crunched)

Daily automation: Zara runs at 7am, pulls 25 fresh leads, drafts personalized openers, starts calling at 9am local time.

---

## Phase 4 — Proactive Daemon (week 4+)

Zara initiates, not just responds.

- **7:30am:** Zara calls *you*, runs your standup, confirms priorities
- **12:30pm:** SMS check-in — "3 hot leads need follow-up today"
- **6:00pm:** EOD call — wins, blockers, tomorrow's plan
- **Real-time:** Gmail webhook → if a hot lead replies, Zara calls you within 2 minutes

---

## Budget for Phase 1

| Item | Cost |
|---|---|
| Twilio phone number | ~$1.15/mo |
| Twilio voice (inbound) | ~$0.013/min |
| Twilio voice (outbound US) | ~$0.022/min |
| ElevenLabs (already using) | existing |
| Anthropic API (already using) | existing |
| Hosting (Railway free tier) | $0 while testing |

**Running 20 outbound calls/day × 3 min × 30 days ≈ $40/mo.** Well inside the $10k math.

---

## Success criteria for "she's live"

- [ ] Phone number live, Zara answers 100% of calls
- [ ] Call transcripts auto-saved to `data/conversations/`
- [ ] Leads captured from calls auto-flow into `leads.json`
- [ ] At least 1 real discovery call booked via phone
- [ ] You can call her from anywhere and run a standup

When all 5 ✓ → Phase 1 done → move to Phase 2.
