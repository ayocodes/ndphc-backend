# models/morning_reading.py
from sqlalchemy import Column, Integer, Float, ForeignKey, DateTime, Date, CheckConstraint, UniqueConstraint, Numeric, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.db.database import Base


class MorningReading(Base):
    __tablename__ = "morning_readings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    date = Column(Date, nullable=False)
    power_plant_id = Column(Integer, ForeignKey("power_plants.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    declaration_total = Column(Numeric(precision=10, scale=2), nullable=False)  # In MW
    availability_capacity = Column(Numeric(precision=10, scale=2), nullable=False)  # In MW
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    submission_deadline = Column(DateTime(timezone=True), nullable=True)
    is_late_submission = Column(Boolean, default=False)
    last_modified_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Relationships
    power_plant = relationship("PowerPlant", back_populates="morning_readings")
    user = relationship("User", back_populates="morning_readings", foreign_keys=[user_id])
    hourly_declarations = relationship("TurbineHourlyDeclaration", back_populates="morning_reading", cascade="all, delete-orphan")
    
    # Ensure no duplicate readings for the same plant/date
    __table_args__ = (
        UniqueConstraint('date', 'power_plant_id', name='unique_morning_reading'),
    )


class TurbineHourlyDeclaration(Base):
    __tablename__ = "turbine_hourly_declarations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    morning_reading_id = Column(UUID(as_uuid=True), ForeignKey("morning_readings.id"), nullable=False)
    turbine_id = Column(Integer, ForeignKey("turbines.id"), nullable=False)
    hour = Column(Integer, nullable=False)
    declared_output = Column(Numeric(precision=10, scale=2), nullable=False)  # In MW
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    morning_reading = relationship("MorningReading", back_populates="hourly_declarations")
    turbine = relationship("Turbine", back_populates="turbine_hourly_declarations")
    
    # Ensure hours are between 1-24
    __table_args__ = (
        CheckConstraint('hour >= 1 AND hour <= 24', name='hour_range_check'),
    )
