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


class DeepalCommandAuthError(DeepalAuthError):
    """Raised when remote-command signing material is rejected."""


class DeepalCommandNotReady(DeepalAuthError):
    """Raised when remote-command prerequisites are missing."""
