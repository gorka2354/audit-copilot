.PHONY: install test test-all lint typecheck check demo

install:            ## синхронизировать окружение (uv + dev-группа)
	uv sync

test:               ## юнит-тесты (без integration)
	uv run pytest -m "not integration"

test-all:           ## все тесты, включая интеграцию с security-lab
	uv run pytest

lint:               ## ruff: стиль и импорты
	uv run ruff check .

typecheck:          ## mypy strict
	uv run mypy

check: lint typecheck test  ## полный прогон качества

demo:               ## демо статического анализа: make demo SOL=path/to/Contract.sol
	uv run python scripts/demo_analyze.py $(SOL)
