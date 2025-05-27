# app/services/calculation_service.py
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Any, Union
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.daily_report import DailyReport, TurbineDailyStats, TurbineHourlyGeneration
from app.models.power_plant import PowerPlant


class CalculationService:
    """
    Service for calculating derived metrics for daily reports.
    """
    
    @classmethod
    def calculate_and_update_all_metrics(cls, db: Session, report_id: uuid.UUID) -> None:
        """
        Calculate and update all derived metrics for a daily report.
        """
        # Get the daily report
        report = db.query(DailyReport).filter(DailyReport.id == report_id).first()
        if not report:
            return
        
        # Get the power plant info
        power_plant = db.query(PowerPlant).filter(PowerPlant.id == report.power_plant_id).first()
        if not power_plant:
            return
        
        # Update total energy generated and exported by summing from turbine daily stats
        cls._update_energy_totals(db, report)
        
        # Calculate and update other metrics
        # Note: energy_generated and total_energy_exported should be updated by the _update_energy_totals method
        
        # Set defaults for calculated values
        report.energy_consumed = 0.0
        report.availability_factor = 0.0
        report.plant_heat_rate = 0.0
        report.thermal_efficiency = 0.0
        report.availability_forecast = 0.0
        report.dependability_index = 0.0
        report.avg_energy_sent_out = 0.0
        report.gas_utilization = 0.0
        report.load_factor = 0.0
        
        # First update energy consumed
        if report.energy_generated is not None and report.total_energy_exported is not None:
            report.energy_consumed = report.energy_generated - report.total_energy_exported
        
        # Calculate availability factor
        if report.availability_capacity is not None and power_plant.installed_capacity and power_plant.installed_capacity > 0:
            report.availability_factor = (report.availability_capacity / power_plant.installed_capacity) * 100
        
        # Calculate plant heat rate (Btu/kWh)
        if report.energy_generated and report.gas_consumed and report.energy_generated > 0:
            # Conversion factor from MSCM to MMBtu
            gas_mmBtu = report.gas_consumed * 35.314  # MSCM to MMBtu
            report.plant_heat_rate = gas_mmBtu / (report.energy_generated / 1000)  # Divide by MWh → kWh
        
        # Calculate thermal efficiency
        if report.plant_heat_rate and report.plant_heat_rate > 0:
            report.thermal_efficiency = 3412 / float(report.plant_heat_rate) * 100  # 3412 Btu = 1 kWh
        
        # Calculate availability forecast
        if report.availability_capacity is not None:
            report.availability_forecast = report.availability_capacity * 24  # MW * hours
        
        # Calculate dependability index (actual vs potential)
        if report.availability_forecast and report.availability_forecast > 0 and report.energy_generated is not None:
            report.dependability_index = (report.energy_generated / report.availability_forecast) * 100
        
        # Calculate average energy sent out (MW)
        if report.total_energy_exported:
            report.avg_energy_sent_out = report.total_energy_exported / 24  # MWh / hours
        
        # Calculate gas utilization efficiency (MWh/MSCM)
        if report.gas_consumed and report.gas_consumed > 0 and report.energy_generated is not None:
            report.gas_utilization = report.energy_generated / report.gas_consumed
        
        # Calculate load factor (%)
        if power_plant.installed_capacity and power_plant.installed_capacity > 0 and report.total_energy_exported is not None:
            full_potential = power_plant.installed_capacity * 24  # MW * hours
            report.load_factor = (report.total_energy_exported / full_potential) * 100
        
        db.add(report)
        db.commit()
    
    @classmethod
    def _update_energy_totals(cls, db: Session, report: DailyReport) -> None:
        """
        Update the energy_generated and total_energy_exported fields of a daily report
        by summing from the hourly readings first (most accurate), and using turbine stats as fallback.

        This method has been modified to first try to calculate from hourly readings,
        and only use turbine_daily_stats if hourly readings are not available.
        """
        # Initialize with default values
        report.energy_generated = 0.0
        report.total_energy_exported = 0.0
        
        # Check if we have hourly readings
        hourly_readings_exist = db.query(func.count(TurbineHourlyGeneration.id)).filter(
            TurbineHourlyGeneration.daily_report_id == report.id
        ).scalar() > 0
        
        if hourly_readings_exist:
            # Calculate energy totals from hourly readings (most accurate)
            energy_generated = db.query(func.sum(TurbineHourlyGeneration.energy_generated)).filter(
                TurbineHourlyGeneration.daily_report_id == report.id
            ).scalar() or 0
            
            energy_exported = db.query(func.sum(TurbineHourlyGeneration.energy_exported)).filter(
                TurbineHourlyGeneration.daily_report_id == report.id
            ).scalar() or 0
            
            # Update report totals
            report.energy_generated = energy_generated
            report.total_energy_exported = energy_exported
            
            # Also update the turbine daily stats to ensure consistency
            cls._update_turbine_stats_from_hourly(db, report.id)
        else:
            # Fall back to turbine daily stats if no hourly readings
            energy_generated = db.query(func.sum(TurbineDailyStats.energy_generated)).filter(
                TurbineDailyStats.daily_report_id == report.id
            ).scalar() or 0
            
            energy_exported = db.query(func.sum(TurbineDailyStats.energy_exported)).filter(
                TurbineDailyStats.daily_report_id == report.id
            ).scalar() or 0
            
            # Update report totals
            report.energy_generated = energy_generated
            report.total_energy_exported = energy_exported
    
    @classmethod
    def _update_turbine_stats_from_hourly(cls, db: Session, report_id: uuid.UUID) -> None:
        """
        Update turbine_daily_stats energy values based on hourly readings.
        """
        # Get all turbines for this report
        turbine_ids = db.query(TurbineDailyStats.turbine_id).filter(
            TurbineDailyStats.daily_report_id == report_id
        ).distinct().all()
        
        for (turbine_id,) in turbine_ids:
            # Calculate totals for this turbine
            energy_generated = db.query(func.sum(TurbineHourlyGeneration.energy_generated)).filter(
                TurbineHourlyGeneration.daily_report_id == report_id,
                TurbineHourlyGeneration.turbine_id == turbine_id
            ).scalar() or 0
            
            energy_exported = db.query(func.sum(TurbineHourlyGeneration.energy_exported)).filter(
                TurbineHourlyGeneration.daily_report_id == report_id,
                TurbineHourlyGeneration.turbine_id == turbine_id
            ).scalar() or 0
            
            # Update the turbine stats
            turbine_stats = db.query(TurbineDailyStats).filter(
                TurbineDailyStats.daily_report_id == report_id,
                TurbineDailyStats.turbine_id == turbine_id
            ).first()
            
            if turbine_stats:
                turbine_stats.energy_generated = energy_generated
                turbine_stats.energy_exported = energy_exported
                db.add(turbine_stats)
        
        db.commit()
    
    @classmethod
    def get_calculations_by_id(cls, db: Session, report_id: uuid.UUID) -> Dict[str, float]:
        """
        Return all calculated metrics for a report as a dictionary.
        This ensures no NULL values are returned in the API response.
        """
        try:
            report = db.query(DailyReport).filter(DailyReport.id == report_id).first()
            if not report:
                # Return default values if report not found
                return {
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
            
            # Handle each field individually to ensure it's a valid float
            calculations = {}
            
            # Safety function to convert to float with fallback
            def safe_float(value, default=0.0):
                if value is None:
                    return default
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return default
            
            # Process each field with the safety function
            calculations["availability_factor"] = safe_float(report.availability_factor)
            calculations["plant_heat_rate"] = safe_float(report.plant_heat_rate)
            calculations["thermal_efficiency"] = safe_float(report.thermal_efficiency)
            calculations["energy_generated"] = safe_float(report.energy_generated)
            calculations["energy_exported"] = safe_float(report.total_energy_exported)
            calculations["energy_consumed"] = safe_float(report.energy_consumed)
            calculations["availability_forecast"] = safe_float(report.availability_forecast)
            calculations["dependability_index"] = safe_float(report.dependability_index)
            calculations["avg_energy_sent_out"] = safe_float(report.avg_energy_sent_out)
            calculations["gas_utilization"] = safe_float(report.gas_utilization)
            calculations["load_factor"] = safe_float(report.load_factor)
            
            return calculations
        
        except Exception as e:
            # Log the error and return default values
            print(f"Error in get_calculations_by_id: {str(e)}")
            return {
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
    
    @classmethod
    def get_calculations(cls, db: Session, power_plant_id: int, date_value: date) -> Dict[str, float]:
        """
        Get all calculations for a specific power plant and date.
        Used by the calculation endpoints.
        """
        # Get the daily report
        report = db.query(DailyReport).filter(
            DailyReport.power_plant_id == power_plant_id,
            DailyReport.date == date_value
        ).first()
        
        if not report:
            return {
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
        
        # Return calculations in the format expected by the endpoints
        return {
            "availability_factor": float(report.availability_factor or 0.0),
            "plant_heat_rate": float(report.plant_heat_rate or 0.0),
            "thermal_efficiency": float(report.thermal_efficiency or 0.0),
            "energy_generated": float(report.energy_generated or 0.0),
            "energy_exported": float(report.total_energy_exported or 0.0),
            "energy_consumed": float(report.energy_consumed or 0.0),
            "availability_forecast": float(report.availability_forecast or 0.0),
            "dependability_index": float(report.dependability_index or 0.0),
            "avg_energy_sent_out": float(report.avg_energy_sent_out or 0.0),
            "gas_utilization": float(report.gas_utilization or 0.0),
            "load_factor": float(report.load_factor or 0.0),
        }
    
    @classmethod
    def get_metric_over_time(
        cls, 
        db: Session, 
        power_plant_id: int, 
        metric_name: str, 
        start_date: date, 
        end_date: date
    ) -> List[Dict[str, Any]]:
        """
        Get a specific metric over a date range for a power plant.
        Used by the calculation endpoints.
        """
        # Get all daily reports in the date range
        reports = db.query(DailyReport).filter(
            DailyReport.power_plant_id == power_plant_id,
            DailyReport.date >= start_date,
            DailyReport.date <= end_date
        ).order_by(DailyReport.date).all()
        
        # Generate the time series data
        results = []
        for report in reports:
            # Get the value for the requested metric
            if metric_name == "energy_exported":
                value = report.total_energy_exported
            else:
                value = getattr(report, metric_name, None)
            
            # Convert Decimal to float and handle None values
            if value is None:
                value = 0.0
            elif isinstance(value, Decimal):
                value = float(value)
            
            results.append({
                "date": report.date,
                "value": value
            })
        
        return results
    
    @classmethod
    def compare_plants_by_metric(
        cls, 
        db: Session, 
        power_plant_ids: List[int], 
        metric_name: str, 
        date_value: date
    ) -> List[Dict[str, Any]]:
        """
        Compare multiple power plants by a specific metric on a given date.
        Used by the calculation endpoints.
        """
        results = []
        
        for plant_id in power_plant_ids:
            # Get the power plant
            power_plant = db.query(PowerPlant).filter(PowerPlant.id == plant_id).first()
            if not power_plant:
                continue
            
            # Get the daily report
            report = db.query(DailyReport).filter(
                DailyReport.power_plant_id == plant_id,
                DailyReport.date == date_value
            ).first()
            
            # Get the value for the requested metric (with special case for energy_exported)
            if report:
                if metric_name == "energy_exported":
                    value = report.total_energy_exported
                else:
                    value = getattr(report, metric_name, None)
                
                # Convert Decimal to float and handle None
                if value is None:
                    value = 0.0
                elif isinstance(value, Decimal):
                    value = float(value)
            else:
                value = 0.0
            
            results.append({
                "power_plant_id": plant_id,
                "power_plant_name": power_plant.name,
                "value": value
            })
        
        return results