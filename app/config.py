# app/config.py
from pydantic_settings import BaseSettings
from typing import Optional, List
import os
import platform

class Settings(BaseSettings):
    # Server
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    
    # Database
    database_url: str = "sqlite+aiosqlite:///./data/database.db"
    
    # Redis Configuration with smart defaults
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    redis_ssl: bool = False
    redis_connection_timeout: int = 5
    redis_socket_timeout: int = 5
    
    # Firebase
    firebase_credentials_path: str = "firebase-credentials.json"
    
    # OpenAI
    openai_api_key: str
    openai_realtime_model: str = "gpt-4o-realtime-preview-2024-12-17"
    
    # Logging
    log_level: str = "INFO"
    
    # Development mode
    development_mode: bool = True
    mock_redis: bool = False  # Fallback to in-memory cache
    
    class Config:
        env_file = ".env"
    
    def get_redis_url(self) -> str:
        """Generate Redis URL with proper formatting"""
        auth = f":{self.redis_password}@" if self.redis_password else ""
        protocol = "rediss" if self.redis_ssl else "redis"
        return f"{protocol}://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    def get_redis_hosts_to_try(self) -> List[str]:
        """Get list of Redis hosts to try in order of preference"""
        hosts = [self.redis_host]
        
        # Add common alternatives if original host is localhost
        if self.redis_host in ["localhost", "127.0.0.1"]:
            # Check if we're in WSL
            try:
                with open('/proc/version', 'r') as f:
                    if 'microsoft' in f.read().lower():
                        # WSL-specific hosts
                        hosts.extend([
                            "127.0.0.1",
                            "localhost", 
                            "host.docker.internal",
                            "172.17.0.1"  # Docker bridge
                        ])
            except:
                pass
                
            # Standard alternatives
            if "127.0.0.1" not in hosts:
                hosts.append("127.0.0.1")
            if "0.0.0.0" not in hosts:
                hosts.append("0.0.0.0")
                
        return list(dict.fromkeys(hosts))  # Remove duplicates while preserving order

settings = Settings()