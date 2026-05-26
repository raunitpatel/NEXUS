# services/code_agent/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy shared modules first — separate cached layer
COPY services/shared/ ./shared/

# Install dependencies
COPY services/code_agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service source
COPY services/code_agent/ .

EXPOSE 8003

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]