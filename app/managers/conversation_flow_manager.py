# app/managers/conversation_flow_manager.py - MULTI-USER CONVERSATION FLOW SYSTEM

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)

class ConversationState(Enum):
    """Different conversation states"""
    INITIALIZING = "initializing"
    CHOOSING_EPISODE = "choosing_episode"
    LEARNING = "learning"
    EPISODE_COMPLETE = "episode_complete"
    ERROR = "error"
    DISCONNECTED = "disconnected"

class UserConversationContext:
    """Context for a single user's conversation"""
    
    def __init__(self, esp32_id: str, user_id: str):
        self.esp32_id = esp32_id
        self.user_id = user_id
        self.state = ConversationState.INITIALIZING
        self.current_episode: Optional[Dict[str, Any]] = None
        self.next_episode: Optional[Dict[str, Any]] = None
        self.user_info: Dict[str, Any] = {"name": "friend", "age": 6}
        self.session_start_time = datetime.utcnow()
        self.words_learned_this_session: List[str] = []
        self.topics_covered_this_session: List[str] = []
        self.conversation_time = 0
        self.openai_session_id: Optional[str] = None
        self.last_activity = datetime.utcnow()
        self.error_count = 0
        
    def update_activity(self):
        """Update last activity timestamp"""
        self.last_activity = datetime.utcnow()
        
    def add_word_learned(self, word: str):
        """Add a word to the learned list"""
        if word not in self.words_learned_this_session:
            self.words_learned_this_session.append(word)
            
    def add_topic_covered(self, topic: str):
        """Add a topic to the covered list"""
        if topic not in self.topics_covered_this_session:
            self.topics_covered_this_session.append(topic)
            
    def get_session_stats(self) -> Dict[str, Any]:
        """Get session statistics"""
        duration = (datetime.utcnow() - self.session_start_time).total_seconds()
        return {
            "session_duration_seconds": int(duration),
            "words_learned": len(self.words_learned_this_session),
            "topics_covered": len(self.topics_covered_this_session),
            "conversation_time_seconds": self.conversation_time,
            "state": self.state.value,
            "error_count": self.error_count
        }

