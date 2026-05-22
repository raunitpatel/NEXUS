"""
NEXUS Level 2 Data Generation — simulate_runs.py

Fires 20 real HTTP requests through the full NEXUS orchestration pipeline,
consuming SSE streams to detect run completion. Produces genuine Claude API
responses, Kafka events, and pgvector embeddings.

Usage:
    python data_gen/simulate_runs.py                    # Full 20-run simulation
    python data_gen/simulate_runs.py --dry-run          # 1 run, no report
    python data_gen/simulate_runs.py --count 5          # First 5 queries only
    python data_gen/simulate_runs.py --verify-only      # DB verification only

Requirements:
    All NEXUS Docker services running (gateway, orchestrator, all agents)
    data_gen/.env configured with GATEWAY_BASE_URL and DATABASE_URL_LOCAL
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg
import httpx

# Add nexus root to path so data_gen.config is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from data_gen.config import settings
from data_gen.queries import ALL_QUERIES, QueryDefinition

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("simulate_runs")

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class RunResult:
    """
    Result of a single simulated run.

    Attributes:
        run_id: UUID assigned by the Gateway on run creation.
        query: The query string sent to the Gateway.
        category: Query category (research/code/memory/tool).
        status: Terminal status — "completed", "failed", "timeout", "error".
        event_count: Number of SSE events received before terminal event.
        duration_ms: Wall-clock time from run creation to SSE termination.
        final_output: The synthesized answer from the run_complete event payload.
        error: Error message if status is not "completed".
    """

    run_id: str
    query: str
    category: str
    status: str
    event_count: int
    duration_ms: int
    final_output: str = ""
    error: str = ""


@dataclass
class SimulationReport:
    """
    Summary report written to data_gen/results/simulation_report.json.

    Attributes:
        started_at: ISO 8601 UTC timestamp when simulation began.
        completed_at: ISO 8601 UTC timestamp when simulation ended.
        total_runs: Total number of runs attempted.
        successful_runs: Runs that completed with status "completed".
        failed_runs: Runs that completed with status "failed".
        timeout_runs: Runs that exceeded RUN_TIMEOUT_SECONDS.
        error_runs: Runs that failed due to HTTP/connection errors.
        total_duration_seconds: Wall-clock time for all 20 runs.
        results: Per-run results list.
        db_verification: Results of post-simulation DB checks.
    """

    started_at: str
    completed_at: str = ""
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    timeout_runs: int = 0
    error_runs: int = 0
    total_duration_seconds: float = 0.0
    results: list[RunResult] = field(default_factory=list)
    db_verification: dict[str, Any] = field(default_factory=dict)


# ── SimulationClient ──────────────────────────────────────────────────────────


class SimulationClient:
    """
    HTTP client for the NEXUS simulation.

    Handles authentication, run creation, and SSE stream consumption.
    All requests use a single shared httpx.AsyncClient session for
    connection pool efficiency across 20 runs.

    Attributes:
        _client: Shared async httpx client.
        _token: JWT access token set after login().
        _base_url: Gateway base URL from settings.
    """

    def __init__(self) -> None:
        """Initialise the simulation client with a shared httpx session."""
        self._client = httpx.AsyncClient(
            base_url=settings.gateway_base_url,
            timeout=httpx.Timeout(30.0, read=settings.run_timeout_seconds + 10),
        )
        self._token: str = ""

    async def __aenter__(self) -> SimulationClient:
        """Enter async context — client is already initialised."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Close the shared httpx client on context exit."""
        await self._client.aclose()

    @property
    def _auth_headers(self) -> dict[str, str]:
        """Return Authorization header dict for authenticated requests."""
        return {"Authorization": f"Bearer {self._token}"}

    async def register(self) -> bool:
        """
        Register the simulation user account.

        Safe to call if user already exists — returns True on 201 or 409.

        Returns:
            True if registration succeeded or user already exists.
        """
        try:
            response = await self._client.post(
                "/api/v1/auth/register",
                json={
                    "email": settings.sim_user_email,
                    "password": settings.sim_user_password,
                    "display_name": settings.sim_user_display_name,
                },
            )
            if response.status_code in (201, 409):
                logger.info(
                    "register: %s (HTTP %d)",
                    "already exists" if response.status_code == 409 else "created",
                    response.status_code,
                )
                return True
            logger.error("register failed: HTTP %d — %s", response.status_code, response.text[:200])
            return False
        except httpx.RequestError as exc:
            logger.error("register connection error: %s", exc)
            return False

    async def login(self) -> bool:
        """
        Authenticate the simulation user and store the JWT token.

        Returns:
            True if login succeeded and token stored.
        """
        try:
            response = await self._client.post(
                "/api/v1/auth/login",
                json={
                    "email": settings.sim_user_email,
                    "password": settings.sim_user_password,
                },
            )
            if response.status_code == 200:
                self._token = response.json()["access_token"]
                logger.info("login: success (token: %s...)", self._token[:20])
                return True
            logger.error("login failed: HTTP %d — %s", response.status_code, response.text[:200])
            return False
        except httpx.RequestError as exc:
            logger.error("login connection error: %s", exc)
            return False

    async def create_run(self, query: str) -> str | None:
        """
        Create a new run via POST /api/v1/runs.

        Args:
            query: The user query string to send.

        Returns:
            run_id UUID string on success, None on failure.
        """
        try:
            response = await self._client.post(
                "/api/v1/runs",
                json={"query": query},
                headers=self._auth_headers,
            )
            if response.status_code == 201:
                run_id: str = response.json()["run_id"]
                return run_id
            logger.error(
                "create_run failed for query '%s...': HTTP %d — %s",
                query[:40],
                response.status_code,
                response.text[:200],
            )
            return None
        except httpx.RequestError as exc:
            logger.error("create_run connection error: %s", exc)
            return None

    async def consume_sse_until_complete(
        self,
        run_id: str,
    ) -> tuple[str, int, str]:
        """
        Subscribe to the SSE stream for a run and consume until terminal event.

        Parses Server-Sent Events line-by-line. Returns when a `run_complete`
        or `run_error` event is received, or when timeout is exceeded.

        Args:
            run_id: UUID of the run to subscribe to.

        Returns:
            Tuple of (status, event_count, final_output) where:
                status: "completed", "failed", or "timeout"
                event_count: Number of events received before terminal
                final_output: Content from run_complete payload, or error message

        Raises:
            Never raises — all exceptions are caught and returned as "error" status.
        """
        url = f"/api/v1/sse/{run_id}?token={self._token}"
        event_count = 0
        final_output = ""

        try:
            async with self._client.stream(
                "GET",
                url,
                headers={"Accept": "text/event-stream"},
                timeout=httpx.Timeout(settings.run_timeout_seconds + 5, connect=10.0),
            ) as response:
                if response.status_code != 200:
                    logger.warning(
                        "SSE stream %s returned HTTP %d", run_id[:8], response.status_code
                    )
                    return "error", 0, f"HTTP {response.status_code}"

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or line.startswith(":"):
                        # Empty line or SSE comment/keepalive
                        continue

                    if line.startswith("data:"):
                        raw_data = line[5:].strip()
                        if not raw_data or raw_data == "[DONE]":
                            continue

                        try:
                            event = json.loads(raw_data)
                        except json.JSONDecodeError:
                            continue

                        event_type = event.get("event_type", event.get("type", ""))
                        event_count += 1

                        logger.debug(
                            "  run %s — event #%d: %s",
                            run_id[:8],
                            event_count,
                            event_type,
                        )

                        if event_type == "run_complete":
                            payload = event.get("payload", {})
                            final_output = payload.get("output", "") or ""
                            return "completed", event_count, final_output

                        if event_type == "run_error":
                            payload = event.get("payload", {})
                            error_msg = payload.get("error", "unknown error")
                            return "failed", event_count, error_msg

        except asyncio.TimeoutError:
            logger.warning("SSE stream %s timed out after %ds", run_id[:8], settings.run_timeout_seconds)
            return "timeout", event_count, "timeout"
        except httpx.RequestError as exc:
            logger.error("SSE stream %s connection error: %s", run_id[:8], exc)
            return "error", event_count, str(exc)
        except Exception as exc:
            logger.error("SSE stream %s unexpected error: %s", run_id[:8], exc)
            return "error", event_count, str(exc)

        # Stream closed without terminal event
        return "failed", event_count, "stream closed without terminal event"


