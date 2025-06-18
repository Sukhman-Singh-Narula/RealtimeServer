# app/main.py - FINAL VERSION WITH FIXED EXCEPTION HANDLERS

import os
import logging
import asyncio
import time
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# Import configuration
from app.config import settings

# Import managers - FIXED IMPORTS
from app.managers.realtime_manager import RealtimeManager
from app.managers.content_manager import ContentManager
from app.managers.cache_manager import CacheManager
from app.managers.database_manager import DatabaseManager  # Use single database manager
from app.managers.metrics_manager import MetricsManager
from app.managers.profile_manager import UserProfileManager

# Import WebSocket handler - FIXED IMPORT
from app.api.websocket_handler import WebSocketHandler

# Import API routers
from app.api.endpoints import router as api_router
from app.api.profile_endpoints import profile_router

# Configure logging with UTF-8 encoding to handle emojis
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('server.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Verify required environment variables
REQUIRED_ENV_VARS = ["OPENAI_API_KEY"]
for var in REQUIRED_ENV_VARS:
    if not os.getenv(var):
        logger.error(f"{var} environment variable not set!")
        raise ValueError(f"{var} environment variable not set")

# Initialize FastAPI app
app = FastAPI(
    title="ESP32 Language Learning System",
    description="Multi-user AI-powered language learning system with OpenAI Realtime API",
    version="2.0.0"
)



# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Global managers storage
managers: Dict[str, any] = {}

class ServerState:
    def __init__(self):
        self.active_devices: Dict[str, dict] = {}
        self.conversation_stats: Dict[str, dict] = {}
        self.server_start_time = time.time()
        self.total_conversations = 0
        self.total_messages = 0

server_state = ServerState()

# FIXED: Proper dependency injection function
def get_managers_instance():
    """Get the global managers instance"""
    return managers

# Initialize all managers
async def initialize_managers():
    """Initialize all managers with proper error handling"""
    global managers
    
    try:
        logger.info("Initializing managers...")
        
        # 1. Initialize Database Manager
        logger.info("  Initializing database manager...")
        from app.models.database import init_db
        await init_db(settings.database_url)
        managers['database'] = DatabaseManager(settings.database_url)
        
        # 2. Initialize Cache Manager
        logger.info("  Initializing cache manager...")
        managers['cache'] = CacheManager()
        
        # 3. Initialize Content Manager
        logger.info("  Initializing content manager...")
        managers['content'] = ContentManager(settings.firebase_credentials_path)
        
        # 4. Initialize Realtime Manager
        logger.info("  Initializing realtime manager...")
        managers['realtime'] = RealtimeManager()
        
        # 5. Initialize Metrics Manager
        logger.info("  Initializing metrics manager...")
        managers['metrics'] = MetricsManager(
            cache_manager=managers['cache'],
            database_manager=managers['database']
        )
        
        # 6. Initialize Profile Manager
        logger.info("  Initializing profile manager...")
        managers['profile'] = UserProfileManager(
            database_manager=managers['database'],
            content_manager=managers['content']
        )
        
        # 7. Initialize WebSocket Manager (FIXED - don't pass 'websocket' to itself)
        logger.info("  Initializing websocket manager...")
        # Create managers dict without 'websocket' key to avoid circular dependency
        websocket_managers = {
            'database': managers['database'],
            'cache': managers['cache'],
            'content': managers['content'],
            'realtime': managers['realtime'],
            'metrics': managers['metrics'],
            'profile': managers['profile']
        }
        managers['websocket'] = WebSocketHandler(websocket_managers)
        
        # 8. Set cross-references between managers AFTER all are created
        logger.info("  Setting up manager cross-references...")
        managers['realtime'].set_websocket_handler(managers['websocket'])
        managers['websocket'].set_server_state(server_state)
        
        logger.info("  All managers initialized successfully")
        logger.info("  Multi-user conversation flow system ready")
        return True
        
    except Exception as e:
        logger.error(f"  Failed to initialize managers: {e}")
        raise

# Health check endpoints
@app.get("/health")
async def health_check():
    """Comprehensive health check"""
    try:
        uptime = time.time() - server_state.server_start_time
        
        # Get conversation flow stats
        conversation_stats = {}
        if 'websocket' in managers:
            try:
                conversation_stats = managers['websocket'].conversation_flow.get_active_conversations()
            except:
                conversation_stats = {}
        
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": uptime,
            "managers": {
                "database": "database" in managers,
                "cache": "cache" in managers,
                "content": "content" in managers,
                "realtime": "realtime" in managers,
                "websocket": "websocket" in managers,
                "metrics": "metrics" in managers,
                "profile": "profile" in managers,
                "conversation_flow": "websocket" in managers and hasattr(managers['websocket'], 'conversation_flow')
            },
            "active_connections": len(server_state.active_devices),
            "active_conversations": len(conversation_stats),
            "total_conversations": server_state.total_conversations,
            "version": "2.0.0",
            "service": "ESP32 Language Learning System - Multi-User"
        }
        
        return health_status
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/status")
async def server_status():
    """Get detailed server status"""
    uptime = time.time() - server_state.server_start_time
    
    # Get cache status
    cache_status = "unknown"
    if 'cache' in managers:
        try:
            cache_info = await managers['cache'].get_connection_status()
            cache_status = cache_info['type']
        except:
            cache_status = "error"
    
    # Get realtime connection count
    realtime_connections = 0
    if 'realtime' in managers:
        try:
            stats = managers['realtime'].get_connection_stats()
            realtime_connections = stats.get('active_connections', 0)
        except:
            realtime_connections = 0
    
    # Get conversation flow stats
    conversation_stats = {}
    if 'websocket' in managers:
        try:
            conversation_stats = managers['websocket'].conversation_flow.get_active_conversations()
        except:
            conversation_stats = {}
    
    return {
        "status": "healthy",
        "uptime_seconds": uptime,
        "active_esp32_connections": len(server_state.active_devices),
        "active_realtime_connections": realtime_connections,
        "active_conversations": len(conversation_stats),
        "total_conversations": server_state.total_conversations,
        "total_messages": server_state.total_messages,
        "database": "connected" if 'database' in managers else "not_connected",
        "cache": cache_status,
        "firebase": "connected" if 'content' in managers and managers['content'].db else "mock_mode",
        "openai_connected": bool(os.getenv("OPENAI_API_KEY")),
        "conversation_flow": "ready" if 'websocket' in managers and hasattr(managers['websocket'], 'conversation_flow') else "not_ready"
    }

