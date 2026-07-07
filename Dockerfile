# ==============================================================================
# Dockerfile — Intelligent Candidate Discovery Engine
# Optimized for Render.com, Docker Desktop, and Cloud Container Services
# ==============================================================================

FROM python:3.10-slim as base

# Prevent Python from writing bytecode (.pyc) and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Set working directory inside container
WORKDIR /app

# Install system dependencies required for scientific libraries and document processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy project files into the container
COPY . .

# Ensure output directory exists
RUN mkdir -p output docs

# Expose port (Render.com overrides $PORT dynamically, default 8000)
EXPOSE 8000

# Start production multithreaded HTTP server
CMD ["python", "server.py"]
