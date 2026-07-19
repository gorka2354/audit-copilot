# syntax=docker/dockerfile:1
FROM python:3.12-slim

# uv — быстрый установщик; ставим из официального образа одним слоем
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

# Слой зависимостей отдельно от кода — кэшируется, пока не менялись pyproject/uv.lock
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
RUN uv sync --frozen --no-dev

EXPOSE 8000
# create_app — фабрика приложения; lifespan поднимет пул/эмбеддер/роутер/анализатор
CMD ["uv", "run", "uvicorn", "app.api.app:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8000"]