# ── Per-run orchestrator ──────────────────────────────────────────────────────


async def run_single(
    client: SimulationClient,
    query_def: QueryDefinition,
    semaphore: asyncio.Semaphore,
    run_index: int,
) -> RunResult:
    """
    Execute a single simulation run end-to-end.

    Creates the run, subscribes to SSE, waits for terminal event.
    Uses a semaphore to limit concurrent SSE subscriptions.

    Args:
        client: Authenticated SimulationClient instance.
        query_def: Query definition with category and query text.
        semaphore: Concurrency limiter.
        run_index: 1-based index for logging.

    Returns:
        RunResult with status, event count, and timing.
    """
    async with semaphore:
        start_ms = time.monotonic()
        query = query_def["query"]
        category = query_def["category"]

        logger.info(
            "[%02d/%d] Starting: [%s] %s...",
            run_index,
            len(ALL_QUERIES),
            category,
            query[:60],
        )

        # Step 1: Create run
        run_id = await client.create_run(query)
        if not run_id:
            duration_ms = int((time.monotonic() - start_ms) * 1000)
            logger.error("[%02d] Failed to create run", run_index)
            return RunResult(
                run_id="",
                query=query,
                category=category,
                status="error",
                event_count=0,
                duration_ms=duration_ms,
                error="Failed to create run via POST /api/v1/runs",
            )

        logger.info("[%02d] run_id=%s created — subscribing to SSE", run_index, run_id[:8])

        # Step 2: Consume SSE with timeout
        try:
            status, event_count, final_output_or_error = await asyncio.wait_for(
                client.consume_sse_until_complete(run_id),
                timeout=settings.run_timeout_seconds,
            )
        except asyncio.TimeoutError:
            status = "timeout"
            event_count = 0
            final_output_or_error = f"Run timed out after {settings.run_timeout_seconds}s"

        duration_ms = int((time.monotonic() - start_ms) * 1000)

        emoji = "✅" if status == "completed" else ("⚠️" if status == "failed" else "❌")
        logger.info(
            "%s [%02d] run %s — status=%s events=%d duration=%dms",
            emoji,
            run_index,
            run_id[:8],
            status,
            event_count,
            duration_ms,
        )

        return RunResult(
            run_id=run_id,
            query=query,
            category=category,
            status=status,
            event_count=event_count,
            duration_ms=duration_ms,
            final_output=final_output_or_error if status == "completed" else "",
            error=final_output_or_error if status != "completed" else "",
        )


