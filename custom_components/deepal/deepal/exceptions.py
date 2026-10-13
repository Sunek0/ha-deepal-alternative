"""Custom exceptions for Changan Deepal SDK."""


class DeepalError(Exception):
    """Base exception for all Deepal SDK errors."""
    pass


class DeepalAuthError(DeepalError):
    """Raised when authentication or token validation fails."""
    pass


class DeepalAPIError(DeepalError):
    """Raised when the API returns an error response."""

    def __init__(self, message: str, status_code: int | None = None, code: str | int | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class DeepalConnectionError(DeepalError):
    """Raised when a network or connection error occurs."""
    pass


class DeepalRateLimitError(DeepalAPIError):
    """Raised when the API rate-limits the request."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        code: str | int | None = None,
        retry_after: float | None = None,
    ) -> None:
        """Initialize the error, optionally carrying the gateway's wait."""
        super().__init__(message, status_code=status_code, code=code)
        self.retry_after = retry_after


class DeepalCommandAuthError(DeepalAuthError):
    """Raised when remote-command signing material is rejected."""


class DeepalCommandNotReady(DeepalAuthError):
    """Raised when remote-command prerequisites are missing."""


def parse_retry_after(value: str | None) -> float | None:
    """Parse an HTTP ``Retry-After`` delta-seconds header.

    Returns the positive number of seconds, or ``None`` when the header is
    missing, not a number, or not positive.
    """
    if value is None:
        return None
    try:
        seconds = int(value.strip())
    except (AttributeError, TypeError, ValueError):
        return None
    return float(seconds) if seconds > 0 else None
