# app/managers/realtime_manager.py - OFFICIAL OPENAI DOCUMENTATION COMPLIANT

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
    """Represents a single OpenAI Realtime API connection following official docs"""
    
    def __init__(self, esp32_id: str, websocket, callback: Callable):
        self.esp32_id = esp32_id
        self.websocket = websocket
        self.callback = callback
        self.session_id: Optional[str] = None
        self.is_active = True
        self.created_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        self.is_generating_response = False
        self.session_ready = False
        self._listener_task = None
        
    def update_activity(self):
        """Update last activity timestamp"""
        self.last_activity = datetime.utcnow()
        
    def close(self):
        """Mark connection as closed"""
        self.is_active = False
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()

class RealtimeManager:
    """Manages OpenAI Realtime API connections following official documentation patterns"""
    
    def __init__(self):
        self.connections: Dict[str, RealtimeConnection] = {}
        self.websocket_handler: Optional[Callable] = None
        logger.info("RealtimeManager initialized (Official OpenAI Compliant)")
    
    def set_websocket_handler(self, handler):
        """Set reference to websocket handler for sending responses"""
        self.websocket_handler = handler
        logger.info("WebSocket handler set for RealtimeManager")
    
    async def create_connection(self, esp32_id: str, callback: Callable) -> Optional[RealtimeConnection]:
        """Create OpenAI Realtime connection following official connection pattern"""
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
            
            # Connect to OpenAI Realtime API with official model
            uri = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17"
            
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
            
            # Start the unified message listener
            connection._listener_task = asyncio.create_task(
                self._handle_session_lifecycle(connection)
            )
            
            # Wait for session to be ready (with timeout)
            max_wait_time = 15.0
            wait_start = time.time()
            
            while not connection.session_ready and time.time() - wait_start < max_wait_time:
                if not connection.is_active:
                    logger.error(f"Connection failed during session setup for {esp32_id}")
                    self.close_connection(esp32_id)
                    return None
                await asyncio.sleep(0.1)
            
            if connection.session_ready:
                logger.info(f"Session ready for {esp32_id}: {connection.session_id}")
                return connection
            else:
                logger.error(f"Session setup timeout for {esp32_id}")
                self.close_connection(esp32_id)
                return None
                
        except Exception as e:
            logger.error(f"Failed to create realtime connection for {esp32_id}: {e}")
            if esp32_id in self.connections:
                self.close_connection(esp32_id)
            return None
    
    async def _handle_session_lifecycle(self, connection: RealtimeConnection):
        """Handle complete session lifecycle following official documentation"""
        try:
            logger.info(f"Starting session lifecycle handler for {connection.esp32_id}")
            
            while connection.is_active:
                try:
                    # Wait for message with timeout
                    response = await asyncio.wait_for(
                        connection.websocket.recv(), 
                        timeout=30.0
                    )
                    
                    data = json.loads(response)
                    event_type = data.get("type")
                    
                    # Update activity
                    connection.update_activity()
                    
                    # Handle session creation (first priority)
                    if event_type == "session.created" and not connection.session_ready:
                        session_id = data.get("session", {}).get("id")
                        if session_id:
                            connection.session_id = session_id
                            connection.session_ready = True
                            logger.info(f"Session created for {connection.esp32_id}: {session_id}")
                        continue
                    
                    # Handle session update confirmation
                    elif event_type == "session.updated":
                        logger.info(f"Session updated for {connection.esp32_id}")
                        # Forward to callback for any additional handling
                        if connection.session_ready:
                            await connection.callback(connection.esp32_id, data)
                        continue
                    
                    # Handle errors during setup
                    elif event_type == "error" and not connection.session_ready:
                        logger.error(f"OpenAI API error during setup for {connection.esp32_id}: {data}")
                        connection.close()
                        break
                    
                    # Handle all official server events after session is ready
                    elif connection.session_ready:
                        await self._handle_server_event(connection, data)
                    
                    # Log unexpected messages during setup
                    else:
                        logger.debug(f"Waiting for session.created, got: {event_type} for {connection.esp32_id}")
                    
                except asyncio.TimeoutError:
                    # Send periodic ping to keep connection alive
                    if connection.is_active:
                        try:
                            await connection.websocket.ping()
                            logger.debug(f"Sent ping to OpenAI for {connection.esp32_id}")
                        except Exception as e:
                            logger.warning(f"Ping failed for {connection.esp32_id}: {e}")
                            break
                    continue
                    
                except websockets.exceptions.ConnectionClosed:
                    logger.info(f"OpenAI connection closed for {connection.esp32_id}")
                    break
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON from OpenAI for {connection.esp32_id}: {e}")
                    continue
                    
                except Exception as e:
                    logger.error(f"Error in session lifecycle for {connection.esp32_id}: {e}")
                    break
                    
        except Exception as e:
            logger.error(f"Error in session lifecycle setup for {connection.esp32_id}: {e}")
        finally:
            connection.close()
            if connection.esp32_id in self.connections:
                del self.connections[connection.esp32_id]
                logger.info(f"Cleaned up OpenAI connection for {connection.esp32_id}")
    
    async def _handle_server_event(self, connection: RealtimeConnection, data: Dict[str, Any]):
        """Handle server events following official documentation patterns"""
        event_type = data.get("type")
        esp32_id = connection.esp32_id
        
        try:
            # Audio events (most common)
            if event_type == "response.audio.delta":
                # Forward audio chunks to user (official pattern)
                await connection.callback(esp32_id, data)
                
            elif event_type == "response.audio.done":
                # Audio response completed
                logger.info(f"Audio response completed for {esp32_id}")
                await connection.callback(esp32_id, data)
                
            elif event_type == "response.audio_transcript.delta":
                # Forward transcript updates
                await connection.callback(esp32_id, data)
                
            elif event_type == "response.audio_transcript.done":
                # Transcript completed
                await connection.callback(esp32_id, data)
            
            # Text events
            elif event_type == "response.text.delta":
                # Forward text chunks
                await connection.callback(esp32_id, data)
                
            elif event_type == "response.text.done":
                # Text response completed
                await connection.callback(esp32_id, data)
            
            # Function calling events (official pattern)
            elif event_type == "response.function_call_arguments.delta":
                # Function call arguments being built
                await connection.callback(esp32_id, data)
                
            elif event_type == "response.function_call_arguments.done":
                # Function call arguments complete - this is where we handle function calls
                logger.info(f"Function call arguments complete for {esp32_id}")
                await connection.callback(esp32_id, data)
            
            # Response lifecycle events
            elif event_type == "response.created":
                logger.info(f"Response created for {esp32_id}")
                connection.is_generating_response = True
                await connection.callback(esp32_id, data)
                
            elif event_type == "response.done":
                logger.info(f"Response completed for {esp32_id}")
                connection.is_generating_response = False
                await connection.callback(esp32_id, data)
            
            # Conversation events
            elif event_type == "conversation.item.created":
                logger.debug(f"Conversation item created for {esp32_id}")
                await connection.callback(esp32_id, data)
                
            elif event_type == "conversation.item.truncated":
                logger.debug(f"Conversation item truncated for {esp32_id}")
                await connection.callback(esp32_id, data)
            
            # Input audio buffer events (VAD)
            elif event_type == "input_audio_buffer.speech_started":
                logger.info(f"User started speaking: {esp32_id}")
                await connection.callback(esp32_id, data)
                
            elif event_type == "input_audio_buffer.speech_stopped":
                logger.info(f"User stopped speaking: {esp32_id}")
                await connection.callback(esp32_id, data)
                
            elif event_type == "input_audio_buffer.committed":
                logger.debug(f"Audio buffer committed for {esp32_id}")
                await connection.callback(esp32_id, data)
            
            # Rate limiting events
            elif event_type == "rate_limits.updated":
                logger.debug(f"Rate limits updated for {esp32_id}")
                # Usually don't need to forward these
            
            # Error handling
            elif event_type == "error":
                logger.error(f"OpenAI API error for {esp32_id}: {data}")
                await connection.callback(esp32_id, data)
            
            # Unknown events
            else:
                logger.warning(f"Unknown server event for {esp32_id}: {event_type}")
                await connection.callback(esp32_id, data)
            
        except Exception as e:
            logger.error(f"Error handling server event {event_type} for {esp32_id}: {e}")
    
    def get_connection(self, esp32_id: str) -> Optional[RealtimeConnection]:
        """Get active connection for ESP32 device"""
        connection = self.connections.get(esp32_id)
        if connection and connection.is_active and connection.session_ready:
            return connection
        return None
    
    def close_connection(self, esp32_id: str):
        """Close connection for ESP32 device"""
        if esp32_id in self.connections:
            connection = self.connections[esp32_id]
            connection.close()
            
            try:
                if connection._listener_task and not connection._listener_task.done():
                    connection._listener_task.cancel()
            except Exception as e:
                logger.warning(f"Error canceling listener task for {esp32_id}: {e}")
            
            try:
                asyncio.create_task(connection.websocket.close())
            except Exception as e:
                logger.warning(f"Error closing websocket for {esp32_id}: {e}")
            
            del self.connections[esp32_id]
            logger.info(f"Closed realtime connection for {esp32_id}")
    
    def update_session(self, esp32_id: str, instructions: str, voice: str = "alloy", tools: list = None):
        """Update session configuration following official documentation"""
        connection = self.get_connection(esp32_id)
        if not connection:
            logger.error(f"No active connection found for {esp32_id}")
            return False
        
        try:
            # Official session.update event format
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
                    }
                }
            }
            
            # Add tools if provided (official function calling format)
            if tools:
                session_update["session"]["tools"] = tools
                session_update["session"]["tool_choice"] = "auto"
            
            success = self._send_to_connection_sync(connection, session_update)
            if success:
                logger.info(f"Session updated for {esp32_id} with voice: {voice}")
            return success
            
        except Exception as e:
            logger.error(f"Error updating session for {esp32_id}: {e}")
            return False
    
    def send_event(self, esp32_id: str, event: dict):
        """Send event to OpenAI following official event format"""
        connection = self.get_connection(esp32_id)
        if connection:
            success = self._send_to_connection_sync(connection, event)
            if not success:
                logger.warning(f"Failed to send event {event.get('type')} to {esp32_id}")
        else:
            logger.warning(f"No active connection found for {esp32_id} when sending event {event.get('type')}")
    
    def send_audio(self, esp32_id: str, audio_data: bytes):
        """Send audio data using official input_audio_buffer.append format"""
        try:
            # Encode audio to base64 (official format)
            base64_audio = base64.b64encode(audio_data).decode('utf-8')
            
            # Official input_audio_buffer.append event
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
    
    def commit_audio(self, esp32_id: str):
        """Commit audio buffer (official pattern for when VAD is disabled)"""
        self.send_event(esp32_id, {
            "type": "input_audio_buffer.commit"
        })
    
    def clear_audio_buffer(self, esp32_id: str):
        """Clear audio buffer (official pattern)"""
        self.send_event(esp32_id, {
            "type": "input_audio_buffer.clear"
        })
    
    def create_response(self, esp32_id: str, modalities: list = None):
        """Create response using official response.create format"""
        try:
            if modalities is None:
                modalities = ["text", "audio"]
            
            # Official response.create event format
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
        """Start conversation using official pattern"""
        try:
            # Official conversation.item.create format for starting conversation
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
    
    def send_function_call_output(self, esp32_id: str, call_id: str, output: str):
        """Send function call output using official format"""
        try:
            # Official function_call_output format
            function_output_item = {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": output
                }
            }
            
            self.send_event(esp32_id, function_output_item)
            logger.info(f"Function call output sent for {esp32_id}, call_id: {call_id}")
            
        except Exception as e:
            logger.error(f"Error sending function call output for {esp32_id}: {e}")
    
    def end_conversation(self, esp32_id: str):
        """End conversation and cleanup"""
        logger.info(f"Ending conversation for {esp32_id}")
        self.close_connection(esp32_id)
    
    def _send_to_connection_sync(self, connection: RealtimeConnection, data: dict) -> bool:
        """Send data to connection synchronously"""
        try:
            if connection.is_active and connection.session_ready:
                # Create an async task to send the data
                asyncio.create_task(self._send_to_connection_async(connection, data))
                connection.update_activity()
                return True
            else:
                logger.warning(f"Attempted to send to inactive/unready connection: {connection.esp32_id}")
                return False
        except Exception as e:
            logger.error(f"Error sending to connection {connection.esp32_id}: {e}")
            connection.close()
            return False
    
    async def _send_to_connection_async(self, connection: RealtimeConnection, data: dict):
        """Send data to connection asynchronously"""
        try:
            await connection.websocket.send(json.dumps(data))
        except Exception as e:
            logger.error(f"Error in async send to {connection.esp32_id}: {e}")
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
            "active_connections": len([c for c in self.connections.values() if c.is_active and c.session_ready]),
            "connections": {}
        }
        
        for esp32_id, connection in self.connections.items():
            stats["connections"][esp32_id] = {
                "session_id": connection.session_id,
                "is_active": connection.is_active,
                "session_ready": connection.session_ready,
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