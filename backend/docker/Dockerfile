ARG PYTHON_IMAGE=python:3.14-slim

FROM astral/uv:latest AS dependency_resolver

FROM ${PYTHON_IMAGE} AS builder
COPY --from=dependency_resolver /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=./uv.lock,target=uv.lock \
    --mount=type=bind,source=./pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

FROM ${PYTHON_IMAGE} AS production

RUN useradd --create-home --uid 10001 tpc

WORKDIR /app

COPY --from=builder --chown=tpc:tpc /app/.venv /app/.venv

COPY --chown=tpc:tpc ./app ./app
COPY --chown=tpc:tpc ./settings ./settings
COPY --chown=tpc:tpc ./docker/docker-entrypoint.sh ./docker/docker-entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN chmod +x /app/docker/docker-entrypoint.sh

USER tpc

ENTRYPOINT ["/app/docker/docker-entrypoint.sh"]

CMD ["help"]
