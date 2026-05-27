# ADR-001: Use LangGraph for Agent Orchestration

**Status:** Accepted  
**Date:** 2025-05
**Deciders:** NEXUS engineering

---

## Context

NEXUS needs to orchestrate multiple specialized AI agents to answer a user query. The orchestration logic must:
- Decompose a natural-language query into a structured task plan
- Dispatch tasks to agents in dependency order
- Retry failed tasks up to 3 times before aborting
- Synthesize all agent results into a final answer
- Stream progress events to the browser in real time

Three options were evaluated: raw asyncio task management, CrewAI, and LangGraph.

## Decision

Use **LangGraph** (`langgraph==0.1.19`) with a `StateGraph[OrchestratorState]` defined in `services/orchestrator/graph.py`.

## Alternatives Considered

### Raw asyncio

Implementing the state machine manually with `asyncio.Task` and shared state would give full control but requires building retry logic, conditional routing, and state merging from scratch. Estimated 3× more code. State bugs are hard to reproduce.

### CrewAI

CrewAI provides a higher-level agent abstraction but:
- Forces a "crew" mental model that doesn't match NEXUS's per-task dispatch pattern
- Less control over retry logic and conditional edges
- Harder to integrate custom SSE event emission per node
- Less transparent state — harder to stream to a UI

## Consequences

**Positive:**
- State machine topology is explicit and readable in `graph.py`
- Conditional routing is pure Python functions (`_route_after_validate`, etc.)
- Each node is an isolated `async def` — trivial to unit test with mocked dependencies
- LangGraph's `StateGraph` handles state merging; nodes return partial dicts

**Negative:**
- LangGraph is a relatively new library; API stability is not guaranteed
- Adds a non-trivial dependency (`langgraph`, `langchain-core`) for what is essentially a state machine
- Graph compilation happens at startup — must not run per-request

## Implementation

- `services/orchestrator/graph.py` — `build_graph()` function
- `services/orchestrator/state.py` — `OrchestratorState` TypedDict
- `services/orchestrator/nodes/` — one file per node