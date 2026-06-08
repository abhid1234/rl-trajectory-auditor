import json
import pytest
from src.judge.gemini import GeminiClient, GeminiError


def _gemini_response(payload_obj, prompt_tokens=100, out_tokens=20):
    """Shape of a generateContent response, with our JSON in the text part."""
    return {
        "candidates": [{"content": {"parts": [{"text": json.dumps(payload_obj)}]}}],
        "usageMetadata": {"promptTokenCount": prompt_tokens, "candidatesTokenCount": out_tokens,
                          "totalTokenCount": prompt_tokens + out_tokens},
    }


def test_generate_json_parses_text_part():
    calls = []

    def fake_transport(url, body):
        calls.append((url, body))
        return _gemini_response({"diagnosis": "CLEAN", "confidence": 0.5})

    c = GeminiClient(api_key="k", model="gemini-flash", transport=fake_transport)
    out = c.generate_json("hello", {"type": "object"})
    assert out["diagnosis"] == "CLEAN"
    assert "gemini-flash" in calls[0][0]
    assert c.total_tokens == 120


def test_generate_json_retries_then_succeeds():
    state = {"n": 0}

    def flaky_transport(url, body):
        state["n"] += 1
        if state["n"] < 3:
            raise GeminiError("429 rate limited")
        return _gemini_response({"ok": True})

    c = GeminiClient(api_key="k", model="m", transport=flaky_transport, max_retries=5, backoff_base=0)
    out = c.generate_json("p", {"type": "object"})
    assert out["ok"] is True
    assert state["n"] == 3


def test_generate_json_raises_after_max_retries():
    def always_fail(url, body):
        raise GeminiError("500")

    c = GeminiClient(api_key="k", model="m", transport=always_fail, max_retries=2, backoff_base=0)
    with pytest.raises(GeminiError):
        c.generate_json("p", {"type": "object"})


def test_missing_api_key_raises():
    with pytest.raises(GeminiError):
        GeminiClient(api_key="", model="m", transport=lambda u, b: {})
