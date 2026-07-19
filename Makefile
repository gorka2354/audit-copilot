.PHONY: install test test-all lint typecheck check demo serve up down logs audit eval

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

audit:              ## демо агента-аудитора: make audit SOL=examples/VulnerableVault.sol
	uv run python scripts/demo_audit.py $(SOL)

eval:               ## eval-харнесс: make eval | агент+judge: make eval SAMPLE=5 EVAL_ARGS=--judge
	uv run python scripts/demo_eval.py --sample $(or $(SAMPLE),0) $(EVAL_ARGS)

serve:              ## запустить API локально с автоперезагрузкой (нужен .env)
	uv run uvicorn app.api.app:create_app --factory --reload

up:                 ## поднять весь стек в docker (postgres + api) на :8000
	docker compose up --build -d

down:               ## остановить стек
	docker compose down

logs:               ## следить за логами API-контейнера
	docker compose logs -f app
