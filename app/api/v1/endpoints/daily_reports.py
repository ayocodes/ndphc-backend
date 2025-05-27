# app/api/v1/endpoints/daily_reports.py

from datetime import datetime, timedelta, time, timezone, date
from zoneinfo import ZoneInfo
from typing import Any, List, Optional
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps import get_current_user, get_db
from app.models.daily_report import DailyReport, TurbineDailyStats, TurbineHourlyGeneration
from app.models.power_plant import PowerPlant
from app.models.turbine import Turbine
from app.models.user import User, UserRole
from app.schemas.daily_report import (
    DailyReportCreate,
    DailyReportResponse, 
    DailyReportWithDetails,
    DailyReportUpdate,
    TurbineStatsUpdate,
    InitialDailyReportCreate,
    InitialTurbineStats,
)
from app.services.calculation_service import CalculationService

router = APIRouter()


@router.post("/", response_model=DailyReportResponse)
def create_daily_report(
    *,
    db: Session = Depends(get_db),
    report_in: InitialDailyReportCreate,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Create a new daily report with minimal information.
    This is typically done at the start of the day.
    """
    # Check if user has permission
    if (current_user.role != UserRole.EDITOR and 
        current_user.role != UserRole.OPERATOR and
        current_user.power_plant_id != report_in.power_plant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to create reports for this power plant",
        )
    
    # Check if power plant exists
    power_plant = db.query(PowerPlant).filter(PowerPlant.id == report_in.power_plant_id).first()
    if not power_plant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Power plant not found",
        )
    
    # Check if a report already exists for this date and power plant
    existing_report = db.query(DailyReport).filter(
        DailyReport.date == report_in.date,
        DailyReport.power_plant_id == report_in.power_plant_id,
    ).first()
    
    # If a report already exists, return it instead of creating a new one
    if existing_report:
        return existing_report
    
    # Set submission deadline (midday of the next day)
    NG_TIMEZONE = ZoneInfo("Africa/Lagos")
    next_day = report_in.date + timedelta(days=1)
    submission_deadline = datetime.combine(next_day, time(12, 0, 0)).replace(tzinfo=NG_TIMEZONE)
    
    # Create the daily report with default values where needed
    daily_report = DailyReport(
        date=report_in.date,
        power_plant_id=report_in.power_plant_id,
        user_id=current_user.id,
        gas_loss=report_in.gas_loss or 0.0,
        ncc_loss=report_in.ncc_loss or 0.0,
        internal_loss=report_in.internal_loss or 0.0,
        gas_consumed=report_in.gas_consumed or 0.0,
        declaration_total=report_in.declaration_total,
        availability_capacity=report_in.availability_capacity,
        submission_deadline=submission_deadline,
        is_late_submission=False,
        last_modified_by_id=current_user.id,
    )
    db.add(daily_report)
    db.commit()
    db.refresh(daily_report)
    
    # Get all turbines for this power plant
    turbines = db.query(Turbine).filter(Turbine.power_plant_id == report_in.power_plant_id).all()
    
    # Create a dictionary to store user-provided turbine stats
    user_provided_stats = {}
    if report_in.initial_turbine_stats:
        for stat in report_in.initial_turbine_stats:
            user_provided_stats[stat.turbine_id] = stat
    
    # Initialize turbine stats for all turbines
    for turbine in turbines:
        # Check if user provided values for this turbine
        if turbine.id in user_provided_stats:
            # Use user-provided values
            stat = user_provided_stats[turbine.id]
            daily_stats = TurbineDailyStats(
                daily_report_id=daily_report.id,
                turbine_id=turbine.id,
                energy_generated=stat.energy_generated,
                energy_exported=stat.energy_exported,
                operating_hours=stat.operating_hours,
                startup_count=stat.startup_count,
                shutdown_count=stat.shutdown_count,
                trips=stat.trips,
            )
        else:
            # Use default values of 0 if no user values provided
            daily_stats = TurbineDailyStats(
                daily_report_id=daily_report.id,
                turbine_id=turbine.id,
                energy_generated=0.0,
                energy_exported=0.0,
                operating_hours=0.0,
                startup_count=0,
                shutdown_count=0,
                trips=0,
            )
        db.add(daily_stats)
    
    db.commit()
    
    # Calculate metrics based on the newly created data
    CalculationService.calculate_and_update_all_metrics(db, daily_report.id)
    db.refresh(daily_report)
    
    return daily_report


@router.put("/{report_id}", response_model=DailyReportResponse)
def update_daily_report(
    *,
    db: Session = Depends(get_db),
    report_id: uuid.UUID,
    report_in: DailyReportUpdate,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Update non-hourly fields of a daily report.
    Operators can only update until the submission deadline (midday of the next day).
    Editors can update at any time.
    """
    # Get the existing report
    report = db.query(DailyReport).filter(DailyReport.id == report_id).first()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Daily report not found",
        )
    
    # Check if current time is past the deadline
    NG_TIMEZONE = ZoneInfo("Africa/Lagos")
    now = datetime.now(NG_TIMEZONE)
    past_deadline = now > report.submission_deadline if report.submission_deadline else False
    
    # Permission checks
    if current_user.role != UserRole.EDITOR:
        # Operator permissions
        if current_user.power_plant_id != report.power_plant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update reports for this power plant",
            )
        
        # Time constraint check
        if past_deadline:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Submission deadline has passed. Please contact an editor to update this report.",
            )
    
    # Track if this is a late submission
    if past_deadline and not report.is_late_submission:
        report.is_late_submission = True
    
    # Update basic fields if provided
    if report_in.gas_loss is not None:
        report.gas_loss = report_in.gas_loss
    
    if report_in.ncc_loss is not None:
        report.ncc_loss = report_in.ncc_loss
    
    if report_in.internal_loss is not None:
        report.internal_loss = report_in.internal_loss
    
    if report_in.gas_consumed is not None:
        report.gas_consumed = report_in.gas_consumed
    
    if report_in.declaration_total is not None:
        report.declaration_total = report_in.declaration_total
    
    if report_in.availability_capacity is not None:
        report.availability_capacity = report_in.availability_capacity
    
    # Update turbine stats if provided
    if report_in.turbine_stats:
        for turbine_stat in report_in.turbine_stats:
            # Verify turbine belongs to the power plant
            turbine = db.query(Turbine).filter(
                Turbine.id == turbine_stat.turbine_id,
                Turbine.power_plant_id == report.power_plant_id,
            ).first()
            
            if not turbine:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Turbine with ID {turbine_stat.turbine_id} not found in this power plant",
                )
            
            # Get existing stats
            existing_stat = db.query(TurbineDailyStats).filter(
                TurbineDailyStats.daily_report_id == report_id,
                TurbineDailyStats.turbine_id == turbine_stat.turbine_id
            ).first()
            
            if existing_stat:
                # Update existing stats
                if turbine_stat.operating_hours is not None:
                    existing_stat.operating_hours = turbine_stat.operating_hours
                
                if turbine_stat.startup_count is not None:
                    existing_stat.startup_count = turbine_stat.startup_count
                
                if turbine_stat.shutdown_count is not None:
                    existing_stat.shutdown_count = turbine_stat.shutdown_count
                
                if turbine_stat.trips is not None:
                    existing_stat.trips = turbine_stat.trips
                    
                # Update energy values if provided
                if turbine_stat.energy_generated is not None:
                    existing_stat.energy_generated = Decimal(str(turbine_stat.energy_generated))
                
                if turbine_stat.energy_exported is not None:
                    existing_stat.energy_exported = Decimal(str(turbine_stat.energy_exported))
                
                db.add(existing_stat)
            else:
                # Create new stats
                new_stat = TurbineDailyStats(
                    daily_report_id=report_id,
                    turbine_id=turbine_stat.turbine_id,
                    operating_hours=turbine_stat.operating_hours or 0,
                    startup_count=turbine_stat.startup_count or 0,
                    shutdown_count=turbine_stat.shutdown_count or 0,
                    trips=turbine_stat.trips or 0,
                    energy_generated=Decimal(str(turbine_stat.energy_generated)) if turbine_stat.energy_generated is not None else 0,
                    energy_exported=Decimal(str(turbine_stat.energy_exported)) if turbine_stat.energy_exported is not None else 0
                )
                db.add(new_stat)
            
            db.commit()
    
    # Update last modified info
    report.last_modified_by_id = current_user.id
    report.updated_at = datetime.now()
    
    # Save changes
    db.add(report)
    db.commit()
    
    # Recalculate metrics (which will sum up the turbine values)
    CalculationService.calculate_and_update_all_metrics(db, report.id)
    
    # Refresh the report
    db.refresh(report)
    
    return report


