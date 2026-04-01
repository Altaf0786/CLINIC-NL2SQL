"""Groq LLM service adapter for Vanna 2.0.

Provides async chat-completion via the Groq API with automatic
model fallback across a configurable list of LLMs. Uses asyncio
concurrency to race multiple fallback models simultaneously.
"""

import asyncio
import json
import os
from typing import AsyncGenerator

from groq import AsyncGroq
from vanna.core.llm import LlmRequest, LlmResponse, LlmService

from backend.config.prompts import SYSTEM_PROMPT
from backend.config.settings import settings


class GroqLlmService(LlmService):
    """Groq-backed LLM service with concurrent multi-model fallback.

    Sends chat completions via AsyncGroq, preserving assistant
    tool-call history to prevent the agent from repeating actions.
    Races all fallback models concurrently to minimise latency.
    """

    def __init__(self) -> None:
        """Initialise the Groq client and build the ordered model list."""
        api_key = settings.GROQ_API_KEY or os.getenv("GROQ_API_KEY", "")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is required")

        self.client = AsyncGroq(api_key=api_key)
        configured_models = (
            settings.MODEL_FALLBACKS
            if isinstance(settings.MODEL_FALLBACKS, list)
            else []
        )
        primary_model = settings.MODEL_NAME or os.getenv(
            "MODEL_NAME", "llama-3.3-70b-versatile"
        )
        self.models = list(dict.fromkeys([primary_model, *configured_models]))
        self.model = self.models[0]

    def _build_messages(self, request: LlmRequest) -> list[dict]:
        """Build the chat-completion messages list once (avoids rebuilding per retry)."""
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        for message in request.messages:
            payload = {"role": message.role, "content": message.content}

            # Preserve assistant tool-call history to prevent repeated run_sql loops.
            if message.role == "assistant" and getattr(message, "tool_calls", None):
                serialized_tool_calls = []
                for tool_call in message.tool_calls:
                    if isinstance(tool_call, dict):
                        tool_call_id = tool_call.get("id")
                        tool_name = tool_call.get("name")
                        tool_arguments = tool_call.get("arguments", {})
                    else:
                        tool_call_id = getattr(tool_call, "id", None)
                        tool_name = getattr(tool_call, "name", None)
                        tool_arguments = getattr(tool_call, "arguments", {})

                    serialized_tool_calls.append(
                        {
                            "id": tool_call_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(tool_arguments),
                            },
                        }
                    )
                payload["tool_calls"] = serialized_tool_calls

            if message.role == "tool" and hasattr(message, "tool_call_id"):
                payload["tool_call_id"] = message.tool_call_id
            messages.append(payload)

        return messages

    async def _try_model(self, model_name: str, messages: list[dict], tools: list | None):
        """Attempt a completion with a single model. Returns (model, completion) or raises."""
        completion = await self.client.chat.completions.create(
            model=model_name,
            messages=messages,
            tools=tools,
            temperature=0.0,
            max_completion_tokens=500,
        )
        return model_name, completion

    async def send_request(self, request: LlmRequest) -> LlmResponse:
        """Send a chat-completion request, racing fallback models concurrently.

        The primary model is tried first. On failure, all remaining fallbacks
        are launched concurrently via asyncio.as_completed() so the fastest
        successful response wins — cutting worst-case latency vs sequential retry.
        """
        messages = self._build_messages(request)

        tools = None
        if request.tools:
            tools = [{"type": "function", "function": tool} for tool in request.tools]

        # Fast path — try primary model first (most requests succeed here)
        try:
            model_name, completion = await self._try_model(self.models[0], messages, tools)
            self.model = model_name
        except Exception:
            # Parallel fallback — race remaining models concurrently
            if len(self.models) <= 1:
                return LlmResponse(
                    content="All configured Groq models failed.",
                    model=self.model,
                    tool_calls=[],
                )

            fallback_tasks = [
                asyncio.create_task(self._try_model(m, messages, tools))
                for m in self.models[1:]
            ]

            completion = None
            model_name = self.model
            last_error = None

            for coro in asyncio.as_completed(fallback_tasks):
                try:
                    model_name, completion = await coro
                    self.model = model_name
                    # Cancel remaining tasks — we have a winner
                    for task in fallback_tasks:
                        task.cancel()
                    break
                except Exception as exc:
                    last_error = exc

            if completion is None:
                # Cancel any still-pending tasks
                for task in fallback_tasks:
                    task.cancel()
                return LlmResponse(
                    content=f"All configured Groq models failed: {last_error}",
                    model=self.model,
                    tool_calls=[],
                )

        message = completion.choices[0].message
        tool_calls = []
        if message.tool_calls:
            for tool_call in message.tool_calls:
                tool_calls.append(
                    {
                        "id": tool_call.id,
                        "name": tool_call.function.name,
                        "arguments": json.loads(tool_call.function.arguments),
                    }
                )

        return LlmResponse(
            content=message.content or "", model=self.model, tool_calls=tool_calls
        )

    async def stream_request(
        self, request: LlmRequest
    ) -> AsyncGenerator[LlmResponse, None]:
        """Stream a response (delegates to send_request as Groq streaming is not used)."""
        yield await self.send_request(request)

    async def validate_tools(self, tools: list) -> bool:
        """Validate tool definitions (always passes for Groq)."""
        return True
