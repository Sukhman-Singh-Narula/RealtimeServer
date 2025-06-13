from sqlalchemy import create_engine, Column, String, Integer, Boolean, DateTime, JSON, ForeignKey, Float, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from datetime import datetime, date

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True)
    esp32_id = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Learning progress tracking
    current_language = Column(String, default="spanish")
    current_season = Column(Integer, default=1)
    current_episode = Column(Integer, default=1)
    
    # Total statistics
    total_conversation_time = Column(Integer, default=0)  # in seconds
    total_words_learned = Column(Integer, default=0)
    total_topics_learned = Column(Integer, default=0)
    total_episodes_completed = Column(Integer, default=0)
    
    # Relationships
    progress = relationship("UserProgress", back_populates="user")
    sessions = relationship("LearningSession", back_populates="user")
    daily_activity = relationship("DailyActivity", back_populates="user")
    words_learned = relationship("WordLearned", back_populates="user")
    topics_learned = relationship("TopicLearned", back_populates="user")

class UserProgress(Base):
    __tablename__ = "user_progress"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"))
    language = Column(String)
    season = Column(Integer)
    episode = Column(Integer)
    completed = Column(Boolean, default=False)
    progress_data = Column(JSON)
    vocabulary_learned = Column(JSON)  # List of words learned in this episode
    topics_learned = Column(JSON)     # List of topics/objectives learned
    completion_time = Column(Integer, default=0)  # Time taken to complete episode (seconds)
    attempts = Column(Integer, default=0)  # Number of times attempted
    completed_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="progress")

class LearningSession(Base):
    __tablename__ = "learning_sessions"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"))
    episode_info = Column(JSON)
    duration = Column(Integer, default=0)  # Session duration in seconds
    conversation_time = Column(Integer, default=0)  # Actual conversation time (excluding silence)
    interaction_count = Column(Integer, default=0)
    words_practiced = Column(JSON, default=list)  # Words practiced in this session
    topics_covered = Column(JSON, default=list)   # Topics covered in this session
    session_type = Column(String, default="learning")  # learning, practice, review
    created_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="sessions")

class DailyActivity(Base):
    __tablename__ = "daily_activity"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"))
    activity_date = Column(DateTime, default=lambda: datetime.utcnow().date())
    
    # Daily statistics
    total_session_time = Column(Integer, default=0)  # Total time spent in sessions (seconds)
    total_conversation_time = Column(Integer, default=0)  # Actual talking time (seconds)
    sessions_count = Column(Integer, default=0)
    words_learned_today = Column(Integer, default=0)
    topics_learned_today = Column(Integer, default=0)
    episodes_completed_today = Column(Integer, default=0)
    
    # Session details
    session_details = Column(JSON, default=list)  # List of session info for the day
    
    # Streaks and milestones
    is_streak_day = Column(Boolean, default=True)
    
    # Timestamps
    first_activity = Column(DateTime, nullable=True)
    last_activity = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="daily_activity")

class WordLearned(Base):
    __tablename__ = "words_learned"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"))
    word = Column(String)
    language = Column(String)
    season = Column(Integer)
    episode = Column(Integer)
    episode_title = Column(String)
    
    # Learning details
    confidence_level = Column(String, default="medium")  # low, medium, high
    attempts_to_learn = Column(Integer, default=1)
    first_learned_at = Column(DateTime, default=datetime.utcnow)
    last_practiced_at = Column(DateTime, default=datetime.utcnow)
    
    # Context
    context = Column(Text, nullable=True)  # Story context where word was learned
    translation = Column(String, nullable=True)  # English translation
    
    # Relationships
    user = relationship("User", back_populates="words_learned")

class TopicLearned(Base):
    __tablename__ = "topics_learned"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"))
    topic = Column(String)  # e.g., "Basic greetings", "Family members"
    language = Column(String)
    season = Column(Integer)
    episode = Column(Integer)
    episode_title = Column(String)
    
    # Learning details
    mastery_level = Column(String, default="introduced")  # introduced, practicing, mastered
    words_in_topic = Column(JSON, default=list)  # Words that belong to this topic
    learned_at = Column(DateTime, default=datetime.utcnow)
    last_reviewed_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="topics_learned")

# Curriculum tracking table for managing seasons and episodes
class CurriculumProgress(Base):
    __tablename__ = "curriculum_progress"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"))
    language = Column(String)
    
    # Season tracking (each season has 7 episodes)
    current_season = Column(Integer, default=1)
    current_episode = Column(Integer, default=1)
    seasons_completed = Column(Integer, default=0)
    total_episodes_completed = Column(Integer, default=0)
    
    # Progress percentages
    season_progress = Column(Float, default=0.0)  # 0.0 to 1.0
    overall_progress = Column(Float, default=0.0)  # 0.0 to 1.0
    
    # Unlocked content
    unlocked_seasons = Column(JSON, default=[1])  # Seasons available to user
    next_episode_available = Column(Boolean, default=True)
    
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Database setup
async def init_db(database_url: str):
    engine = create_async_engine(database_url, echo=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine