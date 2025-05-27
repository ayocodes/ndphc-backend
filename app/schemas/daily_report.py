# app/schemas/daily_report.py
from datetime import date, datetime
from typing import Dict, List, Optional, Union
import uuid

from pydantic import BaseModel, Field
from app.schemas.hourly_reading import (
    HourlyReadingResponse
)


# Schema for turbine stats in initial report creation
class InitialTurbineStats(BaseModel):
    turbine_id: int
    energy_generated: float
    energy_exported: float
    operating_hours: float
    startup_count: int
    shutdown_count: int
    trips: int = 0  # Added trips field with default value


# Schema for creating a new daily report (minimal information)
class InitialDailyReportCreate(BaseModel):
    date: date
    power_plant_id: int
    gas_loss: Optional[float] = 0.0
    ncc_loss: Optional[float] = 0.0
    internal_loss: Optional[float] = 0.0
    gas_consumed: Optional[float] = 0.0
    declaration_total: Optional[float] = None
    availability_capacity: Optional[float] = None
    # Added field for initial turbine stats
    initial_turbine_stats: Optional[List[InitialTurbineStats]] = None


# Schema for updating manual turbine stats 
class TurbineStatsUpdate(BaseModel):
    turbine_id: int
    operating_hours: Optional[float] = None
    startup_count: Optional[int] = None
    shutdown_count: Optional[int] = None
    trips: Optional[int] = None  # Added trips field
    energy_generated: Optional[float] = None  # User inputted value
    energy_exported: Optional[float] = None   # User inputted value


# Schema for updating an existing daily report (non-hourly fields)
class DailyReportUpdate(BaseModel):
    gas_loss: Optional[float] = None
    ncc_loss: Optional[float] = None
    internal_loss: Optional[float] = None
    gas_consumed: Optional[float] = None
    declaration_total: Optional[float] = None
    availability_capacity: Optional[float] = None
    turbine_stats: Optional[List[TurbineStatsUpdate]] = None
    
    class Config:
        extra = "forbid"


# Response schema for turbine stats
class TurbineStatsResponse(BaseModel):
    id: Union[uuid.UUID, str]
    daily_report_id: Union[uuid.UUID, str]
    turbine_id: int
    energy_generated: float
    energy_exported: float
    operating_hours: float
    startup_count: int
    shutdown_count: int
    trips: Optional[int] = 0  # Made trips optional with default value of 0
    
    class Config:
        from_attributes = True


# Response schema for daily reports
class DailyReportResponse(BaseModel):
    id: Union[uuid.UUID, str]
    date: date
    power_plant_id: int
    user_id: int
    
    # Manual input fields
    gas_loss: float
    ncc_loss: float
    internal_loss: float
    gas_consumed: float
    declaration_total: Optional[float]
    availability_capacity: Optional[float]
    
    # Calculated fields - now all have default values
    availability_factor: Optional[float] = 0.0
    plant_heat_rate: Optional[float] = 0.0
    thermal_efficiency: Optional[float] = 0.0
    energy_generated: Optional[float] = 0.0
    total_energy_exported: Optional[float] = 0.0
    energy_consumed: Optional[float] = 0.0
    availability_forecast: Optional[float] = 0.0
    dependability_index: Optional[float] = 0.0
    avg_energy_sent_out: Optional[float] = 0.0
    gas_utilization: Optional[float] = 0.0
    load_factor: Optional[float] = 0.0
    
    # Metadata
    submission_deadline: Optional[datetime]
    is_late_submission: bool
    last_modified_by_id: Optional[int]
    updated_at: Optional[datetime]
    created_at: Optional[datetime]
    
    class Config:
        from_attributes = True


# Default calculations dictionary
DEFAULT_CALCULATIONS = {
    "availability_factor": 0.0,
    "plant_heat_rate": 0.0,
    "thermal_efficiency": 0.0,
    "energy_generated": 0.0,
    "energy_exported": 0.0,
    "energy_consumed": 0.0,
    "availability_forecast": 0.0,
    "dependability_index": 0.0,
    "avg_energy_sent_out": 0.0,
    "gas_utilization": 0.0,
    "load_factor": 0.0
}

# Schema for daily report with details
class DailyReportWithDetails(DailyReportResponse):
    turbine_stats: List[TurbineStatsResponse]
    hourly_readings: List[HourlyReadingResponse]
    calculations: Dict[str, float] = Field(default_factory=lambda: DEFAULT_CALCULATIONS.copy())


# Keep this for backward compatibility if needed
class DailyReportCreate(BaseModel):
    date: date
    power_plant_id: int
    gas_loss: float
    ncc_loss: float
    internal_loss: float
    gas_consumed: float
    declaration_total: Optional[float] = None
    availability_capacity: Optional[float] = None
    turbine_stats: List[TurbineStatsUpdate]