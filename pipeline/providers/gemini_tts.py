"""Narration with Gemini TTS, over its REST API.

The endpoint and the request follow Google's text-to-speech guide for the
Interactions API. The model detects the language of the text itself, Amharic
included. A unary request comes back as a complete WAV file (24 kHz, mono,
16-bit), so the bytes are saved as they arrive.
"""
from __future__ import annotations

import base64
from typing import Any

from ..providers import ProviderError, post

INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"


def request_payload(*, model: str, text: str, voice: str, style: str) -> dict[str, Any]:
    """The body of one request.

    The text is read exactly as written. How it is read, the delivery, is
    metadata: the model would speak any instruction left inside the text.
    """
    content: dict[str, Any] = {"type": "text", "text": text}
    if style:
        content["annotations"] = [{"type": "speech_metadata", "style": style}]
    return {
        "model": model,
        "input": [{"type": "user_input", "content": [content]}],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": voice}]},
    }


def audio_from_response(body: dict[str, Any]) -> bytes:
    """The last piece of audio the model produced, decoded."""
    for step in reversed(body.get("steps") or []):
        if step.get("type") != "model_output":
            continue
        for part in reversed(step.get("content") or []):
            if part.get("type") == "audio" and part.get("data"):
                return base64.b64decode(part["data"])
    raise ProviderError(f"the response held no audio (status {body.get('status')!r}, error {body.get('error')!r})")


def synthesize(text: str, *, voice: str, style: str, model: str, api_key: str, timeout: float = 180.0) -> bytes:
    """Speak one line and return the bytes of a WAV file."""
    response = post(
        INTERACTIONS_URL,
        timeout=timeout,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json=request_payload(model=model, text=text, voice=voice, style=style),
    )
    if response.status_code != 200:
        raise ProviderError(f"{model} answered HTTP {response.status_code}: {response.text[:300]}")
    return audio_from_response(response.json())
