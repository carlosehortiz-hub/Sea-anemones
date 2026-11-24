.PHONY: install lint format test run clean

install:
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

test:
	uv run pytest

run:
	uv run python -m anemone_kg run all

clean:
	rm -rf data/interim/* data/processed/* reports/*
