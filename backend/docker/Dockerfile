FROM astral/uv:latest AS dependency_resolver

FROM python:3.14 AS builder
COPY --from=dependency_resolver /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0

WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=./uv.lock,target=uv.lock \
    --mount=type=bind,source=./pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev
COPY ./pyproject.toml ./uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python:3.14 AS production
WORKDIR /app
# It is important to use the image that matches the builder, as the path to the
# Python executable must be the same, e.g., using `python:3.11-slim-bookworm`
# will fail.
# Copy the application from the builder
COPY --from=builder --chown=tpc:tpc /app /app
COPY ./ ./
# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"
RUN chmod +x /app/docker/docker-entrypoint.sh

ENTRYPOINT ["/app/docker/docker-entrypoint.sh"]
# Show help text if no command override was passed
CMD ["help"]