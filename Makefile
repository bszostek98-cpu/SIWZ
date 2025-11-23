.PHONY: help install test lint format clean run

help:  ## Pokaż tę pomoc
	@echo "Dostępne komendy:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36mmake %-15s\033[0m %s\n", $$1, $$2}'

install:  ## Zainstaluj zależności
	pip install -r requirements.txt

install-dev:  ## Zainstaluj zależności developerskie
	pip install -e ".[dev]"

test:  ## Uruchom testy
	pytest tests/ -v

test-cov:  ## Uruchom testy z coverage
	pytest tests/ --cov=src/siwz_mapper --cov-report=html --cov-report=term-missing

lint:  ## Sprawdź kod (ruff + mypy)
	ruff check src/ tests/
	mypy src/

format:  ## Formatuj kod (black + ruff)
	black src/ tests/ scripts/
	ruff check src/ tests/ scripts/ --fix

clean:  ## Wyczyść pliki tymczasowe
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov/ .coverage build/ dist/

run-example:  ## Uruchom przykładowy pipeline (wymaga danych)
	python scripts/run_pipeline.py \
		--pdf data/siwz_przyklad.pdf \
		--services tests/fixtures/sample_services.json \
		--log-level INFO

run-tests-simple:  ## Uruchom tylko szybkie testy
	pytest tests/test_models.py -v

check-all: lint test  ## Sprawdź kod i uruchom testy

.DEFAULT_GOAL := help

