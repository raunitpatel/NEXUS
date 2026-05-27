# ADR-002: Use pgvector for Vector Storage

**Status:** Accepted  
**Date:** 2025-05
**Deciders:** NEXUS engineering

---

## Context

The Memory Agent needs to store 384-dimension embeddings from `all-MiniLM-L6-v2` and perform approximate nearest-neighbour (ANN) cosine similarity search at query time. The system already uses PostgreSQL 15 as its primary database.

Three options were evaluated: pgvector (PostgreSQL extension), Pinecone (managed vector database), and Qdrant (self-hosted vector database).

## Decision

Use **pgvector** (`pgvector/pgvector:pg15` Docker image) with an IVFFlat index in `db/schema.sql`.

## Alternatives Considered

### Pinecone

Pinecone is a fully managed vector database with excellent query performance. However:
- Adds an external paid dependency with no free tier at meaningful scale
- Requires managing a separate API key and service
- Cross-service latency: every memory query requires an HTTPS call to Pinecone's API
- Overkill for a portfolio project with < 10k vectors

### Qdrant

Qdrant is a performant self-hosted vector database. However:
- Adds another Docker container to manage
- Separate data store means vectors are decoupled from the relational data they reference
- More operational complexity for no meaningful performance gain at NEXUS scale

## Consequences

**Positive:**
- Zero additional infrastructure — vectors live in the same PostgreSQL instance
- Single backup strategy covers all data
- JOINs between `embeddings_metadata` and `runs`/`tasks` are trivially fast
- pgvector `<=>` cosine distance operator integrates with standard SQL WHERE clauses
- `pgvector/pgvector:pg15` Docker image is a drop-in replacement

**Negative:**
- IVFFlat index requires `VACUUM` and reindexing as the vector count grows beyond ~1M
- Not suitable for billion-scale retrieval (use Pinecone then)
- `lists=100` IVFFlat parameter is appropriate for the current scale; must be tuned upward in production

## Implementation

- `db/schema.sql` — `embeddings_metadata` table with `vector(384)` column and IVFFlat index
- `services/orchestrator/agents/memory_agent/pgvector_store.py` — `insert_embedding()` and `cosine_search()`
- `services/orchestrator/agents/memory_agent/embeddings.py` — `EmbeddingModel` singleton wrapping `sentence-transformers`