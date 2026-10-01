from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .models import QueryRequest, QueryResult


class DatabaseRepository(ABC):
    """Engine-independent repository contract for database access."""

    @abstractmethod
    def execute_read(self, request: QueryRequest) -> QueryResult:
        raise NotImplementedError

    def close(self) -> None:
        """Optional lifecycle hook for repositories backed by a pool."""
        return None


class DatabaseConnectionFactory(ABC):
    """Factory boundary allowing PostgreSQL and SQL Server implementations."""

    @abstractmethod
    def create_repository(self) -> DatabaseRepository:
        raise NotImplementedError
