"""
Code Agent — internal module for the NEXUS Orchestrator.

Previously a standalone FastAPI service (services/code_agent/).
Now a direct Python import used by nodes/dispatch_next_task.py.
"""

from __future__ import annotations

import re
import time
from typing import Any

import structlog
from shared.metrics import agent_task_duration_seconds, agent_tasks_total

logger = structlog.get_logger(__name__)

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
    """Return value from CodeAgent.run()."""

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
    NEXUS Code Agent — internal Python class, not a FastAPI service.

    Called directly from nodes/dispatch_next_task.py.
    """

    def __init__(self) -> None:
        from llm_provider import get_llm_provider
        from config import settings
        from .executor import CodeExecutor

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
        """Execute the generate-execute-debug loop."""
        from llm_provider import LLMProviderError

        start_ms = time.monotonic()

        await self._publish_event(
            run_id=run_id,
            task_id=task_id,
            event_type="agent_start",
            payload={"instruction": instruction, "agent": "code"},
        )

        code = ""
        execution = None

        for iteration in range(1, self._max_iterations + 1):
            logger.info(
                "code_agent.iteration_start",
                run_id=run_id,
                task_id=task_id,
                iteration=iteration,
            )

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
                logger.error("code_agent.llm_error", run_id=run_id, task_id=task_id, error=str(exc))
                elapsed = int((time.monotonic() - start_ms) * 1000)
                result = CodeAgentResult(
                    code=code,
                    stdout="",
                    stderr=f"LLM provider error: {exc}",
                    exit_code=1,
                    iterations=iteration,
                )
                agent_task_duration_seconds.labels(agent="code", status="error").observe(elapsed / 1000)
                agent_tasks_total.labels(agent="code", status="error").inc()
                await self._publish_event(
                    run_id=run_id,
                    task_id=task_id,
                    event_type="agent_end",
                    payload={**result.to_dict(), "error": str(exc)},
                )
                return result

            execution = await self._executor.execute(code=code, language=language)

            await self._publish_event(
                run_id=run_id,
                task_id=task_id,
                event_type="code_iteration",
                payload={
                    "iteration": iteration,
                    "code": code,
                    "exit_code": execution.exit_code,
                    "stdout": execution.stdout,
                    "stderr": execution.stderr,
                },
            )

            if execution.exit_code == 0:
                elapsed = int((time.monotonic() - start_ms) * 1000)
                result = CodeAgentResult(
                    code=code,
                    stdout=execution.stdout,
                    stderr=execution.stderr,
                    exit_code=0,
                    iterations=iteration,
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

        assert execution is not None
        elapsed = int((time.monotonic() - start_ms) * 1000)
        result = CodeAgentResult(
            code=code,
            stdout=execution.stdout,
            stderr=execution.stderr,
            exit_code=execution.exit_code,
            iterations=self._max_iterations,
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
        user_msg = f"Write {language} code that fulfils this instruction:\n\n{instruction}"
        response = await self._provider.complete(
            system=_WRITE_CODE_SYSTEM,
            user=user_msg,
            json_mode=False,
        )
        return self._extract_code(response.content)

    async def _fix_code(self, code: str, error: str, instruction: str, language: str) -> str:
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
        fence_pattern = re.compile(r"```(?:python|py)?\s*\n?(.*?)```", re.DOTALL)
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
        from config import settings
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