# Get active conversations endpoint
@app.get("/conversations")
async def get_active_conversations():
    """Get all active conversations"""
    if 'websocket' not in managers:
        return {"conversations": {}}
    
    try:
        conversations = managers['websocket'].conversation_flow.get_active_conversations()
        return {"conversations": conversations, "total": len(conversations)}
    except Exception as e:
        logger.error(f"Error getting conversations: {e}")
        return {"error": str(e)}

# WebSocket endpoint
@app.websocket("/upload/{esp32_id}")
async def websocket_endpoint(websocket: WebSocket, esp32_id: str):
    """Main WebSocket endpoint for ESP32 connections"""
    logger.info(f"New connection attempt from ESP32: {esp32_id}")
    
    try:
        # Update server state
        server_state.active_devices[esp32_id] = {
            "status": "connecting",
            "connected_at": datetime.now(),
            "conversation_active": False,
            "websocket": websocket
        }
        
        # Update conversation count
        server_state.total_conversations += 1
        
        # Handle the connection using the WebSocket handler
        await managers['websocket'].handle_connection(websocket, esp32_id)
        
    except WebSocketDisconnect:
        logger.info(f"ESP32 {esp32_id} disconnected")
    except Exception as e:
        logger.error(f"Connection error for {esp32_id}: {e}")
    finally:
        # Cleanup
        if esp32_id in server_state.active_devices:
            del server_state.active_devices[esp32_id]


# Admin endpoints
@app.post("/admin/reset")
async def reset_server_state():
    """Reset server state (admin only)"""
    try:
        # Disconnect all devices
        for esp32_id in list(server_state.active_devices.keys()):
            try:
                if 'websocket' in managers:
                    await managers['websocket']._cleanup_connection(esp32_id)
            except Exception as e:
                logger.warning(f"Error disconnecting {esp32_id}: {e}")
        
        # Reset state
        server_state.active_devices.clear()
        server_state.conversation_stats.clear()
        server_state.total_conversations = 0
        server_state.total_messages = 0
        
        logger.info("Server state reset")
        return {"message": "Server state reset successfully"}
    except Exception as e:
        logger.error(f"Error resetting server state: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/conversations/{esp32_id}")
