# VYRON — production image
# Single container running `python main.py` (web + workers + scheduler + bot).
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps: curl for healthchecks, gcc for building wheels if needed
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --uid 1000 vyron \
    && mkdir -p /app/uploads \
    && chown -R vyron:vyron /app
USER vyron

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/ready || exit 1

CMD ["python", "main.py"]
