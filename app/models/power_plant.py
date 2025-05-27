from sqlalchemy import Column, Integer, String, Float, DateTime, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.database import Base


class PowerPlant(Base):
    __tablename__ = "power_plants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    location = Column(String)
    total_capacity = Column(Numeric(precision=10, scale=2), nullable=False)  # In MW, using Numeric for precision
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    users = relationship("User", back_populates="power_plant")
    turbines = relationship("Turbine", back_populates="power_plant", cascade="all, delete-orphan", lazy="selectin")
    morning_readings = relationship("MorningReading", back_populates="power_plant")
    daily_reports = relationship("DailyReport", back_populates="power_plant")