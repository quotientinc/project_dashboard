"""
FastAPI dependency injection for DatabaseManager and DataProcessor.
"""
import logging
from functools import lru_cache

from app.core.config import settings
from app.services.database import DatabaseManager
from app.services.data_processor import DataProcessor

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_db_manager() -> DatabaseManager:
    """Return a cached singleton DatabaseManager."""
    return DatabaseManager(db_path=settings.database_path)


def get_db() -> DatabaseManager:
    """FastAPI dependency that provides a DatabaseManager instance."""
    return _get_db_manager()


def close_db():
    """Close the database connection and clear the singleton cache."""
    db = _get_db_manager()
    db.close()
    _get_db_manager.cache_clear()


def get_data_processor() -> type:
    """FastAPI dependency that provides the DataProcessor class (static methods)."""
    return DataProcessor
