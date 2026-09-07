
import os
import json
import base64
from typing import Any
from adapters.llm.gemini import (
    call_with_failover,
    gemini_manager,
    get_gemini_models,
    GeminiKey
)
from core.config import DEFAULT_GEMINI_MODEL
from core.errors import LLMUnavailable

def looks_like_gemini_key(value: str) -> bool:
    return value.startswith(("AIza", "AQ."))

def format_gemini_status() -> str:
    if not gemini_manager.keys:
        return "No Gemini keys found in .env."

    lines = [
        f"Gemini model: {DEFAULT_GEMINI_MODEL}",
        f"Fallback models: {', '.join(get_gemini_models())}",
        "Google Search grounding: on",
        "Keys:",
    ]
    
    status_dict = {
        "active": gemini_manager.active_key.name if gemini_manager.active_key else None,
        "last_success": gemini_manager.last_success,
        "keys": [
            {
                "number": index + 1,
                "name": key.name,
                "active": index == gemini_manager.active_index,
                "looks_valid": looks_like_gemini_key(key.value),
                "last_error": gemini_manager.last_errors.get(key.name),
            }
            for index, key in enumerate(gemini_manager.keys)
        ],
    }

    for key in status_dict["keys"]:
        marker = "*" if key["active"] else "-"
        warning = "" if key["looks_valid"] else " | check key format"
        error = f" | last error: {key['last_error']}" if key["last_error"] else ""
        lines.append(f"{marker} {key['number']}. {key['name']}{warning}{error}")
    return "\n".join(lines)

def format_gemini_answer(result: dict[str, Any]) -> str:
    text = result["text"]
    citations = result.get("citations") or []
    if not citations:
        return text

    unique_sources = []
    seen = set()
    for citation in citations:
        url = citation["url"]
        if url in seen:
            continue
        seen.add(url)
        unique_sources.append(citation)

    source_lines = [
        f"{index}. {source['title']}: {source['url']}"
        for index, source in enumerate(unique_sources[:5], start=1)
    ]
    return f"{text}\n\nSources:\n" + "\n".join(source_lines)

async def generate_with_gemini_fallback(
    prompt: str,
    model: str | None = None,
    use_search: bool = True,
) -> dict[str, Any]:
    models = get_gemini_models(model)
    return await call_with_failover(prompt, models, schema=None, use_search=use_search, max_attempts=3)

async def generate_with_gemini_vision(
    image_bytes: bytes,
    mime_type: str,
    prompt: str,
    model: str | None = None,
) -> dict[str, Any]:
    # Pass through to Gemini directly - not fully refactored for brevity, just wrapper stub
    raise NotImplementedError("Vision endpoint needs failover logic migration")

async def stream_with_gemini_fallback(prompt: str, model: str | None = None, use_search: bool = True):
    from adapters.llm.gemini import gemini_manager, get_gemini_models, gemini_breaker
    import aiohttp
    import json
    
    if not gemini_breaker.allow():
        yield "Gemini service temporarily unavailable (circuit breaker open)."
        return
        
    models = get_gemini_models(model)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]
    }
    
    attempts = 0
    max_attempts = 3
    
    while attempts < max_attempts:
        key_obj = gemini_manager.active_key
        if not key_obj:
            yield "No active Gemini API keys available."
            return
            
        m = models[attempts % len(models)]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:streamGenerateContent?alt=sse"
        headers = {"Content-Type": "application/json", "X-goog-api-key": key_obj.value}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        gemini_breaker.record_success()
                        async for line in response.content:
                            line_str = line.decode('utf-8').strip()
                            if line_str.startswith("data: "):
                                data_str = line_str[6:]
                                if data_str == "[DONE]":
                                    continue
                                try:
                                    chunk_data = json.loads(data_str)
                                    if "candidates" in chunk_data and chunk_data["candidates"]:
                                        parts = chunk_data["candidates"][0].get("content", {}).get("parts", [])
                                        for p in parts:
                                            if "text" in p:
                                                yield p["text"]
                                except json.JSONDecodeError:
                                    pass
                        return  # Successfully finished
                    elif response.status == 429:
                        st = gemini_manager.key_states.get(key_obj.name)
                        if st:
                            st.record(response.status)
                        gemini_manager.active_index = (gemini_manager.active_index + 1) % len(gemini_manager.keys)
                    else:
                        error_text = await response.text()
                        print(f"Gemini stream error {response.status}: {error_text}")
        except Exception as e:
            print(f"Gemini streaming connection error: {e}")
            
        attempts += 1
        
    yield "\n\n[All streaming attempts failed. Please try again later.]"
