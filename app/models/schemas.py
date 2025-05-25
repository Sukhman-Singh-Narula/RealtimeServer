from pydantic import BaseModel
from typing import Optional, Dict, List, Any, Literal
from datetime import datetime

class UserCreate(BaseModel):
    esp32_id: str

class UserResponse(BaseModel):
    id: str
    esp32_id: str
    created_at: datetime
    last_active: datetime

class EpisodeSelection(BaseModel):
    language: str
    season: int
    episode: int
    title: Optional[str] = None

class EpisodeContent(BaseModel):
    language: str
    season: int
    episode: int
    title: str
    vocabulary: List[str]
    story_context: str
    difficulty: str
    estimated_duration: int
    learning_objectives: List[str]

class SessionData(BaseModel):
    user_id: str
    agent_state: Literal["CHOOSING", "LEARNING"]
    current_episode: Optional[Dict[str, Any]] = None
    connected_at: datetime
    last_activity: datetime
    openai_session_id: Optional[str] = None
    current_agent: Optional[str] = None

class WebSocketMessage(BaseModel):
    type: str
    esp32_id: str
    data: Optional[Dict[str, Any]] = None
    audio_data: Optional[str] = None
    timestamp: Optional[int] = None

class RealtimeEvent(BaseModel):
    type: str
    event_id: Optional[str] = None
    session: Optional[Dict[str, Any]] = None
    conversation: Optional[Dict[str, Any]] = None
    response: Optional[Dict[str, Any]] = None
    item: Optional[Dict[str, Any]] = None
    delta: Optional[str] = None
    audio: Optional[List[int]] = None