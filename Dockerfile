FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LEARNBUDDY_CONFIG_PATH=/app/config/learnbuddy.yaml \
    LEARNBUDDY_DATA_DIR=/app/data

WORKDIR /opt/learnbuddy

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY plugins ./plugins
COPY examples ./examples
COPY templates ./templates
COPY docs ./docs
COPY scripts/docker-entrypoint.sh ./scripts/docker-entrypoint.sh

RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -e . \
    && chmod +x ./scripts/docker-entrypoint.sh \
    && mkdir -p /app/config /app/data /app/backups

WORKDIR /app
ENTRYPOINT ["/opt/learnbuddy/scripts/docker-entrypoint.sh"]
CMD ["doctor", "--config", "/app/config/learnbuddy.yaml"]
