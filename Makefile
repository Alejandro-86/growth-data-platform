.PHONY: install seed dbt-build sync test lint format api

DUCKDB_PATH := $(CURDIR)/growth_platform.duckdb
export GROWTH_PLATFORM_DUCKDB_PATH := $(DUCKDB_PATH)

install:
	pip install -e ".[dev,dbt,airflow]"

seed:
	python -c "from growth_platform.seed_data.generator import generate_and_load; print(generate_and_load('$(DUCKDB_PATH)'))"

dbt-build:
	cd dbt_project && dbt build --profiles-dir .

api:
	uvicorn growth_platform.marttech_api.app:app --port 8100

sync:
	python -c "from growth_platform.sync.reverse_etl import run_sync; print(run_sync(duckdb_path='$(DUCKDB_PATH)'))"

test:
	pytest tests/ -v
	cd dbt_project && dbt build --profiles-dir .

lint:
	ruff check src/ tests/
	mypy src/

format:
	ruff format src/ tests/
	black src/ tests/
