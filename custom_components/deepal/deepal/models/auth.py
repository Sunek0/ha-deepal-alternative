"""Authentication data models."""

from typing import Optional
from pydantic import BaseModel, Field


class AuthToken(BaseModel):
    """OAuth2 / Bearer Token model."""
    access_token: str = Field(..., description="API Access Bearer Token")
    token_type: str = Field(default="Bearer", description="Token type")
    expires_in: Optional[int] = Field(default=None, description="Expiration time in seconds")
    refresh_token: Optional[str] = Field(default=None, description="Refresh token if available")
    cac_token: Optional[str] = Field(default=None, description="International CAC token if available")
    user_id: Optional[str] = Field(default=None, description="User ID associated with token")


class UserProfile(BaseModel):
    """Deepal User Profile model."""
    user_id: str
    phone: Optional[str] = None
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
