from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.database import Base


class Turbine(Base):
    __tablename__ = "turbines"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    capacity = Column(Numeric(precision=10, scale=2), nullable=False)  # Make sure this matches

    power_plant_id = Column(Integer, ForeignKey("power_plants.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    power_plant = relationship("PowerPlant", back_populates="turbines")
    turbine_hourly_declarations = relationship("TurbineHourlyDeclaration", back_populates="turbine", cascade="all, delete-orphan")
    turbine_hourly_generations = relationship("TurbineHourlyGeneration", back_populates="turbine", cascade="all, delete-orphan")
    turbine_daily_stats = relationship("TurbineDailyStats", back_populates="turbine", cascade="all, delete-orphan")