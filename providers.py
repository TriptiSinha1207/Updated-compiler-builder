from __future__ import annotations
import json
import os
import urllib.request
import urllib.error
from typing import Any, Dict, Optional

class ProviderError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class BaseProvider:
    def __init__(self, api_key: Optional[str], model_name: str) -> None:
        self.api_key = api_key
        self.model_name = model_name

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def call(self, prompt: str, **kwargs: Any) -> Dict[str, Any]:
        raise NotImplementedError("Provider must implement call")

    @staticmethod
    def _request_json(url: str, data: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        request_data = json.dumps(data).encode("utf-8")
        request = urllib.request.Request(url, request_data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise ProviderError(f"HTTP {exc.code}: {body}", status_code=exc.code)
        except urllib.error.URLError as exc:
            raise ProviderError(str(exc))


class OpenAIProvider(BaseProvider):
    def call(self, prompt: str, **kwargs: Any) -> Dict[str, Any]:
        if not self.available:
            raise ProviderError("OpenAI API key is missing")
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": kwargs.get("max_tokens", 512),
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        result = self._request_json(url, payload, headers)
        usage = result.get("usage", {})
        text = "".join(choice.get("message", {}).get("content", "") for choice in result.get("choices", []))
        return {"success": True, "response": text, "usage": usage}


class AnthropicProvider(BaseProvider):
    def call(self, prompt: str, **kwargs: Any) -> Dict[str, Any]:
        if not self.available:
            raise ProviderError("Anthropic API key is missing")
        url = "https://api.anthropic.com/v1/complete"
        prompt_text = f"\n\nHuman: {prompt}\n\nAssistant:"
        payload = {
            "model": self.model_name,
            "prompt": prompt_text,
            "max_tokens_to_sample": kwargs.get("max_tokens", 512),
            "temperature": 0.2,
        }
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        result = self._request_json(url, payload, headers)
        return {"success": True, "response": result.get("completion", ""), "usage": result.get("usage", {})}


class OpenRouterProvider(BaseProvider):
    def call(self, prompt: str, **kwargs: Any) -> Dict[str, Any]:
        if not self.available:
            raise ProviderError("OpenRouter API key is missing")
        url = "https://api.openrouter.ai/v1/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": kwargs.get("max_tokens", 512),
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        result = self._request_json(url, payload, headers)
        text = "".join(choice.get("message", {}).get("content", "") for choice in result.get("choices", []))
        return {"success": True, "response": text, "usage": result.get("usage", {})}


class StubProvider(BaseProvider):
    def call(self, prompt: str, **kwargs: Any) -> Dict[str, Any]:
        return {
            "success": True,
            "response": f"[stubbed answer from {self.model_name}]",
            "usage": {"prompt_tokens": self._estimate_tokens(prompt), "completion_tokens": 16, "total_tokens": self._estimate_tokens(prompt) + 16},
        }

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(1, len(text) // 4)
