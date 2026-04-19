"""
Voice I/O layer — microphone input (STT) and speaker output (TTS).

TTS priority: Edge TTS (free, neural quality) → gTTS (online) → pyttsx3 (offline).
STT:          Google Speech Recognition → offline Sphinx fallback.

Edge TTS uses Microsoft's neural voices — same engine behind Windows 11 and
Microsoft products. No API key, no account, no cost. Quality is close to ElevenLabs.
"""

import asyncio
import os
import tempfile
from typing import Optional

import speech_recognition as sr

import config

# Best Canadian/North American English voices from Edge TTS
# Full list: run `edge-tts --list-voices` in your terminal
EDGE_TTS_VOICE = os.getenv("EDGE_TTS_VOICE", "en-CA-ClaraNeural")  # warm, professional female


# ---------------------------------------------------------------------------
# Text-to-Speech — public entry point
# ---------------------------------------------------------------------------

def speak(text: str) -> None:
    """Convert text to speech and play it aloud. Always prints text too."""
    print(f"\n[{config.AGENT_NAME}]: {text}\n")

    success = _speak_edge(text)
    if not success:
        success = _speak_gtts(text)
    if not success:
        _speak_pyttsx3(text)


# ---------------------------------------------------------------------------
# Edge TTS — free neural voices, no API key required
# ---------------------------------------------------------------------------

def _speak_edge(text: str) -> bool:
    """
    Use Microsoft Edge TTS (edge-tts package) for high-quality neural speech.
    Free, no account needed. Falls back gracefully if not installed.

    Install: pip install edge-tts
    List voices: edge-tts --list-voices
    Good voices for Zara:
      en-CA-ClaraNeural    — Canadian English, warm female (default)
      en-US-JennyNeural    — US English, conversational female
      en-GB-SoniaNeural    — British English, professional female
      en-AU-NatashaNeural  — Australian English, friendly female
    """
    try:
        import edge_tts
        import pygame

        async def _synthesise():
            communicate = edge_tts.Communicate(text, EDGE_TTS_VOICE)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = tmp.name
            await communicate.save(tmp_path)
            return tmp_path

        # Run the async call synchronously
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            tmp_path = loop.run_until_complete(_synthesise())
        except RuntimeError:
            # If there's already a running loop (e.g. inside async context)
            tmp_path = asyncio.run(_synthesise())

        pygame.mixer.init()
        pygame.mixer.music.load(tmp_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.music.unload()
        os.unlink(tmp_path)
        return True

    except ImportError:
        # edge-tts not installed — silent fallback
        return False
    except Exception as exc:
        print(f"[Edge TTS error]: {exc} — falling back to gTTS")
        return False


# ---------------------------------------------------------------------------
# gTTS — good quality, requires internet
# ---------------------------------------------------------------------------

def _speak_gtts(text: str) -> bool:
    """Use gTTS (Google Text-to-Speech) + pygame. Returns True on success."""
    try:
        from gtts import gTTS
        import pygame

        tts = gTTS(text=text, lang=config.TTS_LANGUAGE, slow=config.TTS_SLOW)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
            tts.save(tmp_path)

        pygame.mixer.init()
        pygame.mixer.music.load(tmp_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.music.unload()
        os.unlink(tmp_path)
        return True

    except ImportError:
        return False
    except Exception as exc:
        print(f"[gTTS error]: {exc} — falling back to pyttsx3")
        return False


# ---------------------------------------------------------------------------
# pyttsx3 — fully offline fallback, no internet required
# ---------------------------------------------------------------------------

def _speak_pyttsx3(text: str) -> None:
    """Offline TTS using pyttsx3. Robotic but works everywhere."""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 165)
        engine.setProperty("volume", 1.0)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    except Exception as exc:
        print(f"[pyttsx3 error]: {exc} — text-only mode.")


# ---------------------------------------------------------------------------
# Speech-to-Text
# ---------------------------------------------------------------------------

def listen(prompt: Optional[str] = None) -> Optional[str]:
    """
    Listen via the microphone and return the transcribed text.
    Returns None if nothing was heard or recognition failed.
    """
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = config.MIC_ENERGY_THRESHOLD
    recognizer.pause_threshold  = config.MIC_PAUSE_THRESHOLD

    if prompt:
        print(f"[Listening for: {prompt}]")

    with sr.Microphone() as source:
        print("[Adjusting for ambient noise…]")
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        print("[Listening… speak now]")
        try:
            audio = recognizer.listen(
                source,
                phrase_time_limit=config.MIC_PHRASE_TIME_LIMIT,
            )
        except sr.WaitTimeoutError:
            return None

    print("[Processing speech…]")
    try:
        if config.USE_GOOGLE_SPEECH:
            text = recognizer.recognize_google(audio)
        else:
            text = recognizer.recognize_sphinx(audio)
        print(f"[You said]: {text}")
        return text
    except sr.UnknownValueError:
        return None
    except sr.RequestError as exc:
        print(f"[Speech recognition error]: {exc}")
        return None


def listen_with_retry(prompt: Optional[str] = None, max_attempts: int = 3) -> Optional[str]:
    """Keep listening until we get something or exhaust retries."""
    for attempt in range(max_attempts):
        result = listen(prompt)
        if result:
            return result
        if attempt < max_attempts - 1:
            speak("I didn't catch that — could you please repeat?")
    return None
