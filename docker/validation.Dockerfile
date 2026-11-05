# Optional test image; production Dockerfile and locked runtime stay unchanged.
ARG BASE_IMAGE=ad-aggregator:scalability
FROM ${BASE_IMAGE}
RUN uv sync --frozen --extra dev --no-editable
ENTRYPOINT ["python", "-m", "pytest"]
