from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
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

@router.get("/users/{esp32_id}/progress")
async def get_user_progress(esp32_id: str, managers: Dict = Depends(get_managers)):
    """Get user progress for all episodes"""
    db_manager = managers['database']
    user = await db_manager.get_or_create_user(esp32_id)
    progress = await db_manager.get_user_progress(user.id)
    
    return {
        "user_id": user.id,
        "progress": [
            {
                "language": p.language,
                "season": p.season,
                "episode": p.episode,
                "completed": p.completed,
                "vocabulary_learned": p.vocabulary_learned,
                "completed_at": p.completed_at
            }
            for p in progress
        ]
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
async def get_available_episodes(managers: Dict = Depends(get_managers)):
    """Get all available episodes"""
    content_manager = managers['content']
    episodes = await content_manager.get_available_episodes("system")
    return {"episodes": episodes}

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
async def get_user_analytics(user_id: str, managers: Dict = Depends(get_managers)):
    """Get learning analytics for user"""
    db_manager = managers['database']
    
    # Get all progress
    progress = await db_manager.get_user_progress(user_id)
    
    # Calculate analytics
    total_episodes = len(progress)
    completed_episodes = len([p for p in progress if p.completed])
    total_vocabulary = sum(len(p.vocabulary_learned or []) for p in progress)
    
    # Group by language
    by_language = {}
    for p in progress:
        if p.language not in by_language:
            by_language[p.language] = {
                "total": 0,
                "completed": 0,
                "vocabulary": 0
            }
        by_language[p.language]["total"] += 1
        if p.completed:
            by_language[p.language]["completed"] += 1
        by_language[p.language]["vocabulary"] += len(p.vocabulary_learned or [])
    
    return {
        "user_id": user_id,
        "total_episodes": total_episodes,
        "completed_episodes": completed_episodes,
        "completion_rate": completed_episodes / total_episodes if total_episodes > 0 else 0,
        "total_vocabulary_learned": total_vocabulary,
        "by_language": by_language
    }

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "ESP32 Language Learning API"
    }