@router.get("/plant/{power_plant_id}/date/{date}", response_model=DailyReportWithDetails)
def read_daily_report_by_plant_and_date(
    power_plant_id: int,
    date: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get daily report by power plant ID and date. All users can access this endpoint.
    """
    daily_report = db.query(DailyReport).filter(
        DailyReport.power_plant_id == power_plant_id,
        DailyReport.date == date,
    ).first()
    
    if not daily_report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Daily report not found",
        )
    
    # Get all turbine stats for this report
    turbine_stats = db.query(TurbineDailyStats).filter(
        TurbineDailyStats.daily_report_id == daily_report.id
    ).all()
    
    # Get all hourly generations for this report
    hourly_readings = db.query(TurbineHourlyGeneration).filter(
        TurbineHourlyGeneration.daily_report_id == daily_report.id
    ).order_by(
        TurbineHourlyGeneration.turbine_id, 
        TurbineHourlyGeneration.hour
    ).all()
    
    # Get calculated metrics with safe error handling
    try:
        calculations = CalculationService.get_calculations_by_id(db, daily_report.id)
    except Exception as e:
        # If calculations fail, use defaults
        calculations = {
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
    
    # Ensure all required calculation fields exist and are valid floats
    required_keys = [
        "availability_factor", "plant_heat_rate", "thermal_efficiency",
        "energy_generated", "energy_exported", "energy_consumed",
        "availability_forecast", "dependability_index",
        "avg_energy_sent_out", "gas_utilization", "load_factor"
    ]
    
    for key in required_keys:
        if key not in calculations or calculations[key] is None:
            calculations[key] = 0.0
    
    # Create a clean copy of the SQLAlchemy model dictionary
    report_dict = {}
    for key, value in daily_report.__dict__.items():
        # Skip SQLAlchemy internal attributes
        if not key.startswith('_'):
            # Handle None values in calculated fields
            if key in required_keys and value is None:
                report_dict[key] = 0.0
            else:
                report_dict[key] = value
    
    # Structure the response
    response = {
        **report_dict,
        "turbine_stats": turbine_stats,
        "hourly_readings": hourly_readings,
        "calculations": calculations
    }
    
    return response


@router.get("/plant/{power_plant_id}", response_model=List[DailyReportResponse])
def read_daily_reports_by_plant(
    power_plant_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get all daily reports for a specific power plant. All users can access this endpoint.
    """
    reports = db.query(DailyReport).filter(
        DailyReport.power_plant_id == power_plant_id
    ).order_by(DailyReport.date.desc()).offset(skip).limit(limit).all()
    
    return reports