from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps import get_current_user, get_db
from app.models.daily_report import DailyReport, TurbineHourlyGeneration, TurbineDailyStats
from app.models.morning_reading import MorningReading, TurbineHourlyDeclaration
from app.models.power_plant import PowerPlant
from app.models.turbine import Turbine
from app.models.user import User
from app.services.calculation_service import CalculationService

router = APIRouter()


@router.get("/summary")
def get_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get aggregate metrics for all power plants for current and previous day.
    Shows total energy generated, exported, consumed, gas consumed, and average power exported.
    """
    today = date.today()
    yesterday = today - timedelta(days=1)
    day_before_yesterday = today - timedelta(days=2)
    
    # Get data for current day (yesterday in reality because data is submitted at end of day)
    current_day_data = get_aggregate_metrics(db, yesterday)
    
    # Get data for previous day
    previous_day_data = get_aggregate_metrics(db, day_before_yesterday)
    
    # Calculate percentage changes
    percentage_changes = {}
    for key in current_day_data.keys():
        if key != "date" and previous_day_data.get(key, 0) != 0:
            current = float(current_day_data.get(key, 0))
            previous = float(previous_day_data.get(key, 0))
            if previous != 0:
                percentage_changes[key] = round(((current - previous) / previous) * 100, 2)
            else:
                percentage_changes[key] = 0
    
    return {
        "current_day": current_day_data,
        "previous_day": previous_day_data,
        "percentage_change": percentage_changes
    }


def get_aggregate_metrics(db: Session, report_date: date) -> Dict[str, Any]:
    """
    Helper function to get aggregate metrics for all power plants on a specific date.
    """
    # Get all daily reports for the specified date
    reports = db.query(DailyReport).filter(DailyReport.date == report_date).all()
    
    # Initialize aggregates
    energy_exported = Decimal('0.0')
    energy_generated = Decimal('0.0')
    gas_consumed = Decimal('0.0')
    
    # Initialize percentage-based metrics
    total_dependability_index = Decimal('0.0')
    total_gas_utilization = Decimal('0.0')
    total_availability_factor = Decimal('0.0')
    valid_reports_count = 0
    
    # Sum up the metrics
    for report in reports:
        if report.total_energy_exported is not None:
            energy_exported += Decimal(str(report.total_energy_exported))
        if report.energy_generated is not None:
            energy_generated += Decimal(str(report.energy_generated))
        if report.gas_consumed is not None:
            gas_consumed += Decimal(str(report.gas_consumed))
            
        # Add percentage-based metrics if they exist
        if report.dependability_index is not None:
            total_dependability_index += Decimal(str(report.dependability_index))
        if report.gas_utilization is not None:
            total_gas_utilization += Decimal(str(report.gas_utilization))
        if report.availability_factor is not None:
            total_availability_factor += Decimal(str(report.availability_factor))
        valid_reports_count += 1
    
    # Calculate derived metrics
    energy_consumed = energy_generated - energy_exported
    avg_power_exported = energy_exported / 24 if energy_exported > 0 else Decimal('0.0')
    
    # Calculate averages for percentage-based metrics
    avg_dependability_index = total_dependability_index / valid_reports_count if valid_reports_count > 0 else Decimal('0.0')
    avg_gas_utilization = total_gas_utilization / valid_reports_count if valid_reports_count > 0 else Decimal('0.0')
    avg_availability_factor = total_availability_factor / valid_reports_count if valid_reports_count > 0 else Decimal('0.0')
    
    return {
        "date": report_date,
        "energy_generated": float(energy_generated),
        "energy_exported": float(energy_exported),
        "energy_consumed": float(energy_consumed),
        "gas_consumed": float(gas_consumed),
        "avg_power_exported": float(avg_power_exported),
        "avg_dependability_index": float(avg_dependability_index),
        "avg_gas_utilization": float(avg_gas_utilization),
        "avg_availability_factor": float(avg_availability_factor)
    }


@router.get("/comparison")
def get_plants_comparison(
    metrics: List[str] = Query(..., description="Comma-separated list of metrics to compare"),
    power_plant_ids: Optional[List[int]] = Query(None, description="Comma-separated list of power plant IDs to filter"),
    time_range: str = Query(..., description="week, month, quarter, year, or custom"),
    start_date: Optional[date] = Query(None, description="Start date for custom range"),
    end_date: Optional[date] = Query(None, description="End date for custom range"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Compare multiple metrics across filtered power plants over a time range.
    Returns data for multiple bar charts with comparison data.
    """
    # Validate metrics
    valid_metrics = [
        "energy_generated", "total_energy_exported", "energy_consumed", 
        "gas_consumed", "availability_factor", "plant_heat_rate", 
        "thermal_efficiency", "dependability_index", "avg_energy_sent_out", 
        "gas_utilization", "load_factor"
    ]
    invalid_metrics = [m for m in metrics if m not in valid_metrics]
    if invalid_metrics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid metrics: {', '.join(invalid_metrics)}. Valid options: {', '.join(valid_metrics)}"
        )

    # Date range calculation
    today = date.today()
    if time_range == "custom" and start_date and end_date:
        range_start, range_end = start_date, end_date
    else:
        if time_range == "week":
            range_start = today - timedelta(days=7)
            range_end = today
        elif time_range == "month":
            range_start = today.replace(day=1)
            range_end = today
        elif time_range == "quarter":
            quarter_month = ((today.month - 1) // 3) * 3 + 1
            range_start = today.replace(month=quarter_month, day=1)
            range_end = today
        elif time_range == "year":
            range_start = today.replace(month=1, day=1)
            range_end = today
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid time_range. Use: week, month, quarter, year, or custom"
            )

    # Get filtered power plants
    plant_query = db.query(PowerPlant)
    if power_plant_ids:
        plant_query = plant_query.filter(PowerPlant.id.in_(power_plant_ids))
    power_plants = plant_query.all()

    # Metric units mapping
    METRIC_UNITS = {
        "energy_generated": "MWh",
        "total_energy_exported": "MWh",
        "energy_consumed": "MWh",
        "gas_consumed": "MSCM",
        "availability_factor": "%",
        "plant_heat_rate": "kJ/kWh",
        "thermal_efficiency": "%",
        "dependability_index": "%",
        "avg_energy_sent_out": "MW",
        "gas_utilization": "MWh/MSCM",
        "load_factor": "%"
    }

    # Initialize result structure
    result = {
        "time_range": time_range,
        "start_date": range_start.isoformat(),
        "end_date": range_end.isoformat(),
        "metrics": []
    }

    # Process each metric
    for metric in metrics:
        metric_max = 0.0
        metric_data = []
        
        for plant in power_plants:
            # Get reports for the date range
            reports = db.query(DailyReport).filter(
                DailyReport.power_plant_id == plant.id,
                DailyReport.date.between(range_start, range_end)
            ).all()

            # Calculate metric average
            total = Decimal('0.0')
            valid_reports = 0
            for report in reports:
                value = getattr(report, metric, None)
                if value is not None:
                    total += Decimal(str(value))
                    valid_reports += 1
            
            avg_value = float(total / valid_reports) if valid_reports else 0.0
            metric_max = max(metric_max, avg_value)
            
            metric_data.append({
                "power_plant": plant.name,
                "value": avg_value,
                "percentage": 0.0
            })

        # Calculate percentages
        if metric_max > 0:
            for item in metric_data:
                item["percentage"] = round((item["value"] / metric_max) * 100, 2)

        # Add to final result
        result["metrics"].append({
            "name": metric,
            "unit": METRIC_UNITS[metric],
            "data": metric_data
        })

    return result


