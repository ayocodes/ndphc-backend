# app/api/v1/endpoints/turbines.py
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_superuser, get_current_user, get_db
from app.models.power_plant import PowerPlant
from app.models.turbine import Turbine
from app.models.user import User
from app.schemas.turbine import TurbineCreate, TurbineResponse, TurbineUpdate

router = APIRouter()


@router.get("/power-plant/{power_plant_id}/turbines", response_model=List[TurbineResponse])
def read_turbines_by_power_plant(
    power_plant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Retrieve all turbines for a specific power plant. All users can access this endpoint.
    """
    # Check if power plant exists
    power_plant = db.query(PowerPlant).filter(PowerPlant.id == power_plant_id).first()
    if not power_plant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Power plant not found",
        )
    
    turbines = db.query(Turbine).filter(Turbine.power_plant_id == power_plant_id).all()
    return turbines


@router.post("/power-plant/{power_plant_id}/turbines", response_model=TurbineResponse)
def create_turbine(
    *,
    db: Session = Depends(get_db),
    power_plant_id: int,
    turbine_in: TurbineCreate,
    current_user: User = Depends(get_current_active_superuser),
) -> Any:
    """
    Create new turbine for a power plant. Only accessible by admin users.
    """
    # Check if power plant exists
    power_plant = db.query(PowerPlant).filter(PowerPlant.id == power_plant_id).first()
    if not power_plant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Power plant not found",
        )
    
    # Check for duplicate turbine name within this power plant
    existing = db.query(Turbine).filter(
        Turbine.power_plant_id == power_plant_id,
        Turbine.name == turbine_in.name
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A turbine with name '{turbine_in.name}' already exists in this power plant",
        )
    
    turbine = Turbine(
        name=turbine_in.name,
        capacity=turbine_in.capacity,
        power_plant_id=power_plant_id,
    )
    db.add(turbine)
    db.commit()
    db.refresh(turbine)
    return turbine


@router.get("/turbines/{turbine_id}", response_model=TurbineResponse)
def read_turbine(
    turbine_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get specific turbine by ID. All users can access this endpoint.
    """
    turbine = db.query(Turbine).filter(Turbine.id == turbine_id).first()
    if not turbine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turbine not found",
        )
    return turbine


@router.put("/turbines/{turbine_id}", response_model=TurbineResponse)
def update_turbine(
    *,
    db: Session = Depends(get_db),
    turbine_id: int,
    turbine_in: TurbineUpdate,
    current_user: User = Depends(get_current_active_superuser),
) -> Any:
    """
    Update a turbine. Only accessible by admin users.
    """
    turbine = db.query(Turbine).filter(Turbine.id == turbine_id).first()
    if not turbine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turbine not found",
        )
    
    # Check for duplicate name if name is being changed
    if turbine_in.name and turbine_in.name != turbine.name:
        existing = db.query(Turbine).filter(
            Turbine.power_plant_id == turbine.power_plant_id,
            Turbine.name == turbine_in.name
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"A turbine with name '{turbine_in.name}' already exists in this power plant",
            )
    
    # Update turbine attributes
    if turbine_in.name is not None:
        turbine.name = turbine_in.name
    if turbine_in.capacity is not None:
        turbine.capacity = turbine_in.capacity
    
    db.add(turbine)
    db.commit()
    db.refresh(turbine)
    return turbine


@router.delete("/turbines/{turbine_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_turbine(
    *,
    db: Session = Depends(get_db),
    turbine_id: int,
    current_user: User = Depends(get_current_active_superuser),
) -> Response:
    """
    Delete a turbine. Only accessible by admin users.
    """
    turbine = db.query(Turbine).filter(Turbine.id == turbine_id).first()
    if not turbine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turbine not found",
        )
    
    # Check if there is historical data for this turbine
    from app.models.daily_report import TurbineDailyStats, TurbineHourlyGeneration
    from app.models.morning_reading import TurbineHourlyDeclaration
    
    stats_count = db.query(TurbineDailyStats).filter(TurbineDailyStats.turbine_id == turbine_id).count()
    gen_count = db.query(TurbineHourlyGeneration).filter(TurbineHourlyGeneration.turbine_id == turbine_id).count()
    decl_count = db.query(TurbineHourlyDeclaration).filter(TurbineHourlyDeclaration.turbine_id == turbine_id).count()
    
    if stats_count > 0 or gen_count > 0 or decl_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete turbine with existing data. Found {stats_count} stats, {gen_count} hourly records, and {decl_count} declarations.",
        )
    
    db.delete(turbine)
    db.commit()
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)

