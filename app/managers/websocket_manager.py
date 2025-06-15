# File: app/api/websocket_handler.py - ENHANCED VERSION WITH SERVER STATE INTEGRATION

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
        self.realtime_manager = managers['realtime']
        self.content_manager = managers['content']
        self.db_manager = managers['database']  # Add this
        self.cache_manager = managers['cache']  # Add this
        self.ws_manager = managers.get('websocket', self)  # Add this
        self.active_connections: Dict[str, WebSocket] = {}
        self.server_state = None

    def set_server_state(self, server_state):
        """Set reference to server state for statistics tracking"""
        self.server_state = server_state

    async def handle_connection(self, websocket: WebSocket, device_id: str):
        """Handle ESP32/device WebSocket connection with comprehensive error handling"""
        connection_start_time = time.time()
        
        try:
            await websocket.accept()
            self.active_connections[device_id] = websocket
            
            # Update server state
            if self.server_state:
                self.server_state.active_devices[device_id] = {
                    "status": "connected",
                    "connected_at": datetime.now(),
                    "conversation_active": False,
                    "websocket": websocket,
                    "message_count": 0,
                    "last_activity": datetime.now()
                }
            
            logger.info(f"  ESP32 connection established for {device_id}")

            # Send immediate connection confirmation
            await self._send_to_device(device_id, {
                "type": "connected",
                "message": "connected",
                "device_id": device_id,
                "timestamp": datetime.now().isoformat()
            })

            # Start the conversation workflow
            await self._start_conversation_workflow(device_id)

            # Listen for messages from device
            await self._message_listener_loop(device_id, websocket)

        except WebSocketDisconnect:
            logger.info(f"🔌 ESP32 {device_id} disconnected normally")
        except Exception as e:
            logger.error(f"  Connection error for {device_id}: {e}")
        finally:
            connection_duration = time.time() - connection_start_time
            logger.info(f"📊 Connection {device_id} lasted {connection_duration:.2f} seconds")
            await self._cleanup_connection(device_id)

    async def _message_listener_loop(self, device_id: str, websocket: WebSocket):
        """Main message listening loop with timeout and error handling"""
        while True:
            try:
                # Set a timeout for receiving messages
                message = await asyncio.wait_for(
                    websocket.receive_text(), 
                    timeout=60.0  # 60 second timeout
                )
                
                # Update activity timestamp
                if self.server_state and device_id in self.server_state.active_devices:
                    self.server_state.active_devices[device_id]["last_activity"] = datetime.now()
                    self.server_state.active_devices[device_id]["message_count"] += 1
                
                await self._handle_device_message(device_id, message)
                
            except asyncio.TimeoutError:
                logger.debug(f"💓 No message from {device_id} in 60s, sending keepalive")
                # Send keepalive
                keepalive_sent = await self._send_to_device(device_id, {
                    "type": "keepalive",
                    "timestamp": datetime.now().isoformat()
                })
                if not keepalive_sent:
                    logger.warning(f"⚠️ Failed to send keepalive to {device_id}, connection may be dead")
                    break
                    
            except WebSocketDisconnect:
                logger.info(f"🔌 ESP32 {device_id} disconnected during message loop")
                break
            except Exception as e:
                logger.error(f"  Error in message loop for {device_id}: {e}")
                # Try to send error notification to device
                await self._send_to_device(device_id, {
                    "type": "error",
                    "message": f"Message processing error: {str(e)}"
                })
                break

    async def _start_conversation_workflow(self, device_id: str):
        """Start the complete conversation workflow with enhanced error handling"""
        try:
            logger.info(f"🚀 Starting conversation workflow for {device_id}")

            # Update device status
            if self.server_state and device_id in self.server_state.active_devices:
                self.server_state.active_devices[device_id]["status"] = "initializing"

            # Step 1: Get next episode
            user = await self.db_manager.get_or_create_user(device_id)

            # Get user progress
            user_progress = {
                'current_language': user.current_language,
                'current_season': user.current_season,
                'current_episode': user.current_episode
            }

            # Then get the next episode
            episode_info = await self.content_manager.get_next_episode_for_user(user.id, user_progress)
            if not episode_info:
                logger.error(f"  No episode found for {device_id}")
                await self._send_to_device(device_id, {
                    "type": "error",
                    "message": "No episode available"
                })
                return False

            logger.info(f"📺 Episode selected for {device_id}: {episode_info['name']} (S{episode_info['season']}E{episode_info['episode']})")

            # Update device status with episode info
            if self.server_state and device_id in self.server_state.active_devices:
                self.server_state.active_devices[device_id]["current_episode"] = episode_info['name']
                self.server_state.active_devices[device_id]["status"] = "connecting_ai"

            # Step 2: Create OpenAI Realtime connection
            logger.info(f"🤖 Creating OpenAI Realtime connection for {device_id}")
            session_id = await self.realtime_manager.create_session(device_id)
            if not session_id:
                logger.error(f"  Failed to create realtime session for {device_id}")
                await self._send_to_device(device_id, {
                    "type": "error",
                    "message": "Failed to connect to AI service"
                })
                return False

            logger.info(f"  Realtime session created for {device_id}: {session_id}")

            # Step 3: Generate agent configuration
            logger.info(f"⚙️ Generating agent config for {device_id} with episode: {episode_info['name']}")
            
            # Import here to avoid circular imports
            from app.agents.agent_configs import get_choice_agent_config
            choice_config = get_choice_agent_config(episode_info['name'])
            
            logger.info(f"👤 Agent config created: {choice_config['friend']}, age {choice_config['age']}")

            # Step 4: Configure the session with agent
            logger.info(f"🔧 Configuring session for {device_id}")
            await self.realtime_manager.configure_session(
                device_id=device_id,
                config=choice_config,
                voice="alloy"  # TODO: Make this configurable per user/device
            )

            # Update device status
            if self.server_state and device_id in self.server_state.active_devices:
                self.server_state.active_devices[device_id]["status"] = "starting_conversation"

            # Step 5: Start conversation and trigger initial AI response
            logger.info(f"🎬 Starting conversation for {device_id}")
            await self.realtime_manager.start_conversation(device_id)

            # Update device status and server stats
            if self.server_state and device_id in self.server_state.active_devices:
                self.server_state.active_devices[device_id]["status"] = "conversation_active"
                self.server_state.active_devices[device_id]["conversation_active"] = True
                self.server_state.total_conversations += 1
                
                # Initialize conversation stats
                self.server_state.conversation_stats[device_id] = {
                    "start_time": datetime.now(),
                    "episode": episode_info['name'],
                    "messages": 0,
                    "device_id": device_id
                }

            logger.info(f"  Setup complete for {device_id}. Ready for {episode_info['name']}!")
            
            # Send setup complete notification
            await self._send_to_device(device_id, {
                "type": "conversation_started",
                "episode": episode_info['name'],
                "message": f"Conversation started with {choice_config['friend']}"
            })

            return True

        except Exception as e:
            logger.error(f"  Error in conversation workflow for {device_id}: {e}")
            
            # Update device status to error
            if self.server_state and device_id in self.server_state.active_devices:
                self.server_state.active_devices[device_id]["status"] = "error"
            
            await self._send_to_device(device_id, {
                "type": "error", 
                "message": f"Setup failed: {str(e)}"
            })
            return False

    async def _handle_device_message(self, device_id: str, message: str):
        """Handle incoming messages from ESP32/device with comprehensive logging"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            logger.info(f"📥 Received from {device_id}: {msg_type}")

            # Update server message stats
            if self.server_state:
                self.server_state.total_messages += 1
                if device_id in self.server_state.conversation_stats:
                    self.server_state.conversation_stats[device_id]["messages"] += 1

            if msg_type == "audio_data":
                # Forward audio to realtime manager
                audio_data = data.get("audio")
                if audio_data:
                    logger.debug(f"🎵 Forwarding audio data from {device_id} ({len(audio_data)} chars)")
                    await self.realtime_manager.send_audio(device_id, audio_data)
                else:
                    logger.warning(f"⚠️ Empty audio data received from {device_id}")
                
            elif msg_type == "start_recording":
                logger.info(f"🎙️ Started recording for {device_id}")
                if self.server_state and device_id in self.server_state.active_devices:
                    self.server_state.active_devices[device_id]["status"] = "recording"
                
            elif msg_type == "stop_recording":
                logger.info(f"🛑 Stopped recording for {device_id}")
                if self.server_state and device_id in self.server_state.active_devices:
                    self.server_state.active_devices[device_id]["status"] = "processing"
                await self.realtime_manager.commit_audio(device_id)
                
            elif msg_type == "button_press":
                logger.info(f"🔘 Button pressed for {device_id}")
                await self._end_conversation(device_id)
                
            elif msg_type == "ping":
                # Respond to ping with pong
                await self._send_to_device(device_id, {
                    "type": "pong",
                    "timestamp": datetime.now().isoformat(),
                    "original_timestamp": data.get("timestamp")
                })
                
            elif msg_type == "device_info":
                # Handle device info updates
                logger.info(f"📱 Device info from {device_id}: {data}")
                if self.server_state and device_id in self.server_state.active_devices:
                    self.server_state.active_devices[device_id].update({
                        "device_info": data,
                        "last_info_update": datetime.now()
                    })
                
            else:
                logger.warning(f"❓ Unknown message type from {device_id}: {msg_type}")
                await self._send_to_device(device_id, {
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}"
                })

        except json.JSONDecodeError as e:
            logger.error(f"  Invalid JSON from {device_id}: {message[:100]}...")
            await self._send_to_device(device_id, {
                "type": "error",
                "message": "Invalid JSON format"
            })
        except Exception as e:
            logger.error(f"  Error handling device message from {device_id}: {e}")
            await self._send_to_device(device_id, {
                "type": "error",
                "message": f"Message processing error: {str(e)}"
            })

    async def _end_conversation(self, device_id: str):
        """End the conversation and cleanup with statistics"""
        try:
            logger.info(f"🏁 Ending conversation for {device_id}")
            
            # Calculate conversation duration and update stats
            if self.server_state and device_id in self.server_state.conversation_stats:
                start_time = self.server_state.conversation_stats[device_id]["start_time"]
                duration = (datetime.now() - start_time).total_seconds()
                self.server_state.conversation_stats[device_id]["duration"] = duration
                
                logger.info(f"📊 Conversation stats for {device_id}:")
                logger.info(f"   Duration: {duration:.1f} seconds")
                logger.info(f"   Messages: {self.server_state.conversation_stats[device_id]['messages']}")
                logger.info(f"   Episode: {self.server_state.conversation_stats[device_id]['episode']}")

            # Update device status
            if self.server_state and device_id in self.server_state.active_devices:
                self.server_state.active_devices[device_id]["conversation_active"] = False
                self.server_state.active_devices[device_id]["status"] = "ending_conversation"

            # End realtime session
            await self.realtime_manager.end_conversation(device_id)
            
            # Send end signal to device
            await self._send_to_device(device_id, {
                "type": "conversation_ended",
                "message": "Conversation ended successfully",
                "duration": self.server_state.conversation_stats.get(device_id, {}).get("duration", 0) if self.server_state else 0
            })

            # Update final status
            if self.server_state and device_id in self.server_state.active_devices:
                self.server_state.active_devices[device_id]["status"] = "connected"

        except Exception as e:
            logger.error(f"  Error ending conversation for {device_id}: {e}")
            await self._send_to_device(device_id, {
                "type": "error",
                "message": f"Error ending conversation: {str(e)}"
            })

    async def _send_to_device(self, device_id: str, data: dict) -> bool:
        """Send data to ESP32/device with error handling and logging"""
        if device_id not in self.active_connections:
            logger.warning(f"⚠️ No active connection for {device_id}")
            return False
            
        try:
            websocket = self.active_connections[device_id]
            message = json.dumps(data)
            await websocket.send_text(message)
            
            logger.debug(f"📤 Sent to {device_id}: {data.get('type', 'unknown')} ({len(message)} chars)")
            
            # Update device last activity
            if self.server_state and device_id in self.server_state.active_devices:
                self.server_state.active_devices[device_id]["last_activity"] = datetime.now()
            
            return True
            
        except Exception as e:
            logger.error(f"  Error sending to {device_id}: {e}")
            await self._cleanup_connection(device_id)
            return False

    async def _cleanup_connection(self, device_id: str):
        """Clean up connection and resources with comprehensive cleanup"""
        try:
            logger.info(f"🧹 Cleaning up connection for {device_id}")

            # Remove from active connections
            if device_id in self.active_connections:
                try:
                    websocket = self.active_connections[device_id]
                    if websocket.client_state != websocket.client_state.DISCONNECTED:
                        await websocket.close()
                except Exception as e:
                    logger.warning(f"⚠️ Error closing websocket for {device_id}: {e}")
                finally:
                    del self.active_connections[device_id]

            # End realtime session if active
            try:
                await self.realtime_manager.end_conversation(device_id)
            except Exception as e:
                logger.warning(f"⚠️ Error ending realtime session for {device_id}: {e}")

            # Update server state
            if self.server_state:
                # Mark conversation as ended if it was active
                if device_id in self.server_state.conversation_stats:
                    if "duration" not in self.server_state.conversation_stats[device_id]:
                        start_time = self.server_state.conversation_stats[device_id]["start_time"]
                        duration = (datetime.now() - start_time).total_seconds()
                        self.server_state.conversation_stats[device_id]["duration"] = duration
                        self.server_state.conversation_stats[device_id]["ended_reason"] = "connection_lost"

                # Remove from active devices
                if device_id in self.server_state.active_devices:
                    del self.server_state.active_devices[device_id]
            
            logger.info(f"  Cleanup completed for {device_id}")

        except Exception as e:
            logger.error(f"  Error during cleanup for {device_id}: {e}")

    # Method for realtime manager to send AI responses to device
    async def send_response_to_device(self, device_id: str, response_data: dict):
        """Called by realtime manager to send AI responses to device"""
        try:
            # Add timestamp to response
            response_data["timestamp"] = datetime.now().isoformat()
            
            # Log AI response
            response_type = response_data.get("type", "unknown")
            if response_type == "audio_chunk":
                logger.debug(f"🤖 Forwarding AI audio chunk to {device_id}")
            else:
                logger.info(f"🤖 Forwarding AI response to {device_id}: {response_type}")
            
            success = await self._send_to_device(device_id, response_data)
            
            if success and self.server_state:
                # Update message stats
                self.server_state.total_messages += 1
                if device_id in self.server_state.conversation_stats:
                    self.server_state.conversation_stats[device_id]["messages"] += 1
                
                # Update device status based on response type
                if device_id in self.server_state.active_devices:
                    if response_type == "audio_chunk":
                        self.server_state.active_devices[device_id]["status"] = "ai_speaking"
                    elif response_type == "audio_complete":
                        self.server_state.active_devices[device_id]["status"] = "waiting_for_user"
            
            return success
            
        except Exception as e:
            logger.error(f"  Error sending AI response to {device_id}: {e}")
            return False

    # Utility methods for server management
    def get_active_device_count(self) -> int:
        """Get count of active device connections"""
        return len(self.active_connections)

    def get_device_list(self) -> list:
        """Get list of active device IDs"""
        return list(self.active_connections.keys())

    def is_device_connected(self, device_id: str) -> bool:
        """Check if a specific device is connected"""
        return device_id in self.active_connections

    async def broadcast_message(self, message: dict, exclude_devices: list = None):
        """Broadcast a message to all connected devices"""
        exclude_devices = exclude_devices or []
        
        for device_id in self.active_connections:
            if device_id not in exclude_devices:
                await self._send_to_device(device_id, message)

    async def send_admin_message(self, device_id: str, message: str):
        """Send an admin message to a specific device"""
        admin_message = {
            "type": "admin_message",
            "message": message,
            "timestamp": datetime.now().isoformat()
        }
        return await self._send_to_device(device_id, admin_message)

    def get_connection_stats(self) -> dict:
        """Get detailed connection statistics"""
        stats = {
            "total_active_connections": len(self.active_connections),
            "devices": {}
        }
        
        if self.server_state:
            for device_id, device_info in self.server_state.active_devices.items():
                stats["devices"][device_id] = {
                    "status": device_info.get("status", "unknown"),
                    "connected_at": device_info.get("connected_at", "unknown"),
                    "conversation_active": device_info.get("conversation_active", False),
                    "message_count": device_info.get("message_count", 0),
                    "current_episode": device_info.get("current_episode"),
                    "last_activity": device_info.get("last_activity", "unknown")
                }
        
        return stats