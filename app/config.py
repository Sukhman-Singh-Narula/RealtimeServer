from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Server
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    # secret_key: str
    
    # Database
    database_url: str = "sqlite+aiosqlite:///./data/database.db"
    
    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    
    # Firebase
    firebase_credentials_path: str
    
    # OpenAI
    openai_api_key: str
    openai_realtime_model: str = "gpt-4o-realtime-preview-2024-12-17"
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"

settings = Settings()