@router.get("/hourly-generation")
def get_hourly_generation(
    date_param: date = Query(..., description="Date to get hourly generation data"),
    power_plant_id: Optional[int] = Query(None, description="Optional filter for specific power plant"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get hourly generation data for all power plants on a specific date, organized per turbine.
    """
    # Base query to get power plants
    query = db.query(PowerPlant)
    
    # Filter by power plant ID if provided
    if power_plant_id is not None:
        query = query.filter(PowerPlant.id == power_plant_id)
    
    power_plants = query.all()
    
    if not power_plants:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No power plants found",
        )
    
    result = []
    
    for plant in power_plants:
        # Get the daily report for this plant and date
        daily_report = db.query(DailyReport).filter(
            DailyReport.power_plant_id == plant.id,
            DailyReport.date == date_param
        ).first()
        
        if not daily_report:
            # Skip if no report exists for this date
            continue
        
        # Get all turbines for this power plant
        turbines = db.query(Turbine).filter(
            Turbine.power_plant_id == plant.id
        ).order_by(Turbine.name).all()
        
        turbine_data = []
        
        for turbine in turbines:
            # Get hourly generation data for this turbine and daily report
            hourly_entries = db.query(TurbineHourlyGeneration).filter(
                TurbineHourlyGeneration.daily_report_id == daily_report.id,
                TurbineHourlyGeneration.turbine_id == turbine.id
            ).order_by(TurbineHourlyGeneration.hour).all()
            
            # Initialize hours dictionary with zeros for all hours (1-24)
            hours = {f"{hour:02d}:00": 0.0 for hour in range(1, 25)}
            
            for entry in hourly_entries:
                hour_key = f"{entry.hour:02d}:00"
                hours[hour_key] = float(entry.energy_generated)
            
            total = sum(hours.values())
            
            turbine_data.append({
                "turbine": turbine.name,
                "hours": hours,
                "total": total
            })
        
        # Get last modified by user information
        last_modified_by = None
        if daily_report.last_modified_by_id:
            last_modified_user = db.query(User).filter(User.id == daily_report.last_modified_by_id).first()
            if last_modified_user:
                last_modified_by = {
                    "id": last_modified_user.id,
                    "full_name": last_modified_user.full_name,
                    "email": last_modified_user.email
                }
        
        if turbine_data:
            result.append({
                "power_plant": plant.name,
                "data": turbine_data,
                "audit_info": {
                    "created_at": daily_report.created_at.isoformat() if daily_report.created_at else None,
                    "updated_at": daily_report.updated_at.isoformat() if daily_report.updated_at else None,
                    "last_modified_by": last_modified_by
                }
            })
    
    return {
        "date": date_param.isoformat(),
        "power_plants": result
    }

@router.get("/operational")
def get_operational_data(
    metric: str,
    date_param: date = Query(..., description="Date to analyze"),
    power_plant_id: Optional[int] = Query(None, description="Optional filter for specific power plant"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get operational data for turbines including operating hours, startups, shutdowns, and trips.
    """
    # Validate the metric
    valid_metrics = ["operating_hours", "startups", "shutdowns", "trips"]
    
    if metric not in valid_metrics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid metric. Valid options are: {', '.join(valid_metrics)}",
        )
    
    # Base query to get power plants
    query = db.query(PowerPlant)
    
    # Filter by power plant ID if provided
    if power_plant_id is not None:
        query = query.filter(PowerPlant.id == power_plant_id)
    
    power_plants = query.all()
    
    if not power_plants:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No power plants found",
        )
    
    result = []
    
    for plant in power_plants:
        # Get the daily report for this plant and date
        daily_report = db.query(DailyReport).filter(
            DailyReport.power_plant_id == plant.id,
            DailyReport.date == date_param
        ).first()
        
        if not daily_report:
            # Skip if no report exists for this date
            continue
        
        # Get turbine stats for this report
        turbine_stats = db.query(TurbineDailyStats).join(
            Turbine, TurbineDailyStats.turbine_id == Turbine.id
        ).filter(
            TurbineDailyStats.daily_report_id == daily_report.id
        ).order_by(Turbine.name).all()
        
        turbine_data = []
        
        for stat in turbine_stats:
            turbine = db.query(Turbine).filter(Turbine.id == stat.turbine_id).first()
            if not turbine:
                continue
                
            # Extract the requested metric
            if metric == "operating_hours":
                value = float(stat.operating_hours)
            elif metric == "startups":
                value = stat.startup_count
            elif metric == "shutdowns":
                value = stat.shutdown_count
            elif metric == "trips":
                value = stat.trips
            else:
                value = 0
                
            turbine_data.append({
                "turbine": turbine.name,
                "value": value
            })
        
        # Get last modified by user information
        last_modified_by = None
        if daily_report.last_modified_by_id:
            last_modified_user = db.query(User).filter(User.id == daily_report.last_modified_by_id).first()
            if last_modified_user:
                last_modified_by = {
                    "id": last_modified_user.id,
                    "full_name": last_modified_user.full_name,
                    "email": last_modified_user.email
                }
        
        if turbine_data:
            result.append({
                "power_plant": plant.name,
                "data": turbine_data,
                "audit_info": {
                    "created_at": daily_report.created_at.isoformat() if daily_report.created_at else None,
                    "updated_at": daily_report.updated_at.isoformat() if daily_report.updated_at else None,
                    "last_modified_by": last_modified_by
                }
            })
    
    return {
        "date": date_param.isoformat(),
        "metric": metric,
        "power_plants": result
    }


