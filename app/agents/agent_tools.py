from typing import Dict, Any, List
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

async def handle_start_episode(args: Dict[str, Any], esp32_id: str, managers: Dict[str, Any]) -> Dict[str, Any]:
    """Handle episode start from Choice Agent - simplified version"""
    ready = args.get('ready', False)
    user_message = args.get('user_message', '')
    
    logger.info(f"Episode start requested for {esp32_id}, ready: {ready}")
    
    if not ready:
        return {
            "success": False,
            "message": "User not ready yet, continue conversation"
        }
    
    # Get session to find the next episode
    session = await managers['cache'].get_session(esp32_id)
    if not session:
        return {
            "success": False,
            "error": "No active session"
        }
    
    user_id = session.get('user_id')
    if not user_id:
        return {
            "success": False,
            "error": "No user ID in session"
        }
    
    # Get user progress to determine next episode
    try:
        # Get user data from database
        user = await managers['database'].get_or_create_user(esp32_id)
        user_progress = {
            'current_language': user.current_language,
            'current_season': user.current_season,
            'current_episode': user.current_episode
        }
        
        # Get the next episode data (including prompts)
        next_episode = await managers['content'].get_next_episode_for_user(user_id, user_progress)
        
        if not next_episode:
            return {
                "success": False,
                "error": "No next episode found"
            }
        
        # Update session with episode data
        session['current_episode'] = next_episode
        session['agent_state'] = 'LEARNING'
        session['episode_start_time'] = datetime.utcnow().isoformat()
        await managers['cache'].set_session(esp32_id, session)
        
        # Create learning session in database
        learning_session = await managers['database'].create_session(
            user_id, next_episode
        )
        session['learning_session_id'] = learning_session.id
        await managers['cache'].set_session(esp32_id, session)
        
        return {
            "success": True,
            "episode": next_episode,
            "message": f"Starting {next_episode['title']}! Get ready to learn!"
        }
        
    except Exception as e:
        logger.error(f"Error starting episode for {esp32_id}: {e}")
        return {
            "success": False,
            "error": f"Failed to start episode: {str(e)}"
        }

async def handle_mark_vocabulary_learned(args: Dict[str, Any], esp32_id: str, 
                                        managers: Dict[str, Any]) -> Dict[str, Any]:
    """Handle vocabulary learning progress with comprehensive tracking"""
    word = args.get('word')
    confidence = args.get('confidence', 'medium')
    
    logger.info(f"Word learned: {word} with confidence: {confidence}")
    
    # Update session with vocabulary progress
    session = await managers['cache'].get_session(esp32_id)
    if not session:
        return {"success": False, "error": "No active session"}
    
    # Update vocabulary progress in session
    if 'vocabulary_progress' not in session:
        session['vocabulary_progress'] = {}
    session['vocabulary_progress'][word] = confidence
    await managers['cache'].set_session(esp32_id, session)
    
    # Get current episode info
    current_episode = session.get('current_episode')
    user_id = session.get('user_id')
    
    if user_id and current_episode:
        # Get translation for the word
        translations = current_episode.get('vocabulary_translations', {})
        translation = translations.get(word, word)
        
        # Add word to learning tracking
        word_learned = await managers['database'].add_word_learned(
            user_id=user_id,
            word=word,
            language=current_episode['language'],
            season=current_episode['season'],
            episode=current_episode['episode'],
            episode_title=current_episode['title'],
            confidence=confidence,
            context=current_episode['story_context'],
            translation=translation
        )
        
        # Update conversation time tracking
        learning_session_id = session.get('learning_session_id')
        if learning_session_id:
            # Add 10 seconds of conversation time for learning a word
            await managers['database'].update_session_conversation_time(
                learning_session_id, 10
            )
    
    return {
        "success": True,
        "word": word,
        "confidence": confidence,
        "translation": translation if 'translation' in locals() else None,
        "message": f"Great job learning '{word}'!"
    }

