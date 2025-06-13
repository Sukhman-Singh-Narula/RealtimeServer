from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from app.models.schemas import UserResponse, EpisodeContent
from app.managers.database_manager import DatabaseManager
from app.managers.content_manager import ContentManager
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api"])

# These would be injected via dependency injection in main.py
async def get_managers():
    # Placeholder - actual implementation in main.py
    pass

@router.get("/users/{esp32_id}")
async def get_user(esp32_id: str, managers: Dict = Depends(get_managers)):
    """Get user information"""
    db_manager = managers['database']
    user = await db_manager.get_or_create_user(esp32_id)
    return UserResponse(
        id=user.id,
        esp32_id=user.esp32_id,
        created_at=user.created_at,
        last_active=user.last_active
    )

@router.get("/users/{esp32_id}/analytics")
async def get_user_analytics(esp32_id: str, managers: Dict = Depends(get_managers)):
    """Get comprehensive learning analytics for user"""
    db_manager = managers['database']
    user = await db_manager.get_or_create_user(esp32_id)
    analytics = await db_manager.get_user_learning_analytics(user.id)
    
    if not analytics:
        raise HTTPException(status_code=404, detail="Analytics not found")
    
    return analytics

@router.get("/users/{esp32_id}/progress")
async def get_user_progress(esp32_id: str, managers: Dict = Depends(get_managers)):
    """Get user progress for all episodes"""
    db_manager = managers['database']
    user = await db_manager.get_or_create_user(esp32_id)
    progress = await db_manager.get_user_progress(user.id)
    
    return {
        "user_id": user.id,
        "current_language": user.current_language,
        "current_season": user.current_season,
        "current_episode": user.current_episode,
        "total_conversation_time": user.total_conversation_time,
        "total_words_learned": user.total_words_learned,
        "total_topics_learned": user.total_topics_learned,
        "total_episodes_completed": user.total_episodes_completed,
        "progress": [
            {
                "language": p.language,
                "season": p.season,
                "episode": p.episode,
                "completed": p.completed,
                "vocabulary_learned": p.vocabulary_learned,
                "topics_learned": p.topics_learned,
                "completion_time": p.completion_time,
                "attempts": p.attempts,
                "completed_at": p.completed_at.isoformat() if p.completed_at else None,
                "started_at": p.started_at.isoformat() if p.started_at else None
            }
            for p in progress
        ]
    }

@router.get("/users/{esp32_id}/words")
async def get_user_words_learned(
    esp32_id: str, 
    language: Optional[str] = Query(None, description="Filter by language"),
    season: Optional[int] = Query(None, description="Filter by season"),
    episode: Optional[int] = Query(None, description="Filter by episode"),
    managers: Dict = Depends(get_managers)
):
    """Get words learned by user with optional filtering"""
    db_manager = managers['database']
    user = await db_manager.get_or_create_user(esp32_id)
    
    # This would require a new method in DatabaseManager
    # For now, we'll get it from the analytics
    analytics = await db_manager.get_user_learning_analytics(user.id)
    words_by_episode = analytics.get('words_learned_by_episode', {})
    
    # Filter results if parameters provided
    filtered_words = {}
    for episode_key, episode_data in words_by_episode.items():
        # Parse episode key like "spanish_S1E2"
        parts = episode_key.split('_')
        if len(parts) >= 2:
            ep_language = parts[0]
            season_episode = parts[1]  # Like "S1E2"
            
            # Extract season and episode numbers
            season_num = int(season_episode[1:season_episode.index('E')])
            episode_num = int(season_episode[season_episode.index('E')+1:])
            
            # Apply filters
            if language and ep_language != language:
                continue
            if season and season_num != season:
                continue
            if episode and episode_num != episode:
                continue
                
            filtered_words[episode_key] = episode_data
    
    return {
        "user_id": user.id,
        "total_words": sum(len(ep['words']) for ep in filtered_words.values()),
        "filters": {
            "language": language,
            "season": season,
            "episode": episode
        },
        "words_by_episode": filtered_words
    }

