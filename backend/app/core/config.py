"""
Application settings via pydantic-settings.

Reads from environment variables and .env file. All settings can be overridden
via environment variables prefixed with the appropriate names.
"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


# Resolve paths relative to the project root (two levels up from this file)
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_PROJECT_ROOT = _BACKEND_DIR.parent


class Settings(BaseSettings):
    """Application configuration loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "Project Dashboard API"
    debug: bool = False
    log_level: str = "INFO"

    # --- Database ---
    # Path to the SQLite database file (relative to project root or absolute)
    database_path: str = str(_PROJECT_ROOT / "data" / "project_dashboard.db")

    # --- CORS ---
    # Comma-separated list of allowed origins
    cors_origins: list[str] = [
        "http://localhost:5173",   # Vite dev server
        "http://localhost:8501",   # Streamlit (during migration)
        "http://localhost:3000",   # Alternative frontend dev server
    ]

    # --- Deltek API (optional, for sync feature) ---
    deltek_api_base_url: str = ""
    deltek_api_key: str = ""
    deltek_client_id: str = ""
    deltek_client_secret: str = ""
    deltek_token_url: str = ""
    deltek_username: str = ""
    deltek_password: str = ""
    deltek_api_timeout: int = 30
    deltek_api_max_retries: int = 3
    deltek_api_enabled: bool = False


# Singleton settings instance
settings = Settings()
