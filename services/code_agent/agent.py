"""
Code Agent core — generate-execute-debug loop with provider-agnostic LLM.

Three-phase pipeline per iteration:
  1. Generate (or fix) code via LLM call
  2. Execute code via CodeExecutor (subprocess sandbox)
  3. Emit code_iteration Kafka event for SSE streaming

Maximum MAX_ITERATIONS attempts. Returns the last result regardless of success.

Usage:
    agent = CodeAgent()
    result = await agent.run(
        task_id="t1",
        run_id="r1",
        user_id="u1",
        instruction="Write a function that returns the Fibonacci sequence up to n",
    )
"""

from __future__ import annotations

import re
import time
from typing import Any

from shared.metrics import (
    agent_task_duration_seconds,
    agent_tasks_total,
    llm_tokens_total,
    llm_requests_total,
)

import structlog

from config import settings
from executor import CodeExecutor, ExecutionResult
from llm_provider import LLMProviderError, get_llm_provider

logger = structlog.get_logger(__name__)

# ── System prompts ────────────────────────────────────────────────────────────

_WRITE_CODE_SYSTEM = """\
You are an expert Python programmer. Your job is to write clean, correct Python code
that fulfils the given instruction.

Rules:
1. Return ONLY the raw Python code — no markdown, no code fences, no explanation.
2. The code must be self-contained and runnable with `python3 -c <code>`.
3. Include all necessary imports at the top.
4. Print the result of any function calls so execution produces visible output.
5. Do not use triple-quoted strings that would break when passed to -c.
   Use single or double quoted strings, or escape newlines with \\n.
"""

_FIX_CODE_SYSTEM = """\
You are an expert Python debugger. You will be given Python code that failed to execute
and the error output. Your job is to fix the code.

Rules:
1. Return ONLY the corrected raw Python code — no markdown, no code fences, no explanation.
2. The code must be self-contained and runnable with `python3 -c <code>`.
3. Include all necessary imports.
4. Address ONLY the error shown — do not rewrite unrelated parts.
5. Print the result so execution produces visible output.
"""