@router.get("/users/{esp32_id}/topics")
async def get_user_topics_learned(
    esp32_id: str,
    language: Optional[str] = Query(None, description="Filter by language"),
    season: Optional[int] = Query(None, description="Filter by season"),
    managers: Dict = Depends(get_managers)
):
    """Get topics learned by user with optional filtering"""
    db_manager = managers['database']
    user = await db_manager.get_or_create_user(esp32_id)
    
    analytics = await db_manager.get_user_learning_analytics(user.id)
    topics_by_episode = analytics.get('topics_learned_by_episode', {})
    
    # Filter results if parameters provided
    filtered_topics = {}
    for episode_key, episode_data in topics_by_episode.items():
        parts = episode_key.split('_')
        if len(parts) >= 2:
            ep_language = parts[0]
            season_episode = parts[1]
            season_num = int(season_episode[1:season_episode.index('E')])
            
            # Apply filters
            if language and ep_language != language:
                continue
            if season and season_num != season:
                continue
                
            filtered_topics[episode_key] = episode_data
    
    return {
        "user_id": user.id,
        "total_topics": sum(len(ep['topics']) for ep in filtered_topics.values()),
        "filters": {
            "language": language,
            "season": season
        },
        "topics_by_episode": filtered_topics
    }

@router.get("/users/{esp32_id}/daily-activity")
async def get_user_daily_activity(
    esp32_id: str,
    days: int = Query(30, description="Number of days to retrieve (max 90)"),
    managers: Dict = Depends(get_managers)
):
    """Get daily activity data for user"""
    if days > 90:
        days = 90
    
    db_manager = managers['database']
    user = await db_manager.get_or_create_user(esp32_id)
    
    analytics = await db_manager.get_user_learning_analytics(user.id)
    daily_activity = analytics.get('daily_activity', [])
    
    # Limit to requested number of days
    limited_activity = daily_activity[:days]
    
    # Calculate summary statistics
    total_session_time = sum(day['session_time_seconds'] for day in limited_activity)
    total_conversation_time = sum(day['conversation_time_seconds'] for day in limited_activity)
    total_sessions = sum(day['sessions_count'] for day in limited_activity)
    active_days = len([day for day in limited_activity if day['sessions_count'] > 0])
    
    return {
        "user_id": user.id,
        "period_days": days,
        "summary": {
            "active_days": active_days,
            "total_sessions": total_sessions,
            "total_session_time_seconds": total_session_time,
            "total_conversation_time_seconds": total_conversation_time,
            "average_session_time": total_session_time // total_sessions if total_sessions > 0 else 0,
            "average_daily_conversation_time": total_conversation_time // days if days > 0 else 0
        },
        "daily_activity": limited_activity
    }

@router.get("/users/{esp32_id}/curriculum-progress")
async def get_curriculum_progress(esp32_id: str, managers: Dict = Depends(get_managers)):
    """Get detailed curriculum progress including seasons and episodes"""
    db_manager = managers['database']
    user = await db_manager.get_or_create_user(esp32_id)
    
    analytics = await db_manager.get_user_learning_analytics(user.id)
    current_progress = analytics.get('current_progress', {})
    
    # Calculate detailed progress
    current_season = current_progress.get('season', 1)
    current_episode = current_progress.get('episode', 1)
    total_episodes_completed = current_progress.get('total_episodes_completed', 0)
    seasons_completed = current_progress.get('seasons_completed', 0)
    
    # Calculate progress within current season (7 episodes per season)
    episodes_in_current_season = (current_episode - 1) if current_episode > 1 else 0
    current_season_progress = episodes_in_current_season / 7.0
    
    # Calculate overall progress (assuming we track total available seasons)
    available_seasons = 5  # You might want to make this configurable
    total_available_episodes = available_seasons * 7
    overall_progress = total_episodes_completed / total_available_episodes
    
    return {
        "user_id": user.id,
        "language": current_progress.get('language', 'spanish'),
        "current_position": {
            "season": current_season,
            "episode": current_episode,
            "next_episode_title": await _get_next_episode_title(
                current_progress.get('language', 'spanish'), 
                current_season, 
                current_episode,
                managers
            )
        },
        "progress_statistics": {
            "seasons_completed": seasons_completed,
            "total_episodes_completed": total_episodes_completed,
            "current_season_progress": round(current_season_progress, 2),
            "overall_progress": round(overall_progress, 2),
            "episodes_in_current_season": episodes_in_current_season,
            "episodes_remaining_in_season": 7 - episodes_in_current_season
        },
        "unlocked_content": {
            "seasons": list(range(1, seasons_completed + 2)),  # Completed seasons + current
            "next_season_unlocked": current_season <= available_seasons
        }
    }

