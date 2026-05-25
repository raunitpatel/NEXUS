"""
Provider-agnostic LLM abstraction for the NEXUS Orchestrator.

All LLM calls in orchestrator nodes go through the LLMProvider protocol.
The concrete implementation is selected at startup via config.LLM_PROVIDER.

Supported providers:
  - "ollama"  → OllamaProvider  (local, free, offline)
  - "gemini"  → GeminiProvider  (Google Gemini API)
  - "claude"  → ClaudeProvider  (Anthropic Claude API)

To add a new provider:
  1. Implement the LLMProvider Protocol below
  2. Add a branch in get_llm_provider()
  3. Update config.py with any new env vars

No changes to decompose_query.py or synthesize_output.py are required
when switching providers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import anthropic
import google.generativeai as genai
import httpx
import structlog

logger = structlog.get_logger(__name__)


# Shared response type
@dataclass
class LLMResponse:
    """
    Normalised response from any LLM provider.

    Attributes:
        content: The model's text response.
        prompt_tokens: Input tokens consumed (0 if provider does not report).
        completion_tokens: Output tokens consumed (0 if provider does not report).
    """

    content: str
    prompt_tokens: int
    completion_tokens: int


# Protocol
@runtime_checkable
class LLMProvider(Protocol):
    """
    Provider-agnostic interface for LLM completions used by orchestrator nodes.

    Implementors must be safe to call from async context (asyncio event loop).
    """

    async def complete(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
    ) -> LLMResponse:
        """
        Send a chat completion request and return a normalised LLMResponse.

        Args:
            system: System prompt.
            user: User message.
            json_mode: If True, instruct the provider to return valid JSON only.

        Returns:
            LLMResponse with content, prompt_tokens, completion_tokens.

        Raises:
            LLMProviderError: On any provider-side failure
            (connection, timeout, bad response).
        """
        ...

    async def complete_with_tools(
        self,
        system: str,
        user: str,
        tools: list[dict[str, Any]],
    ) -> ToolCallResult:
        """Send completion with tool definitions and parse tool call response."""
        ...


class LLMProviderError(Exception):
    """Raised when the LLM provider returns an error or is unreachable."""

    def __init__(self, provider: str, message: str) -> None:
        """
        Args:
            provider: Provider name for diagnostic messages.
            message: Human-readable error description.
        """

        super().__init__(f"[{provider}] {message}")
        self.provider = provider


# Ollama implementation
class OllamaProvider:
    """
    LLMProvider implementation that calls a local Ollama HTTP server.

    Uses the /api/chat endpoint with streaming disabled.
    JSON mode is enforced by appending an instruction to the system prompt
    and setting format="json" in the request body.

    Attributes:
        base_url: Ollama server base URL
            (e.g. "http://localhost:11434").
        model: Ollama model tag (e.g. "qwen3:7b").
        timeout: httpx timeout in seconds for the full response.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = 60.0,
    ) -> None:
        """
        Args:
            base_url: Ollama base URL.
            model: Model identifier as returned by `ollama list`.
            timeout: Seconds before httpx raises TimeoutException.
        """

        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    async def complete(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
    ) -> LLMResponse:
        """
        Call Ollama /api/chat and return a normalised LLMResponse.
        """

        effective_system = system

        if json_mode:
            effective_system = (
                system + "\n\nIMPORTANT: You MUST respond with valid JSON only. "
                "No markdown, no prose, no code fences. Raw JSON only."
            )

        payload: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": effective_system},
                {"role": "user", "content": user},
            ],
            "stream": False,
        }

        if json_mode:
            payload["format"] = "json"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/api/chat",
                    json=payload,
                )

        except httpx.ConnectError as exc:
            raise LLMProviderError(
                "ollama",
                f"Cannot connect to Ollama at {self._base_url}. "
                f"Is `ollama serve` running? Error: {exc}",
            ) from exc

        except httpx.TimeoutException as exc:
            raise LLMProviderError(
                "ollama",
                f"Ollama request timed out after {self._timeout}s.",
            ) from exc

        if response.status_code != 200:
            raise LLMProviderError(
                "ollama",
                f"HTTP {response.status_code}: {response.text[:200]}",
            )

        try:
            body = response.json()

        except json.JSONDecodeError as exc:
            raise LLMProviderError(
                "ollama",
                f"Ollama returned non-JSON body: {response.text[:200]}",
            ) from exc

        content: str = body.get("message", {}).get("content", "")
        prompt_tokens: int = body.get("prompt_eval_count", 0) or 0
        completion_tokens: int = body.get("eval_count", 0) or 0

        logger.debug(
            "ollama.complete",
            model=self._model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        return LLMResponse(
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    async def complete_with_tools(
        self,
        system: str,
        user: str,
        tools: list[dict[str, Any]],
    ) -> ToolCallResult:
        """
        Fallback tool dispatch for non-Claude providers via JSON prompt engineering.

        Instructs the LLM to respond with a JSON object specifying which tool to call.
        Less reliable than native function calling — Claude is recommended for tool_agent.

        Args:
            system: System prompt.
            user: User message.
            tools: Tool definitions (used to build the prompt, not passed natively).

        Returns:
            ToolCallResult parsed from JSON response.
        """
        tool_list = "\n".join(f"- {t['name']}: {t['description']}" for t in tools)
        tool_names = [t["name"] for t in tools]

        augmented_system = (
            f"{system}\n\n"
            f"You have access to these tools:\n{tool_list}\n\n"
            "IMPORTANT: Respond ONLY with a JSON object:\n"
            '{"tool": "<tool_name>", "input": {<tool_input_fields>}}\n'
            f"tool must be one of: {tool_names}. No prose, no markdown."
        )

        try:
            llm_response = await self.complete(
                system=augmented_system,
                user=user,
                json_mode=True,
            )
            raw = json.loads(llm_response.content)
            return ToolCallResult(
                tool_name=raw.get("tool"),
                tool_input=raw.get("input", {}),
                stop_reason="tool_use",
                prompt_tokens=llm_response.prompt_tokens,
                completion_tokens=llm_response.completion_tokens,
            )
        except (json.JSONDecodeError, KeyError):
            # LLM failed to follow JSON format — return as plain answer
            return ToolCallResult(
                tool_name=None,
                tool_input={},
                stop_reason="end_turn",
                prompt_tokens=0,
                completion_tokens=0,
                raw_text=llm_response.content if "llm_response" in dir() else "",
            )


# Gemini implementation
class GeminiProvider:
    """
    LLMProvider implementation using Google's Gemini API.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = 60.0,
    ) -> None:
        self._model = model
        self._timeout = timeout

        genai.configure(api_key=api_key)

        self._client = genai.GenerativeModel(model)

    async def complete(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
    ) -> LLMResponse:
        """
        Call Gemini API and return normalized response.
        """

        try:
            prompt = f"{system}\n\nUser:\n{user}"

            generation_config = {}

            if json_mode:
                generation_config["response_mime_type"] = "application/json"

            response = await self._client.generate_content_async(
                prompt,
                generation_config=generation_config,
                request_options={
                    "timeout": self._timeout,
                },
            )

        except Exception as exc:
            raise LLMProviderError(
                "gemini",
                f"Gemini request failed: {exc}",
            ) from exc

        content = response.text or ""

        usage = getattr(response, "usage_metadata", None)

        prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0 if usage else 0

        completion_tokens = getattr(usage, "candidates_token_count", 0) or 0 if usage else 0

        logger.debug(
            "gemini.complete",
            model=self._model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        return LLMResponse(
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    async def complete_with_tools(
        self,
        system: str,
        user: str,
        tools: list[dict[str, Any]],
    ) -> ToolCallResult:
        """
        Fallback tool dispatch for non-Claude providers via JSON prompt engineering.

        Instructs the LLM to respond with a JSON object specifying which tool to call.
        Less reliable than native function calling — Claude is recommended for tool_agent.

        Args:
            system: System prompt.
            user: User message.
            tools: Tool definitions (used to build the prompt, not passed natively).

        Returns:
            ToolCallResult parsed from JSON response.
        """
        tool_list = "\n".join(f"- {t['name']}: {t['description']}" for t in tools)
        tool_names = [t["name"] for t in tools]

        augmented_system = (
            f"{system}\n\n"
            f"You have access to these tools:\n{tool_list}\n\n"
            "IMPORTANT: Respond ONLY with a JSON object:\n"
            '{"tool": "<tool_name>", "input": {<tool_input_fields>}}\n'
            f"tool must be one of: {tool_names}. No prose, no markdown."
        )

        try:
            llm_response = await self.complete(
                system=augmented_system,
                user=user,
                json_mode=True,
            )
            raw = json.loads(llm_response.content)
            return ToolCallResult(
                tool_name=raw.get("tool"),
                tool_input=raw.get("input", {}),
                stop_reason="tool_use",
                prompt_tokens=llm_response.prompt_tokens,
                completion_tokens=llm_response.completion_tokens,
            )
        except (json.JSONDecodeError, KeyError):
            # LLM failed to follow JSON format — return as plain answer
            return ToolCallResult(
                tool_name=None,
                tool_input={},
                stop_reason="end_turn",
                prompt_tokens=0,
                completion_tokens=0,
                raw_text=llm_response.content if "llm_response" in dir() else "",
            )


# Claude implementation
class ClaudeProvider:
    """
    LLMProvider implementation using Anthropic Claude API.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = 60.0,
    ) -> None:
        self._model = model
        self._timeout = timeout

        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            timeout=timeout,
        )

    async def complete(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
    ) -> LLMResponse:
        """
        Call Claude API and return normalized response.
        """

        try:
            effective_user = user

            if json_mode:
                effective_user = (
                    user + "\n\nIMPORTANT: Return valid JSON only. "
                    "No markdown, no prose, no code fences."
                )

            response = await self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=system,
                messages=[
                    {
                        "role": "user",
                        "content": effective_user,
                    }
                ],
            )

        except Exception as exc:
            raise LLMProviderError(
                "claude",
                f"Claude request failed: {exc}",
            ) from exc

        content = ""

        if response.content:
            content = response.content[0].text

        prompt_tokens = getattr(response.usage, "input_tokens", 0) or 0
        completion_tokens = getattr(response.usage, "output_tokens", 0) or 0

        logger.debug(
            "claude.complete",
            model=self._model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        return LLMResponse(
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    async def complete_with_tools(
        self,
        system: str,
        user: str,
        tools: list[dict[str, Any]],
    ) -> ToolCallResult:
        """
        Send a completion request with tool definitions and parse the tool call.

        Args:
            system: System prompt.
            user: User message.
            tools: List of tool definition dicts from get_tool_definitions().

        Returns:
            ToolCallResult with tool_name, tool_input, stop_reason, token counts.

        Raises:
            LLMProviderError: On API failure.
        """
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=system,
                tools=tools,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:
            raise LLMProviderError("claude", f"Tool-use request failed: {exc}") from exc

        prompt_tokens = getattr(response.usage, "input_tokens", 0) or 0
        completion_tokens = getattr(response.usage, "output_tokens", 0) or 0
        stop_reason = response.stop_reason or "end_turn"

        # Extract tool call from content blocks
        tool_name: str | None = None
        tool_input: dict[str, Any] = {}
        raw_text = ""

        for block in response.content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = dict(block.input)
            elif block.type == "text":
                raw_text = block.text

        return ToolCallResult(
            tool_name=tool_name,
            tool_input=tool_input,
            stop_reason=stop_reason,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            raw_text=raw_text,
        )


def get_llm_provider() -> LLMProvider:
    """
    Return the configured LLMProvider instance based on config.settings.

    Imports config lazily to avoid circular imports.

    Returns:
        A concrete LLMProvider ready to call.

    Raises:
        ValueError: If LLM_PROVIDER env var is set to an unknown value.
    """

    from config import settings  # lazy import — avoids circular at module load

    provider_name = settings.llm_provider.lower()

    if provider_name == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout=float(settings.ollama_timeout_seconds),
        )

    if provider_name == "gemini":
        return GeminiProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout=float(settings.gemini_timeout_seconds),
        )

    if provider_name == "claude":
        return ClaudeProvider(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            timeout=float(settings.anthropic_timeout_seconds),
        )

    raise ValueError(
        f"Unknown LLM_PROVIDER='{provider_name}'. Supported values: 'ollama', 'gemini', 'claude'."
    )