async def get_conversation_details(esp32_id: str):
    """Get detailed conversation info for specific device"""
    if 'websocket' not in managers:
        raise HTTPException(status_code=500, detail="WebSocket manager not available")
    
    try:
        context = managers['websocket'].conversation_flow.get_user_context(esp32_id)
        if not context:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        return {
            "esp32_id": esp32_id,
            "user_id": context.user_id,
            "state": context.state.value,
            "current_episode": context.current_episode,
            "next_episode": context.next_episode,
            "user_info": context.user_info,
            "session_stats": context.get_session_stats(),
            "words_learned_this_session": context.words_learned_this_session,
            "topics_covered_this_session": context.topics_covered_this_session,
            "openai_session_id": context.openai_session_id,
            "last_activity": context.last_activity.isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation details: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# FIXED: Error handlers that return proper Response objects
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Handle 404 errors with proper JSON response"""
    return JSONResponse(
        status_code=404,
        content={"error": "Endpoint not found", "path": str(request.url)}
    )

@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    """Handle 500 errors with proper JSON response"""
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "details": str(exc)}
    )

# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """Server startup tasks"""
    logger.info("ESP32 Language Learning System starting up...")
    
    try:
        # Initialize all managers
        await initialize_managers()
        
        # FIXED: Set up dependency injection on the app level
        logger.info("  Setting up API dependency injection...")
        
        # Import the get_managers functions from endpoints and override them
        from app.api.endpoints import get_managers as endpoints_get_managers
        from app.api.profile_endpoints import get_managers as profile_get_managers
        
        app.dependency_overrides[endpoints_get_managers] = get_managers_instance
        app.dependency_overrides[profile_get_managers] = get_managers_instance
        
        # Include routers after dependency injection is set up
        logger.info("  Including API routers...")
        app.include_router(api_router)
        app.include_router(profile_router)
        
        logger.info("System startup complete - ready to accept multiple user connections")
        
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Server shutdown tasks"""
    logger.info("ESP32 Language Learning System shutting down...")
    
    # Disconnect all devices gracefully
    for esp32_id in list(server_state.active_devices.keys()):
        try:
            if 'websocket' in managers:
                await managers['websocket']._cleanup_connection(esp32_id)
        except Exception as e:
            logger.warning(f"Error during cleanup for {esp32_id}: {e}")
    
    # Close managers
    if 'cache' in managers:
        try:
            await managers['cache'].close()
        except Exception as e:
            logger.warning(f"Error closing cache manager: {e}")
    
    if 'realtime' in managers:
        try:
            await managers['realtime'].cleanup_all_connections()
        except Exception as e:
            logger.warning(f"Error cleaning up realtime manager: {e}")
    
    logger.info("Shutdown complete")

# Main entry point
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info("=" * 60)
    logger.info("ESP32 LANGUAGE LEARNING SYSTEM - MULTI-USER")
    logger.info("=" * 60)
    logger.info(f"Starting server on {host}:{port}")
    logger.info(f"OpenAI API Key: {'Configured' if os.getenv('OPENAI_API_KEY') else 'Missing'}")
    logger.info(f"Dashboard: http://localhost:{port}/dashboard")
    logger.info(f"API Docs: http://localhost:{port}/docs")
    logger.info(f"WebSocket: ws://localhost:{port}/upload/{{esp32_id}}")
    logger.info(f"Conversations: http://localhost:{port}/conversations")
    logger.info("=" * 60)
    logger.info("Features:")
    logger.info("- Multi-user simultaneous connections")
    logger.info("- One-to-one OpenAI Realtime API per user")
    logger.info("- Dynamic system prompts based on user progress")
    logger.info("- Conversation flow management")
    logger.info("- Real-time analytics and monitoring")
    logger.info("=" * 60)
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        log_level="info",
        reload=False,
        access_log=True
    )