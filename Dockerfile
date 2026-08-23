FROM python:3.12-slim

LABEL maintainer="Trunal Patil"
LABEL description="eSim Automated Tool Manager — sandboxed demo environment"

# Install system dependencies that might be needed for testing
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY pyproject.toml ./
COPY src/ ./src/
COPY tests/ ./tests/
COPY README.md ./

# Install the package in editable mode with dev dependencies
RUN pip install --no-cache-dir -e ".[dev]"

# Default command: run the test suite
CMD ["pytest", "--cov=esim_tool_manager", "--cov-report=term-missing", "-v"]
