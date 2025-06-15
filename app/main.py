# File: main.py - COMPLETE SERVER WITH ALL FUNCTIONALITIES

import os
import logging
import asyncio
import json
import time
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# Import all managers and handlers
from app.managers.realtime_manager import RealtimeManager
from app.managers.content_manager import ContentManager
from app.api.websocket_handler import WebSocketHandler
from app.agents.agent_configs import create_choice_agent_config

# Configure comprehensive logging
logging.basicConfig(
    level=logging.INFO,
    format='[SERVER] %(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('server.log')
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
    title="StoryTeller Server",
    description="AI-powered conversational teddy bear server",
    version="1.0.0"
)

# Enable CORS with specific configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Global state management
class ServerState:
    def __init__(self):
        self.active_devices: Dict[str, dict] = {}
        self.conversation_stats: Dict[str, dict] = {}
        self.server_start_time = time.time()
        self.total_conversations = 0
        self.total_messages = 0

server_state = ServerState()

# Initialize managers with proper error handling
try:
    realtime_manager = RealtimeManager()
    content_manager = ContentManager()
    websocket_handler = WebSocketHandler(realtime_manager, content_manager)
    
    # Connect components
    realtime_manager.set_websocket_handler(websocket_handler)
    websocket_handler.set_server_state(server_state)
    
    logger.info("✅ All managers initialized successfully")
except Exception as e:
    logger.error(f"❌ Failed to initialize managers: {e}")
    raise

# Pydantic models for API endpoints
class DeviceStatus(BaseModel):
    device_id: str
    status: str
    connected_at: datetime
    conversation_active: bool
    episode: Optional[str] = None

class ConversationStats(BaseModel):
    device_id: str
    start_time: datetime
    duration: Optional[float] = None
    messages_exchanged: int
    episode: Optional[str] = None

class ServerStats(BaseModel):
    uptime_seconds: float
    active_devices: int
    total_conversations: int
    total_messages: int
    openai_connected: bool

# === HEALTH CHECK ENDPOINTS ===

