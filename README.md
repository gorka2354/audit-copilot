# audit-copilot

![CI](https://github.com/gorka2354/audit-copilot/actions/workflows/ci.yml/badge.svg)

**AI-копилот аудита смарт-контрактов.** Автономный слой поверх статического движка
детекторов: прогоняет контракт через детекторы, обогащает каждый сигнал контекстом
из базы знаний по безопасности (RAG) и синтезирует обоснованный отчёт с цитатами —
с **измеримым качеством** вместо «доверься модели».

## Идея

Классический статический анализ отвечает на вопрос «**где** может быть риск», но не
«**настоящий** ли это баг, **насколько** серьёзный и **почему**». Последний шаг обычно
делает человек-аудитор. `audit-copilot` автоматизирует именно его: агент оркеструет
детекторы и базу знаний, а каждое утверждение обязано опираться на источник — иначе
находка отбрасывается (контроль галлюцинаций).

Ключевой инвариант: **находки = детекторы 1:1**. LLM не выдумывает уязвимости и не
теряет их — он только оценивает severity, объясняет риск, предлагает фикс и цитирует
источник. Поэтому провенанс каждого пункта отчёта прослеживается до детектора.

## Архитектура

Гексагональная: домен ничего не знает об инфраструктуре, всё внешнее спрятано за портами
(`typing.Protocol`) и взаимозаменяемо.

```
app/
├── domain/        модели и порты (чистый Python, без зависимостей)
├── adapters/
│   ├── analyzer/     статический движок за портом StaticAnalyzer (security-lab)
│   ├── llm/          LLM-провайдеры за единым портом (Ollama + Anthropic) + роутер с бюджетом
│   ├── vectorstore/  pgvector И Qdrant за портом VectorStore (переключаются конфигом)
│   └── embedder/     эмбеддинги за портом Embedder
├── rag/           чанкинг → эмбеддинги → гибридный поиск (dense + BM25, RRF) → class-фильтр → реранк
├── agent/         агент-аудитор: recon → RAG(class) → LLM-синтез, провенанс цитат
├── eval/          измеримое качество: recall детекторов, faithfulness, cross-model judge, стоимость
├── api/           FastAPI (/audit, /search, /health)
└── observability/ учёт токенов и стоимости (BudgetTracker)
```

Статический движок подключается как **внешний компонент** через порт: адаптер импортирует
детекторы по пути из `SECURITY_LAB_PATH` и нормализует их вывод в доменные `Finding`.

## Быстрый старт

```bash
uv sync                              # окружение (Python 3.12)
cp .env.example .env                 # SECURITY_LAB_PATH и (опц.) ANTHROPIC_API_KEY
docker compose up -d postgres         # pgvector
make audit SOL=examples/VulnerableVault.sol   # аудит контракта в терминале
```

Аудит `VulnerableVault.sol` даёт отчёт с severity, обоснованием, фиксом и цитатами на
реальные источники базы знаний (~$0.07 на контракт через Claude).

### API

```bash
make serve                           # uvicorn на :8000 (нужен .env + postgres)
curl localhost:8000/health
curl -X POST localhost:8000/audit -H 'content-type: application/json' \
  -d '{"code": "contract V { function setOwner(address o) public { owner = o; } }"}'
```

| Метод | Роут | Назначение |
|---|---|---|
| `GET` | `/health` | живость процесса + конфигурация LLM (без сетевых вызовов) |
| `POST` | `/audit` | аудит контракта: recon → RAG(class) → LLM-обогащение → отчёт с цитатами |
| `POST` | `/search` | гибридный поиск по базе знаний (class-фильтр + опц. LLM-реранк) |
| `GET` | `/docs` | Swagger UI / OpenAPI-схема |

`/audit` и `/search` открыты локально; задай `API_KEY` в `.env` — и оба потребуют
заголовок `X-API-Key` (защита от чужих трат LLM на публичном деплое). Доменные ошибки
маппятся в HTTP: исчерпан бюджет → `429`, сбой провайдера → `502`.

### Весь стек в Docker

```bash
make up      # postgres + api на :8000 одной командой (Ollama/Anthropic — внешние)
make down    # остановить
```

## Измеримое качество (eval)

Отличие от «ещё одной RAG-обёртки»: система **измеряет собственное качество** честно.

```bash
make eval                    # detector-recall по всему корпусу DeFiVulnLabs (offline, бесплатно)
make eval SAMPLE=5 EVAL_ARGS=--judge   # + агент на подвыборке + cross-model judge
```

На корпусе DeFiVulnLabs (57 репро, класс уязвимости в имени файла):

- **detector recall 71%** (24/34 покрытых классов) — что реально ловим, промахи показаны;
- **структурная faithfulness 100%** — каждая цитата воспроизводима из переданного
  контекста (провенанс), ни одной выдуманной;
- **cross-model grounding 48%** — судья (Ollama) оценивает цитаты генератора (Anthropic);
  честная цифра, а не самопохвала;
- стоимость и латентность по провайдерам.

Т.к. агент 1:1 anti-hallucination, `agent recall ≡ detector recall` — фальшивую метрику
«агент улучшил recall» намеренно не строим.

## Взаимозаменяемость бэкендов

Порт `VectorStore` не декоративный: `VECTOR_STORE=qdrant` переключает весь стек (агент,
RAG, API) с Postgres/pgvector на Qdrant без единой правки выше адаптера.

```bash
docker compose --profile qdrant up -d qdrant
VECTOR_STORE=qdrant make serve
```

## Дорожная карта

| # | Инкремент | Статус |
|---|---|---|
| 0 | Скелет + порт StaticAnalyzer (мост к движку детекторов) | ✅ |
| 1 | LLM за единым портом: Ollama + Anthropic + учёт бюджета | ✅ |
| 2 | RAG: ingest корпуса знаний → pgvector, гибридный поиск | ✅ |
| 3 | Агент-аудитор: детекторы + RAG → отчёт с цитатами | ✅ |
| 4 | FastAPI + docker-compose | ✅ |
| 5 | Eval-харнесс: recall + faithfulness + cross-model judge + стоимость | ✅ |
| 6 | CI + второй vectorstore (Qdrant) за портом | ✅ |

Каждый инкремент прошёл инженерное ревью плана и независимое ревью кода перед мержем.

## Качество

Тесты (unit + живая интеграция pgvector/qdrant/LLM), `mypy --strict`, `ruff`, CI на
каждый push. Атомарные коммиты (Conventional Commits).

## Стек

Python 3.12 · FastAPI · pydantic · PostgreSQL/pgvector · Qdrant · Docker · Ollama ·
Anthropic · uv · ruff · mypy strict · pytest.
