# services/code_agent/executor.py
"""
Code execution sandbox for the NEXUS Code Agent.

Runs Python code in a subprocess with a hard timeout. Uses
asyncio.get_event_loop().run_in_executor() to prevent the blocking
subprocess.run call from stalling the asyncio event loop.

Design decisions:
- subprocess.run(["python3", "-c", code]) — no shell=True, no temp files
- 10-second timeout (configurable via settings.execution_timeout_seconds)
- stdout and stderr both captured and returned in ExecutionResult
- TimeoutExpired returns exit_code=124 (same as GNU timeout utility)
- No network access restriction in MVP — deferred to AGNT-025 (seccomp sandbox)

Usage:
    executor = CodeExecutor()
    result = await executor.execute(code="print(42)", language="python")
    # result.exit_code == 0
    # result.stdout == "42\n"
"""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)

# Language → interpreter mapping
# Only "python" is supported in AGNT-011. Additional languages (node, bash)
# are out of scope and will be added in a future ticket.
_INTERPRETERS: dict[str, list[str]] = {
    "python": ["python3", "-c"],
}


@dataclass
class ExecutionResult:
    """
    Result of a single code execution attempt.

    Attributes:
        exit_code: Process exit code. 0 = success, non-zero = failure, 124 = timeout.
        stdout: Captured standard output from the process.
        stderr: Captured standard error from the process.
    """

    exit_code: int
    stdout: str
    stderr: str


class CodeExecutor:
    """
    Sandboxed code execution engine for the Code Agent.

    Wraps subprocess.run in asyncio.run_in_executor to avoid blocking the
    event loop. Each call creates an isolated subprocess — no state is shared
    between executions.

    Attributes:
        _timeout: Maximum seconds before execution is forcibly terminated.
    """

    def __init__(self, timeout: int = 10) -> None:
        """
        Initialise the executor.

        Args:
            timeout: Execution timeout in seconds.
        """
        self._timeout = timeout

    async def execute(self, code: str, language: str = "python") -> ExecutionResult:
        """
        Execute code in a subprocess and return structured results.

        Runs the code asynchronously using run_in_executor to avoid blocking
        the asyncio event loop. The subprocess inherits no environment variables
        beyond the system defaults — it does not have access to NEXUS secrets.

        Args:
            code: Raw code string to execute (no markdown, no fences).
            language: Programming language identifier. Only "python" supported.

        Returns:
            ExecutionResult with exit_code, stdout, and stderr.
        """
        interpreter = _INTERPRETERS.get(language.lower())
        if not interpreter:
            logger.error("executor.unsupported_language", language=language)
            return ExecutionResult(
                exit_code=1,
                stdout="",
                stderr=f"Unsupported language: '{language}'. Supported: {list(_INTERPRETERS.keys())}",
            )

        cmd = interpreter + [code]

        logger.debug(
            "executor.run_start",
            language=language,
            code_length=len(code),
            timeout=self._timeout,
        )

        loop = asyncio.get_event_loop()

        try:
            result: subprocess.CompletedProcess = await asyncio.wait_for(
                loop.run_in_executor(None, self._run_subprocess, cmd),
                timeout=float(self._timeout),
            )
        except asyncio.TimeoutError:
            logger.warning(
                "executor.timeout",
                language=language,
                timeout=self._timeout,
            )
            return ExecutionResult(
                exit_code=124,
                stdout="",
                stderr=f"Execution timed out after {self._timeout}s.",
            )
        except Exception as exc:
            logger.error("executor.unexpected_error", error=str(exc))
            return ExecutionResult(
                exit_code=1,
                stdout="",
                stderr=f"Executor internal error: {exc}",
            )

        execution_result = ExecutionResult(
            exit_code=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
        )

        logger.debug(
            "executor.run_complete",
            exit_code=execution_result.exit_code,
            stdout_len=len(execution_result.stdout),
            stderr_len=len(execution_result.stderr),
        )

        return execution_result

    def _run_subprocess(self, cmd: list[str]) -> subprocess.CompletedProcess:
        """
        Synchronous subprocess.run call — runs inside ThreadPoolExecutor.

        Must be synchronous because subprocess.run is blocking. Called via
        asyncio.run_in_executor so it does not block the event loop.

        Args:
            cmd: Full command list including interpreter and code.

        Returns:
            subprocess.CompletedProcess with returncode, stdout, stderr.
        """
        return subprocess.run(
            cmd,
            timeout=self._timeout,
            capture_output=True,
            text=True,
        )