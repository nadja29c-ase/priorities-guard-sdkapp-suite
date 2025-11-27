FROM python:3.13-slim

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency metadata first (for caching)
COPY pyproject.toml /app/pyproject.toml
COPY poetry.lock /app/poetry.lock

# Install Poetry
RUN pip install --no-cache-dir poetry

# Install dependencies WITHOUT installing your project
RUN poetry config virtualenvs.create false
RUN poetry install --no-interaction --no-ansi --no-root

# Copy the project code
COPY . /app

# Expose port (Railway overrides this internally)
EXPOSE 8000

# Start FastAPI using Railway's assigned $PORT
CMD uvicorn backend.main:app --host 0.0.0.0 --port $PORT
