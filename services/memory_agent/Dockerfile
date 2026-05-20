FROM python:3.11-slim

WORKDIR /app

# Copy shared modules first — separate cached layer
COPY services/shared/ ./shared/

# Install dependencies
COPY services/memory_agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the SentenceTransformer model at build time
# This avoids a slow first-request cold start in production
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copy service source
COPY services/memory_agent/ .

EXPOSE 8004

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004"]