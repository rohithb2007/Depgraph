# Use official Python 3.11 slim image
FROM python:3.11-slim

# Prevent Python from writing .pyc files & buffer stdout/stderr
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copy requirements and install dependencies
COPY agent/requirements.txt /app/agent/requirements.txt
RUN pip install --no-cache-dir -r /app/agent/requirements.txt pytest

# Copy codebase into container
COPY agent /app/agent
COPY target-repo /app/target-repo

# Cloud Run injects PORT environment variable (default: 8080)
ENV PORT=8080
EXPOSE 8080

# Start DepGraph HTTP API
CMD ["python", "agent/api.py"]
