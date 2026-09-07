
import asyncio
import json
import os
from pathlib import Path
from typing import Any

import aiohttp
from pydantic import BaseModel

from adapters.llm.base import Breaker, ErrClass, KeyState, classify
from core.config import DEFAULT_GEMINI_FALLBACK_MODELS, DEFAULT_GEMINI_MODEL
from core.errors import LLMUnavailable


class GeminiKey(BaseModel):
    name: str
    value: str

class GeminiKeyManager:
    def __init__(self, keys: list[GeminiKey]):
        self.keys = keys
        self.active_index = 0
        self.last_errors: dict[str, str] = {}
        self.last_success: str | None = None
        self.key_states: dict[str, KeyState] = {k.name: KeyState() for k in keys}

    @property
    def active_key(self) -> GeminiKey | None:
        if not self.keys:
            return None
        return self.keys[self.active_index]

    def switch(self, key_ref: str | int) -> GeminiKey:
        if not self.keys:
            raise LLMUnavailable("Gemini", "No Gemini keys are configured in .env")

        ref = str(key_ref).strip()
        if ref.isdigit():
            index = int(ref) - 1
            if 0 <= index < len(self.keys):
                self.active_index = index
                return self.keys[index]

        for index, key in enumerate(self.keys):
            if key.name.lower() == ref.lower():
                self.active_index = index
                return key

        raise LLMUnavailable("Gemini", f"Unknown Gemini key: {key_ref}")

    def ordered_keys(self) -> list[tuple[int, GeminiKey]]:
        if not self.keys:
            return []
        return [
            ((self.active_index + offset) % len(self.keys), self.keys[(self.active_index + offset) % len(self.keys)])
            for offset in range(len(self.keys))
        ]

def discover_gemini_keys() -> list[GeminiKey]:
    keys = []
    seen = set()
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            name, _ = line.split("=", 1)
            name = name.strip()
            if not name.lower().endswith("_gemini") or name.lower() in seen:
                continue
            value = os.getenv(name)
            if value:
                keys.append(GeminiKey(name=name, value=value.strip().strip("\"\'")))
                seen.add(name.lower())
    for name, value in os.environ.items():
        if name.lower().endswith("_gemini") and name.lower() not in seen and value:
            keys.append(GeminiKey(name=name, value=value.strip().strip("\"\'")))
            seen.add(name.lower())
    return keys

gemini_manager = GeminiKeyManager(discover_gemini_keys())
gemini_breaker = Breaker("Gemini", threshold=5, cooldown_secs=300)

def get_gemini_models(model: str | None = None) -> list[str]:
    configured = os.getenv("GEMINI_FALLBACK_MODELS")
    primary_model = model.strip() if (model and model.strip().lower() not in {"string", "default"}) else DEFAULT_GEMINI_MODEL
    models = [primary_model]
    if configured:
        models.extend(item.strip() for item in configured.split(",") if item.strip())
    else:
        models.extend(DEFAULT_GEMINI_FALLBACK_MODELS)
    deduped = []
    for item in models:
        if item not in deduped:
            deduped.append(item)
    return deduped

def extract_interaction_citations(data: dict[str, Any]) -> list[dict[str, str]]:
    citations = []
    for step in data.get("steps", []):
        if step.get("type") != "model_output":
            continue
        for block in step.get("content", []):
            for annotation in block.get("annotations", []) or []:
                if annotation.get("type") == "url_citation" and annotation.get("url"):
                    citations.append({
                        "title": annotation.get("title") or annotation["url"],
                        "url": annotation["url"],
                    })
    return citations

def extract_interaction_text(data: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    if text := data.get("output_text"):
        return str(text).strip(), extract_interaction_citations(data)
    for step in data.get("steps", []):
        if step.get("type") != "model_output":
            continue
        for block in step.get("content", []):
            if block.get("type") == "text" and block.get("text"):
                return str(block["text"]).strip(), extract_interaction_citations(data)
    raise Exception(f"Unexpected Gemini interaction response: {data}")

async def _one_call(api_key: str, prompt: str, model: str, use_search: bool) -> dict[str, Any]:
    if use_search:
        url = "https://generativelanguage.googleapis.com/v1beta/interactions"
        payload = {"model": model, "input": prompt, "tools": [{"type": "google_search"}]}
    else:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
            ]
        }

    headers = {"Content-Type": "application/json", "X-goog-api-key": api_key}
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, headers=headers, json=payload) as response:
            data = await response.json(content_type=None)
            if response.status >= 400:
                message = data.get("error", {}).get("message", str(data))
                class ApiError(Exception):
                    def __init__(self, s, m):
                        self.status = s
                        self.message = m
                        super().__init__(m)
                raise ApiError(response.status, message)

            if use_search:
                text, citations = extract_interaction_text(data)
                return {"text": text, "citations": citations}
            else:
                try:
                    parts = data["candidates"][0]["content"]["parts"]
                    text = "".join(part.get("text", "") for part in parts).strip()
                except Exception as exc:
                    raise Exception(f"Unexpected response: {data}") from exc
                return {"text": text, "citations": []}

