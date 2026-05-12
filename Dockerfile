FROM python:3.11-slim-bookworm AS builder

ARG HF_ENDPOINT=https://huggingface.co
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    HF_HOME=/root/.cache/huggingface \
    HF_ENDPOINT=${HF_ENDPOINT}

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.31 /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev
RUN for attempt in 1 2 3 4 5; do \
      .venv/bin/python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')" && break; \
      if [ "$attempt" = "5" ]; then exit 1; fi; \
      sleep $((attempt * 5)); \
    done

FROM python:3.11-slim-bookworm AS runtime

ENV HF_HOME=/home/app/.cache/huggingface \
    HF_HUB_OFFLINE=1 \
    PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home-dir /home/app --create-home app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /root/.cache/huggingface /home/app/.cache/huggingface
COPY config.yaml README.md ./
COPY src ./src

RUN mkdir -p /app/data \
    && chown -R app:app /app /home/app

USER app
EXPOSE 8000

CMD ["/app/.venv/bin/python", "-m", "tagmemorag", "serve"]
