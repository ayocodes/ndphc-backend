# app/schemas/hourly_reading.py
from typing import List, Optional, Union
import uuid

from pydantic import BaseModel, Field, validator


class HourlyReadingUpdate(BaseModel):
    """Schema for a single hourly reading update"""
    turbine_id: int
    hour: int = Field(..., ge=1, le=24)  # Must be between 1-24
    energy_generated: float  # MWh

    @validator('hour')
    def validate_hour(cls, v):
        if v < 1 or v > 24:
            raise ValueError('Hour must be between 1 and 24')
        return v


class HourlyReadingsUpdate(BaseModel):
    """Schema for updating multiple hourly readings at once"""
    readings: List[HourlyReadingUpdate]


class HourlyReadingResponse(BaseModel):
    """Response schema for hourly readings"""
    id: Union[uuid.UUID, str]
    daily_report_id: Union[uuid.UUID, str]
    turbine_id: int
    hour: int
    energy_generated: float
    
    class Config:
        from_attributes = True