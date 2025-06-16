# app/api/profile_endpoints.py - FIXED VERSION

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, validator
from app.models.schemas import UserResponse
import logging

logger = logging.getLogger(__name__)

# Profile API Router
profile_router = APIRouter(prefix="/api/profiles", tags=["user_profiles"])

# Pydantic models for profile management
class ProfileCreateRequest(BaseModel):
    name: str
    age: int
    preferred_language: str = 'spanish'
    learning_style: str = 'mixed'
    
    @validator('name')
    def validate_name(cls, v):
        if not v or len(v.strip()) < 2 or len(v.strip()) > 20:
            raise ValueError('Name must be 2-20 characters long')
        if not v.strip().replace(' ', '').isalpha():
            raise ValueError('Name must contain only letters and spaces')
        return v.strip().title()
    
    @validator('age')
    def validate_age(cls, v):
        if not isinstance(v, int) or v < 3 or v > 12:
            raise ValueError('Age must be between 3 and 12')
        return v
    
    @validator('preferred_language')
    def validate_language(cls, v):
        if v.lower() not in ['spanish', 'french', 'german']:
            raise ValueError('Language must be spanish, french, or german')
        return v.lower()
    
    @validator('learning_style')
    def validate_learning_style(cls, v):
        if v.lower() not in ['visual', 'audio', 'kinesthetic', 'mixed']:
            raise ValueError('Learning style must be visual, audio, kinesthetic, or mixed')
        return v.lower()

class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    preferred_language: Optional[str] = None
    learning_style: Optional[str] = None
    
    @validator('name')
    def validate_name(cls, v):
        if v is not None:
            if len(v.strip()) < 2 or len(v.strip()) > 20:
                raise ValueError('Name must be 2-20 characters long')
            if not v.strip().replace(' ', '').isalpha():
                raise ValueError('Name must contain only letters and spaces')
            return v.strip().title()
        return v
    
    @validator('age')
    def validate_age(cls, v):
        if v is not None and (not isinstance(v, int) or v < 3 or v > 12):
            raise ValueError('Age must be between 3 and 12')
        return v

class ProfileResponse(BaseModel):
    esp32_id: str
    name: str
    age: int
    preferred_language: str
    learning_style: str
    source: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class ProfileSetupQuestion(BaseModel):
    id: str
    question: str
    type: str
    validation: Optional[str] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min: Optional[int] = None
    max: Optional[int] = None
    options: Optional[List[Dict[str, str]]] = None
    default: Optional[str] = None
    required: bool = True

# Dependency injection - will be overridden in main.py
async def get_managers():
    """Get managers - will be overridden with actual implementation"""
    raise HTTPException(status_code=500, detail="Managers not initialized")

# Helper function to get profile manager
def get_profile_manager(managers: Dict):
    """Get profile manager from managers dict"""
    if 'profile' not in managers:
        raise HTTPException(status_code=500, detail="Profile manager not available")
    return managers['profile']

@profile_router.get("/setup-questions", response_model=list[ProfileSetupQuestion])
async def get_profile_setup_questions(managers: Dict = Depends(get_managers)):
    """Get questions for user profile setup"""
    try:
        profile_manager = get_profile_manager(managers)
        questions = await profile_manager.get_profile_setup_questions()
        return questions
    except Exception as e:
        logger.error(f"Error getting setup questions: {e}")
        raise HTTPException(status_code=500, detail="Failed to get setup questions")

@profile_router.get("/{esp32_id}", response_model=ProfileResponse)
async def get_user_profile(esp32_id: str, managers: Dict = Depends(get_managers)):
    """Get user profile for personalization"""
    try:
        profile_manager = get_profile_manager(managers)
        profile = await profile_manager.get_user_profile(esp32_id)
        return ProfileResponse(
            esp32_id=esp32_id,
            name=profile['name'],
            age=profile['age'],
            preferred_language=profile['preferred_language'],
            learning_style=profile['learning_style'],
            source=profile['source'],
            created_at=profile.get('created_at'),
            updated_at=profile.get('updated_at')
        )
    except Exception as e:
        logger.error(f"Error getting user profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user profile")

