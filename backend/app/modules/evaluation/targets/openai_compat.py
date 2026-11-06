"""OpenAI-compatible chat completion adapter."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from app.modules.evaluation.targets.config import TargetConfig, render_template
from app.modules.evaluation.targets.http_json import HttpJsonAdapter
from app.modules.evaluation.types import AgentRequest

_OPENAI_RESPONSE_MAP = {
    "output": "choices.0.message.content",
    "trace_id": "id",
    "usage": "usage",
    "finish_reason": "choices.0.finish_reason",
}


class OpenAICompatibleAdapter(HttpJsonAdapter):
    def __init__(self, config: TargetConfig | dict[str, Any], **kwargs: Any) -> None:
        super().__init__(config, **kwargs)
        if self._config.url and not self._config.url.rstrip("/").endswith("/chat/completions"):
            self._config = replace(self._config, url=self._config.url.rstrip("/") + "/chat/completions")
        elif not self._config.url:
            self._config = replace(self._config, url="https://api.openai.com/v1/chat/completions")

    def response_mapping(self) -> dict[str, str]:
        return {**_OPENAI_RESPONSE_MAP, **self._config.response}

    def build_payload(self, request: AgentRequest, variables: dict[str, Any]) -> Any:
        if self._config.body is not None:
            return render_template(self._config.body, variables)
        messages: list[dict[str, Any]] = []
        if self._config.system_prompt:
            messages.append({"role": "system", "content": self._config.system_prompt})
        content = variables["input"]
        messages.append(
            {
                "role": "user",
                "content": (
                    content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, sort_keys=True)
                ),
            }
        )
        payload: dict[str, Any] = {
            "model": self._config.model or request.model or "gpt-4o-mini",
            "messages": messages,
            "temperature": self._config.temperature,
        }
        seed = self._config.seed if self._config.seed is not None else request.seed
        if seed is not None:
            payload["seed"] = seed
        return payload
