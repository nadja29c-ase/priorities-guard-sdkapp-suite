FROM python:3.11-slim

# Set work directory inside container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y build-essential && \
    rm -rf /var/lib/apt/lists/*

# Copy dependency file
COPY pyproject.toml /app/pyproject.toml

# If you use poetry:
RUN pip install poetry
RUN poetry config virtualenvs.create false
RUN poetry install --no-interaction --no-ansi

# Copy the full project
COPY . /app

# Expose port (Railway will override)
EXPOSE 8000

# Start FastAPI server
CMD uvicorn backend.main:app --host 0.0.0.0 --port $PORT
