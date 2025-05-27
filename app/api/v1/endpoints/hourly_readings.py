# app/api/v1/endpoints/hourly_readings.py
from typing import Any, List, Optional, Union
import uuid
from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps import get_current_user, get_db
from app.models.daily_report import DailyReport, TurbineHourlyGeneration, TurbineDailyStats
from app.models.power_plant import PowerPlant
from app.models.turbine import Turbine
from app.models.user import User, UserRole
from app.schemas.hourly_reading import (
    HourlyReadingUpdate,
    HourlyReadingsUpdate,
    HourlyReadingResponse
)
from app.services.calculation_service import CalculationService

router = APIRouter()


@router.put("/{report_id}", response_model=List[HourlyReadingResponse])
def update_hourly_readings(
    *,
    db: Session = Depends(get_db),
    report_id: uuid.UUID,
    readings: HourlyReadingsUpdate,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Update hourly readings for a specific report.
    Operators can update until 1.5 days after the report date (until midday of the day after).
    Editors can update at any time.
    """
    # Get the daily report
    daily_report = db.query(DailyReport).filter(DailyReport.id == report_id).first()
    if not daily_report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Daily report not found",
        )
    
    # Calculate submission deadline (midday of the day after the report date)
    NG_TIMEZONE = ZoneInfo("Africa/Lagos")

    report_date = daily_report.date
    next_day = report_date + timedelta(days=1)
    deadline = datetime.combine(next_day, time(12, 0, 0)).replace(tzinfo=NG_TIMEZONE)
    
    # Check if current time is past the deadline
    now = datetime.now(NG_TIMEZONE)
    past_deadline = now > deadline
    
    # Permission checks
    if current_user.role != UserRole.EDITOR:
        # Operator permissions
        if current_user.power_plant_id != daily_report.power_plant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update readings for this power plant",
            )
        
        # Time constraint check
        if past_deadline:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Submission deadline has passed. Please contact an editor to update this report.",
            )
    
    # Track if this is a late submission
    if past_deadline and not daily_report.is_late_submission:
        daily_report.is_late_submission = True
    
    # Update the hourly readings
    updated_readings = []
    for reading in readings.readings:
        # Verify the turbine belongs to the power plant
        turbine = db.query(Turbine).filter(
            Turbine.id == reading.turbine_id,
            Turbine.power_plant_id == daily_report.power_plant_id,
        ).first()
        
        if not turbine:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Turbine with ID {reading.turbine_id} not found in this power plant",
            )
        
        # Check if an hourly reading already exists for this turbine and hour
        existing_reading = db.query(TurbineHourlyGeneration).filter(
            TurbineHourlyGeneration.daily_report_id == report_id,
            TurbineHourlyGeneration.turbine_id == reading.turbine_id,
            TurbineHourlyGeneration.hour == reading.hour,
        ).first()
        
        if existing_reading:
            # Update existing - only energy_generated, energy_exported has been removed
            existing_reading.energy_generated = reading.energy_generated
            db.add(existing_reading)
            updated_readings.append(existing_reading)
        else:
            # Create new - only with energy_generated, energy_exported has been removed
            new_reading = TurbineHourlyGeneration(
                daily_report_id=report_id,
                turbine_id=reading.turbine_id,
                hour=reading.hour,
                energy_generated=reading.energy_generated,
            )
            db.add(new_reading)
            updated_readings.append(new_reading)
    
    # Update the daily report's modification info
    daily_report.last_modified_by_id = current_user.id
    daily_report.updated_at = datetime.now(NG_TIMEZONE)
    db.add(daily_report)
    
    # Commit changes
    db.commit()
    
    # Refresh to get IDs for new readings
    for reading in updated_readings:
        if isinstance(reading, TurbineHourlyGeneration) and not getattr(reading, 'id', None):
            db.refresh(reading)
    
    # No need to update turbine stats based on hourly readings anymore
    # The turbine energy_generated and energy_exported values are set directly by the user
    # through the daily_reports endpoint, not calculated from hourly readings
    
    db.commit()
    
    return updated_readings


@router.get("/{report_id}", response_model=List[HourlyReadingResponse])
def get_hourly_readings(
    report_id: uuid.UUID,
    turbine_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get all hourly readings for a specific report.
    Optionally filter by turbine ID.
    """
    # Verify report exists
    daily_report = db.query(DailyReport).filter(DailyReport.id == report_id).first()
    if not daily_report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Daily report not found",
        )
    
    # Base query
    query = db.query(TurbineHourlyGeneration).filter(
        TurbineHourlyGeneration.daily_report_id == report_id
    )
    
    # Apply turbine filter if provided
    if turbine_id is not None:
        query = query.filter(TurbineHourlyGeneration.turbine_id == turbine_id)
    
    # Order by turbine and hour
    readings = query.order_by(
        TurbineHourlyGeneration.turbine_id, 
        TurbineHourlyGeneration.hour
    ).all()
    
    return readings