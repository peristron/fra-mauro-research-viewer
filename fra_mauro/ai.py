from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Mapping

import requests

from .config import MODEL_PRESETS, PROVIDER_BASE_URLS, ModelPreset


SYSTEM_PROMPT = """You assist with research on the 1459 Fra Mauro map.
Distinguish transcription, transliteration, and translation. Do not invent missing text.
Use [unclear], [illegible], and [possible reading: ...] where needed. Return strict JSON with
keys transcription, transliteration, translation, uncertainty_notes. The translation must be
plain English. Treat all output as a hypothesis requiring human review."""


@dataclass(frozen=True)
class AIResult:
    transcription: str
    transliteration: str
    translation: str
    uncertainty_notes: str
    raw_response: str
    provenance: str


def preset_by_label(label: str) -> ModelPreset:
    return next(preset for preset in MODEL_PRESETS if preset.label == label)


def _secret(secrets: Mapping[str, Any], name: str, default: str = "") -> str:
    try:
        value = secrets.get(name, default)
    except (AttributeError, FileNotFoundError, KeyError):
        return default
    return str(value) if value is not None else default


def effective_model_id(preset: ModelPreset, secrets: Mapping[str, Any]) -> str:
    slug = preset.label.upper().replace(" ", "_").replace(".", "_").replace("-", "_")
    override_key = f"MODEL_{slug}"
    return _secret(secrets, override_key, preset.model_id)


def configured(preset: ModelPreset, secrets: Mapping[str, Any]) -> bool:
    return bool(_secret(secrets, preset.secret_name))


def _data_url(image_bytes: bytes | None) -> str | None:
    if not image_bytes:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode("ascii")


def _extract_json(text: str) -> dict[str, str]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            return {"translation": cleaned}
        parsed = json.loads(cleaned[start : end + 1])
    return {str(key): str(value or "") for key, value in parsed.items()}


def _openai_compatible(
    preset: ModelPreset,
    model_id: str,
    api_key: str,
    prompt: str,
    image_bytes: bytes | None,
    timeout: int,
    base_url: str,
) -> str:
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    data_url = _data_url(image_bytes)
    if data_url and preset.supports_images:
        content.append(
            {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}}
        )
    payload: dict[str, Any] = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
    }
    if preset.provider == "openai":
        payload["max_completion_tokens"] = 1800
    else:
        payload["max_tokens"] = 1800
    base = base_url.rstrip("/")
    response = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return str(response.json()["choices"][0]["message"]["content"])


def _anthropic(
    model_id: str,
    api_key: str,
    prompt: str,
    image_bytes: bytes | None,
    timeout: int,
) -> str:
    content: list[dict[str, Any]] = []
    if image_bytes:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                },
            }
        )
    content.append({"type": "text", "text": prompt})
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model_id,
            "max_tokens": 1800,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": content}],
        },
        timeout=timeout,
    )
    response.raise_for_status()
    blocks = response.json().get("content", [])
    return "\n".join(block.get("text", "") for block in blocks if block.get("type") == "text")


def _gemini(
    model_id: str,
    api_key: str,
    prompt: str,
    image_bytes: bytes | None,
    timeout: int,
) -> str:
    parts: list[dict[str, Any]] = [{"text": f"{SYSTEM_PROMPT}\n\n{prompt}"}]
    if image_bytes:
        parts.append(
            {
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                }
            }
        )
    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent",
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json={
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 1800},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    candidates = response.json().get("candidates", [])
    if not candidates:
        raise ValueError("Gemini returned no candidate response.")
    return "\n".join(
        part.get("text", "") for part in candidates[0]["content"].get("parts", [])
    )


def analyze(
    label: str,
    source_text: str,
    secrets: Mapping[str, Any],
    image_bytes: bytes | None = None,
    timeout: int = 120,
) -> AIResult:
    preset = preset_by_label(label)
    api_key = _secret(secrets, preset.secret_name)
    if not api_key:
        raise ValueError(f"{preset.secret_name} is not configured in Streamlit secrets.")
    model_id = effective_model_id(preset, secrets)
    prompt = (
        "Analyze the supplied map crop and/or draft text. Preserve uncertainty.\n\n"
        f"Draft OCR or transcription:\n{source_text or '[no draft text supplied]'}"
    )
    if preset.provider == "anthropic":
        raw = _anthropic(model_id, api_key, prompt, image_bytes, timeout)
    elif preset.provider == "gemini":
        raw = _gemini(model_id, api_key, prompt, image_bytes, timeout)
    else:
        base_url = _secret(
            secrets,
            f"BASE_URL_{preset.provider.upper()}",
            PROVIDER_BASE_URLS[preset.provider],
        )
        raw = _openai_compatible(
            preset, model_id, api_key, prompt, image_bytes, timeout, base_url
        )
    values = _extract_json(raw)
    return AIResult(
        transcription=values.get("transcription", ""),
        transliteration=values.get("transliteration", ""),
        translation=values.get("translation", ""),
        uncertainty_notes=values.get("uncertainty_notes", ""),
        raw_response=raw,
        provenance=f"AI-generated with {preset.label} ({model_id}); not human-reviewed",
    )
