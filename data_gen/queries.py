"""
Canonical query definitions for NEXUS Level 2 simulation.

20 queries across 4 categories (5 each). These are the fixed inputs used
by simulate_runs.py. Keeping them here (not inline in the runner) allows
tests to import them and verify category coverage without executing HTTP calls.
"""

from typing import TypedDict


class QueryDefinition(TypedDict):
    """A single simulation query with metadata."""

    category: str
    query: str
    expected_agents: list[str]  # Which agent types we expect to be dispatched


QUERY_CATEGORIES: dict[str, list[QueryDefinition]] = {
    "research": [
        {
            "category": "research",
            "query": "Explain how transformer attention mechanisms work and why they replaced RNNs",
            "expected_agents": ["search", "memory_write"],
        },
        {
            "category": "research",
            "query": "What are the key differences between RAG and fine-tuning for LLM customization?",
            "expected_agents": ["search", "memory_write"],
        },
        {
            "category": "research",
            "query": "Summarize the current state of multimodal AI models as of 2024",
            "expected_agents": ["search"],
        },
        {
            "category": "research",
            "query": "How does pgvector implement approximate nearest neighbor search using IVFFlat?",
            "expected_agents": ["search", "memory_write"],
        },
        {
            "category": "research",
            "query": "What are the main tradeoffs between Apache Kafka and RabbitMQ for event streaming?",
            "expected_agents": ["search"],
        },
    ],
    "code": [
        {
            "category": "code",
            "query": "Write a Python implementation of binary search that returns the index or -1 if not found, with type hints",
            "expected_agents": ["code"],
        },
        {
            "category": "code",
            "query": "Implement a Python async context manager for database connection pooling using asyncpg",
            "expected_agents": ["code"],
        },
        {
            "category": "code",
            "query": "Write a Python function that computes the Fibonacci sequence up to n using dynamic programming",
            "expected_agents": ["code"],
        },
        {
            "category": "code",
            "query": "Create a Python decorator that measures and logs function execution time using structlog",
            "expected_agents": ["code"],
        },
        {
            "category": "code",
            "query": "Write a Python class that implements an LRU cache using OrderedDict with a configurable max size",
            "expected_agents": ["code"],
        },
    ],
    "memory": [
        {
            "category": "memory",
            "query": "What topics have I researched before about transformer models?",
            "expected_agents": ["memory_read", "search"],
        },
        {
            "category": "memory",
            "query": "Recall any previous context I have about vector databases and similarity search",
            "expected_agents": ["memory_read"],
        },
        {
            "category": "memory",
            "query": "What Python code have I generated in previous sessions?",
            "expected_agents": ["memory_read"],
        },
        {
            "category": "memory",
            "query": "Find and summarize anything I know about Apache Kafka from past queries",
            "expected_agents": ["memory_read", "search"],
        },
        {
            "category": "memory",
            "query": "What AI architecture topics have come up in my previous questions?",
            "expected_agents": ["memory_read"],
        },
    ],
    "tool": [
        {
            "category": "tool",
            "query": "Calculate the compound interest on $10,000 at 5% annual rate compounded monthly for 10 years",
            "expected_agents": ["tool"],
        },
        {
            "category": "tool",
            "query": "What is the current weather in San Francisco?",
            "expected_agents": ["tool"],
        },
        {
            "category": "tool",
            "query": "Look up information about the history of PostgreSQL on Wikipedia",
            "expected_agents": ["tool"],
        },
        {
            "category": "tool",
            "query": "Calculate: if a model processes 1.5 million tokens per day at $3 per million tokens, what is the monthly cost?",
            "expected_agents": ["tool"],
        },
        {
            "category": "tool",
            "query": "What is the current weather in London and convert the temperature from Celsius to Fahrenheit?",
            "expected_agents": ["tool"],
        },
    ],
}

# Flat list of all 20 queries in deterministic order
ALL_QUERIES: list[QueryDefinition] = [
    query
    for category_queries in QUERY_CATEGORIES.values()
    for query in category_queries
]

assert len(ALL_QUERIES) == 20, f"Expected 20 queries, got {len(ALL_QUERIES)}"