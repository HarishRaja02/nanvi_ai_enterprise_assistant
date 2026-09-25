class EmailAccessDenied(PermissionError):
    pass


class EmailProviderError(RuntimeError):
    pass


class EmailRateLimited(EmailProviderError):
    """Provider rejected the request due to throttling."""
    def __init__(self, message: str = "Email provider rate limit exceeded", retry_after_seconds: int | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class EmailValidationError(ValueError):
    pass
