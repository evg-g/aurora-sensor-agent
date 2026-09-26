# aurora-sensor-agent — developer tasks.

.DEFAULT_GOAL := help
UV ?= uv

.PHONY: help setup test lint fix typecheck ci-local sim fleet soak clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

setup: ## Create the venv and install dependencies (uv)
	$(UV) sync --extra dev

test: ## Run tests with coverage (no hardware / network / Docker needed)
	$(UV) run pytest tests -q -m "not hil" --cov --cov-report=term-missing

lint: ## Lint and check formatting
	$(UV) run ruff check .
	$(UV) run ruff format --check .

fix: ## Auto-fix and format
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

typecheck: ## Static type check (strict)
	$(UV) run mypy

ci-local: lint typecheck test ## Run the full PR gate set locally

sim: ## Run the agent against the simulator (added in a later milestone)
	@echo "The simulator target is implemented in milestone 8/9."

fleet: ## Start N virtual devices (added in a later milestone)
	@echo "The fleet target is implemented in milestone 11."

soak: ## Run the compressed soak test (added in a later milestone)
	@echo "The soak target is implemented in milestone 9."

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache .hypothesis htmlcov .coverage coverage.xml dist build
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