@profile_router.post("/{esp32_id}", response_model=ProfileResponse)
async def create_user_profile(
    esp32_id: str,
    profile_data: ProfileCreateRequest,
    managers: Dict = Depends(get_managers)
):
    """Create a new user profile"""
    try:
        profile_manager = get_profile_manager(managers)
        profile = await profile_manager.create_user_profile(
            esp32_id=esp32_id,
            name=profile_data.name,
            age=profile_data.age,
            preferred_language=profile_data.preferred_language,
            learning_style=profile_data.learning_style
        )
        
        return ProfileResponse(
            esp32_id=esp32_id,
            name=profile['name'],
            age=profile['age'],
            preferred_language=profile['preferred_language'],
            learning_style=profile['learning_style'],
            source=profile['source'],
            created_at=profile.get('created_at'),
            updated_at=profile.get('updated_at')
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating user profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to create user profile")

@profile_router.put("/{esp32_id}", response_model=ProfileResponse)
async def update_user_profile(
    esp32_id: str,
    profile_updates: ProfileUpdateRequest,
    managers: Dict = Depends(get_managers)
):
    """Update existing user profile"""
    try:
        profile_manager = get_profile_manager(managers)
        
        # Filter out None values
        updates = {k: v for k, v in profile_updates.dict().items() if v is not None}
        
        if not updates:
            raise HTTPException(status_code=400, detail="No updates provided")
        
        profile = await profile_manager.update_user_profile(esp32_id, updates)
        
        return ProfileResponse(
            esp32_id=esp32_id,
            name=profile['name'],
            age=profile['age'],
            preferred_language=profile['preferred_language'],
            learning_style=profile['learning_style'],
            source=profile['source'],
            created_at=profile.get('created_at'),
            updated_at=profile.get('updated_at')
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating user profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to update user profile")

@profile_router.post("/{esp32_id}/setup", response_model=ProfileResponse)
async def setup_profile_from_questions(
    esp32_id: str,
    responses: Dict[str, Any],
    managers: Dict = Depends(get_managers)
):
    """Setup user profile from setup question responses"""
    try:
        profile_manager = get_profile_manager(managers)
        profile = await profile_manager.setup_profile_from_responses(esp32_id, responses)
        
        return ProfileResponse(
            esp32_id=esp32_id,
            name=profile['name'],
            age=profile['age'],
            preferred_language=profile['preferred_language'],
            learning_style=profile['learning_style'],
            source=profile['source'],
            created_at=profile.get('created_at'),
            updated_at=profile.get('updated_at')
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error setting up profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to setup profile")

@profile_router.get("/{esp32_id}/personalization-context")
async def get_personalization_context(esp32_id: str, managers: Dict = Depends(get_managers)):
    """Get full personalization context for prompts"""
    try:
        profile_manager = get_profile_manager(managers)
        context = await profile_manager.get_personalization_context(esp32_id)
        return context
    except Exception as e:
        logger.error(f"Error getting personalization context: {e}")
        raise HTTPException(status_code=500, detail="Failed to get personalization context")

@profile_router.get("/{esp32_id}/learning-preferences")
async def get_learning_preferences(esp32_id: str, managers: Dict = Depends(get_managers)):
    """Get learning preferences for this user"""
    try:
        profile_manager = get_profile_manager(managers)
        preferences = await profile_manager.get_learning_preferences(esp32_id)
        return preferences
    except Exception as e:
        logger.error(f"Error getting learning preferences: {e}")
        raise HTTPException(status_code=500, detail="Failed to get learning preferences")

# Enhanced endpoints that integrate with existing API
@profile_router.get("/{esp32_id}/next-episode-with-prompts")
async def get_next_episode_with_prompts(esp32_id: str, managers: Dict = Depends(get_managers)):
    """Get next episode with personalized prompts"""
    try:
        profile_manager = get_profile_manager(managers)
        
        # Get user and their progress
        user = await managers['database'].get_or_create_user(esp32_id)
        user_progress = {
            'current_language': user.current_language,
            'current_season': user.current_season,
            'current_episode': user.current_episode
        }
        
        # Get next episode from content manager
        next_episode = await managers['content'].get_next_episode_for_user(user.id, user_progress)
        
        if not next_episode:
            raise HTTPException(status_code=404, detail="No next episode available")
        
        # Get personalization context
        context = await profile_manager.get_personalization_context(esp32_id)
        
        # Apply personalization to prompts
        if 'choice_agent_prompt' in next_episode:
            next_episode['choice_agent_prompt'] = next_episode['choice_agent_prompt'].format(**context)
        
        if 'episode_agent_prompt' in next_episode:
            next_episode['episode_agent_prompt'] = next_episode['episode_agent_prompt'].format(**context)
        
        return {
            "episode": next_episode,
            "personalization_applied": True,
            "user_context": {
                "name": context['user_name'],
                "age": context['user_age'],
                "language": context['preferred_language']
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting personalized episode: {e}")
        raise HTTPException(status_code=500, detail="Failed to get personalized episode")

# Profile validation endpoint
@profile_router.post("/validate")
async def validate_profile_data(
    profile_data: Dict[str, Any],
    managers: Dict = Depends(get_managers)
):
    """Validate profile data without saving"""
    try:
        profile_manager = get_profile_manager(managers)
        validated = await profile_manager.validate_profile_data(profile_data)
        return {
            "valid": True,
            "validated_data": validated
        }
    except ValueError as e:
        return {
            "valid": False,
            "error": str(e)
        }
    except Exception as e:
        logger.error(f"Error validating profile data: {e}")
        raise HTTPException(status_code=500, detail="Failed to validate profile data")