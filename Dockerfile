# Multi-stage Docker build for InkedUp Polymarket Bot
# Optimized for production deployment with security hardening

# Build stage
FROM python:3.11-slim as builder

# Build arguments
ARG BUILD_DATE
ARG VERSION
ARG VCS_REF

# Install system dependencies for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry==1.6.1

# Set up work directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Configure Poetry
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

# Install dependencies
RUN poetry install --only=main --no-root && rm -rf $POETRY_CACHE_DIR

# Production stage
FROM python:3.11-slim as production

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN groupadd -r inkedup && useradd --no-log-init -r -g inkedup inkedup

# Set up directories
WORKDIR /app
RUN mkdir -p /app/data /app/logs && chown -R inkedup:inkedup /app

# Copy virtual environment from builder stage
COPY --from=builder --chown=inkedup:inkedup /app/.venv /app/.venv

# Add virtual environment to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY --chown=inkedup:inkedup . .

# Install the application
RUN pip install -e .

# Add health check script
COPY --chown=inkedup:inkedup scripts/docker/healthcheck.sh /healthcheck.sh
RUN chmod +x /healthcheck.sh

# Set metadata labels
LABEL maintainer="InkedUp Team" \
      org.label-schema.build-date=$BUILD_DATE \
      org.label-schema.name="inkedup-polymarket-bot" \
      org.label-schema.description="Automated trading bot for Polymarket" \
      org.label-schema.url="https://github.com/inkedup/polymarket-bot" \
      org.label-schema.vcs-ref=$VCS_REF \
      org.label-schema.vcs-url="https://github.com/inkedup/polymarket-bot" \
      org.label-schema.version=$VERSION \
      org.label-schema.schema-version="1.0"

# Switch to non-root user
USER inkedup

# Expose port for health checks and metrics
EXPOSE 8080

# Set up health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD /healthcheck.sh

# Default command
CMD ["python", "-m", "inkedup_bot.cli", "run"]

# Development stage
FROM builder as development

# Install development dependencies
RUN poetry install --no-root

# Install additional development tools
RUN pip install --no-cache-dir \
    ipython \
    jupyter \
    pre-commit

# Copy application code
COPY . .

# Install the application in development mode
RUN poetry install

# Create directories for development
RUN mkdir -p /app/notebooks /app/scripts

# Development user setup
RUN groupadd -r dev && useradd --no-log-init -r -g dev -G inkedup dev
RUN chown -R dev:dev /app

USER dev

# Expose additional ports for development
EXPOSE 8080 8888

CMD ["python", "-m", "inkedup_bot.cli", "run", "--debug"]