@router.get("/morning-declarations")
def get_morning_declarations(
    date_param: date = Query(..., description="Date to get morning declaration data"),
    power_plant_id: Optional[int] = Query(None, description="Optional filter for specific power plant"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get morning declaration data for all power plants on a specific date, organized per turbine.
    """
    # Base query to get power plants
    query = db.query(PowerPlant)

    # Filter by power plant ID if provided
    if power_plant_id is not None:
        query = query.filter(PowerPlant.id == power_plant_id)

    power_plants = query.all()

    if not power_plants:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No power plants found",
        )

    result = []

    for plant in power_plants:
        # Get the morning reading for this plant and date
        morning_reading = db.query(MorningReading).filter(
            MorningReading.power_plant_id == plant.id,
            MorningReading.date == date_param
        ).first()

        if not morning_reading:
            # Skip if no morning reading exists for this date
            continue

        # Get all turbines for this power plant
        turbines = db.query(Turbine).filter(
            Turbine.power_plant_id == plant.id
        ).order_by(Turbine.name).all()

        turbine_data = []

        for turbine in turbines:
            # Get hourly declaration data for this turbine and morning reading
            hourly_entries = db.query(TurbineHourlyDeclaration).filter(
                TurbineHourlyDeclaration.morning_reading_id == morning_reading.id,
                TurbineHourlyDeclaration.turbine_id == turbine.id
            ).order_by(TurbineHourlyDeclaration.hour).all()

            # Initialize hours dictionary with zeros for all hours (1-24)
            hours = {f"{hour:02d}:00": 0.0 for hour in range(1, 25)}

            for entry in hourly_entries:
                hour_key = f"{entry.hour:02d}:00"
                # Use declared_output for morning declarations
                hours[hour_key] = float(entry.declared_output) 

            total = sum(hours.values())

            turbine_data.append({
                "turbine": turbine.name,
                "hours": hours,
                "total": total
            })

        # Get last modified by user information
        last_modified_by = None
        if morning_reading.last_modified_by_id:
            last_modified_user = db.query(User).filter(User.id == morning_reading.last_modified_by_id).first()
            if last_modified_user:
                last_modified_by = {
                    "id": last_modified_user.id,
                    "full_name": last_modified_user.full_name,
                    "email": last_modified_user.email
                }

        if turbine_data:
            result.append({
                "power_plant": plant.name,
                "data": turbine_data,
                "audit_info": {
                    "created_at": morning_reading.created_at.isoformat() if morning_reading.created_at else None,
                    "updated_at": morning_reading.updated_at.isoformat() if morning_reading.updated_at else None,
                    "last_modified_by": last_modified_by
                }
            })

    return {
        "date": date_param.isoformat(),
        "power_plants": result
    }

@router.get("/plant/{power_plant_id}/details")
def get_plant_details(
    power_plant_id: int,
    start_date: date = Query(..., description="Start date of the range"),
    end_date: date = Query(..., description="End date of the range"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get comprehensive time-series data for a specific power plant.
    Includes all metrics for daily graphs and analysis.
    """
    # Check if power plant exists
    power_plant = db.query(PowerPlant).filter(PowerPlant.id == power_plant_id).first()
    if not power_plant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Power plant not found",
        )
    
    # Check date range validity
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Start date must be before end date",
        )
    
    # Get turbines for this power plant
    turbines = db.query(Turbine).filter(Turbine.power_plant_id == power_plant_id).all()
    turbine_data = [{"id": t.id, "name": t.name, "capacity": float(t.capacity)} for t in turbines]
    
    # Get daily reports for the date range
    daily_reports = db.query(DailyReport).filter(
        DailyReport.power_plant_id == power_plant_id,
        DailyReport.date >= start_date,
        DailyReport.date <= end_date,
    ).order_by(DailyReport.date).all()
    
    # Process daily data
    daily_data = []
    for report in daily_reports:
        # Get calculations for this report
        calculations = CalculationService.get_calculations_by_id(db, report.id)
        
        # Get last modified by user information
        last_modified_by = None
        if report.last_modified_by_id:
            last_modified_user = db.query(User).filter(User.id == report.last_modified_by_id).first()
            if last_modified_user:
                last_modified_by = {
                    "id": last_modified_user.id,
                    "full_name": last_modified_user.full_name,
                    "email": last_modified_user.email
                }
        
        # Format the data for response
        day_data = {
            "date": report.date.isoformat(),
            "energy_generated": float(report.energy_generated) if report.energy_generated else 0,
            "energy_exported": float(report.total_energy_exported) if report.total_energy_exported else 0,
            "energy_consumed": float(report.energy_consumed) if report.energy_consumed else 0,
            "gas_consumed": float(report.gas_consumed) if report.gas_consumed else 0,
            "availability_capacity": float(report.availability_capacity) if report.availability_capacity else 0,
            "availability_forecast": float(report.availability_forecast) if report.availability_forecast else 0,
            "availability_factor": float(report.availability_factor) if report.availability_factor else 0,
            "plant_heat_rate": float(report.plant_heat_rate) if report.plant_heat_rate else 0,
            "thermal_efficiency": float(report.thermal_efficiency) if report.thermal_efficiency else 0,
            "dependability_index": float(report.dependability_index) if report.dependability_index else 0,
            "avg_energy_sent_out": float(report.avg_energy_sent_out) if report.avg_energy_sent_out else 0,
            "gas_utilization": float(report.gas_utilization) if report.gas_utilization else 0,
            "load_factor": float(report.load_factor) if report.load_factor else 0,
            "gas_loss": float(report.gas_loss) if report.gas_loss else 0,
            "ncc_loss": float(report.ncc_loss) if report.ncc_loss else 0,
            "internal_loss": float(report.internal_loss) if report.internal_loss else 0,
            "audit_info": {
                "created_at": report.created_at.isoformat() if report.created_at else None,
                "updated_at": report.updated_at.isoformat() if report.updated_at else None,
                "last_modified_by": last_modified_by
            }
        }
        
        daily_data.append(day_data)
    
    return {
        "power_plant": {
            "id": power_plant.id,
            "name": power_plant.name,
            "total_capacity": float(power_plant.total_capacity)
        },
        "time_range": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        },
        "daily_data": daily_data,
        "turbines": turbine_data
    }


