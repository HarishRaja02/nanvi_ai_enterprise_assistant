class FileIntegrationError(Exception):
    """Base error for secure company-file access."""


class InvalidFilePath(FileIntegrationError):
    pass


class FileAccessDenied(FileIntegrationError):
    pass


class FileNotFound(FileIntegrationError):
    pass


class FileTypeNotAllowed(FileIntegrationError):
    pass


class FileTooLarge(FileIntegrationError):
    pass
