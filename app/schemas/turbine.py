# app/schemas/turbine.py
from typing import Optional

from pydantic import BaseModel


class TurbineBase(BaseModel):
    name: Optional[str] = None
    capacity: Optional[float] = None


class TurbineCreate(TurbineBase):
    name: str
    capacity: float


class TurbineUpdate(TurbineBase):
    pass


class TurbineResponse(TurbineBase):
    id: int
    power_plant_id: int
    name: str
    capacity: float
    
    class Config:
        from_attributes = True


