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

    async def send_audio(self, esp32_id: str, audio_data: bytes) -> bool:
        """Send audio data to ESP32 device"""
        try:
            import base64
            base64_audio = base64.b64encode(audio_data).decode('utf-8')
            return await self.send_message(esp32_id, {
                "type": "audio_chunk",
                "audio": base64_audio,
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Error sending audio to {esp32_id}: {e}")
            return False

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
        """Handle incoming audio from ESP32"""
        audio_data_hex = message.get('audio_data', '')
        if audio_data_hex:
            try:
                audio_data = bytes.fromhex(audio_data_hex)
                await self._process_audio_data(esp32_id, audio_data)
            except ValueError as e:
                logger.error(f"Invalid hex audio data from {esp32_id}: {e}")
            except Exception as e:
                logger.error(f"Error processing audio from {esp32_id}: {e}")

    async def handle_binary_audio_from_esp32(self, esp32_id: str, audio_data: bytes):
        """Handle incoming binary audio data from ESP32"""
        try:
            logger.debug(f"Received binary audio from {esp32_id}: {len(audio_data)} bytes")
            await self._process_audio_data(esp32_id, audio_data)
        except Exception as e:
            logger.error(f"Error processing binary audio from {esp32_id}: {e}")

    async def _process_audio_data(self, esp32_id: str, audio_data: bytes):
        """Process audio data and send to conversation flow manager"""
        try:
            # Convert from 16kHz to 24kHz for OpenAI
            from app.utils.audio import AudioProcessor
            audio_processor = AudioProcessor()
            audio_24khz = audio_processor.convert_sample_rate(audio_data, 16000, 24000)
            
            # Send to conversation flow manager
            await self.conversation_flow.handle_user_audio(esp32_id, audio_24khz)
                
        except Exception as e:
            logger.error(f"Error in _process_audio_data for {esp32_id}: {e}")

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
    async def send_response_to_device(self, esp32_id: str, response_data: dict):
        """Called by other managers to send responses to device"""
        try:
            response_data["timestamp"] = datetime.now().isoformat()
            success = await self.send_message(esp32_id, response_data)
            
            if success and self.server_state:
                self.server_state.total_messages += 1
                if esp32_id in self.server_state.conversation_stats:
                    self.server_state.conversation_stats[esp32_id]["messages"] += 1
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending response to {esp32_id}: {e}")
            return False

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