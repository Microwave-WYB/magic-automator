.PHONY: help sync format formatcheck lint typecheck check fix

help:
	@echo "Available targets:"
	@echo "  make sync        - Install/update dependencies"
	@echo "  make format      - Run ruff formatter"
	@echo "  make formatcheck - Check formatting"
	@echo "  make lint        - Run ruff lint"
	@echo "  make typecheck   - Run basedpyright"
	@echo "  make fix         - Format + lint autofix"
	@echo "  make check       - formatcheck + lint + typecheck"

sync:
	uv sync

format:
	uv run ruff format .

formatcheck:
	uv run ruff format . --check

lint:
	uv run ruff check .

typecheck:
	uv run basedpyright src

fix: format
	uv run ruff check . --fix

check: formatcheck lint typecheck