async def call_with_failover(prompt: str, models: list[str], schema: str | None = None, use_search: bool = True, max_attempts: int = 3) -> dict[str, Any]:
    if not gemini_breaker.allow():
        raise LLMUnavailable("Gemini", "circuit breaker open")
    if schema:
        prompt = f"{prompt}\n\nRespond STRICTLY in JSON matching this schema:\n{schema}"
    errors = []
    for attempt in range(max_attempts):
        model_dead = False
        for model in models:
            if model_dead:
                break
            for index, key in gemini_manager.ordered_keys():
                st = gemini_manager.key_states.get(key.name)
                if not st or not st.available():
                    errors.append(f"{key.name}: unavailable (cooldown)")
                    continue
                try:
                    res = await _one_call(key.value, prompt, model, use_search)
                    gemini_manager.active_index = index
                    gemini_manager.last_errors.pop(key.name, None)
                    gemini_manager.last_success = key.name
                    st.error_count = 0
                    gemini_breaker.record_success()

                    if schema:
                        text = res["text"].strip()
                        if text.startswith("```"):
                            text = text.split("\n", 1)[-1].rsplit("\n", 1)[0]
                        if text.startswith("json"):
                            text = text[4:].strip()
                        try:
                            json.loads(text)
                            res["text"] = text
                        except json.JSONDecodeError as e:
                            raise ValueError(f"JSON validation failed: {e}")
                    res["key"] = key.name
                    res["model"] = model
                    return res
                except Exception as exc:
                    status = getattr(exc, "status", 500)
                    msg = getattr(exc, "message", str(exc))
                    cls = classify(status, msg)
                    st.record(cls, msg)
                    gemini_manager.last_errors[key.name] = msg
                    errors.append(f"{model}/{key.name}: {msg}")
                    if cls == ErrClass.FATAL:
                        await gemini_breaker.record_failure(msg)
                        model_dead = True
                        break
        if attempt < max_attempts - 1:
            await asyncio.sleep(min(4, 2 ** attempt))
    await gemini_breaker.record_failure("All attempts exhausted")
    raise LLMUnavailable("Gemini", " | ".join(errors[:8]))

async def validate_reco(reco: str) -> str:
    try:
        json.loads(reco)
        return reco
    except Exception:
        prompt = f"Fix this JSON. Return ONLY valid JSON:\n\n{reco}"
        try:
            from core.config import DEFAULT_GEMINI_FALLBACK_MODELS
            res = await call_with_failover(prompt, DEFAULT_GEMINI_FALLBACK_MODELS, schema=None, use_search=False, max_attempts=1)
            text = res["text"].strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("\n", 1)[0]
            if text.startswith("json"):
                text = text[4:].strip()
            json.loads(text)
            return text
        except Exception:
            return "{}"

async def analyse_candidate(symbol: str, blocks: dict[str, str]) -> str:
    models = get_gemini_models()
    q_prompt = f"Perform deep grounded research on {symbol}. Context: {blocks.get('research', '')}"
    try:
        r1 = await call_with_failover(q_prompt, models, use_search=True, max_attempts=2)
        research = r1["text"]
    except Exception as e:
        research = f"Research failed: {e}"
    schema = '{"recommendation": "BUY|SELL|HOLD", "reason": "string", "confidence": "0-100"}'
    d_prompt = f"Based on this research:\n{research}\n\nAnd technicals:\n{blocks.get('technicals', '')}\nProvide structured decision."
    try:
        r2 = await call_with_failover(d_prompt, models, schema=schema, use_search=False, max_attempts=2)
        return await validate_reco(r2["text"])
    except Exception as e:
        return json.dumps({"recommendation": "HOLD", "reason": f"Analysis failed: {e}", "confidence": "0"})
