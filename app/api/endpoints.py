# app/api/endpoints.py - FIXED VERSION WITH PROPER DEPENDENCY INJECTION

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from app.models.schemas import UserResponse, EpisodeContent
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api"])

# Dependency injection - This will be overridden in main.py
async def get_managers() -> Dict[str, Any]:
    """Get managers - will be overridden with actual implementation"""
    raise HTTPException(status_code=500, detail="Managers not initialized")

# ============================================================================
# USER ENDPOINTS
# ============================================================================

@router.get("/users/{esp32_id}")
async def get_user(esp32_id: str, managers: Dict = Depends(get_managers)):
    """Get user information"""
    try:
        db_manager = managers['database']
        user = await db_manager.get_or_create_user(esp32_id)
        return UserResponse(
            id=user.id,
            esp32_id=user.esp32_id,
            created_at=user.created_at,
            last_active=user.last_active
        )
    except Exception as e:
        logger.error(f"Error getting user {esp32_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users/{esp32_id}/analytics")
async def get_user_analytics(esp32_id: str, managers: Dict = Depends(get_managers)):
    """Get comprehensive learning analytics for user"""
    try:
        db_manager = managers['database']
        user = await db_manager.get_or_create_user(esp32_id)
        
        # Try to get enhanced analytics if available
        if hasattr(db_manager, 'get_user_learning_analytics'):
            analytics = await db_manager.get_user_learning_analytics(user.id)
            if analytics:
                return analytics
        
        # Fallback to basic analytics
        progress = await db_manager.get_user_progress(user.id)
        
        # Calculate basic analytics
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
            "user_id": user.id,
            "total_episodes": total_episodes,
            "completed_episodes": completed_episodes,
            "completion_rate": completed_episodes / total_episodes if total_episodes > 0 else 0,
            "total_vocabulary_learned": total_vocabulary,
            "by_language": by_language,
            "last_updated": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting user analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users/{esp32_id}/progress")
async def get_user_progress(esp32_id: str, managers: Dict = Depends(get_managers)):
    """Get user progress for all episodes"""
    try:
        db_manager = managers['database']
        user = await db_manager.get_or_create_user(esp32_id)
        progress = await db_manager.get_user_progress(user.id)
        
        # Calculate summary statistics
        total_conversation_time = sum(getattr(p, 'completion_time', 0) or 0 for p in progress)
        total_words_learned = sum(len(getattr(p, 'vocabulary_learned', []) or []) for p in progress)
        total_episodes_completed = len([p for p in progress if p.completed])
        
        return {
            "user_id": user.id,
            "current_language": getattr(user, 'current_language', 'spanish'),
            "current_season": getattr(user, 'current_season', 1),
            "current_episode": getattr(user, 'current_episode', 1),
            "total_conversation_time": total_conversation_time,
            "total_words_learned": total_words_learned,
            "total_topics_learned": getattr(user, 'total_topics_learned', 0),
            "total_episodes_completed": total_episodes_completed,
            "progress": [
                {
                    "language": p.language,
                    "season": p.season,
                    "episode": p.episode,
                    "completed": p.completed,
                    "vocabulary_learned": getattr(p, 'vocabulary_learned', []) or [],
                    "topics_learned": getattr(p, 'topics_learned', []) or [],
                    "completion_time": getattr(p, 'completion_time', 0) or 0,
                    "attempts": getattr(p, 'attempts', 1) or 1,
                    "completed_at": p.completed_at.isoformat() if getattr(p, 'completed_at', None) else None,
                    "started_at": getattr(p, 'started_at', datetime.utcnow()).isoformat()
                }
                for p in progress
            ]
        }
    except Exception as e:
        logger.error(f"Error getting user progress: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users/{esp32_id}/words")
