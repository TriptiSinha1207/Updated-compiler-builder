from __future__ import annotations
from typing import Callable, Dict, Any, List


class IntegrationManager:
    """Minimal integration hook registry for third-party actions.

    Integrations are simple callables that receive an action name and payload.
    """

    def __init__(self):
        self._hooks: Dict[str, List[Callable[[Dict[str, Any]], Any]]] = {}

    def register(self, action: str, fn: Callable[[Dict[str, Any]], Any]) -> None:
        self._hooks.setdefault(action, []).append(fn)

    def trigger(self, action: str, payload: Dict[str, Any]) -> None:
        for fn in self._hooks.get(action, []):
            try:
                fn(payload)
            except Exception:
                # Swallow; integrations should not break pipeline
                pass
