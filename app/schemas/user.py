# app/schemas/user.py
from typing import List, Optional

from pydantic import BaseModel, EmailStr

from app.models.user import UserRole


class UserBase(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    power_plant_id: Optional[int] = None


class UserCreate(UserBase):
    email: EmailStr
    password: str
    role: UserRole
    full_name: str


class UserUpdate(UserBase):
    password: Optional[str] = None


class UserResponse(UserBase):
    id: int
    email: EmailStr
    role: UserRole
    
    class Config:
        from_attributes = True


class UserWithPermissions(UserResponse):
    power_plant_name: Optional[str] = None
    permissions: List[str]


