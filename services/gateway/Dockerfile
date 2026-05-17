FROM python:3.11-slim

WORKDIR /app

# Copy shared modules first (cached layer)
COPY services/shared/ ./shared/

# Install dependencies
COPY services/gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service source
COPY services/gateway/ .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]