from fastapi import WebSocket, WebSocketDisconnect
import json
from typing import Dict, Any
import asyncio
from datetime import datetime
import logging
import base64
import time
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
        
        # Conversation time tracking
        self.conversation_timers = {}
    
    async def handle_connection(self, websocket: WebSocket, esp32_id: str):
        """Main WebSocket connection handler with simplified agent system"""
        # Clean up device ID if malformed
        esp32_id = esp32_id.strip('{}')
        logger.info(f"Handling connection for device ID: {esp32_id}")
        
        # Initialize conversation timer
        self.conversation_timers[esp32_id] = {
            'last_audio_time': None,
            'session_start_time': time.time(),
            'total_conversation_time': 0,
            'current_chunk_start': None
        }
        
        # Check if this device already has an active connection
        existing_connection = self.realtime_manager.get_connection(esp32_id)
        if existing_connection:
            logger.info(f"Closing existing connection for {esp32_id}")
            self.realtime_manager.close_connection(esp32_id)
            await asyncio.sleep(0.5)
        
        await self.ws_manager.connect(esp32_id, websocket)
        
        try:
            # Initialize user and get progress
            user = await self.db_manager.get_or_create_user(esp32_id)
            logger.info(f"User initialized: {user.id} for device {esp32_id}")
            
            # Get user info for personalization (in a real system, this might come from a user profile)
            user_info = {
                'name': 'friend',  # Default name, could be fetched from user profile
                'age': 6  # Default age, could be fetched from user profile
            }
            
            # Get user progress to determine next episode
            user_progress = {
                'current_language': user.current_language,
                'current_season': user.current_season,
                'current_episode': user.current_episode
            }
            
            # Get the next episode for this user (including prompts)
            next_episode = await self.content_manager.get_next_episode_for_user(user.id, user_progress)
            
            if not next_episode:
                logger.error(f"No next episode found for user {user.id}")
                await self.ws_manager.send_message(esp32_id, {
                    "type": "error",
                    "message": "No learning content available. Please contact support."
                })
                return
            
            logger.info(f"Next episode for {esp32_id}: {next_episode['title']} (S{next_episode['season']}E{next_episode['episode']})")
            
            # Create session in cache
            session_data = {
                "user_id": user.id,
                "agent_state": "CHOOSING",
                "connected_at": datetime.utcnow().isoformat(),
                "current_agent": "choice_agent",
                "response_active": False,
                "audio_stream_active": False,
                "conversation_time_this_session": 0,
                "words_learned_this_session": [],
                "topics_covered_this_session": [],
                "next_episode": next_episode,  # Store the next episode with prompts
                "user_info": user_info  # Store user info for prompts
            }
            await self.cache_manager.set_session(esp32_id, session_data)
            
            # Create OpenAI Realtime connection
            logger.info(f"Creating OpenAI Realtime connection for {esp32_id}")
            realtime_conn = await self.realtime_manager.create_connection(
                esp32_id,
                lambda msg: self.handle_realtime_message(esp32_id, msg)
            )
            
            # Wait for session to be created
            await asyncio.sleep(2.0)
            
            # Configure Choice Agent with the specific next episode
            choice_config = get_choice_agent_config(next_episode, user_info)
            logger.info(f"Generated choice config for {esp32_id} with episode: {next_episode['title']}")
            
            # Update OpenAI session with Choice Agent configuration
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
            
            # Get user analytics for welcome message
            analytics = await self.db_manager.get_user_learning_analytics(user.id)
            learning_stats = analytics.get('learning_statistics', {})
            
            # Send personalized welcome message
            welcome_message = self._create_welcome_message(learning_stats, next_episode, user_info)
            
            await self.ws_manager.send_message(esp32_id, {
                "type": "connected",
                "user_id": user.id,
                "message": welcome_message,
                "next_episode": {
                    "title": next_episode['title'],
                    "language": next_episode['language'],
                    "season": next_episode['season'],
                    "episode": next_episode['episode']
                },
                "analytics": {
                    "total_words_learned": learning_stats.get('total_words_learned', 0),
                    "total_episodes_completed": learning_stats.get('total_episodes_completed', 0),
                    "current_streak": learning_stats.get('current_streak_days', 0),
                    "conversation_time": learning_stats.get('total_conversation_time_formatted', '0 seconds')
                }
            })
            
            # Start the conversation session
            self.realtime_manager.start_conversation(esp32_id)
            
            logger.info(f"Setup complete for {esp32_id}. Ready for {next_episode['title']}!")
            
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
            await self.cleanup_connection(esp32_id)
    
    def _create_welcome_message(self, learning_stats: Dict, next_episode: Dict, user_info: Dict) -> str:
        """Create personalized welcome message"""
        user_name = user_info.get('name', 'friend')
        total_words = learning_stats.get('total_words_learned', 0)
        total_episodes = learning_stats.get('total_episodes_completed', 0)
        current_streak = learning_stats.get('current_streak_days', 0)
        
        if total_episodes == 0:
            return f"¡Hola {user_name}! Welcome to your Spanish learning adventure! I'm Lingo, and I'm so excited to help you learn! 🌟"
        elif total_episodes < 5:
            return f"Welcome back {user_name}! You've learned {total_words} words so far - that's amazing! Ready for more Spanish fun? 🎉"
        elif current_streak > 0:
            return f"¡Fantástico {user_name}! You're on a {current_streak}-day learning streak and have learned {total_words} words! Let's keep it going! 🔥"
        else:
            return f"Welcome back, Spanish superstar {user_name}! Your next adventure '{next_episode['title']}' is ready! ✨"
    
    async def handle_function_call(self, esp32_id: str, message: Dict[str, Any]):
        """Handle function calls from agents with simplified system"""
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
            
            # Handle specific function results
            if name == 'start_episode' and result.get('success'):
                await self.transition_to_episode_agent(esp32_id, result.get('episode'))
                
            elif name == 'complete_episode' and result.get('success') and result.get('return_to_choice'):
                await self.transition_back_to_choice_agent(esp32_id)
                
            # Update session tracking for learning functions
            if name == 'mark_vocabulary_learned' and result.get('success'):
                session = await self.cache_manager.get_session(esp32_id)
                if session:
                    words_learned = session.get('words_learned_this_session', [])
                    words_learned.append(args.get('word'))
                    session['words_learned_this_session'] = words_learned
                    await self.cache_manager.set_session(esp32_id, session)
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
        """Transition from Choice Agent to Episode Agent using Firebase prompts"""
        logger.info(f"Transitioning {esp32_id} to Episode Agent for '{episode_data['title']}'")
        
        # Get user info from session
        session = await self.cache_manager.get_session(esp32_id)
        if not session:
            logger.error(f"No session found for {esp32_id}")
            return
        
        user_info = session.get('user_info', {'name': 'friend', 'age': 6})
        
        # Stop any active audio stream during transition
        session['audio_stream_active'] = False
        session['current_episode_start'] = datetime.utcnow().isoformat()
        session['current_episode'] = episode_data
        await self.cache_manager.set_session(esp32_id, session)
        
        # Get episode agent configuration using the pre-written prompt from Firebase
        episode_config = get_episode_agent_config(episode_data, user_info)
        
        # Update OpenAI session with new agent configuration
        self.realtime_manager.update_session(
            esp32_id,
            instructions=episode_config['instructions'],
            voice=episode_config['voice'],
            tools=episode_config['tools']
        )
        
        # Update cache with new agent state
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
            "message": f"¡Vamos! Let's start learning with '{episode_data['title']}'! 🌟"
        })
        
        # Give the AI a moment to process the new instructions
        await asyncio.sleep(1.0)
        
        # Trigger initial teaching response
        self.realtime_manager.create_response(esp32_id)
    
    async def transition_back_to_choice_agent(self, esp32_id: str):
        """Transition back to Choice Agent for next episode selection"""
        logger.info(f"Transitioning {esp32_id} back to Choice Agent for next episode")
        
        # Get session and user info
        session = await self.cache_manager.get_session(esp32_id)
        if not session:
            logger.error(f"No session found for {esp32_id}")
            return
        
        user_id = session.get('user_id')
        user_info = session.get('user_info', {'name': 'friend', 'age': 6})
        
        # Get updated user progress
        user = await self.db_manager.get_or_create_user(esp32_id)
        user_progress = {
            'current_language': user.current_language,
            'current_season': user.current_season,
            'current_episode': user.current_episode
        }
        
        # Get the next episode for this user
        next_episode = await self.content_manager.get_next_episode_for_user(user_id, user_progress)
        
        if not next_episode:
            logger.warning(f"No next episode found for user {user_id}")
            await self.ws_manager.send_message(esp32_id, {
                "type": "completion",
                "message": "🎉 Congratulations! You've completed all available episodes! More adventures coming soon!"
            })
            return
        
        # Update session with new next episode
        session['next_episode'] = next_episode
        session['agent_state'] = 'CHOOSING'
        session['current_episode'] = None
        await self.cache_manager.set_session(esp32_id, session)
        
        # Configure Choice Agent with the new next episode
        choice_config = get_choice_agent_config(next_episode, user_info)
        
        # Update OpenAI session with Choice Agent configuration
        self.realtime_manager.update_session(
            esp32_id,
            instructions=choice_config['instructions'],
            voice=choice_config['voice'],
            tools=choice_config['tools']
        )
        
        # Update cache with new agent state
        await self.cache_manager.update_agent_state(
            esp32_id, 
            "CHOOSING",
            "choice_agent"
        )
        
        # Send transition message
        await self.ws_manager.send_message(esp32_id, {
            "type": "agent_switched",
            "new_agent": "choice",
            "next_episode": {
                "title": next_episode['title'],
                "language": next_episode['language'],
                "season": next_episode['season'],
                "episode": next_episode['episode']
            },
            "message": f"🎉 Episode completed! Ready for your next adventure: '{next_episode['title']}'?"
        })
        
        # Give the AI a moment to process
        await asyncio.sleep(1.0)
        
        # Trigger response
        self.realtime_manager.create_response(esp32_id)
    
    # Include all the other methods from the previous WebSocket handler
    # (audio processing, conversation tracking, etc.)
    
    async def process_esp32_message(self, esp32_id: str, message: Dict[str, Any]):
        """Process incoming JSON messages from ESP32 with conversation tracking"""
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
            await self.start_conversation_tracking(esp32_id)
            self.realtime_manager.start_conversation(esp32_id)
        elif msg_type == 'end_conversation':
            logger.info(f"Ending conversation for {esp32_id}")
            await self.end_conversation_tracking(esp32_id)
            self.realtime_manager.end_conversation(esp32_id)
        elif msg_type == 'disconnect':
            logger.info(f"Disconnect request received from {esp32_id}")
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
        """Handle incoming audio from ESP32 with conversation time tracking"""
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
        """Handle incoming binary audio data from ESP32 with conversation tracking"""
        try:
            logger.debug(f"Received binary audio from {esp32_id}: {len(audio_data)} bytes")
            await self._process_audio_data(esp32_id, audio_data)
        except Exception as e:
            logger.error(f"Error processing binary audio from {esp32_id}: {e}")

    async def _process_audio_data(self, esp32_id: str, audio_data: bytes):
        """Enhanced audio processing with conversation time tracking"""
        try:
            current_time = time.time()
            
            # Update conversation time tracking
            if esp32_id in self.conversation_timers:
                timer = self.conversation_timers[esp32_id]
                
                # Start new conversation chunk if this is the first audio in a while
                if (timer['last_audio_time'] is None or 
                    current_time - timer['last_audio_time'] > 2.0):
                    timer['current_chunk_start'] = current_time
                
                timer['last_audio_time'] = current_time
            
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

    async def handle_audio_stream_end(self, esp32_id: str):
        """Handle end of audio stream and calculate conversation time"""
        if esp32_id in self.conversation_timers:
            timer = self.conversation_timers[esp32_id]
            current_time = time.time()
            
            # Calculate conversation time for this chunk
            if timer['current_chunk_start'] is not None:
                chunk_duration = current_time - timer['current_chunk_start']
                timer['total_conversation_time'] += chunk_duration
                timer['current_chunk_start'] = None
                
                logger.debug(f"Conversation chunk for {esp32_id}: {chunk_duration:.1f} seconds")
                
                # Update database if we have an active learning session
                session = await self.cache_manager.get_session(esp32_id)
                if session and session.get('learning_session_id'):
                    await self.db_manager.update_session_conversation_time(
                        session['learning_session_id'], int(chunk_duration)
                    )
                    
                    # Update session cache with conversation time
                    session['conversation_time_this_session'] += int(chunk_duration)
                    await self.cache_manager.set_session(esp32_id, session)

    async def start_conversation_tracking(self, esp32_id: str):
        """Start tracking conversation time"""
        if esp32_id not in self.conversation_timers:
            self.conversation_timers[esp32_id] = {
                'last_audio_time': None,
                'session_start_time': time.time(),
                'total_conversation_time': 0,
                'current_chunk_start': None
            }
        
        timer = self.conversation_timers[esp32_id]
        timer['current_chunk_start'] = time.time()
        logger.debug(f"Started conversation tracking for {esp32_id}")

    async def end_conversation_tracking(self, esp32_id: str):
        """End conversation tracking and update database"""
        if esp32_id in self.conversation_timers:
            timer = self.conversation_timers[esp32_id]
            current_time = time.time()
            
            # Finalize current chunk if active
            if timer['current_chunk_start'] is not None:
                chunk_duration = current_time - timer['current_chunk_start']
                timer['total_conversation_time'] += chunk_duration
                timer['current_chunk_start'] = None
                
                # Update database
                session = await self.cache_manager.get_session(esp32_id)
                if session and session.get('learning_session_id'):
                    await self.db_manager.update_session_conversation_time(
                        session['learning_session_id'], int(chunk_duration)
                    )
            
            total_time = timer['total_conversation_time']
            logger.info(f"Total conversation time for {esp32_id}: {total_time:.1f} seconds")

    async def handle_realtime_message(self, esp32_id: str, message: Dict[str, Any]):
        """Handle messages from OpenAI Realtime API with enhanced tracking"""
        event_type = message.get('type')
        logger.debug(f"Realtime event for {esp32_id}: {event_type}")
        
        if event_type == 'session.created':
            logger.info(f"Realtime session created for {esp32_id}")
            
        elif event_type == 'response.audio.delta':
            # Audio chunk from assistant
            audio_data = message.get('delta')
            if audio_data:
                try:
                    # Decode base64 audio (24kHz from OpenAI)
                    audio_bytes_24khz = base64.b64decode(audio_data)
                    
                    # Convert from 24kHz to 16kHz for ESP32/Web client
                    audio_processor = AudioProcessor()
                    audio_bytes_16khz = audio_processor.convert_sample_rate(audio_bytes_24khz, 24000, 16000)
                    
                    # Send immediately to client
                    await self.ws_manager.send_audio(esp32_id, audio_bytes_16khz)
                    
                except Exception as e:
                    logger.error(f"Error processing audio for {esp32_id}: {e}")
                
        elif event_type == 'response.function_call_arguments.done':
            # Function call from agent
            await self.handle_function_call(esp32_id, message)
            
        elif event_type == 'response.done':
            # Response completed
            response = message.get('response', {})
            status = response.get('status')
            logger.info(f"Response completed for {esp32_id} with status: {status}")
            
            # Mark response as no longer active
            session = await self.cache_manager.get_session(esp32_id)
            if session:
                session['response_active'] = False
                session['audio_stream_active'] = False
                await self.cache_manager.set_session(esp32_id, session)
            
            # Clear the response generation flag
            connection = self.realtime_manager.get_connection(esp32_id)
            if connection:
                connection.is_generating_response = False
            
            # Send completion signal with session stats
            session_stats = await self._get_session_statistics(esp32_id)
            await self.ws_manager.send_message(esp32_id, {
                "type": "response_complete",
                "status": status,
                "session_stats": session_stats
            })
                
        elif event_type == 'error':
            error_info = message.get('error', {})
            logger.error(f"Realtime API error for {esp32_id}: {error_info}")

    async def _get_session_statistics(self, esp32_id: str) -> Dict[str, Any]:
        """Get current session statistics"""
        session = await self.cache_manager.get_session(esp32_id)
        timer = self.conversation_timers.get(esp32_id, {})
        
        return {
            "conversation_time_seconds": session.get('conversation_time_this_session', 0) if session else 0,
            "words_learned_this_session": len(session.get('words_learned_this_session', [])) if session else 0,
            "topics_covered": len(session.get('topics_covered_this_session', [])) if session else 0,
            "session_duration_seconds": int(time.time() - timer.get('session_start_time', time.time()))
        }

    async def handle_text_from_esp32(self, esp32_id: str, message: Dict[str, Any]):
        """Handle text messages from ESP32 with conversation tracking"""
        text = message.get('text', '')
        if text:
            logger.info(f"Text message from {esp32_id}: {text}")
            
            # Track text interaction as conversation time
            if esp32_id in self.conversation_timers:
                self.conversation_timers[esp32_id]['total_conversation_time'] += 3
                
                # Update database
                session = await self.cache_manager.get_session(esp32_id)
                if session and session.get('learning_session_id'):
                    await self.db_manager.update_session_conversation_time(
                        session['learning_session_id'], 3
                    )
            
            # Ensure conversation is active
            self.realtime_manager.start_conversation(esp32_id)
            
            # Send text as conversation item to OpenAI
            self.realtime_manager.send_event(esp32_id, {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}]
                }
            })
            
            # Create response to the text
            session = await self.cache_manager.get_session(esp32_id)
            if session and not session.get('response_active', False):
                session['response_active'] = True  
                await self.cache_manager.set_session(esp32_id, session)
                self.realtime_manager.create_response(esp32_id, ["text", "audio"])

    async def handle_heartbeat(self, esp32_id: str):
        """Handle heartbeat to keep connection alive"""
        connection = self.realtime_manager.get_connection(esp32_id)
        if connection:
            connection.update_activity()
            
        session = await self.cache_manager.get_session(esp32_id)
        if session:
            session['last_activity'] = datetime.utcnow().isoformat()
            await self.cache_manager.set_session(esp32_id, session)
        
        # Send heartbeat acknowledgment with session stats
        session_stats = await self._get_session_statistics(esp32_id)
        await self.ws_manager.send_message(esp32_id, {
            "type": "heartbeat_ack",
            "session_stats": session_stats
        })

    async def cleanup_connection(self, esp32_id: str):
        """Cleanup when ESP32 disconnects with final conversation time tracking"""
        logger.info(f"Cleaning up connection for {esp32_id}")
        
        try:
            # Finalize conversation time tracking
            await self.end_conversation_tracking(esp32_id)
            
            # Clean up conversation timer
            if esp32_id in self.conversation_timers:
                del self.conversation_timers[esp32_id]
        except Exception as e:
            logger.error(f"Error finalizing conversation tracking for {esp32_id}: {e}")
        
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