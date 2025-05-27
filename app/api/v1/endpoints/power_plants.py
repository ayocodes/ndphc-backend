# app/api/v1/endpoints/power_plants.py
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_superuser, get_current_user, get_db
from app.models.power_plant import PowerPlant
from app.models.turbine import Turbine
from app.models.user import User, UserRole
from app.schemas.power_plant import PowerPlantCreate, PowerPlantResponse, PowerPlantUpdate, PowerPlantWithTurbines

router = APIRouter()


@router.get("/", response_model=List[PowerPlantResponse])
def read_power_plants(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Retrieve all power plants. All users can access this endpoint.
    """
    power_plants = db.query(PowerPlant).offset(skip).limit(limit).all()
    
    # Count turbines for each power plant and add to response
    result = []
    for plant in power_plants:
        turbine_count = db.query(Turbine).filter(Turbine.power_plant_id == plant.id).count()
        plant_dict = {**plant.__dict__}
        plant_dict["turbine_count"] = turbine_count
        result.append(plant_dict)
        
    return result


@router.post("/", response_model=PowerPlantResponse)
def create_power_plant(
    *,
    db: Session = Depends(get_db),
    power_plant_in: PowerPlantCreate,
    current_user: User = Depends(get_current_active_superuser),
) -> Any:
    """
    Create new power plant. Only accessible by admin users.
    """
    # Check for duplicate name
    existing = db.query(PowerPlant).filter(PowerPlant.name == power_plant_in.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A power plant with this name already exists",
        )
        
    power_plant = PowerPlant(
        name=power_plant_in.name,
        location=power_plant_in.location,
        total_capacity=power_plant_in.total_capacity,
    )
    db.add(power_plant)
    db.commit()
    db.refresh(power_plant)
    return power_plant


@router.get("/{power_plant_id}", response_model=PowerPlantWithTurbines)
def read_power_plant(
    *,
    db: Session = Depends(get_db),
    power_plant_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get power plant by ID with its turbines. All users can access this endpoint.
    """
    power_plant = db.query(PowerPlant).filter(PowerPlant.id == power_plant_id).first()
    if not power_plant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Power plant not found",
        )
    
    # Get turbines for this power plant
    turbines = db.query(Turbine).filter(Turbine.power_plant_id == power_plant_id).all()
    
    # Create response with turbines included
    response = {**power_plant.__dict__, "turbines": turbines}
    
    return response


@router.put("/{power_plant_id}", response_model=PowerPlantResponse)
def update_power_plant(
    *,
    db: Session = Depends(get_db),
    power_plant_id: int,
    power_plant_in: PowerPlantUpdate,
    current_user: User = Depends(get_current_active_superuser),
) -> Any:
    """
    Update a power plant. Only accessible by admin users.
    """
    power_plant = db.query(PowerPlant).filter(PowerPlant.id == power_plant_id).first()
    if not power_plant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Power plant not found",
        )
    
    # Check for duplicate name (if name is being updated)
    if power_plant_in.name and power_plant_in.name != power_plant.name:
        existing = db.query(PowerPlant).filter(PowerPlant.name == power_plant_in.name).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A power plant with this name already exists",
            )
    
    # Update power plant attributes
    if power_plant_in.name is not None:
        power_plant.name = power_plant_in.name
    if power_plant_in.location is not None:
        power_plant.location = power_plant_in.location
    if power_plant_in.total_capacity is not None:
        power_plant.total_capacity = power_plant_in.total_capacity
    
    db.add(power_plant)
    db.commit()
    db.refresh(power_plant)
    return power_plant


@router.delete("/{power_plant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_power_plant(
    *,
    db: Session = Depends(get_db),
    power_plant_id: int,
    current_user: User = Depends(get_current_active_superuser),
) -> Response:
    """
    Delete a power plant. Only accessible by admin users.
    """
    power_plant = db.query(PowerPlant).filter(PowerPlant.id == power_plant_id).first()
    if not power_plant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Power plant not found",
        )
    
    # Check if there are any reports or readings for this power plant
    # This prevents accidental deletion of plants with historical data
    from app.models.daily_report import DailyReport
    from app.models.morning_reading import MorningReading
    
    reports_count = db.query(DailyReport).filter(DailyReport.power_plant_id == power_plant_id).count()
    readings_count = db.query(MorningReading).filter(MorningReading.power_plant_id == power_plant_id).count()
    
    if reports_count > 0 or readings_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete power plant with existing data. Found {reports_count} reports and {readings_count} readings.",
        )
    
    # Check if there are users assigned to this power plant
    users_count = db.query(User).filter(User.power_plant_id == power_plant_id).count()
    if users_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete power plant with {users_count} assigned users. Reassign users first.",
        )
    
    # Delete all turbines for this power plant
    db.query(Turbine).filter(Turbine.power_plant_id == power_plant_id).delete()
    
    # Delete the power plant
    db.delete(power_plant)
    db.commit()
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)


