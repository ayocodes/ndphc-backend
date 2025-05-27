# app/services/calculation_service.py
from datetime import date
from typing import Dict, List, Optional, Union
from decimal import Decimal
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import func


from app.models.daily_report import DailyReport, TurbineDailyStats
from app.models.morning_reading import MorningReading
from app.models.power_plant import PowerPlant
from app.models.turbine import Turbine


class CalculationService:
    """Service for handling complex calculations based on power plant data."""
    
    @staticmethod
    def calculate_and_update_all_metrics(
        db: Session,
        daily_report_id: uuid.UUID
    ) -> None:
        """
        Calculate and update all derived metrics for a daily report.
        This should be called when a report is created or updated.
        """
        # Get the daily report
        daily_report = db.query(DailyReport).filter(DailyReport.id == daily_report_id).first()
        if not daily_report:
            return
        
        # Get related data
        power_plant = db.query(PowerPlant).filter(PowerPlant.id == daily_report.power_plant_id).first()
        if not power_plant:
            return
            
        # Get morning reading if exists
        morning_reading = db.query(MorningReading).filter(
            MorningReading.date == daily_report.date,
            MorningReading.power_plant_id == daily_report.power_plant_id
        ).first()
        
        # Get turbine stats
        turbine_stats = db.query(TurbineDailyStats).filter(
            TurbineDailyStats.daily_report_id == daily_report_id
        ).all()
        
        # Calculate total energy generated
        total_energy_generated = sum(Decimal(str(stat.energy_generated)) for stat in turbine_stats)
        daily_report.energy_generated = total_energy_generated
        
        # Calculate total energy exported
        total_energy_exported = sum(Decimal(str(stat.energy_exported)) for stat in turbine_stats)
        daily_report.total_energy_exported = total_energy_exported
        
        # Energy Consumed = Energy Generated - Energy Exported
        daily_report.energy_consumed = total_energy_generated - total_energy_exported
        
        # If declaration values weren't provided directly, try to get from morning reading
        if not daily_report.declaration_total and morning_reading:
            daily_report.declaration_total = morning_reading.declaration_total
            
        if not daily_report.availability_capacity and morning_reading:
            daily_report.availability_capacity = morning_reading.availability_capacity
        
        # Calculate availability factor
        if daily_report.availability_capacity and power_plant.total_capacity > 0:
            daily_report.availability_factor = (Decimal(str(daily_report.availability_capacity)) / 
                                             Decimal(str(power_plant.total_capacity))) * 100
        
        # Calculate availability forecast (MWh)
        if daily_report.declaration_total:
            daily_report.availability_forecast = Decimal(str(daily_report.declaration_total)) * 24
        
        # Calculate dependability index / capacity factor
        if daily_report.availability_forecast and Decimal(str(daily_report.availability_forecast)) > 0:
            daily_report.dependability_index = (total_energy_generated / 
                                             Decimal(str(daily_report.availability_forecast))) * 100
        
        # Calculate average energy sent out
        daily_report.avg_energy_sent_out = total_energy_exported / Decimal('24')
        
        # Calculate gas utilization
        if Decimal(str(daily_report.gas_consumed)) > 0:
            daily_report.gas_utilization = total_energy_generated / Decimal(str(daily_report.gas_consumed))
        
        # Calculate total operating hours
        total_operating_hours = sum(Decimal(str(stat.operating_hours)) for stat in turbine_stats)
        
        # Calculate plant heat rate
        if daily_report.gas_utilization and Decimal(str(daily_report.gas_utilization)) > 0:
            daily_report.plant_heat_rate = (Decimal('43.65') * 1000 * 24) / Decimal(str(daily_report.gas_utilization))
        
        # Calculate thermal efficiency
        if daily_report.plant_heat_rate and Decimal(str(daily_report.plant_heat_rate)) > 0:
            daily_report.thermal_efficiency = (Decimal('3600') / Decimal(str(daily_report.plant_heat_rate))) * 100
        
        # Calculate load factor
        if power_plant.total_capacity and total_energy_generated:
            daily_report.load_factor = ((Decimal(str(total_energy_generated)) / Decimal('24')) / Decimal(str(power_plant.total_capacity))) * Decimal('100')
        
        # Save all calculations
        db.add(daily_report)
        db.commit()
    
    @staticmethod
    def get_calculations_by_id(
        db: Session, 
        daily_report_id: uuid.UUID
    ) -> Dict[str, Decimal]:
        """
        Get calculations for a specific daily report by ID.
        First tries to get stored values, then calculates if necessary.
        """
        daily_report = db.query(DailyReport).filter(DailyReport.id == daily_report_id).first()
        
        if not daily_report:
            return {}
        
        # Return the stored calculations if available
        calculations = {}
        
        # Helper function to extract decimal values safely
        def get_decimal_value(value):
            if value is None:
                return None
            return Decimal(str(value))
        
        # Add all calculated fields to the result
        calculations["availability_factor"] = get_decimal_value(daily_report.availability_factor)
        calculations["plant_heat_rate"] = get_decimal_value(daily_report.plant_heat_rate)
        calculations["thermal_efficiency"] = get_decimal_value(daily_report.thermal_efficiency)
        calculations["energy_generated"] = get_decimal_value(daily_report.energy_generated)
        calculations["energy_exported"] = get_decimal_value(daily_report.total_energy_exported)
        calculations["energy_consumed"] = get_decimal_value(daily_report.energy_consumed)
        calculations["availability_forecast"] = get_decimal_value(daily_report.availability_forecast)
        calculations["dependability_index"] = get_decimal_value(daily_report.dependability_index)
        calculations["avg_energy_sent_out"] = get_decimal_value(daily_report.avg_energy_sent_out)
        calculations["gas_utilization"] = get_decimal_value(daily_report.gas_utilization)
        calculations["load_factor"] = get_decimal_value(daily_report.load_factor)
        
        return calculations
    
    @staticmethod
    def get_calculations(
        db: Session, 
        power_plant_id: int, 
        report_date: date
    ) -> Dict[str, Decimal]:
        """
        Get calculations for a specific power plant and date.
        First tries to get stored values, then calculates if necessary.
        """
        daily_report = db.query(DailyReport).filter(
            DailyReport.power_plant_id == power_plant_id,
            DailyReport.date == report_date,
        ).first()
        
        if not daily_report:
            return {}
        
        return CalculationService.get_calculations_by_id(db, daily_report.id)
    
    @staticmethod
    def get_metric_over_time(
        db: Session,
        power_plant_id: int,
        metric_name: str,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, Union[date, Decimal]]]:
        """
        Get a specific metric for a power plant over a date range.
        Returns a list of date-value pairs.
        """
        # Validate the metric name
        valid_metrics = [
            "availability_factor",
            "plant_heat_rate",
            "thermal_efficiency",
            "energy_generated",
            "energy_consumed",
            "availability_forecast",
            "dependability_index",
            "avg_energy_sent_out",
            "gas_utilization",
            "load_factor"
        ]
        
        if metric_name not in valid_metrics:
            return []
        
        # Get reports for the date range
        reports = db.query(DailyReport).filter(
            DailyReport.power_plant_id == power_plant_id,
            DailyReport.date >= start_date,
            DailyReport.date <= end_date,
        ).order_by(DailyReport.date).all()
        
        # Extract the metric for each date
        result = []
        for report in reports:
            value = getattr(report, metric_name)
            
            # Special case for energy_exported which is now total_energy_exported
            if metric_name == "energy_exported":
                value = report.total_energy_exported
                
            if value is not None:
                result.append({
                    "date": report.date,
                    "value": Decimal(str(value))
                })
        
        return result
    
    @staticmethod
    def compare_plants_by_metric(
        db: Session,
        power_plant_ids: List[int],
        metric_name: str,
        report_date: date
    ) -> List[Dict[str, Union[int, str, Decimal]]]:
        """
        Compare multiple power plants by a specific metric on a given date.
        """
        # Validate the metric name
        valid_metrics = [
            "availability_factor",
            "plant_heat_rate",
            "thermal_efficiency",
            "energy_generated",
            "energy_consumed",
            "availability_forecast",
            "dependability_index",
            "avg_energy_sent_out",
            "gas_utilization",
            "load_factor"
        ]
        
        if metric_name not in valid_metrics:
            return []
        
        result = []
        for plant_id in power_plant_ids:
            # Get the power plant
            power_plant = db.query(PowerPlant).filter(PowerPlant.id == plant_id).first()
            if not power_plant:
                continue
            
            # Get the report for this date
            report = db.query(DailyReport).filter(
                DailyReport.power_plant_id == plant_id,
                DailyReport.date == report_date,
            ).first()
            
            if not report:
                continue
            
            # Get the metric value
            value = getattr(report, metric_name)
            
            # Special case for energy_exported which is now total_energy_exported
            if metric_name == "energy_exported":
                value = report.total_energy_exported
                
            if value is not None:
                result.append({
                    "power_plant_id": plant_id,
                    "power_plant_name": power_plant.name,
                    "value": Decimal(str(value))
                })
        
        return result