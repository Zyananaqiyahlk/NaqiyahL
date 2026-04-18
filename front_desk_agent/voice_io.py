"""
Voice I/O layer — microphone input (STT) and speaker output (TTS).

TTS priority: ElevenLabs (natural, expressive) → gTTS (online) → pyttsx3 (offline).
STT:          Google Speech Recognition → offline Sphinx fallback.
"""

import os
import sys
import tempfile
from typing import Optional

import speech_recognition as sr

import config

# ---------------------------------------------------------------------------
# Text-to-Speech — public entry point
# ---------------------------------------------------------------------------

def speak(text: str) -> None:
    """Convert text to speech and play it aloud. Always prints text too."""
    print(f"\n[{config.AGENT_NAME}]: {text}\n")

    engine = config.TTS_ENGINE.lower()
    if engine == "elevenlabs":
        success = _speak_elevenlabs(text)
        if not success:
            _speak_gtts(text)
    elif engine == "gtts":
        _speak_gtts(text)
    else:
        _speak_pyttsx3(text)


# ---------------------------------------------------------------------------
# ElevenLabs TTS — best voice quality, requires API key
# ---------------------------------------------------------------------------

def _speak_elevenlabs(text: str) -> bool:
    """
    Stream audio from ElevenLabs and play it via pygame.
    Returns True on success, False on any error (caller will fall back to gTTS).
    Set ELEVENLABS_API_KEY in your .env file.
    """
    api_key = os.getenv("ELEVENLABS_API_KEY", "")
    if not api_key:
        return False

    try:
        import requests
        import pygame

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{config.ELEVENLABS_VOICE_ID}/stream"
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": config.ELEVENLABS_MODEL,
            "voice_settings": {
                "stability": config.ELEVENLABS_STABILITY,
                "similarity_boost": config.ELEVENLABS_SIMILARITY,
            },
        }

        response = requests.post(url, headers=headers, json=payload, stream=True, timeout=15)
        if response.status_code != 200:
            print(f"[ElevenLabs error]: HTTP {response.status_code}")
            return False

        # Write streamed audio to a temp file and play with pygame
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            for chunk in response.iter_content(chunk_size=4096):
                tmp.write(chunk)
            tmp_path = tmp.name

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
        print(f"[ElevenLabs error]: {exc} — falling back to gTTS")
        return False


# ---------------------------------------------------------------------------
# gTTS — good quality, requires internet
# ---------------------------------------------------------------------------

def _speak_gtts(text: str) -> None:
    """Use gTTS (Google Text-to-Speech) + pygame to play audio."""
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

    except ImportError:
        _speak_pyttsx3(text)
    except Exception as exc:
        print(f"[gTTS error]: {exc}")
        _speak_pyttsx3(text)


# ---------------------------------------------------------------------------
# pyttsx3 — fully offline fallback
# ---------------------------------------------------------------------------

def _speak_pyttsx3(text: str) -> None:
    """Use pyttsx3 for fully offline TTS — no internet required."""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 165)
        engine.setProperty("volume", 1.0)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    except Exception as exc:
        print(f"[pyttsx3 error]: {exc} — text only mode.")


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
