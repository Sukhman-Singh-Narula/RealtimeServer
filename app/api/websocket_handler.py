from fastapi import WebSocket, WebSocketDisconnect
import json
from typing import Dict, Any
import asyncio
from datetime import datetime
import logging
import base64
from app.agents.agent_configs import get_choice_agent_config, get_episode_agent_config
from app.agents.agent_tools import TOOL_HANDLERS
from app.utils.audio import AudioProcessor

logger = logging.getLogger(__name__)

class WebSocketHandler:
    def __init__(self, managers: Dict[str, Any]):
        self.db_manager = managers['database']
        self.cache_manager = managers['cache']
        self.content_manager = managers['content']
        self.realtime_manager = managers['realtime']
        self.ws_manager = managers['websocket']
    
    async def handle_connection(self, websocket: WebSocket, esp32_id: str):
        """Main WebSocket connection handler with enhanced audio streaming"""
        # Clean up device ID if malformed
        esp32_id = esp32_id.strip('{}')
        logger.info(f"Handling connection for cleaned device ID: {esp32_id}")
        
        # Check if this device already has an active connection
        existing_connection = self.realtime_manager.get_connection(esp32_id)
        if existing_connection:
            logger.info(f"Closing existing connection for {esp32_id}")
            self.realtime_manager.close_connection(esp32_id)
            await asyncio.sleep(0.5)  # Brief pause for cleanup
        
        await self.ws_manager.connect(esp32_id, websocket)
        
        try:
            # Initialize user and session
            user = await self.db_manager.get_or_create_user(esp32_id)
            logger.info(f"User initialized for {esp32_id}: {user.id}")
            
            # Create session in cache
            await self.cache_manager.set_session(esp32_id, {
                "user_id": user.id,
                "agent_state": "CHOOSING",
                "connected_at": datetime.utcnow().isoformat(),
                "current_agent": "choice_agent",
                "response_active": False,
                "audio_stream_active": False  # Track audio stream state
            })
            
            # Create OpenAI Realtime connection
            logger.info(f"Creating OpenAI Realtime connection for {esp32_id}")
            realtime_conn = await self.realtime_manager.create_connection(
                esp32_id,
                lambda msg: self.handle_realtime_message(esp32_id, msg)
            )
            
            # Wait for session to be created
            await asyncio.sleep(2.0)
            
            # Load episodes and configure Choice Agent
            episodes = await self.content_manager.get_available_episodes(user.id)
            logger.info(f"Loaded {len(episodes)} episodes for {esp32_id}")
            
            choice_config = get_choice_agent_config(episodes)
            logger.info(f"Generated choice config for {esp32_id}")
            
            # Update session with Choice Agent
            self.realtime_manager.update_session(
                esp32_id,
                instructions=choice_config['instructions'],
                voice=choice_config['voice'],
                tools=choice_config['tools']
            )
            
            # Wait for session update
            await asyncio.sleep(2.0)
            
            # Store realtime session info
            await self.cache_manager.set_realtime_connection(esp32_id, {
                "session_id": realtime_conn.session_id,
                "connected_at": datetime.utcnow().isoformat()
            })
            
            # Send welcome message 
            await self.ws_manager.send_message(esp32_id, {
                "type": "connected",
                "user_id": user.id,
                "message": "Welcome! I'm Lingo, ready to help you learn languages! 🎉"
            })
            
            # Start the conversation session
            self.realtime_manager.start_conversation(esp32_id)
            
            logger.info(f"Setup complete for {esp32_id}. Conversation started and ready!")
            
            # Main message loop with enhanced error handling
            while True:
                try:
                    # Check WebSocket state
                    if hasattr(websocket, 'client_state') and websocket.client_state.name != 'CONNECTED':
                        logger.info(f"WebSocket for {esp32_id} is no longer connected")
                        break
                    
                    # Increased timeout for better stability
                    message = await asyncio.wait_for(websocket.receive(), timeout=300.0)  # 5 minutes
                    
                    # Check for WebSocket close message
                    if message.get("type") == "websocket.disconnect":
                        logger.info(f"ESP32 {esp32_id} disconnected (disconnect message)")
                        break
                    
                    if "text" in message:
                        # Handle JSON messages
                        try:
                            data = json.loads(message["text"])
                            await self.process_esp32_message(esp32_id, data)
                        except json.JSONDecodeError as e:
                            logger.error(f"Invalid JSON from {esp32_id}: {e}")
                            
                    elif "bytes" in message:
                        # Handle binary audio data
                        audio_data = message["bytes"]
                        await self.handle_binary_audio_from_esp32(esp32_id, audio_data)
                        
                    else:
                        logger.warning(f"Unknown message format from {esp32_id}: {message}")
                        
                except WebSocketDisconnect:
                    logger.info(f"ESP32 {esp32_id} disconnected (WebSocketDisconnect)")
                    break
                except asyncio.TimeoutError:
                    # Timeout on receive - send ping to check connection
                    try:
                        await websocket.ping()
                        logger.debug(f"Sent ping to {esp32_id}")
                        continue
                    except:
                        logger.info(f"Connection lost for {esp32_id} (ping failed)")
                        break
                except Exception as e:
                    logger.error(f"Error processing message from {esp32_id}: {e}")
                    # Check if error indicates connection is closed
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
            await self.cleanup_connection(esp32_id)
    
    async def process_esp32_message(self, esp32_id: str, message: Dict[str, Any]):
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
            logger.info(f"End stream signal received from {esp32_id}")
            # Note: With new conversation flow, we don't commit here
            # The server VAD will handle response triggering automatically
        elif msg_type == 'start_conversation':
            logger.info(f"Starting conversation for {esp32_id}")
            self.realtime_manager.start_conversation(esp32_id)
        elif msg_type == 'end_conversation':
            logger.info(f"Ending conversation for {esp32_id}")
            self.realtime_manager.end_conversation(esp32_id)
        elif msg_type == 'disconnect':
            logger.info(f"Disconnect request received from {esp32_id}")
            # This is an explicit disconnect request - close gracefully
            connection = self.realtime_manager.get_connection(esp32_id)
            if connection:
                connection.close()
        else:
            logger.warning(f"Unknown message type from ESP32: {msg_type}")
            
        # Update activity for any message received
        connection = self.realtime_manager.get_connection(esp32_id)
        if connection:
            connection.update_activity()
    
    async def handle_audio_from_esp32(self, esp32_id: str, message: Dict[str, Any]):
        """Handle incoming audio from ESP32 with improved processing"""
        audio_data_hex = message.get('audio_data', '')
        if audio_data_hex:
            try:
                # Convert hex to bytes
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
        """Enhanced audio processing with proper sample rate conversion and activity tracking"""
        try:
            # Update activity for the connection
            connection = self.realtime_manager.get_connection(esp32_id)
            if connection:
                connection.update_activity()
            
            # Convert from 16kHz to 24kHz for OpenAI
            audio_processor = AudioProcessor()
            audio_24khz = audio_processor.convert_sample_rate(audio_data, 16000, 24000)
            
            # Send to OpenAI Realtime API
            self.realtime_manager.send_audio(esp32_id, audio_24khz)
            
            # Update activity in session cache
            session = await self.cache_manager.get_session(esp32_id)
            if session:
                session['last_activity'] = datetime.utcnow().isoformat()
                await self.cache_manager.set_session(esp32_id, session)
                
        except Exception as e:
            logger.error(f"Error in _process_audio_data for {esp32_id}: {e}")
                
    async def handle_text_from_esp32(self, esp32_id: str, message: Dict[str, Any]):
        """Handle text messages from ESP32"""
        text = message.get('text', '')
        if text:
            logger.info(f"Text message from {esp32_id}: {text}")
            
            # Ensure conversation is active
            self.realtime_manager.start_conversation(esp32_id)
            
            # Send text as conversation item to OpenAI
            self.realtime_manager.send_event(esp32_id, {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": text
                        }
                    ]
                }
            })
            
            # Create response to the text
            session = await self.cache_manager.get_session(esp32_id)
            if session and not session.get('response_active', False):
                session['response_active'] = True  
                await self.cache_manager.set_session(esp32_id, session)
                self.realtime_manager.create_response(esp32_id, ["text", "audio"])
    
    async def handle_realtime_message(self, esp32_id: str, message: Dict[str, Any]):
        """Handle messages from OpenAI Realtime API with enhanced audio streaming"""
        event_type = message.get('type')
        logger.debug(f"Realtime event for {esp32_id}: {event_type}")
        
        if event_type == 'session.created':
            logger.info(f"Realtime session created for {esp32_id}")
            session_id = message.get('session', {}).get('id')
            logger.info(f"Session ID: {session_id}")
            
        elif event_type == 'session.updated':
            logger.info(f"Realtime session updated for {esp32_id}")
            
        elif event_type == 'response.audio.delta':
            # Audio chunk from assistant - CRITICAL FOR SMOOTH PLAYBACK
            audio_data = message.get('delta')
            if audio_data:
                try:
                    # Decode base64 audio (24kHz from OpenAI)
                    audio_bytes_24khz = base64.b64decode(audio_data)
                    
                    # Convert from 24kHz to 16kHz for ESP32/Web client
                    audio_processor = AudioProcessor()
                    audio_bytes_16khz = audio_processor.convert_sample_rate(audio_bytes_24khz, 24000, 16000)
                    
                    logger.debug(f"Sending audio chunk to {esp32_id}: {len(audio_bytes_16khz)} bytes")
                    
                    # Send immediately to client
                    await self.ws_manager.send_audio(esp32_id, audio_bytes_16khz)
                    
                    # Mark audio stream as active
                    session = await self.cache_manager.get_session(esp32_id)
                    if session and not session.get('audio_stream_active', False):
                        session['audio_stream_active'] = True
                        await self.cache_manager.set_session(esp32_id, session)
                        
                        # Notify client that audio stream started
                        await self.ws_manager.send_message(esp32_id, {
                            "type": "audio_start"
                        })
                    
                except Exception as e:
                    logger.error(f"Error processing audio for {esp32_id}: {e}")
                
        elif event_type == 'response.audio.done':
            # Audio generation completed - IMPORTANT FOR PROPER CLEANUP
            logger.info(f"Audio generation completed for {esp32_id}")
            
            # Mark audio stream as inactive
            session = await self.cache_manager.get_session(esp32_id)
            if session:
                session['audio_stream_active'] = False
                await self.cache_manager.set_session(esp32_id, session)
            
            # Notify client that audio is complete
            await self.ws_manager.send_message(esp32_id, {
                "type": "audio_complete"
            })
            
        elif event_type == 'response.audio_transcript.delta':
            # Transcript update
            text = message.get('delta', '')
            if text:
                logger.debug(f"Transcript delta for {esp32_id}: {text}")
                await self.ws_manager.send_text(esp32_id, text, is_final=False)
            
        elif event_type == 'response.audio_transcript.done':
            # Final transcript
            text = message.get('transcript', '')
            if text:
                logger.info(f"Final transcript for {esp32_id}: {text}")
                await self.ws_manager.send_text(esp32_id, text, is_final=True)
            
        elif event_type == 'response.text.delta':
            # Text response chunk
            text = message.get('delta', '')
            if text:
                logger.debug(f"Text delta for {esp32_id}: {text}")
                await self.ws_manager.send_text(esp32_id, text, is_final=False)
                
        elif event_type == 'response.text.done':
            # Final text response
            text = message.get('text', '')
            if text:
                logger.info(f"Final text for {esp32_id}: {text}")
                await self.ws_manager.send_text(esp32_id, text, is_final=True)
            
        elif event_type == 'response.function_call_arguments.done':
            # Function call from agent
            await self.handle_function_call(esp32_id, message)
            
        elif event_type == 'response.created':
            logger.info(f"Response creation confirmed for {esp32_id}")
            # Mark response as active
            session = await self.cache_manager.get_session(esp32_id)
            if session:
                session['response_active'] = True
                await self.cache_manager.set_session(esp32_id, session)
            
        elif event_type == 'response.done':
            # Response completed - CRITICAL FOR CONVERSATION FLOW
            response = message.get('response', {})
            status = response.get('status')
            logger.info(f"Response completed for {esp32_id} with status: {status}")
            
            # Mark response as no longer active - CRITICAL for continued conversation
            session = await self.cache_manager.get_session(esp32_id)
            if session:
                session['response_active'] = False
                session['audio_stream_active'] = False  # Ensure audio stream is marked inactive
                await self.cache_manager.set_session(esp32_id, session)
            
            # Clear the response generation flag in the connection
            connection = self.realtime_manager.get_connection(esp32_id)
            if connection:
                connection.is_generating_response = False
            
            # Send final completion signal
            await self.ws_manager.send_message(esp32_id, {
                "type": "response_complete",
                "status": status
            })
                
        elif event_type == 'error':
            error_info = message.get('error', {})
            logger.error(f"Realtime API error for {esp32_id}: {error_info}")
            
            # Mark response as no longer active on error - CRITICAL for recovery
            session = await self.cache_manager.get_session(esp32_id)
            if session:
                session['response_active'] = False
                session['audio_stream_active'] = False
                await self.cache_manager.set_session(esp32_id, session)
                
            # Clear the response generation flag
            connection = self.realtime_manager.get_connection(esp32_id)
            if connection:
                connection.is_generating_response = False
            
            await self.ws_manager.send_message(esp32_id, {
                "type": "error",
                "message": error_info.get('message', 'An error occurred')
            })
    
    async def handle_function_call(self, esp32_id: str, message: Dict[str, Any]):
        """Handle function calls from agents"""
        call_id = message.get('call_id')
        name = message.get('name')
        arguments = message.get('arguments', '{}')
        
        try:
            args = json.loads(arguments)
        except:
            args = {}
        
        logger.info(f"Function call from {esp32_id}: {name}({args})")
        
        # Handle the function call
        if name in TOOL_HANDLERS:
            handler = TOOL_HANDLERS[name]
            result = await handler(args, esp32_id, {
                'database': self.db_manager,
                'cache': self.cache_manager,
                'content': self.content_manager,
                'realtime': self.realtime_manager,
                'websocket': self.ws_manager
            })
            
            # Special handling for episode selection
            if name == 'select_episode' and result.get('success'):
                await self.transition_to_episode_agent(esp32_id, result.get('episode'))
        else:
            result = {"error": f"Unknown function: {name}"}
        
        # Send function result back to OpenAI
        self.realtime_manager.send_event(esp32_id, {
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps(result)
            }
        })
        
        # Trigger response
        self.realtime_manager.create_response(esp32_id)
    
    async def transition_to_episode_agent(self, esp32_id: str, episode_data: Dict[str, Any]):
        """Transition from Choice Agent to Episode Agent"""
        logger.info(f"Transitioning {esp32_id} to Episode Agent")
        
        # Stop any active audio stream during transition
        session = await self.cache_manager.get_session(esp32_id)
        if session:
            session['audio_stream_active'] = False
            await self.cache_manager.set_session(esp32_id, session)
        
        # Get episode agent configuration
        episode_config = get_episode_agent_config(episode_data)
        
        # Update OpenAI session with new agent
        self.realtime_manager.update_session(
            esp32_id,
            instructions=episode_config['instructions'],
            voice=episode_config['voice'],
            tools=episode_config['tools']
        )
        
        # Update cache
        await self.cache_manager.update_agent_state(
            esp32_id, 
            "LEARNING",
            episode_config['name']
        )
        
        # Send transition message to ESP32
        await self.ws_manager.send_message(esp32_id, {
            "type": "agent_switched",
            "new_agent": "episode",
            "episode_info": episode_data,
            "message": f"Great choice! Let's start learning {episode_data['language']} with '{episode_data['title']}'! 🌟"
        })
        
        # Give the AI a moment to process the new instructions
        await asyncio.sleep(1.0)
        
        # Trigger initial teaching response
        self.realtime_manager.create_response(esp32_id)
    
    async def handle_heartbeat(self, esp32_id: str):
        """Handle heartbeat to keep connection alive"""
        # Update activity for the OpenAI connection
        connection = self.realtime_manager.get_connection(esp32_id)
        if connection:
            connection.update_activity()
            
        session = await self.cache_manager.get_session(esp32_id)
        if session:
            session['last_activity'] = datetime.utcnow().isoformat()
            await self.cache_manager.set_session(esp32_id, session)
        
        await self.ws_manager.send_message(esp32_id, {"type": "heartbeat_ack"})
    
    async def cleanup_connection(self, esp32_id: str):
        """Cleanup when ESP32 disconnects"""
        logger.info(f"Cleaning up connection for {esp32_id}")
        
        try:
            # End any active learning session
            session = await self.cache_manager.get_session(esp32_id)
            if session:
                learning_session_id = session.get('learning_session_id')
                if learning_session_id:
                    await self.db_manager.end_session(learning_session_id)
        except Exception as e:
            logger.error(f"Error ending learning session for {esp32_id}: {e}")
        
        try:
            # Close OpenAI connection
            self.realtime_manager.close_connection(esp32_id)
        except Exception as e:
            logger.error(f"Error closing OpenAI connection for {esp32_id}: {e}")
        
        try:
            # Remove from WebSocket manager
            await self.ws_manager.disconnect(esp32_id)
        except Exception as e:
            logger.error(f"Error disconnecting from WebSocket manager for {esp32_id}: {e}")
        
        try:
            # Clear cache
            await self.cache_manager.delete_connection(esp32_id)
        except Exception as e:
            logger.error(f"Error clearing cache for {esp32_id}: {e}")
            
        logger.info(f"Cleanup completed for {esp32_id}")