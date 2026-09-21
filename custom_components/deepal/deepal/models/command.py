"""Command result models for the international remote-control gateway."""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class CommandResultStatus(str, Enum):
    """Normalized status of an international command result."""

    PENDING = "pending"
    SUCCESS = "success"
    ALREADY_DONE = "already_done"
    FAILED = "failed"


_RESULT_CODE_STATUS: dict[int, CommandResultStatus] = {
    -100: CommandResultStatus.PENDING,
    0: CommandResultStatus.SUCCESS,
    1201: CommandResultStatus.SUCCESS,
    1015: CommandResultStatus.ALREADY_DONE,
    -1: CommandResultStatus.FAILED,
    -2: CommandResultStatus.FAILED,
}


class CommandResult(BaseModel):
    """Classified command result with the raw payload kept for diagnostics."""

    code: Optional[int] = None
    status: CommandResultStatus
    error_message: Optional[str] = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "CommandResult":
        """Classify a raw ``control-result`` payload with the app result codes."""
        raw_code = payload.get("resultCode")
        code: Optional[int] = None
        if raw_code is None:
            status = CommandResultStatus.PENDING
        else:
            try:
                code = int(raw_code)
            except (TypeError, ValueError):
                status = CommandResultStatus.FAILED
            else:
                status = _RESULT_CODE_STATUS.get(code, CommandResultStatus.FAILED)

        error_message = payload.get("errorMsg")
        return cls(
            code=code,
            status=status,
            error_message=str(error_message) if error_message is not None else None,
            raw=payload,
        )
