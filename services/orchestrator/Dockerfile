# services/orchestrator/Dockerfile
# Hybrid Railway architecture: orchestrator + all internal agents in one image.
FROM python:3.11-slim

WORKDIR /app

# Copy shared modules first — cached layer
COPY services/shared/ ./shared/

# Install dependencies (merged orchestrator + all agents)
COPY services/orchestrator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download SentenceTransformer model at build time
# Avoids cold-start latency on first memory request
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copy orchestrator source (includes agents/ subdirectory)
COPY services/orchestrator/ .

EXPOSE 8001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]