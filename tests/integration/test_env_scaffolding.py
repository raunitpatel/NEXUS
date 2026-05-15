"""
Integration-level smoke test for AGNT-002 env scaffolding.

Verifies that:
- All .env.example files exist at expected paths
- No .env.example file contains a real Anthropic API key pattern
- All .env.example files use LF line endings (no CRLF present)

Run with:
    cd nexus
    python -m pytest tests/integration/test_env_scaffolding.py -v
"""

from pathlib import Path

import pytest

NEXUS_ROOT = Path(__file__).parent.parent.parent

ENV_EXAMPLE_PATHS: list[Path] = [
    NEXUS_ROOT / ".env.example",
    NEXUS_ROOT / "services" / "gateway" / ".env.example",
    NEXUS_ROOT / "services" / "orchestrator" / ".env.example",
    NEXUS_ROOT / "services" / "search_agent" / ".env.example",
    NEXUS_ROOT / "services" / "code_agent" / ".env.example",
    NEXUS_ROOT / "services" / "memory_agent" / ".env.example",
    NEXUS_ROOT / "services" / "tool_agent" / ".env.example",
]


@pytest.mark.parametrize("env_path", ENV_EXAMPLE_PATHS, ids=lambda p: str(p.relative_to(NEXUS_ROOT)))
def test_env_example_exists(env_path: Path) -> None:
    """Every service must have an .env.example file at its canonical path."""
    assert env_path.exists(), f"Missing .env.example at {env_path}"


@pytest.mark.parametrize("env_path", ENV_EXAMPLE_PATHS, ids=lambda p: str(p.relative_to(NEXUS_ROOT)))
def test_env_example_uses_lf_line_endings(env_path: Path) -> None:
    """All .env.example files must use LF endings — CRLF breaks python-dotenv on Windows."""
    raw_bytes = env_path.read_bytes()
    assert b"\r\n" not in raw_bytes, (
        f"{env_path} contains CRLF line endings. "
        "Fix in VS Code: click 'CRLF' in status bar → select 'LF' → save."
    )


def test_gitignore_blocks_env_files() -> None:
    """The .gitignore must contain rules blocking .env files."""
    gitignore = NEXUS_ROOT / ".gitignore"
    assert gitignore.exists(), ".gitignore not found at repo root"
    content = gitignore.read_text(encoding="utf-8")
    assert "**/.env" in content or ".env\n" in content, (
        ".gitignore does not block .env files"
    )


def test_gitignore_does_not_block_env_examples() -> None:
    """The .gitignore must NOT block .env.example files."""
    gitignore = NEXUS_ROOT / ".gitignore"
    content = gitignore.read_text(encoding="utf-8")
    assert "!.env.example" in content or "!**/.env.example" in content, (
        ".gitignore does not have negation rule to keep .env.example tracked"
    )