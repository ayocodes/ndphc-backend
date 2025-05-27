# app/schemas/token.py
from typing import Optional, List, Dict, Any

from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    exp: Optional[int] = None