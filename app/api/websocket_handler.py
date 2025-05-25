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
        """Main WebSocket connection handler"""
        await self.ws_manager.connect(esp32_id, websocket)
        
        try:
            # Initialize user and session
            user = await self.db_manager.get_or_create_user(esp32_id)
            
            # Create session in cache
            await self.cache_manager.set_session(esp32_id, {
                "user_id": user.id,
                "agent_state": "CHOOSING",
                "connected_at": datetime.utcnow().isoformat(),
                "current_agent": "choice_agent"
            })
            
            # Create OpenAI Realtime connection
            realtime_conn = await self.realtime_manager.create_connection(
                esp32_id,
                lambda msg: self.handle_realtime_message(esp32_id, msg)
            )
            
            # Wait for session to be created
            await asyncio.sleep(0.5)
            
            # Load episodes and configure Choice Agent
            episodes = await self.content_manager.get_available_episodes(user.id)
            choice_config = get_choice_agent_config(episodes)
            
            # Update session with Choice Agent
            self.realtime_manager.update_session(
                esp32_id,
                instructions=choice_config['instructions'],
                voice=choice_config['voice'],
                tools=choice_config['tools']
            )
            
            # Store realtime session info
            await self.cache_manager.set_realtime_connection(esp32_id, {
                "session_id": realtime_conn.session_id,
                "connected_at": datetime.utcnow().isoformat()
            })
            
            # Send welcome message
            await self.ws_manager.send_message(esp32_id, {
                "type": "connected",
                "user_id": user.id,
                "message": "Welcome! I'm here to help you choose a fun language learning episode! 🎉"
            })
            
            # Send initial message to trigger audio response
            self.realtime_manager.send_event(esp32_id, {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Hi! Please introduce yourself and the available episodes with your voice."
                        }
                    ]
                }
            })
            
            # Trigger initial response with audio
            self.realtime_manager.send_event(esp32_id, {
                "type": "response.create",
                "response": {
                    "modalities": ["text", "audio"]
                }
            })
            
            # Main message loop
            while True:
                data = await websocket.receive_json()
                await self.process_esp32_message(esp32_id, data)
                
        except WebSocketDisconnect:
            logger.info(f"ESP32 {esp32_id} disconnected")
        except Exception as e:
            logger.error(f"Error handling connection for {esp32_id}: {e}")
        finally:
            await self.cleanup_connection(esp32_id)
    
    async def process_esp32_message(self, esp32_id: str, message: Dict[str, Any]):
        """Process incoming messages from ESP32"""
        msg_type = message.get('type')
        
        if msg_type == 'audio':
            await self.handle_audio_from_esp32(esp32_id, message)
        elif msg_type == 'heartbeat':
            await self.handle_heartbeat(esp32_id)
        else:
            logger.warning(f"Unknown message type from ESP32: {msg_type}")
    
    async def handle_audio_from_esp32(self, esp32_id: str, message: Dict[str, Any]):
        """Handle incoming audio from ESP32"""
        audio_data_hex = message.get('audio_data', '')
        if audio_data_hex:
            # Convert hex to bytes
            audio_data = bytes.fromhex(audio_data_hex)
            
            # Convert from 16kHz to 24kHz for OpenAI
            audio_processor = AudioProcessor()
            audio_24khz = audio_processor.convert_sample_rate(audio_data, 16000, 24000)
            
            # Log audio info
            logger.debug(f"Received audio from {esp32_id}: {len(audio_data)} bytes -> {len(audio_24khz)} bytes (24kHz)")
            
            # Send to OpenAI Realtime API
            self.realtime_manager.send_audio(esp32_id, audio_24khz)
            
            # Check if this is silence
            if audio_processor.detect_silence(audio_data):
                logger.debug(f"Detected silence from {esp32_id}")
            else:
                # Commit audio buffer to trigger response after non-silence
                self.realtime_manager.commit_audio(esp32_id)
            
            # Update activity
            session = await self.cache_manager.get_session(esp32_id)
            if session:
                session['last_activity'] = datetime.utcnow().isoformat()
                await self.cache_manager.set_session(esp32_id, session)
    
    async def handle_realtime_message(self, esp32_id: str, message: Dict[str, Any]):
        """Handle messages from OpenAI Realtime API"""
        event_type = message.get('type')
        logger.debug(f"Realtime event for {esp32_id}: {event_type}")
        
        if event_type == 'session.created':
            logger.info(f"Realtime session created for {esp32_id}")
            session_id = message.get('session', {}).get('id')
            logger.info(f"Session ID: {session_id}")
            
        elif event_type == 'response.audio.done':
            # Audio generation completed
            logger.info(f"Audio generation completed for {esp32_id}")
            # You might want to send an event to indicate audio is complete
            await self.ws_manager.send_message(esp32_id, {
                "type": "audio_complete"
            })
            
        elif event_type == 'response.audio.delta':
            # Audio chunk from assistant
            audio_data = message.get('delta')
            if audio_data:
                try:
                    # Decode base64 audio (24kHz from OpenAI)
                    audio_bytes_24khz = base64.b64decode(audio_data)
                    
                    # Convert from 24kHz to 16kHz for ESP32
                    audio_processor = AudioProcessor()
                    audio_bytes_16khz = audio_processor.convert_sample_rate(audio_bytes_24khz, 24000, 16000)
                    
                    logger.debug(f"Sending audio chunk to {esp32_id} (24kHz: {len(audio_bytes_24khz)} -> 16kHz: {len(audio_bytes_16khz)} bytes)")
                    await self.ws_manager.send_audio(esp32_id, audio_bytes_16khz)
                except Exception as e:
                    logger.error(f"Error processing audio for {esp32_id}: {e}")
                
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
            
        elif event_type == 'response.done':
            # Response completed
            response = message.get('response', {})
            status = response.get('status')
            logger.info(f"Response completed for {esp32_id} with status: {status}")
            
            # Check output types
            output = response.get('output', [])
            for item in output:
                logger.debug(f"Output item type: {item.get('type')}")
                
        elif event_type == 'error':
            error_info = message.get('error', {})
            logger.error(f"Realtime API error for {esp32_id}: {error_info}")
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
        await asyncio.sleep(0.5)
        
        # Trigger initial teaching response
        self.realtime_manager.create_response(esp32_id)
    
    async def handle_heartbeat(self, esp32_id: str):
        """Handle heartbeat to keep connection alive"""
        session = await self.cache_manager.get_session(esp32_id)
        if session:
            session['last_activity'] = datetime.utcnow().isoformat()
            await self.cache_manager.set_session(esp32_id, session)
        
        await self.ws_manager.send_message(esp32_id, {"type": "heartbeat_ack"})
    
    async def cleanup_connection(self, esp32_id: str):
        """Cleanup when ESP32 disconnects"""
        logger.info(f"Cleaning up connection for {esp32_id}")
        
        # End any active learning session
        session = await self.cache_manager.get_session(esp32_id)
        if session:
            learning_session_id = session.get('learning_session_id')
            if learning_session_id:
                await self.db_manager.end_session(learning_session_id)
        
        # Close OpenAI connection
        self.realtime_manager.close_connection(esp32_id)
        
        # Remove from WebSocket manager
        await self.ws_manager.disconnect(esp32_id)
        
        # Clear cache
        await self.cache_manager.delete_connection(esp32_id)