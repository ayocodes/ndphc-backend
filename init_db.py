# init_db.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.security import get_password_hash
from app.core.config import settings
from app.models.power_plant import PowerPlant
from app.models.turbine import Turbine
from app.models.morning_reading import MorningReading, TurbineHourlyDeclaration
from app.models.daily_report import DailyReport, TurbineDailyStats, TurbineHourlyGeneration
from app.db.database import Base
from dotenv import load_dotenv
from app.models.power_plant import PowerPlant 
from app.models.user import User, UserRole


load_dotenv()

# Use database URL from settings (which handles dev/prod logic)
engine = create_engine(settings.SQLALCHEMY_DATABASE_URI)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # Check if admin exists
        admin = db.query(User).filter(User.email == "admin@powerplant.com").first()
        if not admin:
            print("Creating admin user...")
            admin = User(
                email="admin@powerplant.com",
                full_name="System Administrator",
                hashed_password=get_password_hash("admin123"), # Change this to a secure password
                role=UserRole.ADMIN,
                is_active=True
            )
            db.add(admin)
            db.commit()
            print(f"Admin user created successfully in {settings.env} environment!")
        else:
            print(f"Admin user already exists in {settings.env} environment")
    finally:
        db.close()

if __name__ == "__main__":
    print(f"Initializing database for {settings.env} environment...")
    print(f"Using database: {settings.SQLALCHEMY_DATABASE_URI}")
    init_db()