"""
Tool Agent core — LLM function-calling dispatch to calculator, weather, and Wikipedia.

Pipeline:
  1. Send instruction + 3 tool definitions to LLM
  2. LLM returns a tool call (name + input)
  3. Execute the matching tool
  4. Persist tool call + result to tool_results table
  5. Send tool result back to LLM for final natural-language synthesis
  6. Publish agent_start and agent_end Kafka events

Usage:
    agent = ToolAgent(db_engine=app.state.db_engine)
    result = await agent.run(task_id="t1", run_id="r1", user_id="u1",
                             instruction="What is 137 * 42?")
"""

from __future__ import annotations

import json
import time
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from config import settings
from llm_provider import LLMProviderError, ToolCallResult, get_llm_provider, get_tool_definitions
from tools.calculator import CalculatorTool
from tools.weather import WeatherTool
from tools.wikipedia import WikipediaTool

from shared.metrics import (
    agent_task_duration_seconds,
    agent_tasks_total,
    llm_tokens_total,
    llm_requests_total,
)

logger = structlog.get_logger(__name__)

# System prompts

_TOOL_DISPATCH_SYSTEM = """\
You are the Tool Agent for NEXUS, an AI orchestration platform.
Your job is to use the available tools to answer the user's question accurately.

Rules:
1. Always use a tool if the question can be answered by one.
2. Use the calculator for any arithmetic or mathematical question.
3. Use get_weather for any question about current weather, temperature, or climate.
4. Use wikipedia_search for factual questions about people, places, history, or science.
5. If no tool is appropriate, answer directly.
"""

_SYNTHESIZE_SYSTEM = """\
You are summarizing the result of a tool call for the user.
Given the tool name, the input, and the output, write a clear, direct, one-to-three sentence
answer to the user's original question. Do not mention that you used a tool. Just answer naturally.
"""


