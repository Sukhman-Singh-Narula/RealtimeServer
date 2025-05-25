from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)

async def handle_select_episode(args: Dict[str, Any], esp32_id: str, managers: Dict[str, Any]) -> Dict[str, Any]:
    """Handle episode selection from Choice Agent"""
    language = args.get('language')
    season = args.get('season')
    episode = args.get('episode')
    title = args.get('title', '')
    
    logger.info(f"Episode selected: {language} S{season}E{episode} - {title}")
    
    # Get episode content
    episode_data = await managers['content'].get_episode(language, season, episode)
    if not episode_data:
        return {
            "success": False,
            "error": "Episode not found"
        }
    
    # Update session in cache
    session = await managers['cache'].get_session(esp32_id)
    if session:
        session['current_episode'] = episode_data.dict()
        session['agent_state'] = 'LEARNING'
        await managers['cache'].set_session(esp32_id, session)
    
    # Create learning session in database
    user_id = session.get('user_id')
    if user_id:
        learning_session = await managers['database'].create_session(
            user_id, episode_data.dict()
        )
        session['learning_session_id'] = learning_session.id
        await managers['cache'].set_session(esp32_id, session)
    
    return {
        "success": True,
        "episode": episode_data.dict(),
        "message": f"Great choice! Let's start learning {language} with '{title}'!"
    }

async def handle_mark_vocabulary_learned(args: Dict[str, Any], esp32_id: str, 
                                        managers: Dict[str, Any]) -> Dict[str, Any]:
    """Handle vocabulary learning progress"""
    word = args.get('word')
    confidence = args.get('confidence')
    
    # Update session with vocabulary progress
    session = await managers['cache'].get_session(esp32_id)
    if session:
        if 'vocabulary_progress' not in session:
            session['vocabulary_progress'] = {}
        session['vocabulary_progress'][word] = confidence
        await managers['cache'].set_session(esp32_id, session)
    
    return {
        "success": True,
        "word": word,
        "confidence": confidence
    }

async def handle_complete_episode(args: Dict[str, Any], esp32_id: str, 
                                 managers: Dict[str, Any]) -> Dict[str, Any]:
    """Handle episode completion"""
    words_learned = args.get('words_learned', [])
    completion_time = args.get('completion_time', 0)
    
    session = await managers['cache'].get_session(esp32_id)
    if not session:
        return {"success": False, "error": "No active session"}
    
    user_id = session.get('user_id')
    episode = session.get('current_episode')
    
    if user_id and episode:
        # Update progress in database
        progress_data = {
            "completed": True,
            "words_learned": words_learned,
            "completion_time": completion_time,
            "vocabulary_progress": session.get('vocabulary_progress', {})
        }
        
        await managers['database'].update_progress(
            user_id,
            episode['language'],
            episode['season'],
            episode['episode'],
            progress_data
        )
        
        # End learning session
        learning_session_id = session.get('learning_session_id')
        if learning_session_id:
            await managers['database'].end_session(learning_session_id)
    
    # Clear episode from session
    session['current_episode'] = None
    session['vocabulary_progress'] = {}
    session['agent_state'] = 'CHOOSING'
    await managers['cache'].set_session(esp32_id, session)
    
    return {
        "success": True,
        "words_learned": words_learned,
        "message": "Congratulations! You completed the episode!"
    }

# Tool handler mapping
TOOL_HANDLERS = {
    "select_episode": handle_select_episode,
    "mark_vocabulary_learned": handle_mark_vocabulary_learned,
    "complete_episode": handle_complete_episode
}