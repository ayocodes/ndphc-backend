# app/api/v1/router.py
from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    users,
    power_plants,
    turbines,
    morning_readings,
    daily_reports,
    dashboard,
    hourly_readings,
    download
)

api_router = APIRouter()

# Authentication
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])

# User Management
api_router.include_router(users.router, prefix="/users", tags=["User Management"])

# Reference Data
api_router.include_router(power_plants.router, prefix="/power-plants", tags=["Power Plants"])
api_router.include_router(turbines.router, tags=["Turbines"])

# Data Entry
api_router.include_router(morning_readings.router, prefix="/readings/morning", tags=["Morning Readings"])
api_router.include_router(daily_reports.router, prefix="/reports/daily", tags=["Daily Reports"])
api_router.include_router(hourly_readings.router, prefix="/hourly-readings", tags=["hourly-readings"])  

# Admin Operations
api_router.include_router(download.router, prefix="/download", tags=["Admin Operations"])

# Dashboard & Visualization
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])

# Health Check
@api_router.get("/health-check", tags=["Health"])
def health_check():
    return {"status": "ok", "api_version": "1.0.0"}