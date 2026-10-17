"""Custom exceptions for Changan Deepal SDK."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


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
    """Parse an HTTP ``Retry-After`` header, delta-seconds or HTTP-date.

    An HTTP-date resolves to the positive seconds remaining until it. Returns
    ``None`` when the header is missing, not parseable, negative or already in
    the past.
    """
    if value is None:
        return None
    text = value.strip()
    try:
        seconds = float(text)
    except (AttributeError, TypeError, ValueError):
        seconds = _seconds_until_http_date(text)
    return seconds if seconds is not None and seconds > 0 else None


def _seconds_until_http_date(value: str) -> float | None:
    """Return the seconds until an HTTP-date, ``None`` when unparseable."""
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (when - datetime.now(timezone.utc)).total_seconds()
