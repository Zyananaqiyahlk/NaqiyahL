"""
Zara — Twilio phone webhook server.
Phase 1 of going live: inbound phone calls.

How it works:
  1. Someone calls your Twilio number.
  2. Twilio POSTs to /voice on this server.
  3. We greet them and <Gather> their spoken input.
  4. Twilio POSTs the transcript to /respond.
  5. We pass it to Zara (FrontDeskAssistant) and return her reply as TwiML <Say>.
  6. Repeat until the caller hangs up.

Per-call state (mode, conversation history) is kept in memory, keyed by Twilio's CallSid.

Run locally:
    python phone_server.py

Expose to the internet:
    ngrok http 5001

Point Twilio number → voice webhook → https://<ngrok-url>/voice
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv
from flask import Flask, request, Response, jsonify
from twilio.twiml.voice_response import VoiceResponse, Gather

import config
from assistant import FrontDeskAssistant, _save_conversation

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PORT                  = int(os.environ.get("PORT", 5001))
HOST                  = os.environ.get("HOST", "0.0.0.0")
OWNER_PHONE_NUMBER    = os.environ.get("OWNER_PHONE_NUMBER", "")  # your personal cell
DEFAULT_INBOUND_MODE  = os.environ.get("DEFAULT_INBOUND_MODE", "visitor")  # visitor | outreach | owner
RAILWAY_PUBLIC_DOMAIN = os.environ.get("RAILWAY_PUBLIC_DOMAIN", f"http://localhost:{PORT}")
API_SECRET            = os.environ.get("API_SECRET", "")  # set this on Railway for REST API auth
TWILIO_ACCOUNT_SID    = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN     = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER    = os.environ.get("TWILIO_FROM_NUMBER", "")  # your Twilio phone number

# Twilio voice that reads Zara's replies.
TTS_VOICE             = os.environ.get("TWILIO_TTS_VOICE", "Polly.Joanna-Neural")

# ---------------------------------------------------------------------------
# In-memory call state
# ---------------------------------------------------------------------------
# Maps Twilio CallSid → FrontDeskAssistant instance
# This is fine for a single-server deployment. For multi-worker, use Redis.
# ---------------------------------------------------------------------------

CALL_SESSIONS: Dict[str, FrontDeskAssistant] = {}

TRANSCRIPTS_DIR = Path(__file__).parent / "data" / "call_transcripts"
TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)


def _get_or_create_session(call_sid: str, from_number: str) -> FrontDeskAssistant:
    """
    Fetch an existing session for this call, or create one.
    If the caller's number matches OWNER_PHONE_NUMBER, they get OWNER mode.
    Otherwise they get DEFAULT_INBOUND_MODE (visitor by default).
    """
    if call_sid in CALL_SESSIONS:
        return CALL_SESSIONS[call_sid]

    # Route by caller ID
    if OWNER_PHONE_NUMBER and from_number.endswith(OWNER_PHONE_NUMBER.lstrip("+")):
        mode = "owner"
        print(f"📞  Incoming call from OWNER ({from_number}) → owner mode")
    else:
        mode = DEFAULT_INBOUND_MODE
        print(f"📞  Incoming call from {from_number} → {mode} mode")

    session = FrontDeskAssistant(text_mode=True, mode=mode)
    CALL_SESSIONS[call_sid] = session
    return session


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__)


@app.route("/", methods=["GET"])
def health() -> Response:
    return Response(
        f"Zara phone server up. Mode: {DEFAULT_INBOUND_MODE}. Time: {datetime.now().isoformat()}",
        mimetype="text/plain",
    )


@app.route("/voice", methods=["POST"])
def voice() -> Response:
    """First hit when a call comes in. Greet and start listening."""
    call_sid    = request.values.get("CallSid", "")
    from_number = request.values.get("From", "")

    session = _get_or_create_session(call_sid, from_number)

    # Pick greeting based on mode
    if session.mode == "owner":
        greeting = (
            f"Hi Naqiyah, it's {config.AGENT_NAME}. I'm here. "
            "Want your standup, a pipeline snapshot, or something else?"
        )
    elif session.mode == "outreach":
        greeting = (
            f"Hi, this is {config.AGENT_NAME} calling from {config.COMPANY_NAME}. "
            "Did I catch you at an okay moment?"
        )
    else:
        greeting = (
            f"Thanks for calling {config.COMPANY_NAME}. "
            f"This is {config.AGENT_NAME}, how can I help you today?"
        )

    resp   = VoiceResponse()
    gather = Gather(
        input="speech",
        action="/respond",
        method="POST",
        speech_timeout="auto",
        language="en-US",
        speech_model="phone_call",
    )
    gather.say(greeting, voice=TTS_VOICE)
    resp.append(gather)

    # If they don't say anything, prompt again
    resp.redirect("/voice_retry", method="POST")
    return Response(str(resp), mimetype="application/xml")


@app.route("/voice_retry", methods=["POST"])
def voice_retry() -> Response:
    resp   = VoiceResponse()
    gather = Gather(
        input="speech",
        action="/respond",
        method="POST",
        speech_timeout="auto",
        language="en-US",
        speech_model="phone_call",
    )
    gather.say("I didn't catch that — could you repeat?", voice=TTS_VOICE)
    resp.append(gather)
    resp.say("Sounds like you might've stepped away. Call back anytime!", voice=TTS_VOICE)
    resp.hangup()
    return Response(str(resp), mimetype="application/xml")


@app.route("/respond", methods=["POST"])
def respond() -> Response:
    """Handle a transcribed speech turn from the caller."""
    call_sid    = request.values.get("CallSid", "")
    from_number = request.values.get("From", "")
    speech      = (request.values.get("SpeechResult") or "").strip()

    session = _get_or_create_session(call_sid, from_number)

    if not speech:
        resp = VoiceResponse()
        resp.redirect("/voice_retry", method="POST")
        return Response(str(resp), mimetype="application/xml")

    print(f"  👤  [{session.mode}] {speech}")

    # Check for farewell
    lower = speech.lower().strip()
    farewells = {"bye", "goodbye", "that's all", "that's everything",
                 "talk later", "take care", "thanks bye", "have a good one"}
    if any(f in lower for f in farewells):
        resp = VoiceResponse()
        if session.mode == "owner":
            resp.say("Go crush it today, Naqiyah. I'm here when you need me.",
                     voice=TTS_VOICE)
        elif session.mode == "outreach":
            resp.say("Thanks for your time — I'll follow up by email. Have a great day!",
                     voice=TTS_VOICE)
        else:
            resp.say("It was a pleasure. Have a wonderful day!", voice=TTS_VOICE)
        resp.hangup()
        _finalize_call(call_sid)
        return Response(str(resp), mimetype="application/xml")

    # Check for owner-mode hotword mid-call (same as CLI)
    if session.mode != "owner" and session._check_mode_switch(speech):
        # _check_mode_switch already called _say → no-op in text_mode
        resp   = VoiceResponse()
        gather = Gather(
            input="speech", action="/respond", method="POST",
            speech_timeout="auto", language="en-US", speech_model="phone_call",
        )
        gather.say("Owner mode on. What do you need?", voice=TTS_VOICE)
        resp.append(gather)
        resp.redirect("/voice_retry", method="POST")
        return Response(str(resp), mimetype="application/xml")

    # Hand off to Zara's brain (CLAUDE.md + tools + mode)
    try:
        reply = session._chat(speech)
    except Exception as e:
        print(f"  ❌  Chat error: {e}")
        reply = "Something went sideways on my end — can a human call you back?"

    print(f"  🤖  [{session.mode}] {reply}")

    resp   = VoiceResponse()
    gather = Gather(
        input="speech", action="/respond", method="POST",
        speech_timeout="auto", language="en-US", speech_model="phone_call",
    )
    gather.say(reply, voice=TTS_VOICE)
    resp.append(gather)
    resp.redirect("/voice_retry", method="POST")

    return Response(str(resp), mimetype="application/xml")


@app.route("/status", methods=["POST"])
def status() -> Response:
    """Twilio status callback — fires when call ends. Cleans up + saves transcript."""
    call_sid     = request.values.get("CallSid", "")
    call_status  = request.values.get("CallStatus", "")
    print(f"📴  Call {call_sid} → {call_status}")
    if call_status in ("completed", "failed", "busy", "no-answer", "canceled"):
        _finalize_call(call_sid)
    return Response("", mimetype="text/plain")


def _finalize_call(call_sid: str) -> None:
    """Save transcript and evict session from memory."""
    session = CALL_SESSIONS.pop(call_sid, None)
    if session and session.conversation_history:
        _save_conversation(f"phone_{session.mode}", session.conversation_history)


# ===========================================================================
# BROWSER SIMULATOR — test Zara without burning Twilio credits
# ===========================================================================
# Access at:  http://localhost:5001/sim
# Or over ngrok: https://<your-ngrok>.ngrok-free.dev/sim
#
# Runs the same FrontDeskAssistant brain (CLAUDE.md + tools + modes) but in a
# text chat UI instead of a phone call. Perfect for:
#   • End-to-end testing of inbound + outbound flows
#   • Screen-sharing a live Zara demo to a sales prospect
#   • Iterating on Zara's responses without Twilio round-trips
# ===========================================================================

SIM_SESSIONS: Dict[str, FrontDeskAssistant] = {}


@app.route("/sim", methods=["GET"])
def sim_page() -> Response:
    """Serve the simulator UI."""
    return Response(_SIM_HTML, mimetype="text/html")


@app.route("/sim/chat", methods=["POST"])
def sim_chat() -> Response:
    """Send a user message to Zara and return her reply + any tool calls made."""
    data       = request.get_json(silent=True) or {}
    session_id = data.get("session_id", "default")
    mode       = data.get("mode", "visitor")
    message    = (data.get("message") or "").strip()

    if not message:
        return jsonify({"error": "message required"}), 400

    # Get or create the session
    key = f"{session_id}_{mode}"
    if key not in SIM_SESSIONS:
        SIM_SESSIONS[key] = FrontDeskAssistant(text_mode=True, mode=mode)
    session = SIM_SESSIONS[key]

    # Track tool calls for this turn.
    # IMPORTANT: patch at the `assistant` module level — that's where _chat() resolves
    # execute_tool from. Patching `tools.execute_tool` alone doesn't work because
    # assistant.py already has a direct reference bound at import time.
    tool_calls_made: list[dict] = []

    import assistant as _assistant_module
    import tools     as _tools_module
    from tools import execute_tool as _orig_execute

    def _tracking_execute(name: str, tool_input: dict) -> str:
        result = _orig_execute(name, tool_input)
        tool_calls_made.append({
            "name":   name,
            "input":  tool_input,
            "result": result[:300] + ("…" if len(result) > 300 else ""),
        })
        return result

    # Patch both the tools module AND assistant's local reference
    _tools_module.execute_tool    = _tracking_execute
    _assistant_module.execute_tool = _tracking_execute

    try:
        reply = session._chat(message)
    except Exception as e:
        return jsonify({
            "error":      str(e),
            "error_type": type(e).__name__,
        }), 500
    finally:
        # Always restore — even if _chat raises
        _tools_module.execute_tool    = _orig_execute
        _assistant_module.execute_tool = _orig_execute

    return jsonify({
        "reply":      reply,
        "mode":       session.mode,
        "tool_calls": tool_calls_made,
        "turn_count": len([m for m in session.conversation_history if m["role"] == "user"]),
    })


@app.route("/sim/reset", methods=["POST"])
def sim_reset() -> Response:
    """Clear a simulator session so the next message starts fresh."""
    data       = request.get_json(silent=True) or {}
    session_id = data.get("session_id", "default")
    mode       = data.get("mode", "visitor")
    key        = f"{session_id}_{mode}"
    SIM_SESSIONS.pop(key, None)
    return jsonify({"ok": True})


@app.route("/sim/greet", methods=["POST"])
def sim_greet() -> Response:
    """
    Return Zara's opening line for the selected mode.
    For outbound (outreach), Zara speaks FIRST — this simulates her placing the call.
    For inbound (visitor/owner), she greets and waits for the user.
    """
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "visitor")

    if mode == "outreach":
        opener = (
            f"Hi, this is {config.AGENT_NAME} calling from {config.COMPANY_NAME}. "
            "I know I'm catching you cold — do you have 2 minutes?"
        )
    elif mode == "owner":
        opener = (
            f"Hi Naqiyah, {config.AGENT_NAME} here. "
            "Want your standup, a pipeline snapshot, or something else?"
        )
    else:
        opener = (
            f"Thanks for calling {config.COMPANY_NAME}! "
            f"This is {config.AGENT_NAME} at the front desk — how can I help?"
        )

    return jsonify({"greeting": opener})


# ---------------------------------------------------------------------------
# Simulator HTML — self-contained, no build step
# ---------------------------------------------------------------------------

_SIM_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Zara Simulator — Zyana Systems</title>
<style>
  :root {
    --bg:#0a0a0b; --panel:#14141a; --border:#23232d;
    --text:#e8e8ec; --muted:#8a8a95; --accent:#c9a961;
    --zara:#1b1f2a; --user:#1e2b1f; --tool:#2a1f2b;
  }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
         background:var(--bg); color:var(--text); min-height:100vh; }
  header { padding:20px 28px; border-bottom:1px solid var(--border);
           display:flex; align-items:center; justify-content:space-between; }
  header h1 { font-size:17px; font-weight:500; letter-spacing:.3px; }
  header h1 span { color:var(--accent); font-weight:600; }
  .modes { display:flex; gap:8px; }
  .mode-btn { padding:7px 14px; background:transparent; border:1px solid var(--border);
              color:var(--muted); border-radius:6px; cursor:pointer; font:inherit;
              transition:all .15s; }
  .mode-btn:hover { border-color:var(--accent); color:var(--text); }
  .mode-btn.active { background:var(--accent); color:#0a0a0b; border-color:var(--accent); }
  main { max-width:900px; margin:0 auto; padding:24px; display:grid;
         grid-template-columns:1fr; gap:20px; }
  .scenarios { display:flex; gap:10px; flex-wrap:wrap; }
  .scen-btn { padding:8px 14px; background:var(--panel); border:1px solid var(--border);
              color:var(--muted); border-radius:6px; cursor:pointer; font:12px inherit;
              transition:all .15s; }
  .scen-btn:hover { color:var(--text); border-color:var(--accent); }
  #transcript { background:var(--panel); border:1px solid var(--border); border-radius:10px;
                padding:16px; min-height:400px; max-height:60vh; overflow-y:auto; }
  .msg { margin-bottom:14px; padding:10px 14px; border-radius:8px; white-space:pre-wrap;
         animation:fade .2s ease; }
  @keyframes fade { from {opacity:0; transform:translateY(4px);} to {opacity:1;} }
  .msg.zara { background:var(--zara); border-left:3px solid var(--accent); }
  .msg.user { background:var(--user); border-left:3px solid #4a8a4a; margin-left:40px; }
  .msg.tool { background:var(--tool); border-left:3px solid #9a6ac4; font:12px/1.5 "SF Mono",Menlo,monospace;
              color:var(--muted); }
  .msg-label { font-size:11px; text-transform:uppercase; letter-spacing:.8px;
               color:var(--muted); margin-bottom:4px; }
  .msg.user .msg-label { color:#7acc7a; }
  .msg.zara .msg-label { color:var(--accent); }
  .input-row { display:flex; gap:10px; }
  #msg-input { flex:1; padding:12px 14px; background:var(--panel); border:1px solid var(--border);
               color:var(--text); border-radius:8px; font:inherit; outline:none; }
  #msg-input:focus { border-color:var(--accent); }
  button.send { padding:12px 22px; background:var(--accent); border:none; color:#0a0a0b;
                font-weight:600; border-radius:8px; cursor:pointer; }
  button.send:disabled { opacity:.4; cursor:not-allowed; }
  button.reset { padding:12px 14px; background:transparent; border:1px solid var(--border);
                 color:var(--muted); border-radius:8px; cursor:pointer; font:inherit; }
  .status { font-size:12px; color:var(--muted); padding:4px 0; min-height:18px; }
  .empty { color:var(--muted); text-align:center; padding:60px 20px; font-style:italic; }
</style>
</head>
<body>
<header>
  <h1><span>Zara</span> Live Simulator — Zyana Systems</h1>
  <div class="modes">
    <button class="mode-btn active" data-mode="visitor">📞 Inbound Visitor</button>
    <button class="mode-btn" data-mode="outreach">📤 Outbound Call</button>
    <button class="mode-btn" data-mode="owner">👑 Owner (You)</button>
  </div>
</header>

<main>
  <div class="scenarios">
    <button class="scen-btn" data-scenario="visitor-walkin">Scenario: Walk-in asking about services</button>
    <button class="scen-btn" data-scenario="outreach-salon">Scenario: Cold call to salon owner</button>
    <button class="scen-btn" data-scenario="owner-standup">Scenario: Your morning standup</button>
  </div>

  <div id="transcript">
    <div class="empty">Pick a mode above or click a scenario to start.<br>
    Zara uses the same CLAUDE.md brain as your phone agent.</div>
  </div>

  <div class="status" id="status"></div>

  <div class="input-row">
    <input id="msg-input" placeholder="Type what the caller says… (Enter to send)" autofocus />
    <button class="send" id="send-btn">Send</button>
    <button class="reset" id="reset-btn" title="Clear conversation">↻ Reset</button>
  </div>
</main>

<script>
const SESSION_ID = 'browser_' + Math.random().toString(36).slice(2,10);
let currentMode = 'visitor';
let busy = false;

const $transcript = document.getElementById('transcript');
const $input      = document.getElementById('msg-input');
const $send       = document.getElementById('send-btn');
const $reset      = document.getElementById('reset-btn');
const $status     = document.getElementById('status');

function clearTranscript() {
  $transcript.innerHTML = '';
}

function addMsg(role, text) {
  if ($transcript.querySelector('.empty')) $transcript.innerHTML = '';
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  const label = role === 'zara' ? 'Zara' : role === 'user' ? 'Caller (you)' : 'Tool call';
  div.innerHTML = `<div class="msg-label">${label}</div>${escapeHTML(text)}`;
  $transcript.appendChild(div);
  $transcript.scrollTop = $transcript.scrollHeight;
}

function escapeHTML(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[c]));
}

async function sendMessage(text) {
  if (busy || !text.trim()) return;
  busy = true;
  $send.disabled = true;
  addMsg('user', text);
  $input.value = '';
  $status.textContent = 'Zara is thinking…';

  try {
    const res = await fetch('/sim/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: SESSION_ID, mode: currentMode, message: text }),
    });
    const data = await res.json();
    if (data.error) {
      addMsg('tool', '⚠ Error: ' + data.error + ' (' + (data.error_type||'') + ')');
    } else {
      (data.tool_calls || []).forEach(tc => {
        addMsg('tool', `⚙ ${tc.name}(${JSON.stringify(tc.input)})\\n→ ${tc.result}`);
      });
      addMsg('zara', data.reply);
      // Handle mode auto-switch (owner passphrase triggers this)
      if (data.mode && data.mode !== currentMode) {
        currentMode = data.mode;
        document.querySelectorAll('.mode-btn').forEach(b => {
          b.classList.toggle('active', b.dataset.mode === currentMode);
        });
        $status.textContent = 'Mode switched to: ' + currentMode;
        return;
      }
    }
  } catch (e) {
    addMsg('tool', '⚠ Network error: ' + e.message);
  } finally {
    busy = false;
    $send.disabled = false;
    $status.textContent = '';
    $input.focus();
  }
}

async function greet() {
  const res = await fetch('/sim/greet', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode: currentMode }),
  });
  const data = await res.json();
  addMsg('zara', data.greeting);
}

async function resetSession(silent=false) {
  await fetch('/sim/reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: SESSION_ID, mode: currentMode }),
  });
  clearTranscript();
  if (!silent) await greet();
}

// Mode buttons
document.querySelectorAll('.mode-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    if (btn.dataset.mode === currentMode) return;
    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentMode = btn.dataset.mode;
    await resetSession();
  });
});

// Scripted scenarios
const SCENARIOS = {
  'visitor-walkin': {
    mode: 'visitor',
    firstMessage: "Hi, I walked in because I saw your sign. I run a dental clinic and I'm curious what kind of AI automation Zyana does — especially for handling patient calls."
  },
  'outreach-salon': {
    mode: 'outreach',
    firstMessage: "Oh hey — sure, I've got a minute. I run a small hair salon. What is this about?"
  },
  'owner-standup': {
    mode: 'owner',
    firstMessage: "Good morning Zara. Run my standup and tell me what I should prioritize today to hit the 10k goal."
  }
};

document.querySelectorAll('.scen-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    const s = SCENARIOS[btn.dataset.scenario];
    if (!s) return;
    currentMode = s.mode;
    document.querySelectorAll('.mode-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.mode === currentMode);
    });
    await resetSession(true);      // clear without auto-greet (we greet manually for outbound flow)
    if (currentMode !== 'outreach') {
      await greet();                // visitor/owner — Zara speaks first
    }
    await new Promise(r => setTimeout(r, 300));
    await sendMessage(s.firstMessage);
  });
});

// Enter to send
$input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage($input.value);
  }
});
$send.addEventListener('click', () => sendMessage($input.value));
$reset.addEventListener('click', () => resetSession());

// Initial greeting
greet();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

# ===========================================================================
# TWILIO OUTBOUND — Zara dials a prospect
# ===========================================================================

@app.route("/outbound", methods=["POST"])
def outbound_call() -> Response:
    """
    Tell Zara to call a prospect via Twilio.

    POST body (JSON):
      {
        "phone_number":  "+14165551234",  required
        "prospect_name": "Jane Smith",    optional — logged for context
        "company":       "Smith Dental",  optional
        "api_key":       "your-secret"    required if API_SECRET is set in env
      }

    Flow:
      1. Twilio places the call from your TWILIO_FROM_NUMBER
      2. When the prospect answers, Twilio hits /voice?mode=outreach
      3. Zara runs the outreach conversation (qualify → book discovery call)
      4. Transcript saved to data/conversations/ when call ends
    """
    data   = request.get_json(silent=True) or {}
    secret = data.get("api_key", "")

    if API_SECRET and secret != API_SECRET:
        return jsonify({"error": "Unauthorized — provide api_key in body"}), 401

    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_FROM_NUMBER:
        return jsonify({
            "error": (
                "Twilio not fully configured. "
                "Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_FROM_NUMBER in your environment."
            )
        }), 500

    phone = data.get("phone_number", "").strip()
    if not phone:
        return jsonify({"error": "phone_number is required"}), 400

    prospect = data.get("prospect_name", "")
    company  = data.get("company", "")
    print(f"📞  Dialling {prospect or phone} ({company}) → outreach mode")

    try:
        from twilio.rest import Client as TwilioClient
        client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        call   = client.calls.create(
            to              = phone,
            from_           = TWILIO_FROM_NUMBER,
            url             = f"{RAILWAY_PUBLIC_DOMAIN}/voice?mode=outreach",
            status_callback = f"{RAILWAY_PUBLIC_DOMAIN}/status",
            status_callback_method = "POST",
        )
        print(f"✅  Call initiated — SID: {call.sid}")
        return jsonify({"ok": True, "call_sid": call.sid, "to": phone, "status": call.status})
    except Exception as e:
        print(f"❌  Twilio outbound error: {e}")
        return jsonify({"error": str(e)}), 500


# ===========================================================================
# REST API — trigger Zara from Make.com / Zapier / external systems
# ===========================================================================

def _require_auth(req) -> Optional[Response]:
    """Return 401 response if API_SECRET is set and the request doesn't match."""
    if not API_SECRET:
        return None
    provided = (
        req.headers.get("X-API-Key", "")
        or (req.get_json(silent=True) or {}).get("api_key", "")
    )
    if provided != API_SECRET:
        return jsonify({"error": "Unauthorized — set X-API-Key header or api_key in body"}), 401
    return None


