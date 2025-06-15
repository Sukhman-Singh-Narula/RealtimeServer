# File: app/managers/realtime_manager.py - FIXED VERSION

import asyncio
import json
import logging
import websockets
import base64
from typing import Dict, Optional, Callable

logger = logging.getLogger(__name__)

class RealtimeManager:
    def __init__(self):
        self.sessions: Dict[str, dict] = {}
        self.websocket_handler: Optional[Callable] = None

    def set_websocket_handler(self, handler):
        """Set reference to websocket handler for sending responses"""
        self.websocket_handler = handler

    async def create_session(self, device_id: str) -> Optional[str]:
        """Create OpenAI Realtime session"""
        try:
            logger.info(f"Connecting to OpenAI Realtime API for {device_id}")
            
            # Connect to OpenAI Realtime API
            websocket = await websockets.connect(
                "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01",
                additional_headers={
                    "Authorization": f"Bearer {self._get_openai_api_key()}",
                    "OpenAI-Beta": "realtime=v1"
                }
            )
            
            logger.info(f"Connected to OpenAI Realtime API for {device_id}")
            
            # Store session info
            session_info = {
                "websocket": websocket,
                "session_id": None,
                "device_id": device_id,
                "audio_buffer": b"",
                "is_recording": False
            }
            
            self.sessions[device_id] = session_info
            
            # Start listening to OpenAI responses
            asyncio.create_task(self._listen_to_openai(device_id))
            
            # Wait for session.created event
            try:
                while True:
                    response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                    data = json.loads(response)
                    
                    if data.get("type") == "session.created":
                        session_id = data.get("session", {}).get("id")
                        session_info["session_id"] = session_id
                        logger.info(f"Session ID for {device_id}: {session_id}")
                        return session_id
                    else:
                        logger.debug(f"Waiting for session.created, got: {data.get('type')}")
                        
            except asyncio.TimeoutError:
                logger.error(f"Timeout waiting for session creation for {device_id}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to create session for {device_id}: {e}")
            return None

    async def configure_session(self, device_id: str, config: dict, voice: str = "alloy"):
        """Configure session with agent instructions and voice"""
        try:
            session_info = self.sessions.get(device_id)
            if not session_info:
                logger.error(f"No session found for {device_id}")
                return

            websocket = session_info["websocket"]
            
            # Create session update with agent configuration
            session_update = {
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "instructions": config["instructions"],
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
                        "silence_duration_ms": 200
                    },
                    "tools": config.get("tools", [])
                }
            }
            
            logger.info(f"Updating session for {device_id} with voice: {voice}")
            await websocket.send(json.dumps(session_update))
            
            # Add tools if any
            if config.get("tools"):
                logger.info(f"Added {len(config['tools'])} tools for {device_id}")

        except Exception as e:
            logger.error(f"Failed to configure session for {device_id}: {e}")

    async def start_conversation(self, device_id: str):
        """Start conversation and trigger initial AI response"""
        try:
            session_info = self.sessions.get(device_id)
            if not session_info:
                logger.error(f"No session found for {device_id}")
                return

            websocket = session_info["websocket"]
            
            logger.info(f"Starting conversation for {device_id}")
            
            # Send an initial message to trigger AI response
            initial_message = {
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
            
            await websocket.send(json.dumps(initial_message))
            
            # Trigger response generation
            response_create = {
                "type": "response.create",
                "response": {
                    "modalities": ["text", "audio"]
                }
            }
            
            await websocket.send(json.dumps(response_create))
            
            logger.info(f"Conversation started for {device_id}")

        except Exception as e:
            logger.error(f"Error starting conversation for {device_id}: {e}")

    async def _listen_to_openai(self, device_id: str):
        """Listen to OpenAI responses and forward to device"""
        try:
            session_info = self.sessions.get(device_id)
            if not session_info:
                return

            websocket = session_info["websocket"]
            
            while True:
                try:
                    response = await websocket.recv()
                    data = json.loads(response)
                    
                    await self._handle_openai_response(device_id, data)
                    
                except websockets.exceptions.ConnectionClosed:
                    logger.info(f"OpenAI connection closed for {device_id}")
                    break
                except Exception as e:
                    logger.error(f"Error in OpenAI listener for {device_id}: {e}")
                    break

        except Exception as e:
            logger.error(f"Error in OpenAI listener setup for {device_id}: {e}")

    async def _handle_openai_response(self, device_id: str, data: dict):
        """Handle different types of OpenAI responses"""
        try:
            event_type = data.get("type")
            
            if event_type == "response.audio.delta":
                # Forward audio chunk to device
                audio_data = data.get("delta")
                if audio_data and self.websocket_handler:
                    await self.websocket_handler.send_response_to_device(device_id, {
                        "type": "audio_chunk",
                        "audio": audio_data
                    })
                    
            elif event_type == "response.audio.done":
                # Audio response complete
                if self.websocket_handler:
                    await self.websocket_handler.send_response_to_device(device_id, {
                        "type": "audio_complete"
                    })
                    
            elif event_type == "response.text.delta":
                # Text response chunk
                text_data = data.get("delta")
                logger.debug(f"Text delta for {device_id}: {text_data}")
                
            elif event_type == "response.text.done":
                # Text response complete
                text_data = data.get("text")
                logger.info(f"Complete text response for {device_id}: {text_data}")
                
            elif event_type == "conversation.item.input_audio_transcription.completed":
                # User speech transcription
                transcript = data.get("transcript")
                logger.info(f"User said: {transcript}")
                
            elif event_type == "error":
                # Handle errors
                error_info = data.get("error", {})
                logger.error(f"OpenAI API error for {device_id}: {error_info}")
                
                if self.websocket_handler:
                    await self.websocket_handler.send_response_to_device(device_id, {
                        "type": "error",
                        "message": f"AI error: {error_info.get('message', 'Unknown error')}"
                    })
                    
            else:
                logger.debug(f"OpenAI event for {device_id}: {event_type}")

        except Exception as e:
            logger.error(f"Error handling OpenAI response for {device_id}: {e}")

    async def send_audio(self, device_id: str, audio_data: str):
        """Send audio data to OpenAI"""
        try:
            session_info = self.sessions.get(device_id)
            if not session_info:
                logger.error(f"No session found for {device_id}")
                return

            websocket = session_info["websocket"]
            
            # Send audio data to OpenAI
            audio_append = {
                "type": "input_audio_buffer.append",
                "audio": audio_data
            }
            
            await websocket.send(json.dumps(audio_append))
            
        except Exception as e:
            logger.error(f"Error sending audio for {device_id}: {e}")

    async def commit_audio(self, device_id: str):
        """Commit audio buffer and trigger response"""
        try:
            session_info = self.sessions.get(device_id)
            if not session_info:
                logger.error(f"No session found for {device_id}")
                return

            websocket = session_info["websocket"]
            
            # Commit the audio buffer
            commit_message = {
                "type": "input_audio_buffer.commit"
            }
            
            await websocket.send(json.dumps(commit_message))
            
            # Create response
            response_create = {
                "type": "response.create",
                "response": {
                    "modalities": ["text", "audio"]
                }
            }
            
            await websocket.send(json.dumps(response_create))
            
            logger.info(f"Audio committed and response requested for {device_id}")

        except Exception as e:
            logger.error(f"Error committing audio for {device_id}: {e}")

    async def end_conversation(self, device_id: str):
        """End conversation and cleanup"""
        try:
            session_info = self.sessions.get(device_id)
            if not session_info:
                return

            logger.info(f"Ending conversation for {device_id}")
            
            websocket = session_info["websocket"]
            
            # Close WebSocket connection
            await websocket.close()
            
            # Remove from sessions
            del self.sessions[device_id]
            
            logger.info(f"Conversation ended for {device_id}")

        except Exception as e:
            logger.error(f"Error ending conversation for {device_id}: {e}")

    def _get_openai_api_key(self) -> str:
        """Get OpenAI API key from environment"""
        import os
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        return api_key