class ToolAgentResult:
    """
    Return value from ToolAgent.run().

    Attributes:
        answer: Final natural-language answer for the user.
        tool_used: Name of the tool that was invoked (None if no tool called).
        tool_input: Dict of arguments passed to the tool.
        tool_output: Raw dict returned by the tool.
        tokens_used: Total LLM tokens consumed across both calls.
        duration_ms: Total wall-clock time in milliseconds.
        error: Non-None error message on failure.
    """

    def __init__(
        self,
        answer: str,
        tool_used: str | None,
        tool_input: dict[str, Any],
        tool_output: dict[str, Any],
        tokens_used: int,
        duration_ms: int,
        error: str | None = None,
    ) -> None:
        self.answer = answer
        self.tool_used = tool_used
        self.tool_input = tool_input
        self.tool_output = tool_output
        self.tokens_used = tokens_used
        self.duration_ms = duration_ms
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a dict suitable for JSON response and Kafka payload."""
        return {
            "answer": self.answer,
            "tool_used": self.tool_used,
            "tool_input": self.tool_input,
            "tool_output": self.tool_output,
            "tokens_used": self.tokens_used,
            "duration_ms": self.duration_ms,
        }


class ToolAgent:
    """
    NEXUS Tool Agent — LLM function-calling dispatch with three built-in tools.

    Receives a natural-language instruction, calls the LLM with tool definitions,
    executes the chosen tool, persists the call to tool_results, and synthesizes
    a final answer via a second LLM call.

    Attributes:
        _provider: Configured LLMProvider from get_llm_provider().
        _tools: Dict mapping tool name → tool instance.
        _tool_definitions: List of tool schemas passed to LLM.
        _db_engine: Async SQLAlchemy engine for tool_results persistence.
    """

    def __init__(self, db_engine: AsyncEngine | None = None) -> None:
        """
        Initialise the Tool Agent.

        Args:
            db_engine: Async SQLAlchemy engine. If None, DB writes are skipped
                    (used in unit tests that mock the engine).
        """
        self._provider = get_llm_provider()
        self._tools: dict[str, Any] = {
            "calculator": CalculatorTool(),
            "get_weather": WeatherTool(),
            "wikipedia_search": WikipediaTool(),
        }
        self._tool_definitions = get_tool_definitions()
        self._db_engine = db_engine

    async def run(
        self,
        task_id: str,
        run_id: str,
        user_id: str,
        instruction: str,
    ) -> ToolAgentResult:
        """
        Execute the full tool dispatch pipeline for a given instruction.

        Args:
            task_id: UUID of the task row in the tasks table.
            run_id: UUID of the parent orchestration run.
            user_id: UUID of the authenticated user.
            instruction: Natural-language question or instruction.

        Returns:
            ToolAgentResult with answer, tool metadata, and token counts.
        """
        start_ms = time.monotonic()
        total_tokens = 0

        await self._publish_event(
            run_id=run_id,
            task_id=task_id,
            event_type="agent_start",
            payload={"instruction": instruction[:200], "agent": "tool"},
        )

        # Step 1: Ask LLM which tool to call
        try:
            tool_call: ToolCallResult = await self._provider.complete_with_tools(
                system=_TOOL_DISPATCH_SYSTEM,
                user=instruction,
                tools=self._tool_definitions,
            )
        except LLMProviderError as exc:
            elapsed = int((time.monotonic() - start_ms) * 1000)
            logger.error("tool_agent.llm_dispatch_failed", run_id=run_id, error=str(exc))
            result = ToolAgentResult(
                answer=f"Tool dispatch failed: {exc}",
                tool_used=None,
                tool_input={},
                tool_output={},
                tokens_used=0,
                duration_ms=elapsed,
                error=str(exc),
            )

            agent_task_duration_seconds.labels(agent="tool", status="error").observe(elapsed / 1000)
            agent_tasks_total.labels(agent="tool", status="error").inc()
            
            await self._publish_event(
                run_id=run_id, task_id=task_id, event_type="agent_end",
                payload={**result.to_dict(), "error": str(exc)},
            )
            return result

        total_tokens += tool_call.prompt_tokens + tool_call.completion_tokens

        # Step 2: If no tool call, return LLM's direct answer
        if tool_call.tool_name is None:
            elapsed = int((time.monotonic() - start_ms) * 1000)
            logger.info("tool_agent.no_tool_called", run_id=run_id, raw_text=tool_call.raw_text[:100])
            result = ToolAgentResult(
                answer=tool_call.raw_text or "I could not determine which tool to use.",
                tool_used=None,
                tool_input={},
                tool_output={},
                tokens_used=total_tokens,
                duration_ms=elapsed,
            )
            await self._publish_event(
                run_id=run_id, task_id=task_id, event_type="agent_end",
                payload=result.to_dict(),
            )
            return result

        # Step 3: Execute the chosen tool
        tool_start = time.monotonic()
        tool_output = await self._execute_tool(tool_call.tool_name, tool_call.tool_input)
        tool_duration_ms = int((time.monotonic() - tool_start) * 1000)

        logger.info(
            "tool_agent.tool_executed",
            run_id=run_id,
            tool_name=tool_call.tool_name,
            duration_ms=tool_duration_ms,
            has_error="error" in tool_output,
        )

        # Step 4: Persist tool call to tool_results table
        await self._persist_tool_result(
            task_id=task_id,
            tool_name=tool_call.tool_name,
            tool_input=tool_call.tool_input,
            tool_output=tool_output,
            duration_ms=tool_duration_ms,
        )

        # Step 5: Synthesize final answer via second LLM call
        try:
            synthesis_prompt = (
                f"Original question: {instruction}\n\n"
                f"Tool used: {tool_call.tool_name}\n"
                f"Tool input: {json.dumps(tool_call.tool_input)}\n"
                f"Tool output: {json.dumps(tool_output)}\n\n"
                "Please provide a clear, direct answer to the original question."
            )
            synthesis = await self._provider.complete(
                system=_SYNTHESIZE_SYSTEM,
                user=synthesis_prompt,
                json_mode=False,
            )
            answer = synthesis.content.strip()
            total_tokens += synthesis.prompt_tokens + synthesis.completion_tokens
        except LLMProviderError as exc:
            logger.warning("tool_agent.synthesis_failed", run_id=run_id, error=str(exc))
            # Fall back to raw tool output as answer
            answer = f"Tool result: {json.dumps(tool_output)}"

        elapsed = int((time.monotonic() - start_ms) * 1000)
        result = ToolAgentResult(
            answer=answer,
            tool_used=tool_call.tool_name,
            tool_input=tool_call.tool_input,
            tool_output=tool_output,
            tokens_used=total_tokens,
            duration_ms=elapsed,
            error=tool_output.get("error"),
        )

        await self._publish_event(
            run_id=run_id, task_id=task_id, event_type="agent_end",
            payload=result.to_dict(),
        )

        logger.info(
            "tool_agent.run_complete",
            run_id=run_id,
            task_id=task_id,
            tool_used=tool_call.tool_name,
            tokens=total_tokens,
            duration_ms=elapsed,
        )

        agent_task_duration_seconds.labels(
            agent="tool", status="success" if not result.error else "error"
        ).observe(elapsed / 1000)
        agent_tasks_total.labels(
            agent="tool", status="success" if not result.error else "error"
        ).inc()
        llm_tokens_total.labels(
            service="tool-agent",
            model=settings.anthropic_model if settings.llm_provider == "claude" else settings.gemini_model,
            type="input",
        ).inc(result.tokens_used)
        llm_requests_total.labels(
            service="tool-agent",
            model=settings.anthropic_model if settings.llm_provider == "claude" else settings.gemini_model,
            status="success" if not result.error else "error",
        ).inc()

        return result

    async def _execute_tool(
        self, tool_name: str, tool_input: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Route to the correct tool implementation and execute it.

        Args:
            tool_name: Name matching one of the registered tools.
            tool_input: Dict of keyword arguments for the tool.

        Returns:
            Tool output dict. On unknown tool name, returns error dict.
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            logger.error("tool_agent.unknown_tool", tool_name=tool_name)
            return {"error": f"Unknown tool: '{tool_name}'"}

        try:
            if tool_name == "calculator":
                return await tool.run(expression=tool_input.get("expression", ""))
            if tool_name == "get_weather":
                return await tool.run(city=tool_input.get("city", ""))
            if tool_name == "wikipedia_search":
                return await tool.run(query=tool_input.get("query", ""))
            return {"error": f"No executor for tool '{tool_name}'"}
        except Exception as exc:
            logger.error("tool_agent.tool_execution_error", tool_name=tool_name, error=str(exc))
            return {"error": f"Tool execution failed: {exc}"}

    async def _persist_tool_result(
        self,
        task_id: str,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_output: dict[str, Any],
        duration_ms: int,
    ) -> None:
        """
        Insert a row into the tool_results table.

        Failures are logged as ERROR but do not abort the run.

        Args:
            task_id: FK → tasks.id.
            tool_name: One of 'calculator', 'get_weather', 'wikipedia_search'.
                       Must match the CHECK constraint in db/schema.sql.
            tool_input: Dict passed to the tool.
            tool_output: Dict returned by the tool.
            duration_ms: Tool execution wall-clock time.
        """
        if self._db_engine is None:
            logger.warning("tool_agent.no_db_engine_skip_persist", task_id=task_id)
            return

        # Map tool names to schema CHECK constraint values
        _SCHEMA_TOOL_NAMES = {
            "calculator": "calculator",
            "get_weather": "weather",
            "wikipedia_search": "wikipedia",
        }
        schema_tool_name = _SCHEMA_TOOL_NAMES.get(tool_name, tool_name)
        error_val = tool_output.get("error")

        try:
            session_factory = async_sessionmaker(
                bind=self._db_engine,
                expire_on_commit=False,
                autoflush=False,
            )
            async with session_factory() as session:
                await session.execute(
                    text(
                        """
                        INSERT INTO tool_results (task_id, tool_name, input, output, error, duration_ms)
                        VALUES (:task_id, :tool_name, CAST(:input AS jsonb), CAST(:output AS jsonb),
                                :error, :duration_ms)
                        """
                    ),
                    {
                        "task_id": task_id,
                        "tool_name": schema_tool_name,
                        "input": json.dumps(tool_input),
                        "output": json.dumps(tool_output) if not error_val else None,
                        "error": error_val,
                        "duration_ms": duration_ms,
                    },
                )
                await session.commit()
            logger.info("tool_agent.tool_result_persisted", task_id=task_id, tool_name=schema_tool_name)
        except Exception as exc:
            logger.error("tool_agent.persist_failed", task_id=task_id, error=str(exc))

    async def _publish_event(
        self,
        run_id: str,
        task_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        """
        Publish an agent event to nexus.events Kafka topic.

        Failures are logged and swallowed — must not abort the agent run.

        Args:
            run_id: Parent orchestration run UUID.
            task_id: Task UUID.
            event_type: One of 'agent_start', 'agent_end'.
            payload: Arbitrary event data.
        """
        from shared.kafka_client import KafkaProducerFactory
        from shared.kafka_schemas import EventMessage

        try:
            producer = await KafkaProducerFactory.get_producer(
                bootstrap_servers=settings.kafka_bootstrap_servers
            )
            event = EventMessage(
                run_id=run_id,
                task_id=task_id,
                event_type=event_type,  # type: ignore[arg-type]
                source="tool_agent.agent",
                payload=payload,
            )
            await producer.send(
                settings.kafka_topic_events,
                value=event.model_dump_json().encode(),
            )
        except Exception as exc:
            logger.warning(
                "tool_agent.kafka_publish_failed",
                run_id=run_id,
                task_id=task_id,
                error=str(exc),
            )