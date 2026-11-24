.PHONY: install lint format test test-fast cov run clean-outputs \
        extract canonicalize resolve validate build shacl query \
        docker-build docker-run endpoint-up endpoint-load endpoint-check endpoint-down \
        paper paper-html paper-submission

PY := uv run python -m anemone_kg run

install:
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

test:            ## full suite, including the end-to-end run
	ANEMONE_KG_OFFLINE=1 uv run pytest

test-fast:       ## skip the end-to-end run
	ANEMONE_KG_OFFLINE=1 uv run pytest -m "not e2e"

cov:
	ANEMONE_KG_OFFLINE=1 uv run pytest --cov --cov-report=term

run:             ## whole pipeline; uses the API cache, fetches only what is missing
	$(PY) all

extract canonicalize resolve validate build shacl query:
	$(PY) $@

clean-outputs:   ## delete generated outputs (make run regenerates them identically)
	rm -rf data/interim/* data/processed/* reports/* queries/results/*

# ---- Docker and the SPARQL endpoint (Oxigraph) ----------------------------
docker-build:
	docker build -t anemone-kg .

docker-run:      ## whole pipeline inside the image (offline, from the API cache)
	docker run --rm anemone-kg

endpoint-up:     ## Oxigraph on http://localhost:7878 (web UI and /query)
	docker compose up -d oxigraph

endpoint-load:   ## PUT the graph into the endpoint (Graph Store Protocol)
	uv run python -m anemone_kg endpoint load

endpoint-check:  ## run queries/*.rq on the endpoint and compare with rdflib
	uv run python -m anemone_kg endpoint check

endpoint-down:
	docker compose down

# ---- Manuscript -------------------------------------------------------------
paper:           ## manuscript HTML + PDF from the pipeline outputs (PDF needs Node + Playwright)
	uv run python -m anemone_kg paper

paper-html:      ## manuscript HTML only
	uv run python -m anemone_kg paper --no-pdf

paper-submission: ## journal submission files: DOCX, PDF preview, figures as separate files
	uv run python -m anemone_kg paper --submission