# ── DB verification ───────────────────────────────────────────────────────────


async def verify_db(run_ids: list[str]) -> dict[str, Any]:
    """
    Run post-simulation Postgres verification queries.

    Checks that events and embeddings_metadata rows were created as expected.
    Uses asyncpg directly (not SQLAlchemy) matching the db/seed.py pattern.

    Args:
        run_ids: List of run UUIDs that were created during simulation.

    Returns:
        Dict with verification results and pass/fail status for each criterion.
    """
    results: dict[str, Any] = {}

    try:
        conn = await asyncpg.connect(settings.asyncpg_dsn())

        # Criterion 1: runs status distribution
        status_rows = await conn.fetch(
            "SELECT status, COUNT(*) AS cnt FROM runs WHERE id = ANY($1::uuid[]) GROUP BY status",
            run_ids,
        )
        results["run_status_distribution"] = {r["status"]: r["cnt"] for r in status_rows}

        # Criterion 2: events per run (must have ≥3 each)
        events_rows = await conn.fetch(
            """
            SELECT run_id::text, COUNT(*) AS cnt
            FROM events
            WHERE run_id = ANY($1::uuid[])
            GROUP BY run_id
            """,
            run_ids,
        )
        events_per_run = {r["run_id"]: r["cnt"] for r in events_rows}
        runs_with_enough_events = sum(1 for cnt in events_per_run.values() if cnt >= 3)
        results["runs_with_3plus_events"] = runs_with_enough_events
        results["total_events"] = sum(events_per_run.values())
        results["events_criterion_pass"] = runs_with_enough_events >= len(run_ids) * 0.8

        # Criterion 3: embeddings_metadata total rows
        total_embeddings = await conn.fetchval("SELECT COUNT(*) FROM embeddings_metadata")
        results["total_embeddings"] = total_embeddings

        # Per-run embedding counts for diagnostic output
        emb_rows = await conn.fetch(
            "SELECT run_id::text, COUNT(*) AS cnt FROM embeddings_metadata WHERE run_id = ANY($1::uuid[]) GROUP BY run_id",
            run_ids,
        )
        results["embeddings_per_run"] = {r["run_id"]: r["cnt"] for r in emb_rows}

        # Dynamic acceptance threshold: the original script expected >=40 total
        # embeddings for a full 20-run simulation. Make this proportional to the
        # number of runs being verified while keeping the historical minimum.
        expected_per_run = 2  # conservative expected embeddings per run
        expected_total = max(40, expected_per_run * max(1, len(run_ids)))
        results["expected_embeddings"] = expected_total
        results["embeddings_criterion_pass"] = total_embeddings >= expected_total

        await conn.close()

    except Exception as exc:
        logger.error("DB verification failed: %s", exc)
        results["error"] = str(exc)

    return results