class ConversationFlowManager:
    """Manages conversation flow for multiple users simultaneously"""
    
    def __init__(self, database_manager, content_manager, cache_manager, realtime_manager):
        self.db_manager = database_manager
        self.content_manager = content_manager
        self.cache_manager = cache_manager
        self.realtime_manager = realtime_manager
        
        # Track active user conversations
        self.user_contexts: Dict[str, UserConversationContext] = {}
        
        logger.info("ConversationFlowManager initialized")
    
    async def start_user_conversation(self, esp32_id: str, websocket_handler) -> bool:
        """Start a conversation for a new user"""
        try:
            logger.info(f"Starting conversation for user {esp32_id}")
            
            # Get or create user
            user = await self.db_manager.get_or_create_user(esp32_id)
            
            # Create conversation context
            context = UserConversationContext(esp32_id, user.id)
            self.user_contexts[esp32_id] = context
            
            # Get user profile/info for personalization
            context.user_info = await self._get_user_personalization(esp32_id)
            
            # Get user's next episode
            next_episode = await self._get_next_episode_for_user(user)
            if not next_episode:
                logger.error(f"No episodes available for user {esp32_id}")
                await self._handle_no_episodes(esp32_id, websocket_handler)
                return False
            
            context.next_episode = next_episode
            context.state = ConversationState.CHOOSING_EPISODE
            
            # Create OpenAI Realtime connection
            openai_connection = await self.realtime_manager.create_connection(
                esp32_id,
                lambda msg: self._handle_openai_message(esp32_id, msg, websocket_handler)
            )
            
            if not openai_connection:
                logger.error(f"Failed to create OpenAI connection for {esp32_id}")
                context.state = ConversationState.ERROR
                return False
            
            context.openai_session_id = openai_connection.session_id
            
            # Configure initial conversation agent (Choice Agent)
            await self._configure_choice_agent(esp32_id, next_episode)
            
            # Send welcome message
            await self._send_welcome_message(esp32_id, websocket_handler)
            
            # Start the conversation
            self.realtime_manager.start_conversation(esp32_id)
            
            logger.info(f"Conversation started successfully for {esp32_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start conversation for {esp32_id}: {e}")
            if esp32_id in self.user_contexts:
                self.user_contexts[esp32_id].state = ConversationState.ERROR
                self.user_contexts[esp32_id].error_count += 1
            return False
    
    async def _get_user_personalization(self, esp32_id: str) -> Dict[str, Any]:
        """Get user personalization info"""
        try:
            # Try to get from profile manager if available
            # For now, use default values
            return {
                "name": "friend",
                "age": 6,
                "preferred_language": "spanish",
                "learning_style": "mixed"
            }
        except Exception as e:
            logger.warning(f"Could not get user personalization for {esp32_id}: {e}")
            return {"name": "friend", "age": 6}
    
    async def _get_next_episode_for_user(self, user) -> Optional[Dict[str, Any]]:
        """Get the next episode for the user"""
        try:
            user_progress = {
                'current_language': user.current_language,
                'current_season': user.current_season,
                'current_episode': user.current_episode
            }
            
            return await self.content_manager.get_next_episode_for_user(user.id, user_progress)
        except Exception as e:
            logger.error(f"Error getting next episode for user {user.id}: {e}")
            return None
    
    async def _configure_choice_agent(self, esp32_id: str, episode_info: Dict[str, Any]):
        """Configure the Choice Agent for episode selection"""
        try:
            context = self.user_contexts.get(esp32_id)
            if not context:
                return
            
            # Import agent configs
            from app.agents.agent_configs import get_choice_agent_config
            
            # Generate choice agent configuration
            choice_config = get_choice_agent_config(episode_info, context.user_info)
            
            # Update OpenAI session
            self.realtime_manager.update_session(
                esp32_id,
                instructions=choice_config['instructions'],
                voice=choice_config['voice'],
                tools=choice_config['tools']
            )
            
            logger.info(f"Choice agent configured for {esp32_id}")
            
        except Exception as e:
            logger.error(f"Error configuring choice agent for {esp32_id}: {e}")
    
    async def _configure_episode_agent(self, esp32_id: str, episode_info: Dict[str, Any]):
        """Configure the Episode Agent for learning"""
        try:
            context = self.user_contexts.get(esp32_id)
            if not context:
                return
            
            # Import agent configs
            from app.agents.agent_configs import get_episode_agent_config
            
            # Generate episode agent configuration
            episode_config = get_episode_agent_config(episode_info, context.user_info)
            
            # Update OpenAI session
            self.realtime_manager.update_session(
                esp32_id,
                instructions=episode_config['instructions'],
                voice=episode_config['voice'],
                tools=episode_config['tools']
            )
            
            logger.info(f"Episode agent configured for {esp32_id}")
            
        except Exception as e:
            logger.error(f"Error configuring episode agent for {esp32_id}: {e}")
    
    async def _send_welcome_message(self, esp32_id: str, websocket_handler):
        """Send personalized welcome message"""
        try:
            context = self.user_contexts.get(esp32_id)
            if not context:
                return
            
            # Get user analytics for personalized welcome
            try:
                analytics = await self.db_manager.get_user_learning_analytics(context.user_id)
                learning_stats = analytics.get('learning_statistics', {}) if analytics else {}
            except:
                learning_stats = {}
            
            # Create welcome message
            welcome_message = self._create_personalized_welcome(context, learning_stats)
            
            # Send to user
            await websocket_handler.send_message(esp32_id, {
                "type": "connected",
                "user_id": context.user_id,
                "message": welcome_message,
                "next_episode": {
                    "title": context.next_episode['title'],
                    "language": context.next_episode['language'],
                    "season": context.next_episode['season'],
                    "episode": context.next_episode['episode']
                },
                "analytics": {
                    "total_words_learned": learning_stats.get('total_words_learned', 0),
                    "total_episodes_completed": learning_stats.get('total_episodes_completed', 0),
                    "current_streak": learning_stats.get('current_streak_days', 0)
                }
            })
            
        except Exception as e:
            logger.error(f"Error sending welcome message to {esp32_id}: {e}")
    
    def _create_personalized_welcome(self, context: UserConversationContext, learning_stats: Dict) -> str:
        """Create personalized welcome message based on user progress"""
        user_name = context.user_info.get('name', 'friend')
        total_words = learning_stats.get('total_words_learned', 0)
        total_episodes = learning_stats.get('total_episodes_completed', 0)
        current_streak = learning_stats.get('current_streak_days', 0)
        
        if total_episodes == 0:
            return f"Hola {user_name}! Welcome to your Spanish learning adventure! I'm Lingo, and I'm so excited to help you learn!"
        elif total_episodes < 5:
            return f"Welcome back {user_name}! You've learned {total_words} words so far - that's amazing! Ready for more Spanish fun?"
        elif current_streak > 0:
            return f"Fantastico {user_name}! You're on a {current_streak}-day learning streak and have learned {total_words} words! Let's keep it going!"
        else:
            episode_title = context.next_episode.get('title', 'your next adventure')
            return f"Welcome back, Spanish superstar {user_name}! Your next adventure '{episode_title}' is ready!"
    
    async def _handle_openai_message(self, esp32_id: str, message: Dict[str, Any], websocket_handler):
        """Handle messages from OpenAI Realtime API"""
        try:
            context = self.user_contexts.get(esp32_id)
            if not context:
                return
            
            context.update_activity()
            event_type = message.get('type')
            
            if event_type == 'response.audio.delta':
                # Forward audio to user
                audio_data = message.get('delta')
                if audio_data:
                    await self._forward_audio_to_user(esp32_id, audio_data, websocket_handler)
                    
            elif event_type == 'response.function_call_arguments.done':
                # Handle function calls from agents
                await self._handle_agent_function_call(esp32_id, message, websocket_handler)
                
            elif event_type == 'response.done':
                # Response completed
                await self._handle_response_complete(esp32_id, message, websocket_handler)
                
            elif event_type == 'error':
                # Handle OpenAI errors
                await self._handle_openai_error(esp32_id, message, websocket_handler)
                
        except Exception as e:
            logger.error(f"Error handling OpenAI message for {esp32_id}: {e}")
            if esp32_id in self.user_contexts:
                self.user_contexts[esp32_id].error_count += 1
    
    async def _forward_audio_to_user(self, esp32_id: str, audio_data: str, websocket_handler):
        """Forward audio from OpenAI to user"""
        try:
            import base64
            from app.utils.audio import AudioProcessor
            
            # Decode and convert audio
            audio_bytes_24khz = base64.b64decode(audio_data)
            audio_processor = AudioProcessor()
            audio_bytes_16khz = audio_processor.convert_sample_rate(audio_bytes_24khz, 24000, 16000)
            
            # Send to user
            await websocket_handler.send_audio(esp32_id, audio_bytes_16khz)
            
        except Exception as e:
            logger.error(f"Error forwarding audio to {esp32_id}: {e}")
    
    async def _handle_agent_function_call(self, esp32_id: str, message: Dict[str, Any], websocket_handler):
        """Handle function calls from agents"""
        try:
            call_id = message.get('call_id')
            name = message.get('name')
            arguments = message.get('arguments', '{}')
            
            try:
                args = json.loads(arguments)
            except:
                args = {}
            
            logger.info(f"Function call from {esp32_id}: {name}({args})")
            
            # Handle the function call
            result = await self._execute_agent_function(esp32_id, name, args, websocket_handler)
            
            # Send result back to OpenAI
            self.realtime_manager.send_event(esp32_id, {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result)
                }
            })
            
            # Create response
            self.realtime_manager.create_response(esp32_id)
            
        except Exception as e:
            logger.error(f"Error handling function call for {esp32_id}: {e}")
    
    async def _execute_agent_function(self, esp32_id: str, function_name: str, args: Dict[str, Any], websocket_handler) -> Dict[str, Any]:
        """Execute agent function calls"""
        try:
            context = self.user_contexts.get(esp32_id)
            if not context:
                return {"error": "No user context found"}
            
            # Import tool handlers
            from app.agents.agent_tools import TOOL_HANDLERS
            
            if function_name in TOOL_HANDLERS:
                handler = TOOL_HANDLERS[function_name]
                
                # Create managers dict for the handler
                managers = {
                    'database': self.db_manager,
                    'cache': self.cache_manager,
                    'content': self.content_manager,
                    'realtime': self.realtime_manager,
                    'websocket': websocket_handler
                }
                
                result = await handler(args, esp32_id, managers)
                
                # Handle specific function results
                if function_name == 'start_episode' and result.get('success'):
                    await self._transition_to_learning(esp32_id, result.get('episode'), websocket_handler)
                    
                elif function_name == 'complete_episode' and result.get('success'):
                    await self._handle_episode_completion(esp32_id, result, websocket_handler)
                    
                elif function_name == 'mark_vocabulary_learned' and result.get('success'):
                    context.add_word_learned(args.get('word'))
                
                return result
            else:
                return {"error": f"Unknown function: {function_name}"}
                
        except Exception as e:
            logger.error(f"Error executing function {function_name} for {esp32_id}: {e}")
            return {"error": f"Function execution failed: {str(e)}"}
    
    async def _transition_to_learning(self, esp32_id: str, episode_data: Dict[str, Any], websocket_handler):
        """Transition user from choosing to learning state"""
        try:
            context = self.user_contexts.get(esp32_id)
            if not context:
                return
            
            logger.info(f"Transitioning {esp32_id} to learning: {episode_data['title']}")
            
            context.state = ConversationState.LEARNING
            context.current_episode = episode_data
            
            # Configure episode agent
            await self._configure_episode_agent(esp32_id, episode_data)
            
            # Update session cache
            await self.cache_manager.update_agent_state(esp32_id, "LEARNING", "episode_agent")
            
            # Send transition message
            await websocket_handler.send_message(esp32_id, {
                "type": "episode_started",
                "episode": episode_data,
                "message": f"Let's start learning with '{episode_data['title']}'!"
            })
            
        except Exception as e:
            logger.error(f"Error transitioning to learning for {esp32_id}: {e}")
    
    async def _handle_episode_completion(self, esp32_id: str, result: Dict[str, Any], websocket_handler):
        """Handle episode completion"""
        try:
            context = self.user_contexts.get(esp32_id)
            if not context:
                return
            
            logger.info(f"Episode completed for {esp32_id}")
            
            context.state = ConversationState.EPISODE_COMPLETE
            
            # Get next episode for transition back to choice
            user = await self.db_manager.get_or_create_user(esp32_id)
            next_episode = await self._get_next_episode_for_user(user)
            
            if next_episode:
                context.next_episode = next_episode
                context.state = ConversationState.CHOOSING_EPISODE
                
                # Configure choice agent for next episode
                await self._configure_choice_agent(esp32_id, next_episode)
                
                # Send completion message
                await websocket_handler.send_message(esp32_id, {
                    "type": "episode_completed",
                    "message": f"Episode completed! Ready for your next adventure: '{next_episode['title']}'?",
                    "next_episode": next_episode,
                    "stats": context.get_session_stats()
                })
            else:
                # No more episodes
                await websocket_handler.send_message(esp32_id, {
                    "type": "all_episodes_completed",
                    "message": "Congratulations! You've completed all available episodes!",
                    "stats": context.get_session_stats()
                })
                
        except Exception as e:
            logger.error(f"Error handling episode completion for {esp32_id}: {e}")
    
    async def _handle_response_complete(self, esp32_id: str, message: Dict[str, Any], websocket_handler):
        """Handle response completion"""
        try:
            context = self.user_contexts.get(esp32_id)
            if not context:
                return
            
            # Send completion signal with stats
            await websocket_handler.send_message(esp32_id, {
                "type": "response_complete",
                "stats": context.get_session_stats()
            })
            
        except Exception as e:
            logger.error(f"Error handling response complete for {esp32_id}: {e}")
    
    async def _handle_openai_error(self, esp32_id: str, message: Dict[str, Any], websocket_handler):
        """Handle OpenAI API errors"""
        try:
            context = self.user_contexts.get(esp32_id)
            if context:
                context.error_count += 1
                context.state = ConversationState.ERROR
            
            error_info = message.get('error', {})
            logger.error(f"OpenAI API error for {esp32_id}: {error_info}")
            
            await websocket_handler.send_message(esp32_id, {
                "type": "ai_error",
                "message": "I'm having trouble right now. Let me try again.",
                "error": error_info.get('message', 'Unknown error')
            })
            
        except Exception as e:
            logger.error(f"Error handling OpenAI error for {esp32_id}: {e}")
    
    async def _handle_no_episodes(self, esp32_id: str, websocket_handler):
        """Handle case when no episodes are available"""
        try:
            await websocket_handler.send_message(esp32_id, {
                "type": "no_episodes",
                "message": "No learning content available right now. Please try again later."
            })
            
        except Exception as e:
            logger.error(f"Error handling no episodes for {esp32_id}: {e}")
    
    async def handle_user_audio(self, esp32_id: str, audio_data: bytes):
        """Handle audio input from user"""
        try:
            context = self.user_contexts.get(esp32_id)
            if not context:
                logger.warning(f"No context found for audio from {esp32_id}")
                return
            
            context.update_activity()
            
            # Send audio to OpenAI
            self.realtime_manager.send_audio(esp32_id, audio_data)
            
        except Exception as e:
            logger.error(f"Error handling user audio for {esp32_id}: {e}")
    
    async def end_user_conversation(self, esp32_id: str):
        """End conversation for a user"""
        try:
            context = self.user_contexts.get(esp32_id)
            if context:
                context.state = ConversationState.DISCONNECTED
                logger.info(f"Ending conversation for {esp32_id} - Duration: {context.get_session_stats()['session_duration_seconds']}s")
            
            # Close OpenAI connection
            self.realtime_manager.close_connection(esp32_id)
            
            # Remove from active contexts
            if esp32_id in self.user_contexts:
                del self.user_contexts[esp32_id]
                
        except Exception as e:
            logger.error(f"Error ending conversation for {esp32_id}: {e}")
    
    def get_user_context(self, esp32_id: str) -> Optional[UserConversationContext]:
        """Get user conversation context"""
        return self.user_contexts.get(esp32_id)
    
    def get_active_conversations(self) -> Dict[str, Dict[str, Any]]:
        """Get all active conversations"""
        return {
            esp32_id: {
                "state": context.state.value,
                "user_id": context.user_id,
                "session_duration": context.get_session_stats()['session_duration_seconds'],
                "words_learned": len(context.words_learned_this_session),
                "current_episode": context.current_episode['title'] if context.current_episode else None,
                "last_activity": context.last_activity.isoformat()
            }
            for esp32_id, context in self.user_contexts.items()
        }