# app/schemas/power_plant.py
from typing import List, Optional

from pydantic import BaseModel


class PowerPlantBase(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    total_capacity: Optional[float] = None


class PowerPlantCreate(PowerPlantBase):
    name: str
    total_capacity: float


class PowerPlantUpdate(PowerPlantBase):
    pass


class PowerPlantResponse(PowerPlantBase):
    id: int
    name: str
    total_capacity: float
    turbine_count: Optional[int] = None
    
    class Config:
        from_attributes = True


class TurbineInPowerPlant(BaseModel):
    id: int
    name: str
    capacity: float
    
    class Config:
        from_attributes = True


class PowerPlantWithTurbines(PowerPlantResponse):
    turbines: List[TurbineInPowerPlant]


