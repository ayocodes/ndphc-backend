# app/api/v1/endpoints/morning_readings.py
from datetime import datetime, timedelta, time, timezone, date
from zoneinfo import ZoneInfo
from typing import Any, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.api.deps import get_current_user, get_db
from app.models.morning_reading import MorningReading, TurbineHourlyDeclaration
from app.models.power_plant import PowerPlant
from app.models.turbine import Turbine
from app.models.user import User, UserRole
from app.schemas.morning_reading import (
    MorningReadingCreate,
    MorningReadingResponse,
    MorningReadingUpdate,
    MorningReadingWithDeclarations,
    TurbineDeclarationCreate,
)

router = APIRouter()


@router.post("/", response_model=MorningReadingResponse)
def create_morning_reading(
    *,
    db: Session = Depends(get_db),
    reading_in: MorningReadingCreate,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Create new morning reading. 
    - Operators can only submit before the deadline (12:00 PM of the same day)
    - Editors can submit past the deadline, but it's marked as late
    """
    # Set timezone
    NG_TIMEZONE = ZoneInfo("Africa/Lagos")
    
    # Check if user has permission to create reading for this power plant
    if (current_user.role != UserRole.EDITOR and
        current_user.role != UserRole.OPERATOR):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to create readings",
        )
    
    # Check if the user is an operator with assigned power plant
    if (current_user.role == UserRole.OPERATOR and 
        current_user.power_plant_id != reading_in.power_plant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only submit readings for your assigned power plant",
        )
    
    # Check if power plant exists
    power_plant = db.query(PowerPlant).filter(PowerPlant.id == reading_in.power_plant_id).first()
    if not power_plant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Power plant not found",
        )
    
    # Prevent future date submissions
    current_date = datetime.now(NG_TIMEZONE).date()
    if reading_in.date > current_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot submit readings for future dates",
        )
    
    # Check if a reading already exists for this date and power plant
    existing_reading = db.query(MorningReading).filter(
        MorningReading.date == reading_in.date,
        MorningReading.power_plant_id == reading_in.power_plant_id,
    ).first()
    
    if existing_reading:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A morning reading already exists for this date and power plant",
        )

    # Set submission deadline to 12:00 PM of the same day
    submission_deadline = datetime.combine(reading_in.date, time(12, 0)).replace(tzinfo=NG_TIMEZONE)
    
    # Check if submission is late
    is_late = datetime.now(NG_TIMEZONE) > submission_deadline
    
    # If operator and submission is late, prevent submission
    if current_user.role == UserRole.OPERATOR and is_late:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Submission deadline has passed. Please contact an editor or admin.",
        )
    
    # Create the morning reading
    morning_reading = MorningReading(
        date=reading_in.date,
        power_plant_id=reading_in.power_plant_id,
        user_id=current_user.id,
        declaration_total=reading_in.declaration_total,
        availability_capacity=reading_in.availability_capacity,
        submission_deadline=submission_deadline,
        is_late_submission=is_late,
        last_modified_by_id=current_user.id,
    )
    db.add(morning_reading)
    db.commit()
    db.refresh(morning_reading)
    
    # Create hourly declarations for each turbine
    for turbine_declaration in reading_in.turbine_declarations:
        # Verify turbine belongs to the power plant
        turbine = db.query(Turbine).filter(
            Turbine.id == turbine_declaration.turbine_id,
            Turbine.power_plant_id == reading_in.power_plant_id,
        ).first()
        
        if not turbine:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Turbine with ID {turbine_declaration.turbine_id} not found in this power plant",
            )
        
        # Create hourly declarations
        for hour_decl in turbine_declaration.hourly_declarations:
            hourly_declaration = TurbineHourlyDeclaration(
                morning_reading_id=morning_reading.id,
                turbine_id=turbine_declaration.turbine_id,
                hour=hour_decl.hour,
                declared_output=hour_decl.declared_output,
            )
            db.add(hourly_declaration)
    
    db.commit()
    
    return morning_reading


@router.get("/plant/{power_plant_id}/date/{date}", response_model=MorningReadingWithDeclarations)
def read_morning_reading_by_plant_and_date(
    power_plant_id: int,
    date: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get morning reading by power plant ID and date. All users can access this endpoint.
    """
    morning_reading = db.query(MorningReading).filter(
        MorningReading.power_plant_id == power_plant_id,
        MorningReading.date == date,
    ).first()
    
    if not morning_reading:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Morning reading not found",
        )
    
    # Get all hourly declarations for this reading
    hourly_declarations = db.query(TurbineHourlyDeclaration).filter(
        TurbineHourlyDeclaration.morning_reading_id == morning_reading.id
    ).all()
    
    # Structure the response
    response = {
        **morning_reading.__dict__,
        "hourly_declarations": hourly_declarations
    }
    
    return response


