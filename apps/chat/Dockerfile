# syntax=docker/dockerfile:1.7
# Multi-stage: build with uv on a fat base, then copy app+venv into a slim
# python image. Distroless is preferred per CLAUDE.md but google-adk pulls in
# native deps (grpc, protobuf) that are easier to ship on python-slim. Once we
# have a green container we can revisit distroless.

FROM python:3.13-slim AS build

ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml ./
# Install runtime deps only; allow ADK 2.0a1 (pre-release).
RUN uv pip install --system --prerelease=allow .

COPY testlyn_chat ./testlyn_chat


FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

# Run as a non-root user.
RUN useradd --create-home --uid 1001 chat
WORKDIR /app

COPY --from=build /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=build /usr/local/bin /usr/local/bin
COPY --from=build /app/testlyn_chat ./testlyn_chat

USER chat
EXPOSE 8080

CMD ["uvicorn", "testlyn_chat.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
