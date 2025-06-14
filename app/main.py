from fastapi import FastAPI, WebSocket, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
import uvicorn
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any
import os
from pathlib import Path

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
    
    # Validate configuration
    config_issues = settings.validate_config()
    for issue in config_issues:
        if issue.startswith("ERROR"):
            logger.error(issue)
        else:
            logger.warning(issue)
    
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
        await managers['cache'].close()

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

# Mount static files if directory exists
static_dir = Path("static")
if static_dir.exists():
    app.mount("/static", StaticFiles(directory="static"), name="static")
    logger.info("Static files mounted at /static")

# Dependency to inject managers
async def get_managers():
    return managers

# Include API routes with dependency injection
app.include_router(api_router)

# Override the dependency in the router
app.dependency_overrides[get_managers] = get_managers

# WebSocket endpoint
@app.websocket("/upload/{esp32_id}")
async def websocket_endpoint(websocket: WebSocket, esp32_id: str):
    """Main WebSocket endpoint for ESP32 connections"""
    handler = WebSocketHandler(managers)
    await handler.handle_connection(websocket, esp32_id)

# Dashboard endpoint - UPDATED
@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard():
    """Serve the testing dashboard"""
    dashboard_path = Path("static/dashboard.html")
    
    if dashboard_path.exists():
        # Serve the actual dashboard file
        return FileResponse(dashboard_path, media_type="text/html")
    else:
        # Fallback if dashboard file doesn't exist
        fallback_html = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Dashboard Not Found</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 40px 20px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    color: white;
                }
                .container {
                    background: rgba(255, 255, 255, 0.1);
                    padding: 40px;
                    border-radius: 20px;
                    text-align: center;
                }
                h1 { color: #fff; margin-bottom: 20px; }
                p { color: #f0f0f0; margin-bottom: 15px; }
                .code { 
                    background: rgba(0,0,0,0.3); 
                    padding: 15px; 
                    border-radius: 8px; 
                    font-family: monospace; 
                    margin: 20px 0;
                }
                .button {
                    display: inline-block;
                    background: #48bb78;
                    color: white;
                    padding: 12px 24px;
                    text-decoration: none;
                    border-radius: 8px;
                    margin: 10px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🎯 Dashboard Not Available</h1>
                <p>The dashboard HTML file is missing. Please follow these steps:</p>
                
                <div class="code">
                    <strong>1. Create directory:</strong><br>
                    mkdir static
                </div>
                
                <div class="code">
                    <strong>2. Save dashboard as:</strong><br>
                    static/dashboard.html
                </div>
                
                <div class="code">
                    <strong>3. Expected file location:</strong><br>
                    {project_root}/static/dashboard.html
                </div>
                
                <p>After creating the file, refresh this page.</p>
                
                <a href="/status" class="button">📊 System Status</a>
                <a href="/docs" class="button">📚 API Docs</a>
            </div>
        </body>
        </html>
        """
        logger.warning("Dashboard file not found at static/dashboard.html")
        return HTMLResponse(content=fallback_html)

# Dashboard WebSocket for real-time updates
@app.websocket("/dashboard/ws")
async def dashboard_websocket(websocket: WebSocket):
    """WebSocket endpoint for dashboard real-time updates"""
    await websocket.accept()
    logger.info("Dashboard WebSocket connected")
    
    try:
        while True:
            # Send periodic updates to dashboard
            update_data = {
                "type": "connection_update",
                "timestamp": asyncio.get_event_loop().time(),
                "connections": {
                    "esp32": len(managers.get('websocket', {}).active_connections) if 'websocket' in managers else 0,
                    "openai": len(managers.get('realtime', {}).connections) if 'realtime' in managers else 0,
                    "sessions": []  # Add active session data here if available
                }
            }
            
            # Send system metrics
            metrics_data = {
                "type": "system_metrics", 
                "timestamp": asyncio.get_event_loop().time(),
                "metrics": {
                    "messages_per_minute": 0,  # Calculate from actual data
                    "audio_chunks_per_minute": 0,  # Calculate from actual data
                    "avg_response_time": 0,  # Calculate from actual data
                    "error_rate": 0  # Calculate from actual data
                }
            }
            
            await websocket.send_json(update_data)
            await asyncio.sleep(1)  # Small delay
            await websocket.send_json(metrics_data)
            
            await asyncio.sleep(4)  # Update every 5 seconds total
            
    except Exception as e:
        logger.error(f"Dashboard WebSocket error: {e}")
    finally:
        logger.info("Dashboard WebSocket disconnected")

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "ESP32 Language Learning System",
        "version": "2.0.0",
        "api_type": "OpenAI Realtime API",
        "status": "operational",
        "endpoints": {
            "websocket": "/upload/{esp32_id}",
            "dashboard": "/dashboard",
            "api": "/api",
            "status": "/status",
            "docs": "/docs"
        }
    }

@app.get("/status")
async def status():
    """System status endpoint"""
    active_connections = len(managers.get('websocket', {}).active_connections) if 'websocket' in managers else 0
    realtime_connections = len(managers.get('realtime', {}).connections) if 'realtime' in managers else 0
    
    cache_status = "unknown"
    if 'cache' in managers:
        try:
            cache_info = await managers['cache'].get_connection_status()
            cache_status = f"{cache_info['type']} - {'connected' if cache_info['connected'] else 'disconnected'}"
        except:
            cache_status = "error"
    
    return {
        "status": "operational",
        "active_esp32_connections": active_connections,
        "active_realtime_connections": realtime_connections,
        "database": "connected",
        "cache": cache_status,
        "firebase": "connected" if managers.get('content', {}).db else "mock_mode",
        "dashboard_available": Path("static/dashboard.html").exists()
    }

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=True,
        log_level=settings.log_level.lower()
    )