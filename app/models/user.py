from sqlalchemy import Boolean, Column, Integer, String, ForeignKey, DateTime, Enum, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
import uuid
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    EDITOR = "editor"
    VIEWER = "viewer"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    role = Column(Enum(UserRole), default=UserRole.VIEWER, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Optional association to a power plant
    power_plant_id = Column(Integer, ForeignKey("power_plants.id"), nullable=True)
    power_plant = relationship("PowerPlant", back_populates="users")
    
    # Relationships - explicitly specify foreign keys
    morning_readings = relationship(
        "MorningReading", 
        back_populates="user", 
        foreign_keys="MorningReading.user_id"
    )
    daily_reports = relationship(
        "DailyReport", 
        back_populates="user", 
        foreign_keys="DailyReport.user_id"
    )
    
    # Track modifications made by this user - explicitly specify foreign keys
    morning_readings_modified = relationship(
        "MorningReading", 
        foreign_keys="MorningReading.last_modified_by_id", 
        backref="last_modified_by"
    )
    daily_reports_modified = relationship(
        "DailyReport", 
        foreign_keys="DailyReport.last_modified_by_id", 
        backref="last_modified_by"
    )




    