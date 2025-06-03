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
    """Manages a single OpenAI Realtime API WebSocket connection with enhanced keepalive"""
    
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
        self.conversation_active = False
        self.last_audio_time = 0
        self.last_activity_time = time.time()  # Track any activity
        self.silence_threshold = 60.0  # 1 minute of silence before timeout
        self.response_timer = None
        self.keepalive_timer = None  # For sending periodic pings
        self.should_close = False  # Flag for intentional closure
        
    def connect(self):
        """Connect to OpenAI Realtime API with enhanced keepalive"""
        def on_open(ws):
            logger.info(f"Connected to OpenAI Realtime API for {self.esp32_id}")
            self.is_connected = True
            self.last_activity_time = time.time()
            self._start_keepalive()
            
        def on_message(ws, message):
            try:
                # Update activity time on any message
                self.last_activity_time = time.time()
                
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
                    logger.info(f"Creating response for {self.esp32_id}")
                    
                elif event_type == "response.done":
                    self.is_generating_response = False
                    response_status = data.get('response', {}).get('status', 'unknown')
                    logger.info(f"Response completed for {self.esp32_id} with status: {response_status}")
                    
                elif event_type == "input_audio_buffer.speech_started":
                    logger.info(f"Speech started detected for {self.esp32_id}")
                    self.last_audio_time = time.time()
                    # Cancel any pending response timer since user is speaking
                    if self.response_timer:
                        self.response_timer.cancel()
                        self.response_timer = None
                    
                elif event_type == "input_audio_buffer.speech_stopped":
                    logger.info(f"Speech stopped detected for {self.esp32_id}")
                    # User stopped speaking - trigger response after a short delay
                    self._schedule_response_if_needed()
                    
                elif event_type in ["response.audio.delta", "response.audio.done"]:
                    logger.debug(f"Audio event: {event_type}")
                elif event_type == "error":
                    logger.error(f"Realtime API error: {data}")
                
                # Pass message to callback
                asyncio.run(self.on_message_callback(self.esp32_id, data))
            except Exception as e:
                logger.error(f"Error processing message for {self.esp32_id}: {e}")
                logger.error(f"Message was: {message[:200]}...")
                
        def on_error(ws, error):
            # Only log as error if it's not an intentional close
            if not self.should_close:
                logger.error(f"WebSocket error for {self.esp32_id}: {error}")
            else:
                logger.info(f"WebSocket error during intentional close for {self.esp32_id}: {error}")
            
        def on_close(ws, close_status_code, close_msg):
            if not self.should_close:
                logger.warning(f"WebSocket unexpectedly closed for {self.esp32_id}: code={close_status_code}, msg={close_msg}")
            else:
                logger.info(f"WebSocket intentionally closed for {self.esp32_id}: code={close_status_code}")
            
            self.is_connected = False
            self.conversation_active = False
            self._stop_keepalive()
            
        # Enhanced WebSocket configuration for better stability
        self.ws = websocket.WebSocketApp(
            self.url,
            header=self.headers,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        
        # Run WebSocket with enhanced settings
        self.thread = threading.Thread(
            target=lambda: self.ws.run_forever(
                ping_interval=20,  # Send ping every 20 seconds
                ping_timeout=10,   # Wait 10 seconds for pong
                ping_payload=b"keepalive"  # Custom ping payload
            )
        )
        self.thread.daemon = True
        self.thread.start()
        
        # Wait for connection with longer timeout
        timeout = 15
        start = time.time()
        while not self.is_connected and (time.time() - start) < timeout:
            time.sleep(0.1)
            
        if not self.is_connected:
            raise Exception("Failed to connect to OpenAI Realtime API")
    
    def _start_keepalive(self):
        """Start keepalive mechanism"""
        def keepalive_loop():
            while self.is_connected and not self.should_close:
                try:
                    current_time = time.time()
                    time_since_activity = current_time - self.last_activity_time
                    
                    # Check if we should close due to inactivity (1 minute silence)
                    if time_since_activity > self.silence_threshold and not self.is_generating_response:
                        logger.info(f"Closing connection for {self.esp32_id} due to {self.silence_threshold}s of inactivity")
                        self.close()
                        break
                    
                    # Send periodic events to keep connection alive
                    if time_since_activity > 15:  # Send keepalive every 15 seconds of inactivity
                        # Send a session query to keep connection alive
                        self.send_event({
                            "type": "session.get"
                        })
                        logger.debug(f"Sent keepalive event for {self.esp32_id}")
                    
                    time.sleep(5)  # Check every 5 seconds
                    
                except Exception as e:
                    logger.error(f"Error in keepalive loop for {self.esp32_id}: {e}")
                    time.sleep(5)
        
        if self.keepalive_timer:
            self.keepalive_timer.cancel()
        
        self.keepalive_timer = threading.Timer(0, keepalive_loop)
        self.keepalive_timer.daemon = True
        self.keepalive_timer.start()
    
    def _stop_keepalive(self):
        """Stop keepalive mechanism"""
        if self.keepalive_timer:
            self.keepalive_timer.cancel()
            self.keepalive_timer = None
    
    def _schedule_response_if_needed(self):
        """Schedule a response after user stops speaking"""
        if self.is_generating_response:
            logger.debug(f"Already generating response for {self.esp32_id}, skipping")
            return
            
        if self.response_timer:
            self.response_timer.cancel()
        
        # Schedule response after a short delay to ensure speech has truly stopped
        self.response_timer = threading.Timer(0.5, self._trigger_response)
        self.response_timer.start()
        logger.debug(f"Scheduled response for {self.esp32_id} in 0.5s")
    
    def _trigger_response(self):
        """Trigger a response if we're not already generating one"""
        try:
            if not self.is_generating_response and self.conversation_active:
                logger.info(f"Triggering response for {self.esp32_id}")
                self.create_response()
            else:
                logger.debug(f"Skipping response trigger for {self.esp32_id} - already generating or conversation inactive")
        except Exception as e:
            logger.error(f"Error triggering response for {self.esp32_id}: {e}")
    
    def send_event(self, event: Dict[str, Any]):
        """Send event to OpenAI Realtime API"""
        if self.ws and self.is_connected:
            try:
                self.ws.send(json.dumps(event))
                self.last_activity_time = time.time()  # Update activity time
                logger.debug(f"Sent event to {self.esp32_id}: {event.get('type', 'unknown')}")
            except Exception as e:
                logger.error(f"Error sending event to {self.esp32_id}: {e}")
    
    def send_audio(self, audio_data: bytes):
        """Send audio to OpenAI with activity tracking"""
        if not self.is_connected:
            return
            
        # Mark conversation as active and update activity time
        self.conversation_active = True
        self.last_audio_time = time.time()
        self.last_activity_time = time.time()
        
        # Audio should be base64 encoded PCM16 24kHz mono
        event = {
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(audio_data).decode('utf-8')
        }
        self.send_event(event)
    
    def create_response(self, modalities: List[str] = None):
        """Trigger response generation"""
        if modalities is None:
            modalities = ["text", "audio"]
            
        if self.is_generating_response:
            logger.warning(f"Already generating response for {self.esp32_id}, skipping")
            return
            
        if not self.conversation_active:
            logger.warning(f"Conversation not active for {self.esp32_id}, skipping response")
            return
            
        event = {
            "type": "response.create",
            "response": {
                "modalities": modalities,
                "instructions": "Continue the conversation naturally. Respond to what the user just said and keep the conversation flowing."
            }
        }
        
        logger.info(f"Creating response for {self.esp32_id} with modalities: {modalities}")
        self.is_generating_response = True
        self.send_event(event)
    
    def start_conversation(self):
        """Explicitly start a conversation session"""
        self.conversation_active = True
        self.last_activity_time = time.time()
        logger.info(f"Conversation started for {self.esp32_id}")
    
    def end_conversation(self):
        """Explicitly end a conversation session"""
        self.conversation_active = False
        if self.response_timer:
            self.response_timer.cancel()
            self.response_timer = None
        logger.info(f"Conversation ended for {self.esp32_id}")
    
    def update_activity(self):
        """Update last activity time - call this for any user interaction"""
        self.last_activity_time = time.time()
    
    def close(self):
        """Close WebSocket connection gracefully"""
        self.should_close = True
        self.end_conversation()
        self._stop_keepalive()
        
        if self.ws:
            try:
                # Send a clean close frame
                self.ws.close()
            except Exception as e:
                logger.error(f"Error closing WebSocket for {self.esp32_id}: {e}")
            
        self.is_connected = False
        logger.info(f"Closed connection for {self.esp32_id}")

class RealtimeManager:
    """Enhanced Realtime Manager for continuous conversations"""
    
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
        try:
            if esp32_id in self.message_handlers:
                handler = self.message_handlers[esp32_id]
                asyncio.create_task(handler(message))
        except Exception as e:
            logger.error(f"Error in message handler for {esp32_id}: {e}")
    
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
        """Update session configuration with enhanced turn detection"""
        logger.info(f"Updating session for {esp32_id} with voice: {voice}")
        
        # Enhanced turn detection for better conversation flow
        enhanced_turn_detection = turn_detection or {
            "type": "server_vad",
            "threshold": 0.5,
            "prefix_padding_ms": 300,
            "silence_duration_ms": 800,  # Shorter silence duration for more responsive conversations
            "create_response": True  # Auto-create response when user stops talking
        }
        
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
                "temperature": 0.7,  # Slightly higher for more natural conversations
                "max_response_output_tokens": "inf",
                "turn_detection": enhanced_turn_detection
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
        """Send audio to OpenAI with conversation tracking"""
        connection = self.connections.get(esp32_id)
        if connection:
            connection.send_audio(audio_data)
    
    def commit_audio(self, esp32_id: str):
        """Commit audio buffer - not needed with streaming approach"""
        # With the new approach, we don't need to explicitly commit
        # The server VAD will handle this automatically
        pass
    
    def create_response(self, esp32_id: str, modalities: List[str] = None):
        """Trigger response generation"""
        connection = self.connections.get(esp32_id)
        if connection:
            connection.create_response(modalities)
    
    def start_conversation(self, esp32_id: str):
        """Start a conversation session"""
        connection = self.connections.get(esp32_id)
        if connection:
            connection.start_conversation()
    
    def end_conversation(self, esp32_id: str):
        """End a conversation session"""
        connection = self.connections.get(esp32_id)
        if connection:
            connection.end_conversation()
    
    def close_connection(self, esp32_id: str):
        """Close and remove connection"""
        logger.info(f"Closing connection for {esp32_id}")
        
        try:
            if esp32_id in self.connections:
                connection = self.connections[esp32_id]
                connection.close()
                del self.connections[esp32_id]
                logger.info(f"Closed OpenAI connection for {esp32_id}")
        except Exception as e:
            logger.error(f"Error closing OpenAI connection for {esp32_id}: {e}")
            
        try:
            if esp32_id in self.message_handlers:
                del self.message_handlers[esp32_id]
                logger.info(f"Removed message handler for {esp32_id}")
        except Exception as e:
            logger.error(f"Error removing message handler for {esp32_id}: {e}")