# Pipeline image: everything needed to rebuild the dataset, graph and reports.
#   docker build -t anemone-kg .
#   docker run --rm anemone-kg                    # whole pipeline, offline (API cache)
#   docker run --rm anemone-kg run shacl          # one stage
FROM python:3.12-slim

# uv from PyPI, pinned to the version that wrote uv.lock.
RUN pip install --no-cache-dir uv==0.11.32

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    ANEMONE_KG_OFFLINE=1

# Dependencies first, so code changes do not invalidate this layer.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-install-project --no-dev

COPY . .
RUN uv sync --locked --no-dev

ENTRYPOINT ["uv", "run", "--no-sync", "python", "-m", "anemone_kg"]
CMD ["run", "all"]
