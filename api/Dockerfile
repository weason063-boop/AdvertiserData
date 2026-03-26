# Backend Dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (if any)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project to ensure paths like 'calculate_service_fee' work
COPY . .

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Default port for FastAPI
EXPOSE 8000

# The command will be overridden in docker-compose.yml for API and Worker
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
