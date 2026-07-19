"""HTTP-слой (FastAPI): тонкая обёртка над агентом-аудитором за портами."""

from app.api.app import create_app

__all__ = ["create_app"]