@router.get("/plant/{power_plant_id}", response_model=List[MorningReadingResponse])
def read_morning_readings_by_plant(
    power_plant_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get all morning readings for a specific power plant. All users can access this endpoint.
    """
    readings = db.query(MorningReading).filter(
        MorningReading.power_plant_id == power_plant_id
    ).order_by(MorningReading.date.desc()).offset(skip).limit(limit).all()
    
    return readings


@router.put("/{reading_id}", response_model=MorningReadingResponse)
def update_morning_reading(
    *,
    db: Session = Depends(get_db),
    reading_id: uuid.UUID,
    reading_in: MorningReadingUpdate,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Update an existing morning reading. Only admin and editor roles can update readings.
    Uses differential updates to efficiently handle hourly declarations.
    """
    # Check if user has permission to update readings
    if current_user.role != UserRole.ADMIN and current_user.role != UserRole.EDITOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and editors can update readings",
        )
    
    # Get the existing reading
    reading = db.query(MorningReading).filter(MorningReading.id == reading_id).first()
    if not reading:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Morning reading not found",
        )
    
    # Update only provided fields
    if reading_in.power_plant_id is not None:
        # Check if power plant exists
        power_plant = db.query(PowerPlant).filter(PowerPlant.id == reading_in.power_plant_id).first()
        if not power_plant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Power plant not found",
            )
        
        # Check for duplicate (different ID but same date and power plant)
        if reading_in.date is not None or reading.date:
            date_to_check = reading_in.date if reading_in.date is not None else reading.date
            duplicate = db.query(MorningReading).filter(
                MorningReading.date == date_to_check,
                MorningReading.power_plant_id == reading_in.power_plant_id,
                MorningReading.id != reading_id
            ).first()
            
            if duplicate:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Another reading already exists for this date and power plant",
                )
        
        reading.power_plant_id = reading_in.power_plant_id
    
    if reading_in.date is not None:
        # Check for duplicate with the new date
        duplicate = db.query(MorningReading).filter(
            MorningReading.date == reading_in.date,
            MorningReading.power_plant_id == reading.power_plant_id,
            MorningReading.id != reading_id
        ).first()
        
        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Another reading already exists for this date and power plant",
            )
        
        reading.date = reading_in.date
        
        # Update submission deadline
        NG_TIMEZONE = ZoneInfo("Africa/Lagos")
        reading.submission_deadline = datetime.combine(reading_in.date, time(12, 0)).replace(tzinfo=NG_TIMEZONE) if reading_in.date else reading.submission_deadline
        
        # Check if the updated date makes this a late submission
        reading.is_late_submission = datetime.now(NG_TIMEZONE) > reading.submission_deadline
    
    if reading_in.declaration_total is not None:
        reading.declaration_total = reading_in.declaration_total
    
    if reading_in.availability_capacity is not None:
        reading.availability_capacity = reading_in.availability_capacity
    
    # Always update last modified info
    reading.last_modified_by_id = current_user.id
    
    # Update hourly declarations if provided
    if reading_in.turbine_declarations:
        # Get existing hourly declarations
        existing_declarations = db.query(TurbineHourlyDeclaration).filter(
            TurbineHourlyDeclaration.morning_reading_id == reading_id
        ).all()
        
        # Create a map for easy lookup: (turbine_id, hour) -> declaration
        existing_map = {(d.turbine_id, d.hour): d for d in existing_declarations}
        
        # Track which declarations to keep (to determine which ones to delete)
        declarations_to_keep = set()
        
        # Process incoming turbine declarations
        for turbine_declaration in reading_in.turbine_declarations:
            # Verify turbine belongs to the power plant
            turbine = db.query(Turbine).filter(
                Turbine.id == turbine_declaration.turbine_id,
                Turbine.power_plant_id == reading.power_plant_id,
            ).first()
            
            if not turbine:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Turbine with ID {turbine_declaration.turbine_id} not found in this power plant",
                )
            
            # Process hourly declarations for this turbine
            for hour_decl in turbine_declaration.hourly_declarations:
                key = (turbine_declaration.turbine_id, hour_decl.hour)
                
                if key in existing_map:
                    # Update existing declaration
                    existing_decl = existing_map[key]
                    existing_decl.declared_output = hour_decl.declared_output
                    declarations_to_keep.add(key)
                else:
                    # Create new declaration
                    new_declaration = TurbineHourlyDeclaration(
                        morning_reading_id=reading.id,
                        turbine_id=turbine_declaration.turbine_id,
                        hour=hour_decl.hour,
                        declared_output=hour_decl.declared_output,
                    )
                    db.add(new_declaration)
                    declarations_to_keep.add(key)
        
        # Delete declarations that weren't in the update request
        for key, declaration in existing_map.items():
            if key not in declarations_to_keep:
                db.delete(declaration)
    
    # Commit all changes
    db.add(reading)
    db.commit()
    db.refresh(reading)
    
    return reading