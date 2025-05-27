# app/core/config.py
from typing import Any, Dict, List, Optional, Union
from pydantic import AnyHttpUrl, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"  # Ignore extra environment variables
    )
    
    # Environment Configuration
    env: str = "prod"  # dev or prod
    
    # API Configuration - Environment Specific
    SECRET_KEY: str  # REQUIRED from .env
    SERVER_HOST: AnyHttpUrl = "http://localhost:8000"
    
    # CORS Configuration - Environment Specific
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000"]
    
    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            # Handle JSON string format from .env
            if v.startswith('[') and v.endswith(']'):
                import json
                return json.loads(v)
            # Handle comma-separated format
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, list):
            return v
        raise ValueError(f"Invalid CORS origins format: {v}")
    
    # Database URLs from .env
    DATABASE_URL_DEV: Optional[str] = None
    DATABASE_URL_PROD: Optional[str] = None
    
    # Legacy Database Configuration (keeping for backwards compatibility)
    POSTGRES_SERVER: Optional[str] = None
    POSTGRES_USER: Optional[str] = None
    POSTGRES_PASSWORD: Optional[str] = None
    POSTGRES_DB: Optional[str] = None
    
    @field_validator("SQLALCHEMY_DATABASE_URI", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: Optional[str], info) -> str:
        if isinstance(v, str):
            return v
        
        values = info.data
        env = values.get("env", "dev")
        
        # Use environment-specific database URL
        if env == "prod":
            database_url = values.get("DATABASE_URL_PROD")
            if database_url:
                return database_url
        else:  # dev environment
            database_url = values.get("DATABASE_URL_DEV")
            if database_url:
                return database_url
        
        # Fallback to legacy configuration if DATABASE_URL_* not available
        if all(k in values for k in ["POSTGRES_SERVER", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"]):
            return str(PostgresDsn.build(
                scheme="postgresql",
                username=values.get("POSTGRES_USER"),
                password=values.get("POSTGRES_PASSWORD"),
                host=values.get("POSTGRES_SERVER"),
                path=f"{values.get('POSTGRES_DB', '')}"
            ))
        
        raise ValueError(f"No database configuration found for environment: {env}")
    
    SQLALCHEMY_DATABASE_URI: Optional[str] = None
    
    # Application Constants - Not Environment Specific
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Power Plant Monitoring API"
    SERVER_NAME: str = "power-plant-api"
    
    # Security Constants - Can be overridden in .env if needed
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days default
    ALGORITHM: str = "HS256"


settings = Settings()