@dataclass
class ToolCallResult:
    """
    Normalized result of an LLM tool-use response.

    Attributes:
        tool_name: Name of the tool the LLM decided to call.
        tool_input: Dict of arguments the LLM passed to the tool.
        stop_reason: Why the LLM stopped generating ("tool_use", "end_turn", etc.)
        prompt_tokens: Input tokens consumed.
        completion_tokens: Output tokens consumed.
        raw_text: Any text content the LLM emitted before the tool call.
    """

    tool_name: str | None
    tool_input: dict[str, Any]
    stop_reason: str
    prompt_tokens: int
    completion_tokens: int
    raw_text: str = ""


def get_tool_definitions() -> list[dict[str, Any]]:
    """
    Return the 3 NEXUS tool definitions in Anthropic tool-use schema format.

    These are passed directly to the Anthropic messages.create() call as the
    `tools` parameter. For Gemini and Ollama, the same definitions are adapted
    to their respective function-calling schemas in the provider implementations.

    Returns:
        List of tool definition dicts, each with 'name', 'description', 'input_schema'.
    """
    return [
        {
            "name": "calculator",
            "description": (
                "Evaluate a mathematical expression and return the numeric result. "
                "Use for any arithmetic: addition, subtraction, multiplication, division, "
                "exponentiation, modulo. Input must be a valid arithmetic expression string."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Arithmetic expression to evaluate, e.g. '137 * 42' or '(100 + 50) / 3'",
                    }
                },
                "required": ["expression"],
            },
        },
        {
            "name": "get_weather",
            "description": (
                "Get the current weather conditions for a given city. "
                "Returns temperature in Celsius, wind speed, and weather code. "
                "Use for any weather, temperature, or climate question about a specific city."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name to get weather for, e.g. 'London', 'Tokyo', 'New York'",
                    }
                },
                "required": ["city"],
            },
        },
        {
            "name": "wikipedia_search",
            "description": (
                "Look up factual information about a topic, person, place, or event on Wikipedia. "
                "Returns a concise summary of the Wikipedia article. "
                "Use for questions about history, science, people, places, or general knowledge."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query for Wikipedia, e.g. 'Hamlet Shakespeare' or 'Python programming language'",
                    }
                },
                "required": ["query"],
            },
        },
    ]
