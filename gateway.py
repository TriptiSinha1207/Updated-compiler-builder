from __future__ import annotations
import json
import os
import pathlib
import time
from typing import Any, Dict, Optional

from .providers import (
    AnthropicProvider,
    BaseProvider,
    OpenAIProvider,
    OpenRouterProvider,
    ProviderError,
    StubProvider,
)


class MultiProviderGateway:
    """Config-driven stage routing across multiple AI providers."""

    DEFAULT_CONFIG_FILE = pathlib.Path(__file__).resolve().parent / "provider_routing.json"

    def __init__(self, config_path: Optional[str] = None) -> None:
        self.config_path = config_path or str(self.DEFAULT_CONFIG_FILE)
        self.config = self._load_config(self.config_path)
        self.provider_keys = self.config.get("provider_keys", {})
        self.cost_table = self.config.get("cost_table", {})

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Provider routing configuration not found: {config_path}")
        with open(config_path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _model_config(self, model_key: str) -> Dict[str, Any]:
        return self.config.get("models", {}).get(model_key, {})

    def _stage_config(self, stage: str) -> Dict[str, Any]:
        return self.config.get("stages", {}).get(stage, {})

    def _model_for_stage(self, stage: str) -> str:
        stage_conf = self._stage_config(stage)
        override_env = stage_conf.get("override_env")
        if override_env and os.environ.get(override_env):
            return os.environ[override_env]
        return stage_conf.get("primary_model", "gpt-4o-mini")

    def _provider_for_model(self, model_key: str) -> BaseProvider:
        model_conf = self._model_config(model_key)
        provider_name = model_conf.get("provider")
        api_key = os.environ.get(self.provider_keys.get(provider_name, ""))
        model_name = model_conf.get("model_name", model_key)

        if provider_name == "openai":
            return OpenAIProvider(api_key, model_name)
        if provider_name == "anthropic":
            return AnthropicProvider(api_key, model_name)
        if provider_name == "openrouter":
            return OpenRouterProvider(api_key, model_name)
        return StubProvider(api_key, model_name)

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    def _cost_for_model(self, model_key: str, tokens: int) -> float:
        return float(self.cost_table.get(model_key, 0.001)) * tokens

    def _openrouter_equivalent(self, model_key: str) -> str:
        model_conf = self._model_config(model_key)
        return model_conf.get("openrouter_equivalent", model_conf.get("model_name", model_key))

    def _call_provider(self, provider: BaseProvider, prompt: str) -> Dict[str, Any]:
        return provider.call(prompt)

    def _should_retry_with_openrouter(self, error: ProviderError) -> bool:
        return bool(error.status_code and (error.status_code == 429 or 500 <= error.status_code < 600))

    def _build_prompt(self, payload: Dict[str, Any]) -> str:
        if isinstance(payload, str):
            return payload
        if isinstance(payload, dict):
            return json.dumps(payload, indent=2)
        return str(payload)

    def run_stage(self, stage: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        model_key = self._model_for_stage(stage)
        result = self._attempt_stage(stage, payload, model_key)
        if not result["success"] and stage != "repair":
            fallback_key = self._stage_config(stage).get("fallback_model")
            if fallback_key and fallback_key != model_key:
                fallback_result = self._attempt_stage(stage, payload, fallback_key)
                if fallback_result["success"]:
                    return fallback_result
                result["fallback"] = fallback_result
        return result

    def _attempt_stage(self, stage: str, payload: Dict[str, Any], model_key: str) -> Dict[str, Any]:
        prompt = self._build_prompt(payload)
        provider = self._provider_for_model(model_key)
        cost_rate = self.cost_table.get(model_key, 0.001)
        token_count = self._estimate_tokens(prompt)
        event: Dict[str, Any] = {
            "stage": stage,
            "model": model_key,
            "provider": self._model_config(model_key).get("provider"),
            "tokens": token_count,
            "cost": round(self._cost_for_model(model_key, token_count), 6),
            "attempt": 1,
            "success": False,
            "used_openrouter": False,
            "response": None,
            "error": None,
        }

        if not provider.available and not isinstance(provider, StubProvider):
            event["error"] = f"Provider {event['provider']} missing API key"
            return event

        try:
            stage_result = self._call_provider(provider, prompt)
            event["success"] = True
            event["response"] = stage_result.get("response")
            event["usage"] = stage_result.get("usage", {})
            event["cost"] = round(self._cost_for_model(model_key, int(stage_result.get("usage", {}).get("total_tokens", token_count))), 6)
            return event
        except ProviderError as exc:
            event["error"] = str(exc)
            event["status_code"] = exc.status_code
            if self._should_retry_with_openrouter(exc) and event["provider"] != "openrouter":
                return self._retry_with_openrouter(stage, payload, model_key, event)
            return event

    def _retry_with_openrouter(self, stage: str, payload: Dict[str, Any], model_key: str, event: Dict[str, Any]) -> Dict[str, Any]:
        openrouter_model = self._openrouter_equivalent(model_key)
        if not openrouter_model:
            return event
        openrouter_key = "openrouter-gpt-4o" if openrouter_model == "gpt-4o" else f"openrouter-{openrouter_model}"
        provider = self._provider_for_model(openrouter_key)
        if not provider.available:
            event["error"] += "; openrouter fallback unavailable"
            return event
        prompt = self._build_prompt(payload)
        try:
            stage_result = self._call_provider(provider, prompt)
            event["success"] = True
            event["used_openrouter"] = True
            event["model"] = openrouter_key
            event["provider"] = "openrouter"
            event["response"] = stage_result.get("response")
            event["usage"] = stage_result.get("usage", {})
            event["cost"] = round(self._cost_for_model(openrouter_key, int(stage_result.get("usage", {}).get("total_tokens", self._estimate_tokens(prompt)))), 6)
            return event
        except ProviderError as exc:
            event["error"] += f"; openrouter retry failed: {exc}"
            event["status_code"] = exc.status_code
            return event