@router.get("/users/{esp32_id}/learning-streaks")
async def get_learning_streaks(esp32_id: str, managers: Dict = Depends(get_managers)):
    """Get learning streak information"""
    db_manager = managers['database']
    user = await db_manager.get_or_create_user(esp32_id)
    
    analytics = await db_manager.get_user_learning_analytics(user.id)
    current_streak = analytics.get('learning_statistics', {}).get('current_streak_days', 0)
    daily_activity = analytics.get('daily_activity', [])
    
    # Calculate longest streak
    longest_streak = _calculate_longest_streak(daily_activity)
    
    # Calculate weekly activity
    last_7_days = daily_activity[:7]
    active_days_this_week = len([day for day in last_7_days if day['sessions_count'] > 0])
    
    return {
        "user_id": user.id,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "this_week": {
            "active_days": active_days_this_week,
            "target_days": 7,
            "completion_rate": round(active_days_this_week / 7, 2)
        },
        "streak_milestones": {
            "next_milestone": _get_next_streak_milestone(current_streak),
            "achieved_milestones": _get_achieved_milestones(current_streak)
        }
    }

@router.post("/users/{esp32_id}/progress")
async def update_user_progress(
    esp32_id: str,
    language: str,
    season: int,
    episode: int,
    progress_data: dict,
    managers: Dict = Depends(get_managers)
):
    """Update user progress for specific episode"""
    db_manager = managers['database']
    user = await db_manager.get_or_create_user(esp32_id)
    progress = await db_manager.update_progress(
        user.id, language, season, episode, progress_data
    )
    return {"success": True, "progress_id": progress.id}

@router.get("/episodes/available")
async def get_available_episodes(
    language: Optional[str] = Query(None, description="Filter by language"),
    managers: Dict = Depends(get_managers)
):
    """Get all available episodes with filtering"""
    content_manager = managers['content']
    episodes = await content_manager.get_available_episodes("system")
    
    if language:
        episodes = [ep for ep in episodes if ep.get('language') == language]
    
    # Group episodes by season for better organization
    episodes_by_season = {}
    for episode in episodes:
        season = episode.get('season', 1)
        if season not in episodes_by_season:
            episodes_by_season[season] = []
        episodes_by_season[season].append(episode)
    
    return {
        "total_episodes": len(episodes),
        "episodes_by_season": episodes_by_season,
        "available_languages": list(set(ep.get('language') for ep in episodes))
    }

@router.get("/episodes/{language}/{season}/{episode}")
async def get_episode_details(
    language: str, 
    season: int, 
    episode: int,
    managers: Dict = Depends(get_managers)
):
    """Get specific episode details"""
    content_manager = managers['content']
    episode_data = await content_manager.get_episode(language, season, episode)
    if not episode_data:
        raise HTTPException(status_code=404, detail="Episode not found")
    return episode_data

@router.get("/analytics/user/{user_id}")
async def get_user_analytics_by_id(user_id: str, managers: Dict = Depends(get_managers)):
    """Get learning analytics for user by user ID"""
    db_manager = managers['database']
    analytics = await db_manager.get_user_learning_analytics(user_id)
    
    if not analytics:
        raise HTTPException(status_code=404, detail="User analytics not found")
    
    return analytics

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "ESP32 Language Learning API",
        "timestamp": datetime.utcnow().isoformat()
    }

# Helper functions

async def _get_next_episode_title(language: str, season: int, episode: int, managers: Dict) -> str:
    """Get the title of the next episode"""
    try:
        content_manager = managers['content']
        next_episode_data = await content_manager.get_episode(language, season, episode)
        return next_episode_data.title if next_episode_data else "Unknown Episode"
    except:
        return "Next Adventure"

def _calculate_longest_streak(daily_activity: List[Dict]) -> int:
    """Calculate the longest learning streak from daily activity"""
    if not daily_activity:
        return 0
    
    # Sort by date descending
    activities = sorted(daily_activity, key=lambda x: x['date'], reverse=True)
    
    longest_streak = 0
    current_streak = 0
    
    for activity in activities:
        if activity['sessions_count'] > 0:
            current_streak += 1
            longest_streak = max(longest_streak, current_streak)
        else:
            current_streak = 0
    
    return longest_streak

def _get_next_streak_milestone(current_streak: int) -> int:
    """Get the next streak milestone"""
    milestones = [3, 7, 14, 30, 50, 100]
    for milestone in milestones:
        if current_streak < milestone:
            return milestone
    return current_streak + 50  # Beyond 100, next milestone is +50

def _get_achieved_milestones(current_streak: int) -> List[int]:
    """Get list of achieved streak milestones"""
    milestones = [3, 7, 14, 30, 50, 100]
    return [m for m in milestones if current_streak >= m]