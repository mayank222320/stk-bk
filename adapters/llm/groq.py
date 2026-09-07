import json
import os
from typing import Any

import aiohttp

from adapters.llm.base import Breaker

groq_breaker = Breaker("Groq", threshold=3, cooldown_secs=300)

async def groq_json(prompt: str) -> dict[str, Any]:
    if not groq_breaker.allow():
        raise Exception("Groq breaker tripped.")

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise Exception("GROQ_API_KEY not set")

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.1-70b-versatile",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"}
    }

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status >= 400:
                    text = await response.text()
                    await groq_breaker.record_failure(f"HTTP {response.status}: {text}")
                    raise Exception(f"Groq error: {response.status} - {text}")

                data = await response.json()
                content = data["choices"][0]["message"]["content"]
                groq_breaker.record_success()
                return json.loads(content)
        except Exception as e:
            await groq_breaker.record_failure(str(e))
            raise e

async def gate(reco: dict, data: dict) -> dict:
    """Critic / Agreement gate using Groq (Phase 8)."""
    prompt = f"Evaluate this recommendation:\n{json.dumps(reco)}\nBased on this data:\n{json.dumps(data)}\nRespond STRICTLY with JSON matching this schema: {{'agreement': true, 'confidence_penalty': 0}}"

    try:
        res = await groq_json(prompt)
        # Apply logic
        if not res.get("agreement", True):
            penalty = res.get("confidence_penalty", 20)
            reco["confidence"] = max(0, reco.get("confidence", 100) - int(penalty))
    except Exception as e:
        # If Groq is down, catch Exception, lower confidence, and return the reco. Do not block.
        reco["confidence"] = max(0, reco.get("confidence", 100) - 10)
        reco["gate_error"] = str(e)

    return reco
