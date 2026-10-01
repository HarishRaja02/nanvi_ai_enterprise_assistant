class DatabaseIntegrationError(Exception):
    """Base error for the database integration."""


class SQLValidationError(DatabaseIntegrationError):
    pass


class DatabaseAccessDenied(DatabaseIntegrationError):
    pass


class QueryLimitExceeded(DatabaseIntegrationError):
    pass


class DatabaseConfigurationError(DatabaseIntegrationError):
    pass