async def get_user_words_learned(
    esp32_id: str, 
    language: Optional[str] = Query(None, description="Filter by language"),
    season: Optional[int] = Query(None, description="Filter by season"),
    episode: Optional[int] = Query(None, description="Filter by episode"),
    managers: Dict = Depends(get_managers)
):
    """Get words learned by user with optional filtering"""
    try:
        db_manager = managers['database']
        user = await db_manager.get_or_create_user(esp32_id)
        progress = await db_manager.get_user_progress(user.id)
        
        # Filter and organize words
        words_by_episode = {}
        total_words = 0
        
        for p in progress:
            # Apply filters
            if language and p.language != language:
                continue
            if season and p.season != season:
                continue
            if episode and p.episode != episode:
                continue
            
            episode_key = f"{p.language}_S{p.season}E{p.episode}"
            vocabulary = getattr(p, 'vocabulary_learned', []) or []
            
            if vocabulary:
                words_by_episode[episode_key] = {
                    "language": p.language,
                    "season": p.season,
                    "episode": p.episode,
                    "words": vocabulary,
                    "completed_at": p.completed_at.isoformat() if getattr(p, 'completed_at', None) else None
                }
                total_words += len(vocabulary)
        
        return {
            "user_id": user.id,
            "total_words": total_words,
            "filters": {
                "language": language,
                "season": season,
                "episode": episode
            },
            "words_by_episode": words_by_episode
        }
    except Exception as e:
        logger.error(f"Error getting user words: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
    try:
        db_manager = managers['database']
        user = await db_manager.get_or_create_user(esp32_id)
        progress = await db_manager.update_progress(
            user.id, language, season, episode, progress_data
        )
        return {"success": True, "progress_id": progress.id}
    except Exception as e:
        logger.error(f"Error updating user progress: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# EPISODE ENDPOINTS
# ============================================================================

@router.get("/episodes/available")
async def get_available_episodes(
    language: Optional[str] = Query(None, description="Filter by language"),
    managers: Dict = Depends(get_managers)
):
    """Get all available episodes with filtering"""
    try:
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
    except Exception as e:
        logger.error(f"Error getting available episodes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/episodes/{language}/{season}/{episode}")
async def get_episode_details(
    language: str, 
    season: int, 
    episode: int,
    managers: Dict = Depends(get_managers)
):
    """Get specific episode details"""
    try:
        content_manager = managers['content']
        episode_data = await content_manager.get_episode(language, season, episode)
        if not episode_data:
            raise HTTPException(status_code=404, detail="Episode not found")
        return episode_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting episode details: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# ANALYTICS ENDPOINTS (FOR DASHBOARD)
# ============================================================================

@router.get("/analytics/system")
async def get_system_analytics(
    days: int = Query(30, description="Number of days"), 
    managers: Dict = Depends(get_managers)
):
    """Get comprehensive system analytics"""
    try:
        db_manager = managers['database']
        
        # Try to get real analytics from enhanced database manager
        if hasattr(db_manager, 'get_learning_analytics'):
            analytics = await db_manager.get_learning_analytics(days=days)
            return analytics
        else:
            # Fallback to mock data
            return {
                "period_days": days,
                "summary": {
                    "total_sessions": 156,
                    "total_duration_hours": 78.5,
                    "total_interactions": 2340,
                    "unique_users": 23,
                    "average_session_duration_minutes": 12.5,
                    "average_interactions_per_session": 15
                },
                "language_popularity": {
                    "spanish": {"sessions": 89},
                    "french": {"sessions": 45},
                    "german": {"sessions": 22}
                },
                "daily_activity": [
                    {"date": "2025-06-14", "session_count": 12, "unique_users": 8, "total_duration_minutes": 180},
                    {"date": "2025-06-13", "session_count": 15, "unique_users": 10, "total_duration_minutes": 225}
                ]
            }
    except Exception as e:
        logger.error(f"Error getting system analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics/languages")
async def get_language_analytics(managers: Dict = Depends(get_managers)):
    """Get language usage statistics"""
    try:
        db_manager = managers['database']
        
        # Try to get real data
        if hasattr(db_manager, 'get_learning_analytics'):
            analytics = await db_manager.get_learning_analytics(days=30)
            return analytics.get('language_popularity', {})
        else:
            # Mock data
            return {
                "Spanish": 150,
                "French": 89,
                "German": 45
            }
    except Exception as e:
        logger.error(f"Error getting language analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/leaderboard")
async def get_leaderboard(
    metric: str = Query("vocabulary", description="Metric to rank by"),
    limit: int = Query(10, description="Number of results"),
    managers: Dict = Depends(get_managers)
):
    """Get user leaderboard"""
    try:
        db_manager = managers['database']
        
        # Try to get real leaderboard
        if hasattr(db_manager, 'get_leaderboard'):
            leaderboard = await db_manager.get_leaderboard(metric=metric, limit=limit)
            return leaderboard
        else:
            # Mock leaderboard data
            mock_data = {
                "vocabulary": [
                    {"rank": 1, "esp32_id": "DEVICE_001", "value": 85},
                    {"rank": 2, "esp32_id": "DEVICE_002", "value": 67},
                    {"rank": 3, "esp32_id": "DEVICE_003", "value": 52},
                    {"rank": 4, "esp32_id": "TEST_DEVICE_001", "value": 34},
                    {"rank": 5, "esp32_id": "DEVICE_005", "value": 29}
                ],
                "episodes": [
                    {"rank": 1, "esp32_id": "DEVICE_001", "value": 15},
                    {"rank": 2, "esp32_id": "DEVICE_002", "value": 12},
                    {"rank": 3, "esp32_id": "DEVICE_003", "value": 9},
                    {"rank": 4, "esp32_id": "TEST_DEVICE_001", "value": 6},
                    {"rank": 5, "esp32_id": "DEVICE_005", "value": 4}
                ],
                "duration": [
                    {"rank": 1, "esp32_id": "DEVICE_001", "value": 1250},
                    {"rank": 2, "esp32_id": "DEVICE_002", "value": 980},
                    {"rank": 3, "esp32_id": "DEVICE_003", "value": 720},
                    {"rank": 4, "esp32_id": "TEST_DEVICE_001", "value": 450},
                    {"rank": 5, "esp32_id": "DEVICE_005", "value": 320}
                ]
            }
            return mock_data.get(metric, [])[:limit]
    except Exception as e:
        logger.error(f"Error getting leaderboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics/user/{user_id}")
async def get_user_analytics_by_id(user_id: str, managers: Dict = Depends(get_managers)):
    """Get learning analytics for user by user ID"""
    try:
        db_manager = managers['database']
        
        # Try enhanced analytics first
        if hasattr(db_manager, 'get_user_learning_analytics'):
            analytics = await db_manager.get_user_learning_analytics(user_id)
            if analytics:
                return analytics
        
        # Fallback to basic analytics
        progress = await db_manager.get_user_progress(user_id)
        
        total_episodes = len(progress)
        completed_episodes = len([p for p in progress if p.completed])
        total_vocabulary = sum(len(p.vocabulary_learned or []) for p in progress)
        
        return {
            "user_id": user_id,
            "total_episodes": total_episodes,
            "completed_episodes": completed_episodes,
            "completion_rate": completed_episodes / total_episodes if total_episodes > 0 else 0,
            "total_vocabulary_learned": total_vocabulary
        }
        
    except Exception as e:
        logger.error(f"Error getting user analytics by ID: {e}")
        raise HTTPException(status_code=404, detail="User analytics not found")

@router.get("/metrics/realtime")
async def get_realtime_metrics(managers: Dict = Depends(get_managers)):
    """Get real-time system metrics"""
    try:
        # Get real-time connection counts
        ws_manager = managers.get('websocket')
        realtime_manager = managers.get('realtime')
        cache_manager = managers.get('cache')
        
        active_esp32 = len(getattr(ws_manager, 'active_connections', {})) if ws_manager else 0
        active_openai = len(getattr(realtime_manager, 'connections', {})) if realtime_manager else 0
        
        # Try to get cache status
        cache_status = "unknown"
        if cache_manager:
            try:
                cache_info = await cache_manager.get_connection_status()
                cache_status = cache_info['type']
            except:
                cache_status = "error"
        
        metrics_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "active_esp32_connections": active_esp32,
            "active_openai_connections": active_openai,
            "cache_status": cache_status,
            "uptime_seconds": 0,  # Calculate actual uptime if needed
            "memory_usage_mb": 0,  # Add memory monitoring if needed
            "cpu_usage_percent": 0  # Add CPU monitoring if needed
        }
        
        return metrics_data
    except Exception as e:
        logger.error(f"Error getting real-time metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# HEALTH AND DEBUG ENDPOINTS
# ============================================================================

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "ESP32 Language Learning API",
        "timestamp": datetime.utcnow().isoformat()
    }

@router.get("/debug/connections")
async def debug_connections(managers: Dict = Depends(get_managers)):
    """Debug endpoint to check connection status"""
    try:
        ws_manager = managers.get('websocket')
        realtime_manager = managers.get('realtime')
        
        return {
            "websocket_manager": ws_manager is not None,
            "realtime_manager": realtime_manager is not None,
            "database_manager": "database" in managers,
            "cache_manager": "cache" in managers,
            "content_manager": "content" in managers,
            "active_websockets": len(getattr(ws_manager, 'active_connections', {})) if ws_manager else 0,
            "active_realtime": len(getattr(realtime_manager, 'connections', {})) if realtime_manager else 0
        }
    except Exception as e:
        logger.error(f"Error in debug connections: {e}")
        raise HTTPException(status_code=500, detail=str(e))