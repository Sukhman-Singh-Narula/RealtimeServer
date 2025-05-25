from typing import Dict, Set
from fastapi import WebSocket
import json
import asyncio
import logging
import base64

logger = logging.getLogger(__name__)

class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_lock = asyncio.Lock()
    
    async def connect(self, esp32_id: str, websocket: WebSocket):
        """Accept and store WebSocket connection"""
        await websocket.accept()
        async with self.connection_lock:
            self.active_connections[esp32_id] = websocket
        logger.info(f"ESP32 {esp32_id} connected")
    
    async def disconnect(self, esp32_id: str):
        """Remove WebSocket connection"""
        async with self.connection_lock:
            if esp32_id in self.active_connections:
                del self.active_connections[esp32_id]
        logger.info(f"ESP32 {esp32_id} disconnected")
    
    async def send_message(self, esp32_id: str, message: Dict[str, any]):
        """Send JSON message to specific ESP32"""
        if esp32_id in self.active_connections:
            websocket = self.active_connections[esp32_id]
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error sending message to {esp32_id}: {e}")
                await self.disconnect(esp32_id)
    
    async def send_audio(self, esp32_id: str, audio_data: bytes):
        """Send audio data to ESP32"""
        message = {
            "type": "audio_response",
            "audio_data": base64.b64encode(audio_data).decode('utf-8')
        }
        await self.send_message(esp32_id, message)
    
    async def send_text(self, esp32_id: str, text: str, is_final: bool = False):
        """Send text/transcript to ESP32"""
        message = {
            "type": "text_response",
            "text": text,
            "is_final": is_final
        }
        await self.send_message(esp32_id, message)
    
    async def broadcast(self, message: Dict[str, any], exclude: Set[str] = None):
        """Broadcast message to all connected ESP32s"""
        exclude = exclude or set()
        disconnected = []
        
        for esp32_id, websocket in self.active_connections.items():
            if esp32_id not in exclude:
                try:
                    await websocket.send_json(message)
                except:
                    disconnected.append(esp32_id)
        
        # Clean up disconnected clients
        for esp32_id in disconnected:
            await self.disconnect(esp32_id)