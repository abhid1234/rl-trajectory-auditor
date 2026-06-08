from __future__ import annotations
import json
import os
import time
import urllib.request

_API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiError(Exception):
    pass


def _urllib_transport(url: str, body: dict) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:  # noqa
        raise GeminiError(f"HTTP {e.code}: {e.read()[:200]!r}")
    except Exception as e:  # network/timeout
        raise GeminiError(str(e))


class GeminiClient:
    def __init__(self, api_key=None, model=None, transport=None,
                 max_retries=4, backoff_base=1.0):
        self.api_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", "")
        self.model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
        if not self.api_key:
            raise GeminiError("GEMINI_API_KEY is not set")
        self.transport = transport or _urllib_transport
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.total_tokens = 0
        self.last_usage = {}

    def _url(self) -> str:
        return _API.format(model=self.model, key=self.api_key)

    def generate_json(self, prompt: str, schema: dict) -> dict:
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json",
                                 "responseSchema": schema},
        }
        last_err = None
        for attempt in range(self.max_retries):
            try:
                resp = self.transport(self._url(), body)
                usage = resp.get("usageMetadata", {})
                self.last_usage = usage
                self.total_tokens += int(usage.get("totalTokenCount", 0))
                text = resp["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text)
            except GeminiError as e:
                last_err = e
                if attempt < self.max_retries - 1 and self.backoff_base:
                    time.sleep(self.backoff_base * (2 ** attempt))
            except (KeyError, IndexError, json.JSONDecodeError) as e:
                raise GeminiError(f"malformed response: {e}")
        raise GeminiError(f"exhausted retries: {last_err}")
