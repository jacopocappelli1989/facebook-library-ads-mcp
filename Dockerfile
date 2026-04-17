FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md ./
COPY src ./src

RUN uv sync --no-dev

ENV FB_GRAPH_API_VERSION=v21.0

ENTRYPOINT ["uv", "run", "facebook-ads-library-mcp"]