@app.route("/api/chat", methods=["POST"])
def api_chat() -> Response:
    """
    Send a message to Zara and get her reply.
    Use this from Make.com, Zapier, or any webhook source.

    POST body:
      { "message": "...", "mode": "visitor|outreach|owner", "session_id": "...", "api_key": "..." }
    """
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    data       = request.get_json(silent=True) or {}
    session_id = data.get("session_id", "api_default")
    mode       = data.get("mode", "visitor")
    message    = (data.get("message") or "").strip()

    if not message:
        return jsonify({"error": "message is required"}), 400

    key = f"api_{session_id}_{mode}"
    if key not in SIM_SESSIONS:
        SIM_SESSIONS[key] = FrontDeskAssistant(text_mode=True, mode=mode)
    session = SIM_SESSIONS[key]

    try:
        reply = session._chat(message)
    except Exception as e:
        return jsonify({"error": str(e), "type": type(e).__name__}), 500

    return jsonify({
        "reply":      reply,
        "mode":       session.mode,
        "session_id": session_id,
        "turns":      len([m for m in session.conversation_history if m["role"] == "user"]),
    })


@app.route("/api/leads", methods=["GET"])
def api_leads() -> Response:
    """Return all captured leads as JSON. Use for syncing to a CRM or spreadsheet."""
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    from tools import _load, LEADS_FILE
    leads = _load(LEADS_FILE)
    return jsonify({"count": len(leads), "leads": leads})