async def handle_complete_episode(args: Dict[str, Any], esp32_id: str, 
                                 managers: Dict[str, Any]) -> Dict[str, Any]:
    """Handle episode completion with comprehensive analytics tracking"""
    words_learned = args.get('words_learned', [])
    completion_time = args.get('completion_time', 0)
    
    logger.info(f"Episode completed with {len(words_learned)} words learned")
    
    session = await managers['cache'].get_session(esp32_id)
    if not session:
        return {"success": False, "error": "No active session"}
    
    user_id = session.get('user_id')
    episode = session.get('current_episode')
    
    if not user_id or not episode:
        return {"success": False, "error": "Missing user or episode data"}
    
    # Calculate actual completion time if not provided
    if completion_time == 0 and 'episode_start_time' in session:
        start_time = datetime.fromisoformat(session['episode_start_time'])
        completion_time = int((datetime.utcnow() - start_time).total_seconds())
    
    # Get learning objectives (topics) from episode
    topics_learned = episode.get('learning_objectives', [])
    
    # Track topics learned in database
    for topic in topics_learned:
        await managers['database'].add_topic_learned(
            user_id=user_id,
            topic=topic,
            language=episode['language'],
            season=episode['season'],
            episode=episode['episode'],
            episode_title=episode['title'],
            words_in_topic=words_learned,
            mastery_level="introduced"
        )
    
    # Mark episode as completed in database
    progress = await managers['database'].complete_episode(
        user_id=user_id,
        language=episode['language'],
        season=episode['season'],
        episode=episode['episode'],
        words_learned=words_learned,
        topics_learned=topics_learned,
        completion_time=completion_time
    )
    
    # End learning session
    learning_session_id = session.get('learning_session_id')
    if learning_session_id:
        ended_session = await managers['database'].end_session(learning_session_id)
        if ended_session:
            total_conversation_time = ended_session.conversation_time
            logger.info(f"Session ended with {total_conversation_time} seconds of conversation")
    
    # Get updated user analytics
    analytics = await managers['database'].get_user_learning_analytics(user_id)
    current_progress = analytics.get('current_progress', {})
    learning_stats = analytics.get('learning_statistics', {})
    
    # Clear episode from session and prepare for next choice
    session['current_episode'] = None
    session['vocabulary_progress'] = {}
    session['agent_state'] = 'CHOOSING'
    session['episode_start_time'] = None
    await managers['cache'].set_session(esp32_id, session)
    
    # Create celebration message
    celebration_message = _create_celebration_message(
        words_learned, topics_learned, current_progress, learning_stats
    )
    
    return {
        "success": True,
        "words_learned": words_learned,
        "topics_learned": topics_learned,
        "completion_time_seconds": completion_time,
        "current_season": current_progress.get('season', 1),
        "current_episode": current_progress.get('episode', 1),
        "total_words_learned": learning_stats.get('total_words_learned', 0),
        "total_topics_learned": learning_stats.get('total_topics_learned', 0),
        "total_episodes_completed": learning_stats.get('total_episodes_completed', 0),
        "message": celebration_message,
        "return_to_choice": True  # Signal to return to choice agent
    }

async def handle_practice_word(args: Dict[str, Any], esp32_id: str, 
                              managers: Dict[str, Any]) -> Dict[str, Any]:
    """Handle word practice sessions"""
    word = args.get('word')
    success = args.get('success', True)
    attempts = args.get('attempts', 1)
    
    session = await managers['cache'].get_session(esp32_id)
    if not session:
        return {"success": False, "error": "No active session"}
    
    user_id = session.get('user_id')
    learning_session_id = session.get('learning_session_id')
    
    if user_id and learning_session_id:
        # Update conversation time for practice
        conversation_time = 5 * attempts  # 5 seconds per attempt
        await managers['database'].update_session_conversation_time(
            learning_session_id, conversation_time
        )
        
        # Update word confidence based on practice success
        if success:
            confidence = "high" if attempts == 1 else "medium"
        else:
            confidence = "low"
        
        # Get current episode info for updating word record
        current_episode = session.get('current_episode')
        if current_episode:
            await managers['database'].add_word_learned(
                user_id=user_id,
                word=word,
                language=current_episode['language'],
                season=current_episode['season'],
                episode=current_episode['episode'],
                episode_title=current_episode['title'],
                confidence=confidence
            )
    
    return {
        "success": True,
        "word": word,
        "practice_success": success,
        "attempts": attempts,
        "message": f"Good practice with '{word}'!" if success else f"Keep trying with '{word}' - you're doing great!"
    }

def _create_celebration_message(words_learned: List[str], topics_learned: List[str], 
                               current_progress: Dict, learning_stats: Dict) -> str:
    """Create a celebration message with achievements"""
    message_parts = ["🎉 ¡Fantástico! You completed the episode!"]
    
    # Words achievement
    if words_learned:
        message_parts.append(f"✨ You learned {len(words_learned)} new Spanish words!")
        
    # Topics achievement
    if topics_learned:
        message_parts.append(f"📚 You mastered {len(topics_learned)} learning skills!")
    
    # Progress achievement
    current_episode = current_progress.get('episode', 1)
    current_season = current_progress.get('season', 1)
    
    if current_episode == 1 and current_season > 1:
        message_parts.append(f"🌟 ¡Increíble! You've unlocked Season {current_season}!")
    
    # Milestone achievements
    total_words = learning_stats.get('total_words_learned', 0)
    total_episodes = learning_stats.get('total_episodes_completed', 0)
    
    if total_words >= 50 and total_words < 60:
        message_parts.append("🏆 ¡Wow! You've learned 50+ Spanish words!")
    elif total_words >= 100 and total_words < 110:
        message_parts.append("🏆 ¡Increíble! You've learned 100+ Spanish words!")
    
    if total_episodes >= 5 and total_episodes < 10:
        message_parts.append("📖 ¡Excelente! You've completed 5+ episodes!")
    elif total_episodes >= 7 and total_episodes < 14:
        message_parts.append("📖 ¡Fantástico! You completed a whole season!")
    
    message_parts.append("Ready for your next Spanish adventure? 🚀")
    
    return " ".join(message_parts)

# Updated tool handler mapping with simplified functions
TOOL_HANDLERS = {
    "start_episode": handle_start_episode,  # New simplified function
    "mark_vocabulary_learned": handle_mark_vocabulary_learned,
    "complete_episode": handle_complete_episode,
    "practice_word": handle_practice_word,
    
    # Legacy support (can be removed later)
    "select_episode": handle_start_episode  # Map old function to new one
}