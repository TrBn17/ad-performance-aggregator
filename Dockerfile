FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
COPY --from=ghcr.io/astral-sh/uv:0.9.18 /uv /usr/local/bin/uv
RUN uv sync --frozen --no-dev --no-editable
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["ad-aggregate"]