# ── Main simulation runner ────────────────────────────────────────────────────


async def run_simulation(queries: list[QueryDefinition], dry_run: bool = False) -> SimulationReport:
    """
    Execute the full simulation: auth, run creation, SSE consumption, DB verification.

    Fires queries in batches of BATCH_SIZE using asyncio.gather with a
    concurrency semaphore. Writes simulation_report.json on completion.

    Args:
        queries: List of QueryDefinition dicts to simulate.
        dry_run: If True, skips DB verification and report file write.

    Returns:
        SimulationReport with all per-run results and DB verification data.
    """
    report = SimulationReport(
        started_at=datetime.now(timezone.utc).isoformat(),
        total_runs=len(queries),
    )

    simulation_start = time.monotonic()
    semaphore = asyncio.Semaphore(settings.max_concurrent_runs)

    async with SimulationClient() as client:
        # Auth
        logger.info("=== NEXUS Level 2 Simulation — %d runs ===", len(queries))
        logger.info("Gateway: %s", settings.gateway_base_url)

        if not await client.register():
            logger.error("Registration failed — aborting")
            return report

        if not await client.login():
            logger.error("Login failed — aborting")
            return report

        # Fire all runs with concurrency limit
        tasks = [
            run_single(client, query_def, semaphore, idx + 1)
            for idx, query_def in enumerate(queries)
        ]
        results: list[RunResult] = await asyncio.gather(*tasks)

    report.results = results
    report.completed_at = datetime.now(timezone.utc).isoformat()
    report.total_duration_seconds = time.monotonic() - simulation_start

    # Tally results
    for result in results:
        if result.status == "completed":
            report.successful_runs += 1
        elif result.status == "failed":
            report.failed_runs += 1
        elif result.status == "timeout":
            report.timeout_runs += 1
        else:
            report.error_runs += 1

    # DB verification
    if not dry_run:
        run_ids = [r.run_id for r in results if r.run_id]
        logger.info("Running DB verification for %d run IDs...", len(run_ids))
        report.db_verification = await verify_db(run_ids)

    # Print summary
    _print_summary(report)

    # Write report
    if not dry_run:
        report_path = RESULTS_DIR / "simulation_report.json"
        report_data = asdict(report)
        report_path.write_text(json.dumps(report_data, indent=2, default=str))
        logger.info("Report written to: %s", report_path)

    return report


