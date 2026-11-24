.PHONY: install lint format test test-fast cov run clean-outputs \
        extract canonicalize resolve validate build shacl query

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
