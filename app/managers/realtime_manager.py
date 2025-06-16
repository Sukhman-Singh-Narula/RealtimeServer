# app/managers/realtime_manager.py - FIXED FOR WEBSOCKET CONNECTION ISSUES

import asyncio
import json
import logging
import websockets
import base64
import time
import ssl
from typing import Dict, Optional, Callable, Any
from datetime import datetime
import os

logger = logging.getLogger(__name__)

class RealtimeConnection:
    """Represents a single OpenAI Realtime API connection"""
    
    def __init__(self, esp32_id: str, websocket, callback: Callable):
        self.esp32_id = esp32_id
        self.websocket = websocket
        self.callback = callback
        self.session_id: Optional[str] = None
        self.is_active = True
        self.created_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        self.is_generating_response = False
        
    def update_activity(self):
        """Update last activity timestamp"""
        self.last_activity = datetime.utcnow()
        
    def close(self):
        """Mark connection as closed"""
        self.is_active = False

class RealtimeManager:
    """Manages OpenAI Realtime API connections for multiple ESP32 devices"""
    
    def __init__(self):
        self.connections: Dict[str, RealtimeConnection] = {}
        self.websocket_handler: Optional[Callable] = None
        logger.info("RealtimeManager initialized")
    
    def set_websocket_handler(self, handler):
        """Set reference to websocket handler for sending responses"""
        self.websocket_handler = handler
        logger.info("WebSocket handler set for RealtimeManager")
    
    async def create_connection(self, esp32_id: str, callback: Callable) -> Optional[RealtimeConnection]:
        """Create a new OpenAI Realtime connection with proper WebSocket handling"""
        try:
            logger.info(f"Creating OpenAI Realtime connection for {esp32_id}")
            
            # Close existing connection if any
            if esp32_id in self.connections:
                logger.info(f"Closing existing connection for {esp32_id}")
                self.close_connection(esp32_id)
                await asyncio.sleep(0.5)
            
            # Get OpenAI API key
            api_key = self._get_openai_api_key()
            
            # Create SSL context for secure connection
            ssl_context = ssl.create_default_context()
            
            # FIXED: Use proper websockets.connect syntax with extra_headers
            uri = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17"
            
            # Connect to OpenAI Realtime API with proper headers
            websocket = await websockets.connect(
                uri,
                extra_headers={
                    "Authorization": f"Bearer {api_key}",
                    "OpenAI-Beta": "realtime=v1"
                },
                ssl=ssl_context,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=10
            )
            
            logger.info(f"Connected to OpenAI Realtime API for {esp32_id}")
            
            # Create connection object
            connection = RealtimeConnection(esp32_id, websocket, callback)
            self.connections[esp32_id] = connection
            
            # Start listening to OpenAI responses
            asyncio.create_task(self._listen_to_openai(connection))
            
            # Wait for session.created event
            session_id = await self._wait_for_session_created(connection)
            if session_id:
                connection.session_id = session_id
                logger.info(f"Session created for {esp32_id}: {session_id}")
                return connection
            else:
                logger.error(f"Failed to create session for {esp32_id}")
                self.close_connection(esp32_id)
                return None
                
        except Exception as e:
            logger.error(f"Failed to create realtime connection for {esp32_id}: {e}")
            if esp32_id in self.connections:
                self.close_connection(esp32_id)
            return None
    
    async def _wait_for_session_created(self, connection: RealtimeConnection, timeout: float = 15.0) -> Optional[str]:
        """Wait for session.created event with longer timeout"""
        try:
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    response = await asyncio.wait_for(connection.websocket.recv(), timeout=3.0)
                    data = json.loads(response)
                    
                    if data.get("type") == "session.created":
                        session_id = data.get("session", {}).get("id")
                        return session_id
                    elif data.get("type") == "error":
                        logger.error(f"OpenAI API error during session creation: {data}")
                        return None
                    else:
                        logger.debug(f"Waiting for session.created, got: {data.get('type')}")
                        
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Error during session creation wait: {e}")
                    return None
                    
            logger.error(f"Timeout waiting for session creation for {connection.esp32_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error waiting for session creation: {e}")
            return None
    
    async def _listen_to_openai(self, connection: RealtimeConnection):
        """Listen to OpenAI responses and forward to callback"""
        try:
            logger.info(f"Starting OpenAI listener for {connection.esp32_id}")
            
            while connection.is_active:
                try:
                    response = await connection.websocket.recv()
                    data = json.loads(response)
                    
                    # Update activity
                    connection.update_activity()
                    
                    # Forward to callback
                    await connection.callback(connection.esp32_id, data)
                    
                except websockets.exceptions.ConnectionClosed:
                    logger.info(f"OpenAI connection closed for {connection.esp32_id}")
                    break
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON from OpenAI for {connection.esp32_id}: {e}")
                except Exception as e:
                    logger.error(f"Error in OpenAI listener for {connection.esp32_id}: {e}")
                    break
                    
        except Exception as e:
            logger.error(f"Error in OpenAI listener setup for {connection.esp32_id}: {e}")
        finally:
            connection.close()
            if connection.esp32_id in self.connections:
                del self.connections[connection.esp32_id]
                logger.info(f"Cleaned up OpenAI connection for {connection.esp32_id}")
    
    def get_connection(self, esp32_id: str) -> Optional[RealtimeConnection]:
        """Get connection for ESP32 device"""
        return self.connections.get(esp32_id)
    
    def close_connection(self, esp32_id: str):
        """Close connection for ESP32 device"""
        if esp32_id in self.connections:
            connection = self.connections[esp32_id]
            connection.close()
            
            try:
                asyncio.create_task(connection.websocket.close())
            except Exception as e:
                logger.warning(f"Error closing websocket for {esp32_id}: {e}")
            
            del self.connections[esp32_id]
            logger.info(f"Closed realtime connection for {esp32_id}")
    
    def update_session(self, esp32_id: str, instructions: str, voice: str = "alloy", tools: list = None):
        """Update session configuration"""
        connection = self.get_connection(esp32_id)
        if not connection:
            logger.error(f"No connection found for {esp32_id}")
            return
        
        try:
            session_update = {
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "instructions": instructions,
                    "voice": voice,
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "input_audio_transcription": {
                        "model": "whisper-1"
                    },
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 500
                    },
                    "tools": tools or []
                }
            }
            
            asyncio.create_task(self._send_to_connection(connection, session_update))
            logger.info(f"Session updated for {esp32_id} with voice: {voice}")
            
        except Exception as e:
            logger.error(f"Error updating session for {esp32_id}: {e}")
    
    def send_event(self, esp32_id: str, event: dict):
        """Send event to OpenAI"""
        connection = self.get_connection(esp32_id)
        if connection:
            asyncio.create_task(self._send_to_connection(connection, event))
        else:
            logger.warning(f"No connection found for {esp32_id} when sending event")
    
    def send_audio(self, esp32_id: str, audio_data: bytes):
        """Send audio data to OpenAI"""
        try:
            # Encode audio to base64
            base64_audio = base64.b64encode(audio_data).decode('utf-8')
            
            event = {
                "type": "input_audio_buffer.append",
                "audio": base64_audio
            }
            
            self.send_event(esp32_id, event)
            
            # Update activity
            connection = self.get_connection(esp32_id)
            if connection:
                connection.update_activity()
                
        except Exception as e:
            logger.error(f"Error sending audio for {esp32_id}: {e}")
    
    def create_response(self, esp32_id: str, modalities: list = None):
        """Create response from OpenAI"""
        try:
            if modalities is None:
                modalities = ["text", "audio"]
            
            # First commit any pending audio
            self.send_event(esp32_id, {
                "type": "input_audio_buffer.commit"
            })
            
            # Then create response
            response_event = {
                "type": "response.create",
                "response": {
                    "modalities": modalities
                }
            }
            
            self.send_event(esp32_id, response_event)
            
            # Mark as generating response
            connection = self.get_connection(esp32_id)
            if connection:
                connection.is_generating_response = True
                
            logger.info(f"Response creation requested for {esp32_id}")
            
        except Exception as e:
            logger.error(f"Error creating response for {esp32_id}: {e}")
    
    def start_conversation(self, esp32_id: str):
        """Start conversation by triggering initial response"""
        try:
            # Add initial conversation item
            initial_item = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Hello! Please start our conversation."
                        }
                    ]
                }
            }
            
            self.send_event(esp32_id, initial_item)
            
            # Create initial response
            self.create_response(esp32_id)
            
            logger.info(f"Conversation started for {esp32_id}")
            
        except Exception as e:
            logger.error(f"Error starting conversation for {esp32_id}: {e}")
    
    def end_conversation(self, esp32_id: str):
        """End conversation and cleanup"""
        logger.info(f"Ending conversation for {esp32_id}")
        self.close_connection(esp32_id)
    
    async def _send_to_connection(self, connection: RealtimeConnection, data: dict):
        """Send data to a specific connection"""
        try:
            if connection.is_active:
                await connection.websocket.send(json.dumps(data))
                connection.update_activity()
            else:
                logger.warning(f"Attempted to send to inactive connection: {connection.esp32_id}")
        except Exception as e:
            logger.error(f"Error sending to connection {connection.esp32_id}: {e}")
            connection.close()
    
    def _get_openai_api_key(self) -> str:
        """Get OpenAI API key from environment"""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        return api_key
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection statistics"""
        stats = {
            "total_connections": len(self.connections),
            "active_connections": len([c for c in self.connections.values() if c.is_active]),
            "connections": {}
        }
        
        for esp32_id, connection in self.connections.items():
            stats["connections"][esp32_id] = {
                "session_id": connection.session_id,
                "is_active": connection.is_active,
                "created_at": connection.created_at.isoformat(),
                "last_activity": connection.last_activity.isoformat(),
                "is_generating_response": connection.is_generating_response
            }
        
        return stats
    
    async def cleanup_all_connections(self):
        """Cleanup all connections"""
        logger.info("Cleaning up all realtime connections")
        
        for esp32_id in list(self.connections.keys()):
            self.close_connection(esp32_id)
        
        logger.info("All realtime connections cleaned up")