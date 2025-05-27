# app/schemas/morning_reading.py
from datetime import date, datetime
from typing import List, Optional, Union
import uuid

from pydantic import BaseModel


class HourlyDeclarationBase(BaseModel):
    hour: int  # 1-24
    declared_output: float  # MW


class HourlyDeclarationCreate(HourlyDeclarationBase):
    pass


class HourlyDeclarationResponse(HourlyDeclarationBase):
    id: Union[uuid.UUID, str]
    turbine_id: int
    
    class Config:
        from_attributes = True


class TurbineDeclarationBase(BaseModel):
    turbine_id: int
    hourly_declarations: List[HourlyDeclarationCreate]


class TurbineDeclarationCreate(TurbineDeclarationBase):
    pass


class MorningReadingBase(BaseModel):
    date: date
    power_plant_id: int
    declaration_total: float  # MW
    availability_capacity: float  # MW


class MorningReadingCreate(MorningReadingBase):
    turbine_declarations: List[TurbineDeclarationCreate]


class MorningReadingUpdate(BaseModel):
    power_plant_id: Optional[int] = None
    date: Optional[date] = None
    declaration_total: Optional[float] = None
    availability_capacity: Optional[float] = None
    turbine_declarations: Optional[List[TurbineDeclarationCreate]] = None
    
    class Config:
        extra = "forbid"  # Prevent additional fields


class MorningReadingResponse(MorningReadingBase):
    id: Union[uuid.UUID, str]
    user_id: int
    submission_deadline: Optional[datetime] = None
    is_late_submission: Optional[bool] = None
    last_modified_by_id: Optional[int] = None
    
    class Config:
        from_attributes = True


class MorningReadingWithDeclarations(MorningReadingResponse):
    hourly_declarations: List[HourlyDeclarationResponse]