def _print_summary(report: SimulationReport) -> None:
    """
    Print a formatted simulation summary to stdout.

    Args:
        report: Completed SimulationReport.
    """
    print("\n" + "=" * 60)
    print("NEXUS Level 2 Simulation — Results")
    print("=" * 60)
    print(f"Total runs:      {report.total_runs}")
    print(f"✅ Successful:   {report.successful_runs}")
    print(f"⚠️  Failed:       {report.failed_runs}")
    print(f"⏱️  Timed out:    {report.timeout_runs}")
    print(f"❌ Errors:       {report.error_runs}")
    print(f"Duration:        {report.total_duration_seconds:.1f}s")
    print(f"Success rate:    {report.successful_runs / max(report.total_runs, 1) * 100:.0f}%")

    if report.db_verification:
        print("\nDB Verification:")
        v = report.db_verification
        if "error" in v:
            print(f"  ❌ Error: {v['error']}")
        else:
            print(f"  Events (≥3/run):   {'✅' if v.get('events_criterion_pass') else '❌'} {v.get('runs_with_3plus_events', 0)} runs qualify")
            print(f"  Total events:      {v.get('total_events', 0)}")
            status_dist = v.get("run_status_distribution", {})
            print(f"  Run statuses:      {status_dist}")

    # Per-category breakdown
    print("\nPer-category results:")
    categories: dict[str, list[str]] = {}
    for r in report.results:
        categories.setdefault(r.category, []).append(r.status)
    for cat, statuses in categories.items():
        success = statuses.count("completed")
        print(f"  {cat:<12}: {success}/{len(statuses)} successful")

    print("=" * 60)

    # Pass/fail acceptance criteria
    success_rate = report.successful_runs / max(report.total_runs, 1)
    passed = success_rate >= 0.80
    print(f"\nAcceptance criteria (80% success rate): {'✅ PASSED' if passed else '❌ FAILED'}")
    if not passed:
        sys.exit(1)


# ── Entry point ───────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the simulation script."""
    parser = argparse.ArgumentParser(
        description="NEXUS Level 2 data generation — fires 20 real runs"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run 1 query only, skip DB verification and report file",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="Run only the first N queries (default: all 20)",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Skip simulation, only run DB verification queries",
    )
    parser.add_argument(
        "--category",
        choices=["research", "code", "memory", "tool"],
        default=None,
        help="Run only queries from a specific category",
    )
    return parser.parse_args()


async def main() -> None:
    """
    Entry point for simulate_runs.py.

    Parses CLI args, selects queries, runs simulation, exits with code 1
    if fewer than 80% of runs succeed.
    """
    args = _parse_args()

    if args.verify_only:
        logger.info("--verify-only: fetching all sim run IDs from DB")
        conn = await asyncpg.connect(settings.asyncpg_dsn())
        rows = await conn.fetch(
            "SELECT id::text FROM runs ORDER BY created_at DESC LIMIT 20"
        )
        run_ids = [r["id"] for r in rows]
        await conn.close()
        verification = await verify_db(run_ids)
        print(json.dumps(verification, indent=2))
        return

    queries = ALL_QUERIES

    if args.category:
        from data_gen.queries import QUERY_CATEGORIES
        queries = QUERY_CATEGORIES[args.category]
        logger.info("Filtered to category '%s': %d queries", args.category, len(queries))

    if args.dry_run:
        queries = queries[:1]
        logger.info("--dry-run: using 1 query")
    elif args.count:
        queries = queries[: args.count]
        logger.info("--count %d: using %d queries", args.count, len(queries))

    await run_simulation(queries, dry_run=args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())