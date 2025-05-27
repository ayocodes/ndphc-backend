# models/daily_report.py
from sqlalchemy import Column, Integer, Float, ForeignKey, DateTime, Date, CheckConstraint, UniqueConstraint, Numeric, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.db.database import Base


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    date = Column(Date, nullable=False)
    power_plant_id = Column(Integer, ForeignKey("power_plants.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Base measurements (from form)
    gas_loss = Column(Numeric(precision=10, scale=2), nullable=False)  # In MWh
    ncc_loss = Column(Numeric(precision=10, scale=2), nullable=False)  # In MWh
    internal_loss = Column(Numeric(precision=10, scale=2), nullable=False)  # In MWh
    gas_consumed = Column(Numeric(precision=10, scale=2), nullable=False)  # In MMSCH
    
    # Values that may be copied from morning reading
    declaration_total = Column(Numeric(precision=10, scale=2), nullable=True)  # In MW
    availability_capacity = Column(Numeric(precision=10, scale=2), nullable=True)  # In MW
    
    # Derived calculations (stored)
    availability_factor = Column(Numeric(precision=10, scale=2), nullable=True)  # Percentage
    plant_heat_rate = Column(Numeric(precision=10, scale=2), nullable=True)
    thermal_efficiency = Column(Numeric(precision=10, scale=2), nullable=True)  # Percentage
    energy_generated = Column(Numeric(precision=10, scale=2), nullable=True)  # In MWh (sum of turbine generation)
    total_energy_exported = Column(Numeric(precision=10, scale=2), nullable=True)  # In MWh (sum of turbine exports)
    energy_consumed = Column(Numeric(precision=10, scale=2), nullable=True)  # In MWh (generated - exported)
    availability_forecast = Column(Numeric(precision=10, scale=2), nullable=True)  # In MWh
    dependability_index = Column(Numeric(precision=10, scale=2), nullable=True)  # Percentage (Capacity Factor)
    avg_energy_sent_out = Column(Numeric(precision=10, scale=2), nullable=True)  # In MW
    gas_utilization = Column(Numeric(precision=10, scale=2), nullable=True)  # MWh/MSCM
    load_factor = Column(Numeric(precision=10, scale=2), nullable=True)  # Percentage
    
    # Audit fields
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    submission_deadline = Column(DateTime(timezone=True), nullable=True)
    is_late_submission = Column(Boolean, default=False)
    last_modified_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Relationships
    power_plant = relationship("PowerPlant", back_populates="daily_reports")
    user = relationship("User", back_populates="daily_reports", foreign_keys=[user_id])
    turbine_stats = relationship("TurbineDailyStats", back_populates="daily_report", cascade="all, delete-orphan")
    hourly_generations = relationship("TurbineHourlyGeneration", back_populates="daily_report", cascade="all, delete-orphan")
    
    # Ensure no duplicate reports for the same plant/date
    __table_args__ = (
        UniqueConstraint('date', 'power_plant_id', name='unique_daily_report'),
    )


class TurbineDailyStats(Base):
    __tablename__ = "turbine_daily_stats"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    daily_report_id = Column(UUID(as_uuid=True), ForeignKey("daily_reports.id"), nullable=False)
    turbine_id = Column(Integer, ForeignKey("turbines.id"), nullable=False)
    energy_generated = Column(Numeric(precision=10, scale=2), nullable=False)  # In MWh
    energy_exported = Column(Numeric(precision=10, scale=2), nullable=False)  # In MWh
    operating_hours = Column(Numeric(precision=10, scale=2), nullable=False)  # In hours
    startup_count = Column(Integer, default=0)
    shutdown_count = Column(Integer, default=0)
    trips = Column(Integer, default=0)  # Added trips field
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    daily_report = relationship("DailyReport", back_populates="turbine_stats")
    turbine = relationship("Turbine", back_populates="turbine_daily_stats")


class TurbineHourlyGeneration(Base):
    __tablename__ = "turbine_hourly_generations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    daily_report_id = Column(UUID(as_uuid=True), ForeignKey("daily_reports.id"), nullable=False)
    turbine_id = Column(Integer, ForeignKey("turbines.id"), nullable=False)
    hour = Column(Integer, nullable=False)
    energy_generated = Column(Numeric(precision=10, scale=2), nullable=False)  # In MW
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    daily_report = relationship("DailyReport", back_populates="hourly_generations")
    turbine = relationship("Turbine", back_populates="turbine_hourly_generations")
    
    # Ensure hours are between 1-24
    __table_args__ = (
        CheckConstraint('hour >= 1 AND hour <= 24', name='hour_range_check'),
    )