@app.get("/", response_class=HTMLResponse)
async def root():
    """Root endpoint with basic server info"""
    uptime = time.time() - server_state.server_start_time
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>StoryTeller Server</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .status {{ padding: 10px; margin: 10px 0; border-radius: 5px; }}
            .healthy {{ background-color: #d4edda; color: #155724; }}
            .info {{ background-color: #d1ecf1; color: #0c5460; }}
        </style>
    </head>
    <body>
        <h1>🧸 StoryTeller Server</h1>
        <div class="status healthy">✅ Server is running</div>
        <div class="status info">⏱️ Uptime: {uptime:.2f} seconds</div>
        <div class="status info">🔗 Active Devices: {len(server_state.active_devices)}</div>
        <div class="status info">💬 Total Conversations: {server_state.total_conversations}</div>
        
        <h2>Available Endpoints:</h2>
        <ul>
            <li><a href="/health">/health</a> - Health check</li>
            <li><a href="/status">/status</a> - Server status</li>
            <li><a href="/devices">/devices</a> - Active devices</li>
            <li><a href="/dashboard">/dashboard</a> - Dashboard</li>
            <li><strong>WebSocket:</strong> /upload/{{device_id}} - Device connections</li>
        </ul>
    </body>
    </html>
    """
    return html_content

@app.get("/health")
async def health_check():
    """Comprehensive health check"""
    try:
        # Test OpenAI connection
        openai_healthy = bool(os.getenv("OPENAI_API_KEY"))
        
        # Check manager states
        managers_healthy = all([
            realtime_manager is not None,
            content_manager is not None,
            websocket_handler is not None
        ])
        
        uptime = time.time() - server_state.server_start_time
        
        health_status = {
            "status": "healthy" if (openai_healthy and managers_healthy) else "degraded",
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": uptime,
            "checks": {
                "openai_key_configured": openai_healthy,
                "managers_initialized": managers_healthy,
                "active_connections": len(server_state.active_devices),
                "total_conversations": server_state.total_conversations
            },
            "version": "1.0.0",
            "service": "StoryTeller Server"
        }
        
        return health_status
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/status", response_model=ServerStats)
async def server_status():
    """Get detailed server status"""
    uptime = time.time() - server_state.server_start_time
    
    return ServerStats(
        uptime_seconds=uptime,
        active_devices=len(server_state.active_devices),
        total_conversations=server_state.total_conversations,
        total_messages=server_state.total_messages,
        openai_connected=bool(os.getenv("OPENAI_API_KEY"))
    )

# === DEVICE MANAGEMENT ENDPOINTS ===

@app.get("/devices", response_model=List[DeviceStatus])
async def get_active_devices():
    """Get list of all active devices"""
    devices = []
    for device_id, device_info in server_state.active_devices.items():
        devices.append(DeviceStatus(
            device_id=device_id,
            status=device_info.get("status", "unknown"),
            connected_at=device_info.get("connected_at", datetime.now()),
            conversation_active=device_info.get("conversation_active", False),
            episode=device_info.get("current_episode")
        ))
    return devices

@app.get("/devices/{device_id}")
async def get_device_status(device_id: str):
    """Get status of specific device"""
    if device_id not in server_state.active_devices:
        raise HTTPException(status_code=404, detail="Device not found")
    
    device_info = server_state.active_devices[device_id]
    return DeviceStatus(
        device_id=device_id,
        status=device_info.get("status", "unknown"),
        connected_at=device_info.get("connected_at", datetime.now()),
        conversation_active=device_info.get("conversation_active", False),
        episode=device_info.get("current_episode")
    )

@app.post("/devices/{device_id}/disconnect")
async def disconnect_device(device_id: str):
    """Manually disconnect a device"""
    if device_id not in server_state.active_devices:
        raise HTTPException(status_code=404, detail="Device not found")
    
    try:
        # End conversation and cleanup
        await websocket_handler._cleanup_connection(device_id)
        return {"message": f"Device {device_id} disconnected successfully"}
    except Exception as e:
        logger.error(f"Error disconnecting device {device_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# === CONVERSATION MANAGEMENT ===

@app.get("/conversations", response_model=List[ConversationStats])
async def get_conversation_stats():
    """Get conversation statistics"""
    conversations = []
    for device_id, stats in server_state.conversation_stats.items():
        conversations.append(ConversationStats(
            device_id=device_id,
            start_time=stats.get("start_time", datetime.now()),
            duration=stats.get("duration"),
            messages_exchanged=stats.get("messages", 0),
            episode=stats.get("episode")
        ))
    return conversations

@app.get("/conversations/{device_id}")
async def get_device_conversation_stats(device_id: str):
    """Get conversation stats for specific device"""
    if device_id not in server_state.conversation_stats:
        raise HTTPException(status_code=404, detail="No conversation data found for device")
    
    stats = server_state.conversation_stats[device_id]
    return ConversationStats(
        device_id=device_id,
        start_time=stats.get("start_time", datetime.now()),
        duration=stats.get("duration"),
        messages_exchanged=stats.get("messages", 0),
        episode=stats.get("episode")
    )

# === CONTENT MANAGEMENT ===

@app.get("/episodes")
async def get_available_episodes():
    """Get list of available episodes"""
    try:
        episodes = await content_manager.get_available_episodes()
        return {"episodes": episodes}
    except Exception as e:
        logger.error(f"Error fetching episodes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/episodes/{device_id}/next")
async def get_next_episode(device_id: str):
    """Get next episode for device"""
    try:
        episode = await content_manager.get_next_episode(device_id)
        if not episode:
            raise HTTPException(status_code=404, detail="No episodes available")
        return episode
    except Exception as e:
        logger.error(f"Error getting next episode for {device_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# === WEBSOCKET ENDPOINT ===

@app.websocket("/upload/{device_id}")
async def websocket_endpoint(websocket: WebSocket, device_id: str):
    """Main WebSocket endpoint for ESP32/device connections"""
    logger.info(f"🔌 New connection attempt from device: {device_id}")
    
    try:
        # Update server state
        server_state.active_devices[device_id] = {
            "status": "connecting",
            "connected_at": datetime.now(),
            "conversation_active": False,
            "websocket": websocket
        }
        
        # Handle the connection
        await websocket_handler.handle_connection(websocket, device_id)
        
    except WebSocketDisconnect:
        logger.info(f"🔌 Device {device_id} disconnected")
    except Exception as e:
        logger.error(f"❌ Connection error for {device_id}: {e}")
    finally:
        # Cleanup
        if device_id in server_state.active_devices:
            del server_state.active_devices[device_id]

# === DASHBOARD WEBSOCKET ===

@app.websocket("/dashboard/ws")
async def dashboard_websocket(websocket: WebSocket):
    """WebSocket endpoint for dashboard real-time updates"""
    await websocket.accept()
    logger.info("📊 Dashboard connected")
    
    try:
        while True:
            # Send periodic updates to dashboard
            dashboard_data = {
                "type": "status_update",
                "timestamp": datetime.now().isoformat(),
                "active_devices": len(server_state.active_devices),
                "total_conversations": server_state.total_conversations,
                "uptime": time.time() - server_state.server_start_time,
                "devices": [
                    {
                        "device_id": device_id,
                        "status": info.get("status", "unknown"),
                        "conversation_active": info.get("conversation_active", False)
                    }
                    for device_id, info in server_state.active_devices.items()
                ]
            }
            
            await websocket.send_text(json.dumps(dashboard_data))
            await asyncio.sleep(5)  # Update every 5 seconds
            
    except WebSocketDisconnect:
        logger.info("📊 Dashboard disconnected")
    except Exception as e:
        logger.error(f"❌ Dashboard websocket error: {e}")

# === ADMIN ENDPOINTS ===

@app.post("/admin/reset")
async def reset_server_state():
    """Reset server state (admin only)"""
    try:
        # Disconnect all devices
        for device_id in list(server_state.active_devices.keys()):
            try:
                await websocket_handler._cleanup_connection(device_id)
            except Exception as e:
                logger.warning(f"Error disconnecting {device_id}: {e}")
        
        # Reset state
        server_state.active_devices.clear()
        server_state.conversation_stats.clear()
        server_state.total_conversations = 0
        server_state.total_messages = 0
        
        logger.info("🔄 Server state reset")
        return {"message": "Server state reset successfully"}
    except Exception as e:
        logger.error(f"Error resetting server state: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/logs")
async def get_recent_logs():
    """Get recent server logs (admin only)"""
    try:
        # Read last 100 lines of log file
        if os.path.exists("server.log"):
            with open("server.log", "r") as f:
                lines = f.readlines()
                recent_lines = lines[-100:] if len(lines) > 100 else lines
                return {"logs": recent_lines}
        else:
            return {"logs": ["No log file found"]}
    except Exception as e:
        logger.error(f"Error reading logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# === DASHBOARD HTML ===

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Simple dashboard for monitoring"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>StoryTeller Dashboard</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
            .container { max-width: 1200px; margin: 0 auto; }
            .card { background: white; padding: 20px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; }
            .status-card { padding: 15px; border-radius: 5px; text-align: center; }
            .status-good { background: #d4edda; color: #155724; }
            .status-warning { background: #fff3cd; color: #856404; }
            .status-error { background: #f8d7da; color: #721c24; }
            .device-list { list-style: none; padding: 0; }
            .device-item { padding: 10px; margin: 5px 0; background: #f8f9fa; border-radius: 5px; }
            .logs { background: #2d3748; color: #e2e8f0; padding: 15px; border-radius: 5px; font-family: monospace; height: 300px; overflow-y: auto; }
            button { padding: 10px 20px; margin: 5px; border: none; border-radius: 5px; cursor: pointer; }
            .btn-primary { background: #007bff; color: white; }
            .btn-danger { background: #dc3545; color: white; }
            .btn-success { background: #28a745; color: white; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🧸 StoryTeller Dashboard</h1>
            
            <div class="status-grid">
                <div class="status-card status-good">
                    <h3>Server Status</h3>
                    <p id="server-status">✅ Online</p>
                </div>
                <div class="status-card status-good">
                    <h3>Active Devices</h3>
                    <p id="active-devices">0</p>
                </div>
                <div class="status-card status-good">
                    <h3>Total Conversations</h3>
                    <p id="total-conversations">0</p>
                </div>
                <div class="status-card status-good">
                    <h3>Uptime</h3>
                    <p id="uptime">0s</p>
                </div>
            </div>
            
            <div class="card">
                <h2>Connected Devices</h2>
                <ul id="device-list" class="device-list">
                    <li>No devices connected</li>
                </ul>
            </div>
            
            <div class="card">
                <h2>Actions</h2>
                <button class="btn-success" onclick="refreshData()">🔄 Refresh</button>
                <button class="btn-primary" onclick="testConnection()">🔧 Test Connection</button>
                <button class="btn-danger" onclick="resetServer()">⚠️ Reset Server</button>
            </div>
            
            <div class="card">
                <h2>Live Server Logs</h2>
                <div id="logs" class="logs">Connecting to live logs...</div>
            </div>
        </div>
        
        <script>
            let ws = null;
            
            function connectWebSocket() {
                ws = new WebSocket('ws://localhost:8000/dashboard/ws');
                
                ws.onopen = function() {
                    console.log('Dashboard WebSocket connected');
                    document.getElementById('logs').innerHTML = 'Connected to live logs...\\n';
                };
                
                ws.onmessage = function(event) {
                    const data = JSON.parse(event.data);
                    updateDashboard(data);
                };
                
                ws.onclose = function() {
                    console.log('Dashboard WebSocket disconnected');
                    setTimeout(connectWebSocket, 5000);
                };
            }
            
            function updateDashboard(data) {
                document.getElementById('active-devices').textContent = data.active_devices;
                document.getElementById('total-conversations').textContent = data.total_conversations;
                document.getElementById('uptime').textContent = Math.round(data.uptime) + 's';
                
                const deviceList = document.getElementById('device-list');
                if (data.devices && data.devices.length > 0) {
                    deviceList.innerHTML = data.devices.map(device => 
                        `<li class="device-item">📱 ${device.device_id} - ${device.status} ${device.conversation_active ? '💬' : ''}</li>`
                    ).join('');
                } else {
                    deviceList.innerHTML = '<li>No devices connected</li>';
                }
            }
            
            async function refreshData() {
                try {
                    const response = await fetch('/status');
                    const data = await response.json();
                    console.log('Manual refresh:', data);
                } catch (error) {
                    console.error('Refresh failed:', error);
                }
            }
            
            async function testConnection() {
                try {
                    const response = await fetch('/health');
                    const data = await response.json();
                    alert('Health check: ' + data.status);
                } catch (error) {
                    alert('Connection test failed: ' + error.message);
                }
            }
            
            async function resetServer() {
                if (confirm('Are you sure you want to reset the server? This will disconnect all devices.')) {
                    try {
                        const response = await fetch('/admin/reset', { method: 'POST' });
                        const data = await response.json();
                        alert(data.message);
                    } catch (error) {
                        alert('Reset failed: ' + error.message);
                    }
                }
            }
            
            // Start dashboard
            connectWebSocket();
        </script>
    </body>
    </html>
    """
    return html_content

# === ERROR HANDLERS ===

@app.exception_handler(404)
async def not_found_handler(request, exc):
    return {"error": "Endpoint not found", "path": str(request.url)}

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    logger.error(f"Internal server error: {exc}")
    return {"error": "Internal server error", "details": str(exc)}

# === STARTUP/SHUTDOWN EVENTS ===

@app.on_event("startup")
async def startup_event():
    """Server startup tasks"""
    logger.info("🚀 StoryTeller Server starting up...")
    logger.info(f"✅ OpenAI API Key configured: {bool(os.getenv('OPENAI_API_KEY'))}")
    logger.info("✅ All managers initialized")
    logger.info("🎯 Server ready to accept connections")

@app.on_event("shutdown")
async def shutdown_event():
    """Server shutdown tasks"""
    logger.info("🛑 StoryTeller Server shutting down...")
    
    # Disconnect all devices gracefully
    for device_id in list(server_state.active_devices.keys()):
        try:
            await websocket_handler._cleanup_connection(device_id)
        except Exception as e:
            logger.warning(f"Error during cleanup for {device_id}: {e}")
    
    logger.info("✅ Shutdown complete")

# === MAIN ENTRY POINT ===

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info("=" * 50)
    logger.info("🧸 STORYTELLER SERVER")
    logger.info("=" * 50)
    logger.info(f"🌐 Starting server on {host}:{port}")
    logger.info(f"🔑 OpenAI API Key: {'✅ Configured' if os.getenv('OPENAI_API_KEY') else '❌ Missing'}")
    logger.info(f"📊 Dashboard: http://localhost:{port}/dashboard")
    logger.info(f"🔗 WebSocket: ws://localhost:{port}/upload/{{device_id}}")
    logger.info("=" * 50)
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        log_level="info",
        reload=False,  # Set to True for development
        access_log=True
    )