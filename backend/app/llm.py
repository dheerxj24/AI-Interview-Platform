import json

import httpx

from .config import settings


class LLMError(Exception):
    """Raised when the model is not configured, unreachable, or returns something unusable."""


def llm_configured() -> bool:
    return bool(settings.ollama_url or settings.anthropic_api_key)


def complete(prompt: str, max_tokens: int = 600) -> str:
    """Send one prompt to the configured model and return its text reply."""
    if settings.ollama_url:
        try:
            response = httpx.post(
                f"{settings.ollama_url.rstrip('/')}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                },
                timeout=120,
            )
            response.raise_for_status()
            return response.json()["message"]["content"]
        except httpx.TimeoutException as exc:
            raise LLMError("AI model timed out. Try again.") from exc
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise LLMError("AI request failed") from exc

    if settings.anthropic_api_key:
        try:
            response = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.copilot_model,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=60,
            )
            response.raise_for_status()
            return response.json()["content"][0]["text"]
        except httpx.TimeoutException as exc:
            raise LLMError("AI model timed out. Try again.") from exc
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise LLMError("AI request failed") from exc

    raise LLMError("AI co-pilot is not configured")


def parse_json_object(text: str) -> dict:
    """Pull the first JSON object out of a model reply, which may include extra prose."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise LLMError("AI reply did not contain JSON")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError("AI reply was not valid JSON") from exc
    if not isinstance(data, dict):
        raise LLMError("AI reply was not a JSON object")
    return data
