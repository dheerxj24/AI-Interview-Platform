from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Dev default is SQLite so the app runs with no setup.
    # Set DATABASE_URL to postgresql+psycopg://... for the real stack.
    database_url: str = "sqlite:///./dev.db"
    redis_url: str = "redis://localhost:6379/0"
    # "docker" runs submissions in the sandbox image (use this in production).
    # "local" runs them as a plain subprocess; dev only, not a security boundary.
    executor: str = "local"
    celery_eager: bool = False
    # "memory" keeps rooms in this process. "redis" relays messages through Redis so several API processes share rooms.
    realtime_backend: str = "memory"
    # Admin token for the problems page, creating sessions, and the sessions list. Empty disables those routes.
    admin_token: str = ""
    anthropic_api_key: str = ""
    copilot_model: str = "claude-haiku-5-5"
    # If set, the co-pilot uses a local Ollama server instead of Anthropic, e.g. http://host.docker.internal:11434
    ollama_url: str = ""
    ollama_model: str = "qwen2.5-coder:7b"
    cors_origins: str = "http://localhost:5173"


settings = Settings()