class CodeAgentResult:
    """
    Return value from CodeAgent.run().

    Attributes:
        code: Final code string (last iteration's code).
        stdout: stdout from the final execution attempt.
        stderr: stderr from the final execution attempt.
        exit_code: Exit code from the final execution attempt.
        iterations: Total number of generate-execute iterations performed.
        success: True if the final exit_code is 0.
    """

    def __init__(
        self,
        code: str,
        stdout: str,
        stderr: str,
        exit_code: int,
        iterations: int,
    ) -> None:
        self.code = code
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.iterations = iterations
        self.success = exit_code == 0

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a dict suitable for JSON response and Kafka payload."""
        return {
            "code": self.code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "iterations": self.iterations,
            "success": self.success,
        }


class CodeAgent:
    """
    NEXUS Code Agent — iterative generate-execute-debug loop.

    Uses a provider-agnostic LLM to generate Python code, then executes it
    in a sandboxed subprocess. On failure, calls the LLM again with the error
    to produce a fix. Maximum settings.max_iterations attempts.

    Emits one code_iteration Kafka event to nexus.events per iteration so
    the Gateway SSE router can stream live thought traces to the frontend.
    """

    def __init__(self) -> None:
        """Initialise the Code Agent with configured LLM provider and executor."""
        self._provider = get_llm_provider()
        self._executor = CodeExecutor(timeout=settings.execution_timeout_seconds)
        self._max_iterations = settings.max_iterations

    async def run(
        self,
        task_id: str,
        run_id: str,
        user_id: str,
        instruction: str,
        language: str = "python",
    ) -> CodeAgentResult:
        """
        Execute the generate-execute-debug loop for a coding instruction.

        Calls write_code on iteration 1, then fix_code on subsequent iterations
        if execution fails. Publishes one code_iteration Kafka event per attempt.

        Args:
            task_id: UUID of the task row in Postgres tasks table.
            run_id: UUID of the parent orchestration run.
            user_id: UUID of the authenticated user.
            instruction: Natural language coding instruction.
            language: Target programming language. Only "python" supported.

        Returns:
            CodeAgentResult with final code, stdout, stderr, exit_code, iterations.
        """
        start_ms = time.monotonic()

        await self._publish_event(
            run_id=run_id,
            task_id=task_id,
            event_type="agent_start",
            payload={"instruction": instruction[:200], "agent": "code"},
        )

        code = ""
        execution: ExecutionResult | None = None

        for iteration in range(1, self._max_iterations + 1):
            logger.info(
                "code_agent.iteration_start",
                run_id=run_id,
                task_id=task_id,
                iteration=iteration,
                max_iterations=self._max_iterations,
            )

            # Step 1: Generate or fix code via LLM
            try:
                if iteration == 1:
                    code = await self._write_code(instruction, language)
                else:
                    assert execution is not None
                    code = await self._fix_code(
                        code=code,
                        error=execution.stderr,
                        instruction=instruction,
                        language=language,
                    )
            except LLMProviderError as exc:
                logger.error(
                    "code_agent.llm_error",
                    run_id=run_id,
                    task_id=task_id,
                    iteration=iteration,
                    error=str(exc),
                )
                elapsed = int((time.monotonic() - start_ms) * 1000)
                result = CodeAgentResult(
                    code=code,
                    stdout="",
                    stderr=f"LLM provider error: {exc}",
                    exit_code=1,
                    iterations=iteration,
                )
                agent_task_duration_seconds.labels(agent="code", status="error").observe(
                    int((time.monotonic() - start_ms) * 1000) / 1000
                )
                agent_tasks_total.labels(agent="code", status="error").inc()
                await self._publish_event(
                    run_id=run_id,
                    task_id=task_id,
                    event_type="agent_end",
                    payload={**result.to_dict(), "error": str(exc)},
                )
                return result

            # Step 2: Execute code
            execution = await self._executor.execute(code=code, language=language)

            logger.info(
                "code_agent.iteration_complete",
                run_id=run_id,
                task_id=task_id,
                iteration=iteration,
                exit_code=execution.exit_code,
                stdout_len=len(execution.stdout),
                stderr_len=len(execution.stderr),
            )

            # Step 3: Emit code_iteration Kafka event
            await self._publish_event(
                run_id=run_id,
                task_id=task_id,
                event_type="code_iteration",
                payload={
                    "iteration": iteration,
                    "code": code[:1000],  # truncate for Kafka payload size
                    "exit_code": execution.exit_code,
                    "stdout": execution.stdout[:500],
                    "stderr": execution.stderr[:500],
                },
            )

            # Step 4: Return early on success
            if execution.exit_code == 0:
                elapsed = int((time.monotonic() - start_ms) * 1000)
                result = CodeAgentResult(
                    code=code,
                    stdout=execution.stdout,
                    stderr=execution.stderr,
                    exit_code=0,
                    iterations=iteration,
                )
                logger.info(
                    "code_agent.success",
                    run_id=run_id,
                    task_id=task_id,
                    iterations=iteration,
                    elapsed_ms=elapsed,
                )

                agent_task_duration_seconds.labels(agent="code", status="success").observe(elapsed / 1000)
                agent_tasks_total.labels(agent="code", status="success").inc()
                await self._publish_event(
                    run_id=run_id,
                    task_id=task_id,
                    event_type="agent_end",
                    payload=result.to_dict(),
                )
                return result

        # Exhausted all iterations
        assert execution is not None
        elapsed = int((time.monotonic() - start_ms) * 1000)

        result = CodeAgentResult(
            code=code,
            stdout=execution.stdout,
            stderr=execution.stderr,
            exit_code=execution.exit_code,
            iterations=self._max_iterations,
        )

        logger.warning(
            "code_agent.max_iterations_reached",
            run_id=run_id,
            task_id=task_id,
            exit_code=execution.exit_code,
            elapsed_ms=elapsed,
        )

        agent_task_duration_seconds.labels(agent="code", status="error").observe(elapsed / 1000)
        agent_tasks_total.labels(agent="code", status="error").inc()

        await self._publish_event(
            run_id=run_id,
            task_id=task_id,
            event_type="agent_end",
            payload={**result.to_dict(), "error": "Max iterations reached"},
        )

        return result

    async def _write_code(self, instruction: str, language: str) -> str:
        """
        Ask the LLM to write code fulfilling the instruction.

        Args:
            instruction: Natural language description of what the code should do.
            language: Target programming language.

        Returns:
            Raw code string (markdown stripped).

        Raises:
            LLMProviderError: If the LLM call fails.
        """
        user_msg = (
            f"Write {language} code that fulfils this instruction:\n\n{instruction}"
        )
        response = await self._provider.complete(
            system=_WRITE_CODE_SYSTEM,
            user=user_msg,
            json_mode=False,
        )
        return self._extract_code(response.content)

    async def _fix_code(
        self,
        code: str,
        error: str,
        instruction: str,
        language: str,
    ) -> str:
        """
        Ask the LLM to fix failing code given its error output.

        Args:
            code: The code that failed execution.
            error: stderr from the failed execution.
            instruction: Original instruction (for context).
            language: Target programming language.

        Returns:
            Corrected raw code string (markdown stripped).

        Raises:
            LLMProviderError: If the LLM call fails.
        """
        user_msg = (
            f"Original instruction: {instruction}\n\n"
            f"Code that failed:\n{code}\n\n"
            f"Error output:\n{error}\n\n"
            f"Fix the {language} code to resolve this error."
        )
        response = await self._provider.complete(
            system=_FIX_CODE_SYSTEM,
            user=user_msg,
            json_mode=False,
        )
        return self._extract_code(response.content)

    def _extract_code(self, raw: str) -> str:
        """
        Strip markdown code fences from LLM output.

        Some LLMs return code wrapped in ```python ... ``` despite instructions.
        This method handles that gracefully without failing.

        Args:
            raw: Raw LLM response string.

        Returns:
            Clean code string with fences removed.
        """
        # Match ```python ... ``` or ``` ... ``` blocks
        fence_pattern = re.compile(
            r"```(?:python|py)?\s*\n?(.*?)```",
            re.DOTALL,
        )
        match = fence_pattern.search(raw)
        if match:
            return match.group(1).strip()
        return raw.strip()

    async def _publish_event(
        self,
        run_id: str,
        task_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        """
        Publish a code agent event to nexus.events Kafka topic.

        Failures are logged and swallowed — must not abort the agent run.

        Args:
            run_id: Parent orchestration run UUID.
            task_id: Task UUID.
            event_type: One of 'agent_start', 'agent_end', 'code_iteration'.
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
                source="code_agent.agent",
                payload=payload,
            )
            await producer.send(
                settings.kafka_topic_events,
                value=event.model_dump_json().encode(),
            )
        except Exception as exc:
            logger.warning(
                "code_agent.kafka_publish_failed",
                run_id=run_id,
                task_id=task_id,
                error=str(exc),
            )