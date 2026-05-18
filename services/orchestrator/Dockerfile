# services/orchestrator/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy shared modules first — separate layer, cached unless shared/ changes
COPY services/shared/ ./shared/

# Install dependencies
COPY services/orchestrator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service source
COPY services/orchestrator/ .

EXPOSE 8001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]