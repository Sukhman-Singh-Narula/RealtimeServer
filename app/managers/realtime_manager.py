import asyncio
import json
import websocket
import threading
from typing import Dict, Any, Optional, Callable, List
import logging
from app.config import settings
import base64
import time

logger = logging.getLogger(__name__)

class RealtimeConnection:
    """Manages a single OpenAI Realtime API WebSocket connection"""
    
    def __init__(self, esp32_id: str, on_message_callback: Callable):
        self.esp32_id = esp32_id
        self.ws = None
        self.url = f"wss://api.openai.com/v1/realtime?model={settings.openai_realtime_model}"
        self.headers = [
            f"Authorization: Bearer {settings.openai_api_key}",
            "OpenAI-Beta: realtime=v1"
        ]
        self.on_message_callback = on_message_callback
        self.is_connected = False
        self.session_id = None
        self.thread = None
        self.is_generating_response = False
        
    def connect(self):
        """Connect to OpenAI Realtime API"""
        def on_open(ws):
            logger.info(f"Connected to OpenAI Realtime API for {self.esp32_id}")
            self.is_connected = True
            
        def on_message(ws, message):
            try:
                data = json.loads(message)
                event_type = data.get('type', 'unknown')
                logger.debug(f"Realtime API event for {self.esp32_id}: {event_type}")
                
                # Extract session ID from session.created event
                if event_type == "session.created":
                    self.session_id = data.get("session", {}).get("id")
                    logger.info(f"Session ID for {self.esp32_id}: {self.session_id}")
                
                # Track response generation state
                elif event_type == "response.created":
                    self.is_generating_response = True
                    logger.info(f"Creating response for {self.esp32_id} with modalities: {data.get('response', {}).get('modalities', [])}")
                    
                elif event_type == "response.done":
                    self.is_generating_response = False
                    logger.info(f"Response completed for {self.esp32_id} with status: {data.get('response', {}).get('status')}")
                    
                # Log important events
                elif event_type in ["response.audio.delta", "response.audio.done"]:
                    logger.debug(f"Audio event: {event_type}")
                elif event_type == "error":
                    logger.error(f"Realtime API error: {data}")
                
                # Pass message to callback
                asyncio.run(self.on_message_callback(self.esp32_id, data))
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                logger.error(f"Message was: {message[:200]}...")  # Log first 200 chars
                
        def on_error(ws, error):
            logger.error(f"WebSocket error for {self.esp32_id}: {error}")
            
        def on_close(ws, close_status_code, close_msg):
            logger.info(f"WebSocket closed for {self.esp32_id}: code={close_status_code}, msg={close_msg}")
            self.is_connected = False
            
        self.ws = websocket.WebSocketApp(
            self.url,
            header=self.headers,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        
        # Run WebSocket in a separate thread
        self.thread = threading.Thread(target=self.ws.run_forever)
        self.thread.daemon = True
        self.thread.start()
        
        # Wait for connection
        timeout = 10
        start = time.time()
        while not self.is_connected and (time.time() - start) < timeout:
            time.sleep(0.1)
            
        if not self.is_connected:
            raise Exception("Failed to connect to OpenAI Realtime API")
    
    def send_event(self, event: Dict[str, Any]):
        """Send event to OpenAI Realtime API"""
        if self.ws and self.is_connected:
            try:
                self.ws.send(json.dumps(event))
                logger.debug(f"Sent event to {self.esp32_id}: {event.get('type', 'unknown')}")
            except Exception as e:
                logger.error(f"Error sending event: {e}")
    
    def close(self):
        """Close WebSocket connection"""
        if self.ws:
            self.ws.close()
            self.is_connected = False

class RealtimeManager:
    """Manages OpenAI Realtime API connections for all ESP32 devices"""
    
    def __init__(self):
        self.connections: Dict[str, RealtimeConnection] = {}
        self.message_handlers: Dict[str, Callable] = {}
        
    async def create_connection(self, esp32_id: str, message_handler: Callable) -> RealtimeConnection:
        """Create a new Realtime API connection for an ESP32"""
        if esp32_id in self.connections:
            self.connections[esp32_id].close()
            
        self.message_handlers[esp32_id] = message_handler
        connection = RealtimeConnection(esp32_id, self._handle_message)
        connection.connect()
        self.connections[esp32_id] = connection
        
        return connection
    
    async def _handle_message(self, esp32_id: str, message: Dict[str, Any]):
        """Route messages to appropriate handlers"""
        if esp32_id in self.message_handlers:
            await self.message_handlers[esp32_id](message)
    
    def get_connection(self, esp32_id: str) -> Optional[RealtimeConnection]:
        """Get existing connection"""
        return self.connections.get(esp32_id)
    
    def send_event(self, esp32_id: str, event: Dict[str, Any]):
        """Send event to specific connection"""
        connection = self.connections.get(esp32_id)
        if connection:
            connection.send_event(event)
    
    def update_session(self, esp32_id: str, instructions: str, voice: str = "alloy", 
                      tools: list = None, turn_detection: dict = None):
        """Update session configuration"""
        logger.info(f"Updating session for {esp32_id} with voice: {voice}")
        logger.info(f"Setting instructions for {esp32_id}: {instructions[:100]}...")
        
        event = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": instructions,
                "voice": voice,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {"model": "whisper-1"},
                "tool_choice": "auto",
                "temperature": 0.7,
                "max_response_output_tokens": "inf",
                "turn_detection": turn_detection or {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500,
                    "create_response": False  # Don't auto-create responses
                }
            }
        }
        
        # Add tools if provided
        if tools:
            event["session"]["tools"] = tools
            logger.info(f"Added {len(tools)} tools for {esp32_id}")
        else:
            event["session"]["tools"] = []
            
        self.send_event(esp32_id, event)
    
    def send_audio(self, esp32_id: str, audio_data: bytes):
        """Send audio to OpenAI"""
        # Audio should be base64 encoded PCM16 24kHz mono
        event = {
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(audio_data).decode('utf-8')
        }
        self.send_event(esp32_id, event)
    
    def commit_audio(self, esp32_id: str):
        """Commit audio buffer and create response"""
        self.send_event(esp32_id, {"type": "input_audio_buffer.commit"})
    
    def create_response(self, esp32_id: str, modalities: List[str] = None):
        """Trigger response generation with specified modalities"""
        if modalities is None:
            modalities = ["text", "audio"]
            
        connection = self.connections.get(esp32_id)
        if connection and connection.is_generating_response:
            logger.warning(f"Already generating response for {esp32_id}, skipping")
            return
            
        event = {
            "type": "response.create",
            "response": {
                "modalities": modalities,
                "instructions": "Please respond with both text and voice audio."
            }
        }
        
        logger.info(f"Creating response for {esp32_id} with modalities: {modalities}")
        self.send_event(esp32_id, event)
    
    def close_connection(self, esp32_id: str):
        """Close and remove connection"""
        logger.info(f"Closing connection for {esp32_id}")
        if esp32_id in self.connections:
            self.connections[esp32_id].close()
            del self.connections[esp32_id]
        if esp32_id in self.message_handlers:
            del self.message_handlers[esp32_id]