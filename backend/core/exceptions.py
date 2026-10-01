"""Core enterprise platform exceptions."""

from __future__ import annotations


class ConfigurationError(RuntimeError):
    """Raised when environment or startup configuration fails validation."""
    pass


class DependencyUnavailableError(RuntimeError):
    """Raised when an external dependency is unavailable and fallback/synthetic data is forbidden."""

    code: str = "DEPENDENCY_UNAVAILABLE"
    status_code: int = 503

    def __init__(self, message: str = "Dependency unavailable in production", dependency: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.dependency = dependency
