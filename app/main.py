from fastapi import FastAPI, WebSocket, Depends
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any

from app.config import settings
from app.models.database import init_db
from app.managers.database_manager import DatabaseManager
from app.managers.cache_manager import CacheManager
from app.managers.content_manager import ContentManager
from app.managers.realtime_manager import RealtimeManager
from app.managers.websocket_manager import WebSocketManager
from app.api.endpoints import router as api_router
from app.api.websocket_handler import WebSocketHandler

# Configure logging
logging.basicConfig(
    level=settings.log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global managers
managers: Dict[str, Any] = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup
    logger.info("Starting ESP32 Language Learning Server with Realtime API...")
    
    # Initialize database
    await init_db(settings.database_url)
    
    # Initialize managers
    managers['database'] = DatabaseManager(settings.database_url)
    managers['cache'] = CacheManager(
        settings.redis_host,
        settings.redis_port,
        settings.redis_db
    )
    managers['content'] = ContentManager(settings.firebase_credentials_path)
    managers['realtime'] = RealtimeManager()
    managers['websocket'] = WebSocketManager()
    
    logger.info("Server initialized successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down server...")
    # Cleanup connections
    if 'cache' in managers:
        await managers['cache'].redis.close()

# Create FastAPI app
app = FastAPI(
    title="ESP32 Language Learning System - Realtime API",
    version="2.0.0",
    description="Language learning system using OpenAI Realtime API for voice interactions",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency to inject managers
async def get_managers():
    return managers

# Include API routes with dependency injection
app.include_router(api_router)

# Override the dependency in the router
app.dependency_overrides[get_managers] = get_managers

# WebSocket endpoint
@app.websocket("/ws/{esp32_id}")
async def websocket_endpoint(websocket: WebSocket, esp32_id: str):
    """Main WebSocket endpoint for ESP32 connections"""
    handler = WebSocketHandler(managers)
    await handler.handle_connection(websocket, esp32_id)

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "ESP32 Language Learning System",
        "version": "2.0.0",
        "api_type": "OpenAI Realtime API",
        "status": "operational"
    }

@app.get("/status")
async def status():
    """System status endpoint"""
    active_connections = len(managers.get('websocket', {}).active_connections)
    realtime_connections = len(managers.get('realtime', {}).connections)
    
    return {
        "status": "operational",
        "active_esp32_connections": active_connections,
        "active_realtime_connections": realtime_connections,
        "database": "connected",
        "cache": "connected",
        "firebase": "connected" if managers.get('content', {}).db else "mock_mode"
    }

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=True,
        log_level=settings.log_level.lower()
    )