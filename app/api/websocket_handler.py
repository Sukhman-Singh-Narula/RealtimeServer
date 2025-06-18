# app/api/websocket_handler.py - UPDATED TO USE CONVERSATION FLOW MANAGER

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Dict, Optional
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

class WebSocketHandler:
    def __init__(self, managers: Dict[str, any]):
        # Initialize with available managers
        self.db_manager = managers['database']
        self.cache_manager = managers['cache']
        self.content_manager = managers['content']
        self.realtime_manager = managers['realtime']
        
        # Initialize connection tracking
        self.active_connections: Dict[str, WebSocket] = {}
        self.server_state = None
        
        # Initialize conversation flow manager
        from app.managers.conversation_flow_manager import ConversationFlowManager
        self.conversation_flow = ConversationFlowManager(
            database_manager=self.db_manager,
            content_manager=self.content_manager,
            cache_manager=self.cache_manager,
            realtime_manager=self.realtime_manager
        )
        
        logger.info("WebSocketHandler initialized with ConversationFlowManager")

    def set_server_state(self, server_state):
        """Set reference to server state for statistics tracking"""
        self.server_state = server_state
        logger.info("Server state set for WebSocketHandler")

    async def connect(self, esp32_id: str, websocket: WebSocket):
        """Connect a new ESP32 device"""
        await websocket.accept()
        self.active_connections[esp32_id] = websocket
        logger.info(f"ESP32 {esp32_id} connected")

    async def disconnect(self, esp32_id: str):
        """Disconnect an ESP32 device"""
        if esp32_id in self.active_connections:
            del self.active_connections[esp32_id]
            logger.info(f"ESP32 {esp32_id} disconnected")

    async def send_message(self, esp32_id: str, data: dict) -> bool:
        """Send message to ESP32 device"""
        if esp32_id not in self.active_connections:
            logger.warning(f"No active connection for {esp32_id}")
            return False
            
        try:
            websocket = self.active_connections[esp32_id]
            message = json.dumps(data)
            await websocket.send_text(message)
            logger.debug(f"Sent to {esp32_id}: {data.get('type', 'unknown')} ({len(message)} chars)")
            return True
        except Exception as e:
            logger.error(f"Error sending to {esp32_id}: {e}")
            await self._cleanup_connection(esp32_id)
            return False

    def send_audio(self, esp32_id: str, audio_data: bytes):
        """Send audio data using official input_audio_buffer.append format - UPDATED FOR WEBM"""
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
                
            # Log the audio data info
            logger.debug(f"Sent {len(audio_data)} bytes of audio data to OpenAI for {esp32_id}")
                
        except Exception as e:
            logger.error(f"Error sending audio for {esp32_id}: {e}")

    def commit_audio(self, esp32_id: str):
        """Commit audio buffer and trigger response generation"""
        try:
            # Send commit event to trigger OpenAI processing
            event = {
                "type": "input_audio_buffer.commit"
            }
            
            self.send_event(esp32_id, event)
            logger.debug(f"Committed audio buffer for {esp32_id}")
            
            # Optionally trigger response creation
            self.create_response(esp32_id)
            
        except Exception as e:
            logger.error(f"Error committing audio for {esp32_id}: {e}")

    def create_response(self, esp32_id: str):
        """Create a response from OpenAI"""
        try:
            event = {
                "type": "response.create",
                "response": {
                    "modalities": ["text", "audio"],
                    "instructions": "Please respond to the user's audio input."
                }
            }
            
            self.send_event(esp32_id, event)
            logger.debug(f"Requested response creation for {esp32_id}")
            
        except Exception as e:
            logger.error(f"Error creating response for {esp32_id}: {e}")

    async def handle_pcm16_audio(self, esp32_id: str, pcm16_data: bytes, sample_rate: int = 24000):
        """Handle PCM16 audio data (converted from WebM)"""
        try:
            # Validate the PCM16 data
            if len(pcm16_data) % 2 != 0:
                logger.warning(f"PCM16 data length is odd: {len(pcm16_data)} bytes")
                return
            
            # Log audio statistics
            num_samples = len(pcm16_data) // 2
            duration = num_samples / sample_rate
            logger.debug(f"PCM16 audio: {num_samples} samples, {duration:.3f}s at {sample_rate}Hz")
            
            # Send to OpenAI using the standard audio sending method
            self.send_audio(esp32_id, pcm16_data)
            
        except Exception as e:
            logger.error(f"Error handling PCM16 audio for {esp32_id}: {e}")

    async def handle_webm_audio(self, esp32_id: str, webm_data: bytes):
        """Handle WebM audio from browser microphone - UPDATED TO CONVERT TO PCM16"""
        try:
            logger.debug(f"Converting WebM to PCM16 for {esp32_id}: {len(webm_data)} bytes")
            
            # Use audio processor to convert WebM to PCM16
            from app.utils.audio import AudioProcessor
            audio_processor = AudioProcessor()
            
            # Convert WebM to PCM16
            pcm16_data = await audio_processor.webm_to_pcm16(webm_data, 24000)
            
            if pcm16_data and len(pcm16_data) > 0:
                logger.debug(f"WebM conversion successful: {len(pcm16_data)} bytes PCM16")
                await self.handle_pcm16_audio(esp32_id, pcm16_data, 24000)
            else:
                logger.warning(f"WebM conversion failed for {esp32_id}, skipping audio chunk")
            
        except Exception as e:
            logger.error(f"Error handling WebM audio for {esp32_id}: {e}")

    async def process_user_audio(self, esp32_id: str, audio_data: bytes, audio_format: str = "pcm16"):
        """Process user audio based on format - UPDATED"""
        try:
            if audio_format == "pcm16":
                await self.handle_pcm16_audio(esp32_id, audio_data, 24000)
            elif audio_format == "webm":
                await self.handle_webm_audio(esp32_id, audio_data)
            else:
                # Fallback to original PCM handling
                await self.handle_pcm_audio(esp32_id, audio_data)
                
        except Exception as e:
            logger.error(f"Error processing user audio for {esp32_id}: {e}")

    def setup_audio_processing(self, esp32_id: str):
        """Setup audio processing configuration for optimal real-time performance - UPDATED"""
        try:
            # Configure session for optimal PCM16 audio processing
            session_config = {
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "instructions": self.get_system_prompt(esp32_id),
                    "voice": "alloy",  # Can be: alloy, echo, fable, onyx, nova, shimmer
                    "input_audio_format": "pcm16",  # We're sending PCM16
                    "output_audio_format": "pcm16", # We want PCM16 back
                    "input_audio_transcription": {
                        "model": "whisper-1"
                    },
                    "turn_detection": {
                        "type": "server_vad",  # Let OpenAI handle voice activity detection
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 200  # Reduced for more responsive detection
                    },
                    "tools": [],
                    "tool_choice": "auto",
                    "temperature": 0.8,
                    "max_response_output_tokens": 4096
                }
            }
            
            self.send_event(esp32_id, session_config)
            logger.info(f"Configured PCM16 audio processing for {esp32_id}")
            
        except Exception as e:
            logger.error(f"Error setting up audio processing for {esp32_id}: {e}")

    def start_conversation(self, esp32_id: str):
        """Start a new conversation session"""
        try:
            # Clear any existing audio buffer
            event = {
                "type": "input_audio_buffer.clear"
            }
            self.send_event(esp32_id, event)
            
            logger.info(f"Started new conversation for {esp32_id}")
            
        except Exception as e:
            logger.error(f"Error starting conversation for {esp32_id}: {e}")

    

    async def handle_connection(self, websocket: WebSocket, esp32_id: str):
        """Main WebSocket connection handler using ConversationFlowManager"""
        # Clean up device ID if malformed
        esp32_id = esp32_id.strip('{}')
        logger.info(f"Handling connection for device ID: {esp32_id}")
        
        await self.connect(esp32_id, websocket)
        
        try:
            # Start user conversation using the flow manager
            success = await self.conversation_flow.start_user_conversation(esp32_id, self)
            
            if not success:
                logger.error(f"Failed to start conversation for {esp32_id}")
                await self.send_message(esp32_id, {
                    "type": "error",
                    "message": "Failed to start conversation. Please try again."
                })
                return
            
            logger.info(f"Conversation setup complete for {esp32_id}")
            
            # Main message loop
            while True:
                try:
                    if hasattr(websocket, 'client_state') and websocket.client_state.name != 'CONNECTED':
                        logger.info(f"WebSocket for {esp32_id} is no longer connected")
                        break
                    
                    message = await asyncio.wait_for(websocket.receive(), timeout=300.0)
                    
                    if message.get("type") == "websocket.disconnect":
                        logger.info(f"ESP32 {esp32_id} disconnected (disconnect message)")
                        break
                    
                    if "text" in message:
                        try:
                            data = json.loads(message["text"])
                            await self.process_esp32_message(esp32_id, data)
                        except json.JSONDecodeError as e:
                            logger.error(f"Invalid JSON from {esp32_id}: {e}")
                            
                    elif "bytes" in message:
                        audio_data = message["bytes"]
                        await self.handle_binary_audio_from_esp32(esp32_id, audio_data)
                        
                    else:
                        logger.warning(f"Unknown message format from {esp32_id}: {message}")
                        
                except WebSocketDisconnect:
                    logger.info(f"ESP32 {esp32_id} disconnected (WebSocketDisconnect)")
                    break
                except asyncio.TimeoutError:
                    try:
                        await websocket.ping()
                        logger.debug(f"Sent ping to {esp32_id}")
                        continue
                    except:
                        logger.info(f"Connection lost for {esp32_id} (ping failed)")
                        break
                except Exception as e:
                    logger.error(f"Error processing message from {esp32_id}: {e}")
                    error_str = str(e).lower()
                    if any(phrase in error_str for phrase in [
                        "cannot call \"receive\"", 
                        "connection closed", 
                        "websocket disconnected",
                        "connection is closed"
                    ]):
                        logger.info(f"Breaking message loop for {esp32_id} due to connection error")
                        break
                    
        except WebSocketDisconnect:
            logger.info(f"ESP32 {esp32_id} disconnected")
        except Exception as e:
            logger.error(f"Error handling connection for {esp32_id}: {e}")
        finally:
            await self._cleanup_connection(esp32_id)
    
    async def process_esp32_message(self, esp32_id: str, message: Dict[str, any]):
        """Process incoming JSON messages from ESP32"""
        msg_type = message.get('type')
        logger.debug(f"Processing message type '{msg_type}' from {esp32_id}")
        
        if msg_type == 'audio':
            await self.handle_audio_from_esp32(esp32_id, message)
        elif msg_type == 'heartbeat':
            await self.handle_heartbeat(esp32_id)
        elif msg_type == 'text':
            await self.handle_text_from_esp32(esp32_id, message)
        elif msg_type == 'end_stream':
            await self.handle_audio_stream_end(esp32_id)
        elif msg_type == 'start_conversation':
            logger.info(f"Starting conversation for {esp32_id}")
            self.realtime_manager.start_conversation(esp32_id)
        elif msg_type == 'end_conversation':
            logger.info(f"Ending conversation for {esp32_id}")
            await self.conversation_flow.end_user_conversation(esp32_id)
        elif msg_type == 'disconnect':
            logger.info(f"Disconnect request received from {esp32_id}")
            await self.conversation_flow.end_user_conversation(esp32_id)
        else:
            logger.warning(f"Unknown message type from ESP32: {msg_type}")

    async def handle_audio_from_esp32(self, esp32_id: str, message: Dict[str, any]):
        """Handle incoming audio from ESP32 - UPDATED FOR PCM16 CONVERSION"""
        audio_data_base64 = message.get('audio', '') or message.get('audio_data', '')
        audio_format = message.get('format', 'unknown')
        sample_rate = message.get('sample_rate', 16000)
        
        if audio_data_base64:
            try:
                logger.debug(f"Processing {audio_format} audio from {esp32_id}: {len(audio_data_base64)} chars, {sample_rate}Hz")
                
                if audio_format == 'pcm16':
                    # Handle PCM16 audio (converted from WebM on client side)
                    audio_data = base64.b64decode(audio_data_base64)
                    await self._process_pcm16_audio_data(esp32_id, audio_data, sample_rate)
                elif audio_format == 'webm':
                    # Handle WebM audio (fallback if client-side conversion fails)
                    await self._process_webm_audio_data(esp32_id, audio_data_base64)
                else:
                    # Handle raw PCM audio (original format from ESP32)
                    audio_data = bytes.fromhex(audio_data_base64) if audio_format == 'hex' else base64.b64decode(audio_data_base64)
                    await self._process_audio_data(esp32_id, audio_data)
                    
            except ValueError as e:
                logger.error(f"Invalid audio data from {esp32_id}: {e}")
            except Exception as e:
                logger.error(f"Error processing audio from {esp32_id}: {e}")

    async def _process_pcm16_audio_data(self, esp32_id: str, pcm16_data: bytes, sample_rate: int):
        """Process PCM16 audio data (converted from WebM)"""
        try:
            logger.debug(f"Processing PCM16 audio: {len(pcm16_data)} bytes at {sample_rate}Hz")
            
            # Validate PCM16 data
            from app.utils.audio import AudioProcessor
            audio_processor = AudioProcessor()
            
            if not audio_processor.validate_audio_data(pcm16_data, "pcm16"):
                logger.warning(f"Invalid PCM16 data from {esp32_id}")
                return
            
            # Convert sample rate if needed (OpenAI prefers 24kHz)
            if sample_rate != 24000:
                pcm16_data = audio_processor.convert_sample_rate(pcm16_data, sample_rate, 24000)
                logger.debug(f"Converted sample rate from {sample_rate}Hz to 24000Hz")
            
            # Apply noise reduction and normalization
            pcm16_data = audio_processor.normalize_audio(pcm16_data)
            pcm16_data = audio_processor.apply_noise_reduction(pcm16_data)
            
            # Calculate and log audio duration
            duration = audio_processor.get_audio_duration(pcm16_data, 24000, "pcm16")
            logger.debug(f"Audio duration: {duration:.3f}s")
            
            # Send to conversation flow manager
            await self.conversation_flow.handle_user_audio(esp32_id, pcm16_data, "pcm16")
                
        except Exception as e:
            logger.error(f"Error processing PCM16 audio for {esp32_id}: {e}")

    async def _process_webm_audio_data(self, esp32_id: str, webm_base64: str):
        """Process WebM audio from browser microphone"""
        try:
            # Decode base64 WebM data
            webm_data = base64.b64decode(webm_base64)
            
            logger.debug(f"Received WebM audio: {len(webm_data)} bytes")
            
            # For now, we'll send the WebM data directly to OpenAI
            # OpenAI Realtime API can handle various audio formats
            # In production, you might want to convert WebM to PCM16 for better compatibility
            
            # Send to conversation flow manager (which forwards to OpenAI)
            await self.conversation_flow.handle_user_audio(esp32_id, webm_data)
                
        except Exception as e:
            logger.error(f"Error processing WebM audio for {esp32_id}: {e}")

    async def _process_audio_data(self, esp32_id: str, audio_data: bytes):
        """Process raw audio data (existing method - kept for compatibility)"""
        try:
            # Convert from 16kHz to 24kHz for OpenAI if needed
            from app.utils.audio import AudioProcessor
            audio_processor = AudioProcessor()
            
            # Assume input is 16kHz PCM16, convert to 24kHz for OpenAI
            audio_24khz = audio_processor.convert_sample_rate(audio_data, 16000, 24000)
            
            # Send to conversation flow manager
            await self.conversation_flow.handle_user_audio(esp32_id, audio_24khz)
                
        except Exception as e:
            logger.error(f"Error in _process_audio_data for {esp32_id}: {e}")


    # Update the send_response_to_device method to handle the new audio event types
    async def send_response_to_device(self, esp32_id: str, response_data: dict):
        """Called by other managers to send responses to device - UPDATED"""
        try:
            response_data["timestamp"] = datetime.now().isoformat()
            
            # Map internal event types to dashboard-compatible types
            response_type = response_data.get("type")
            
            if response_type == "audio_chunk":
                # Keep as audio_chunk - dashboard expects this
                pass
            elif response_type == "response.audio.delta":
                # Convert OpenAI event to dashboard event
                response_data["type"] = "audio_data"
                # Keep the audio data in the 'delta' field but also add to 'audio' field
                if "delta" in response_data and "audio" not in response_data:
                    response_data["audio"] = response_data["delta"]
            elif response_type == "input_audio_buffer.speech_started":
                response_data["type"] = "speech_started"
            elif response_type == "input_audio_buffer.speech_stopped":
                response_data["type"] = "speech_stopped"
            
            success = await self.send_message(esp32_id, response_data)
            
            if success and self.server_state:
                self.server_state.total_messages += 1
                if esp32_id in self.server_state.conversation_stats:
                    self.server_state.conversation_stats[esp32_id]["messages"] += 1
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending response to {esp32_id}: {e}")
            return False

    async def handle_binary_audio_from_esp32(self, esp32_id: str, audio_data: bytes):
        """Handle incoming binary audio data from ESP32"""
        try:
            logger.debug(f"Received binary audio from {esp32_id}: {len(audio_data)} bytes")
            await self._process_audio_data(esp32_id, audio_data)
        except Exception as e:
            logger.error(f"Error processing binary audio from {esp32_id}: {e}")

    

    async def handle_audio_stream_end(self, esp32_id: str):
        """Handle end of audio stream"""
        # The conversation flow manager will handle the response timing
        pass

    async def handle_text_from_esp32(self, esp32_id: str, message: Dict[str, any]):
        """Handle text messages from ESP32"""
        text = message.get('text', '')
        if text:
            logger.info(f"Text message from {esp32_id}: {text}")
            
            # Send text as conversation item to OpenAI
            self.realtime_manager.send_event(esp32_id, {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}]
                }
            })
            
            # Create response
            self.realtime_manager.create_response(esp32_id, ["text", "audio"])

    async def handle_heartbeat(self, esp32_id: str):
        """Handle heartbeat to keep connection alive"""
        # Get session stats from conversation flow manager
        context = self.conversation_flow.get_user_context(esp32_id)
        session_stats = context.get_session_stats() if context else {}
        
        await self.send_message(esp32_id, {
            "type": "heartbeat_ack",
            "session_stats": session_stats
        })

    async def _cleanup_connection(self, esp32_id: str):
        """Cleanup when ESP32 disconnects"""
        logger.info(f"Cleaning up connection for {esp32_id}")
        
        try:
            # End conversation through flow manager
            await self.conversation_flow.end_user_conversation(esp32_id)
        except Exception as e:
            logger.error(f"Error ending conversation for {esp32_id}: {e}")
        
        try:
            # Remove from WebSocket manager
            await self.disconnect(esp32_id)
        except Exception as e:
            logger.error(f"Error disconnecting from WebSocket manager for {esp32_id}: {e}")
        
        try:
            # Clear cache
            await self.cache_manager.delete_connection(esp32_id)
        except Exception as e:
            logger.error(f"Error clearing cache for {esp32_id}: {e}")
            
        logger.info(f"Cleanup completed for {esp32_id}")

    # Additional utility methods

    def get_active_device_count(self) -> int:
        """Get count of active device connections"""
        return len(self.active_connections)

    def get_device_list(self) -> list:
        """Get list of active device IDs"""
        return list(self.active_connections.keys())

    def is_device_connected(self, esp32_id: str) -> bool:
        """Check if a specific device is connected"""
        return esp32_id in self.active_connections

    def get_connection_stats(self) -> dict:
        """Get detailed connection statistics"""
        active_conversations = self.conversation_flow.get_active_conversations()
        
        stats = {
            "total_active_connections": len(self.active_connections),
            "total_active_conversations": len(active_conversations),
            "devices": {}
        }
        
        for esp32_id in self.active_connections:
            conversation_info = active_conversations.get(esp32_id, {})
            stats["devices"][esp32_id] = {
                "connected": True,
                "conversation_state": conversation_info.get("state", "unknown"),
                "session_duration": conversation_info.get("session_duration", 0),
                "words_learned": conversation_info.get("words_learned", 0),
                "current_episode": conversation_info.get("current_episode"),
                "last_activity": conversation_info.get("last_activity")
            }
        
        return stats