@app.route("/api/pipeline", methods=["GET"])
def api_pipeline() -> Response:
    """
    Return a complete snapshot of all data Zara has saved — across ALL modes
    (browser sim, CLI, phone calls). No auth required for easy checking.
    """
    from tools import _load, LEADS_FILE, VISITORS_FILE, APPOINTMENTS_FILE, MESSAGES_FILE
    leads   = _load(LEADS_FILE)
    visitors = _load(VISITORS_FILE)
    appts   = _load(APPOINTMENTS_FILE)
    messages = _load(MESSAGES_FILE)
    return jsonify({
        "summary": {
            "leads":        len(leads),
            "visitors":     len(visitors),
            "appointments": len(appts),
            "messages":     len(messages),
        },
        "leads":        leads,
        "visitors":     visitors,
        "appointments": appts,
        "messages":     messages,
    })


@app.route("/api/standup", methods=["GET"])
def api_standup() -> Response:
    """Return today's standup priorities — pipe this to Slack, email, or Notion."""
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    from tools import get_daily_standup
    return jsonify({"standup": get_daily_standup()})


@app.route("/api/apollo/search", methods=["POST"])
def api_apollo_search() -> Response:
    """
    Trigger an Apollo lead search via REST.

    POST body:
      { "industry": "dental", "title": "owner", "location": "Toronto", "limit": 10, "api_key": "..." }
    """
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    from tools import search_apollo_leads
    data   = request.get_json(silent=True) or {}
    result = search_apollo_leads(
        industry = data.get("industry", ""),
        title    = data.get("title", ""),
        location = data.get("location", ""),
        limit    = int(data.get("limit", 10)),
    )
    return jsonify({"result": result})


@app.route("/api/apollo/enrich", methods=["POST"])
def api_apollo_enrich() -> Response:
    """
    Enrich a lead via Apollo.

    POST body:
      { "name": "Jane Smith", "email": "jane@example.com", "company": "Smith Dental", "api_key": "..." }
    """
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    from tools import enrich_lead_apollo
    data   = request.get_json(silent=True) or {}
    name   = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    result = enrich_lead_apollo(
        name    = name,
        email   = data.get("email", ""),
        company = data.get("company", ""),
    )
    return jsonify({"result": result})


if __name__ == "__main__":
    print("=" * 62)
    print(f"  {config.AGENT_NAME} — Phone Server (Phase 1)")
    print(f"  Default inbound mode: {DEFAULT_INBOUND_MODE}")
    print(f"  Owner number (routes to owner mode): {OWNER_PHONE_NUMBER or '— not set —'}")
    print(f"  Listening on http://{HOST}:{PORT}")
    print(f"  Expose with: ngrok http {PORT}")
    print("=" * 62)
    app.run(host=HOST, port=PORT, debug=False)
