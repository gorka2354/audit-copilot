# audit-copilot

**AI-копилот аудита смарт-контрактов.** Автономный слой поверх статического движка
детекторов: прогоняет контракт через детекторы, обогащает каждый сигнал контекстом
из базы знаний по безопасности (RAG) и синтезирует обоснованный отчёт с цитатами —
с измеримым качеством вместо «доверься модели».

> Статус: в разработке, по инкрементам. Ниже — то, что уже собрано, и дорожная карта.

## Идея

Классический статический анализ отвечает на вопрос «**где** может быть риск», но не
«**настоящий** ли это баг, **насколько** серьёзный и **почему**». Последний шаг обычно
делает человек-аудитор. `audit-copilot` автоматизирует именно его: агент оркеструет
детекторы и базу знаний, а каждое утверждение обязано опираться на источник — иначе
находка отбрасывается (контроль галлюцинаций).

## Архитектура

Гексагональная: домен ничего не знает об инфраструктуре, всё внешнее спрятано за портами
и взаимозаменяемо.

```
app/
├── domain/        модели и порты (чистый Python, без зависимостей)
├── adapters/
│   ├── analyzer/  статические движки за портом StaticAnalyzer (security-lab, Slither)
│   ├── llm/        LLM-провайдеры за единым портом (Ollama, Anthropic, OpenAI)
│   ├── vectorstore/ pgvector / Qdrant
│   └── embedder/  модели эмбеддингов
├── rag/           парсинг → чанкинг → эмбеддинги → гибридный поиск → реранк
├── agent/         агент-аудитор (tool-use) с anti-hallucination контрактом
├── eval/          measurable quality: precision/recall, faithfulness, стоимость
├── api/           FastAPI
└── observability/ структурное логирование, трейсинг цепочек, учёт токенов
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

### Весь стек в Docker

```bash
make up      # postgres + api на :8000 одной командой (Ollama/Anthropic — внешние)
make down    # остановить
```

## Дорожная карта

| # | Инкремент | Статус |
|---|---|---|
| 0 | Скелет + порт StaticAnalyzer (мост к движку детекторов) | ✅ |
| 1 | LLM за единым портом: Ollama + Anthropic + учёт бюджета | ✅ |
| 2 | RAG: ingest корпуса знаний → pgvector, гибридный поиск | ✅ |
| 3 | Агент-аудитор: детекторы + RAG → отчёт с цитатами | ✅ |
| 4 | FastAPI + docker-compose | ✅ |
| 5 | Eval-харнесс: precision/recall + faithfulness + стоимость | ⏳ |

## Стек

Python 3.12 · FastAPI · pydantic · PostgreSQL/pgvector · Docker · Ollama · uv ·
ruff · mypy strict · pytest.
