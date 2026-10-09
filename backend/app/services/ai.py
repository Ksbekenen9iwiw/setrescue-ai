from __future__ import annotations

import hashlib
import json
import time
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import decrypt_secret, validate_external_https_url
from app.models import AICache, AISetting, AIUsageLog


class DetectedRequirement(BaseModel):
    category: str = Field(pattern=r"^(CAST|EQUIPMENT|LIGHTING|AUDIO|WEATHER|LOCATION|TIME|DEPENDENCY|QUALITY|CONTINGENCY)$")
    name: str = Field(min_length=1, max_length=180)
    source_reason: str = Field(min_length=1, max_length=1000)
    confidence: float = Field(ge=0, le=1)
    suggested_hard_constraint: bool = False


class DetectedIssue(BaseModel):
    severity: str = Field(pattern=r"^(CRITICAL|WARNING|INFO)$")
    category: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    recommended_action: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0, le=1)


class SceneAnalysis(BaseModel):
    scene_number: str = Field(min_length=1, max_length=20)
    detected_requirements: list[DetectedRequirement] = Field(default_factory=list, max_length=50)
    issues: list[DetectedIssue] = Field(default_factory=list, max_length=50)


class AIAnalysis(BaseModel):
    scenes: list[SceneAnalysis] = Field(default_factory=list, max_length=200)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def call_structured_analysis(db: Session, operation: str, input_text: str, context: dict[str, Any]) -> tuple[AIAnalysis, bool, int]:
    setting = db.scalar(select(AISetting).order_by(AISetting.updated_at.desc()))
    if not setting or not setting.enabled or not setting.encrypted_api_key:
        raise AppError(503, "AI_CONNECTION_FAILED", "AI provider is not configured.")
    base_url = validate_external_https_url(setting.base_url)
    # Cache entries must not cross provider/model boundaries when settings change.
    context_json = json.dumps({"provider": setting.provider_name, "base_url": setting.base_url,
                               "model": setting.model, "context": context}, sort_keys=True, separators=(",", ":"))
    input_hash, context_hash = _hash(input_text), _hash(context_json)
    cached = db.scalar(select(AICache).where(
        AICache.operation == operation,
        AICache.input_hash == input_hash,
        AICache.context_hash == context_hash,
    ))
    if cached:
        try:
            parsed = AIAnalysis.model_validate_json(cached.response_json)
        except ValidationError:
            db.delete(cached)
        else:
            db.add(AIUsageLog(operation=operation, model=setting.model, cache_hit=True))
            db.commit()
            return parsed, True, 0

    prompt = (
        "Analyze production documents. Return JSON only with the exact shape: "
        '{"scenes":[{"scene_number":"...","detected_requirements":[{"category":"CAST|EQUIPMENT|LIGHTING|AUDIO|WEATHER|LOCATION|TIME|DEPENDENCY|QUALITY|CONTINGENCY","name":"...","source_reason":"...","confidence":0.0,"suggested_hard_constraint":false}],"issues":[{"severity":"CRITICAL|WARNING|INFO","category":"...","title":"...","description":"...","recommended_action":"...","confidence":0.0}]}]}. '
        "Do not invent scene numbers. Suggestions are advisory and never authoritative.\n"
        f"Known context: {context_json}\nDocuments:\n{input_text[:100_000]}"
    )
    payload = {
        "model": setting.model,
        "messages": [
            {"role": "system", "content": "You extract film-production readiness facts into strict JSON. Never schedule or calculate costs."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    started = time.perf_counter()
    response: httpx.Response | None = None
    error: Exception | None = None
    for attempt in range(2):
        try:
            with httpx.Client(timeout=httpx.Timeout(30, connect=10), follow_redirects=False) as client:
                response = client.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {decrypt_secret(setting.encrypted_api_key)}", "Content-Type": "application/json"},
                    json=payload,
                )
            if response.status_code < 500:
                break
        except httpx.HTTPError as exc:
            error = exc
        if attempt == 0:
            time.sleep(0.4)
    duration = int((time.perf_counter() - started) * 1000)
    if response is None or response.status_code >= 400:
        # Do not include provider body: it may echo credentials or submitted production data.
        raise AppError(502, "AI_CONNECTION_FAILED", "AI provider request failed.", {"status": response.status_code if response else None}) from error
    try:
        raw = response.json()
        content = raw["choices"][0]["message"]["content"]
        parsed = AIAnalysis.model_validate_json(content)
        usage = raw.get("usage") or {}
        input_tokens = int(usage.get("prompt_tokens", 0))
        output_tokens = int(usage.get("completion_tokens", 0))
    except (ValueError, KeyError, TypeError, IndexError, ValidationError) as exc:
        raise AppError(502, "AI_INVALID_RESPONSE", "AI provider returned an invalid structured response.") from exc
    db.add(AICache(operation=operation, input_hash=input_hash, context_hash=context_hash, response_json=parsed.model_dump_json()))
    db.add(AIUsageLog(
        operation=operation, model=setting.model, input_tokens=input_tokens, output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens, duration_ms=duration, cache_hit=False,
    ))
    db.commit()
    return parsed, False, input_tokens + output_tokens


def test_connection(setting: AISetting) -> dict[str, Any]:
    if not setting.encrypted_api_key:
        raise AppError(422, "AI_CONNECTION_FAILED", "Save an API key before testing the connection.")
    base_url = validate_external_https_url(setting.base_url)
    try:
        with httpx.Client(timeout=httpx.Timeout(15, connect=8), follow_redirects=False) as client:
            response = client.get(f"{base_url}/models", headers={"Authorization": f"Bearer {decrypt_secret(setting.encrypted_api_key)}"})
    except httpx.HTTPError as exc:
        raise AppError(502, "AI_CONNECTION_FAILED", "Could not connect to the AI provider.") from exc
    if response.status_code >= 400:
        raise AppError(502, "AI_CONNECTION_FAILED", "AI provider rejected the connection.", {"status": response.status_code})
    return {"connected": True, "provider": setting.provider_name, "model": setting.model}
