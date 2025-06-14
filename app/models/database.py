# app/models/database.py - Simple working version without complex migrations

from sqlalchemy import create_engine, Column, String, Integer, Boolean, DateTime, JSON, ForeignKey, Float, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True)
    esp32_id = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Learning progress tracking - with defaults
    current_language = Column(String, default="spanish")
    current_season = Column(Integer, default=1)
    current_episode = Column(Integer, default=1)
    
    # Statistics - with defaults
    total_conversation_time = Column(Integer, default=0)  # in seconds
    total_words_learned = Column(Integer, default=0)
    total_topics_learned = Column(Integer, default=0)
    total_episodes_completed = Column(Integer, default=0)
    
    # Streak tracking - with defaults
    current_streak_days = Column(Integer, default=0)
    longest_streak_days = Column(Integer, default=0)
    last_activity_date = Column(DateTime, nullable=True)
    
    # Preferences - with defaults
    preferred_difficulty = Column(String, default="beginner")
    notification_enabled = Column(Boolean, default=True)
    
    # Relationships
    progress = relationship("UserProgress", back_populates="user")
    sessions = relationship("LearningSession", back_populates="user")

class UserProgress(Base):
    __tablename__ = "user_progress"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"))
    language = Column(String)
    season = Column(Integer)
    episode = Column(Integer)
    
    # Progress status
    completed = Column(Boolean, default=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Learning data
    vocabulary_learned = Column(JSON, default=list)  # List of words learned
    topics_learned = Column(JSON, default=list)     # List of topics covered
    progress_data = Column(JSON, default=dict)      # Additional progress data
    
    # Performance metrics - with defaults
    completion_time = Column(Integer, default=0)    # Time to complete in seconds
    attempts = Column(Integer, default=1)           # Number of attempts
    accuracy_score = Column(Float, default=0.0)     # Accuracy percentage
    confidence_score = Column(Float, default=0.0)   # Confidence level
    
    # Engagement metrics - with defaults
    interaction_count = Column(Integer, default=0)
    audio_interactions = Column(Integer, default=0)
    text_interactions = Column(Integer, default=0)
    
    # Relationships
    user = relationship("User", back_populates="progress")

class LearningSession(Base):
    __tablename__ = "learning_sessions"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"))
    
    # Session timing
    created_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    duration = Column(Integer, default=0)  # Duration in seconds
    
    # Episode information
    episode_info = Column(JSON, default=dict)
    language = Column(String, nullable=True)
    season = Column(Integer, nullable=True)
    episode = Column(Integer, nullable=True)
    
    # Session metrics - with defaults
    interaction_count = Column(Integer, default=0)
    audio_messages_sent = Column(Integer, default=0)
    audio_messages_received = Column(Integer, default=0)
    text_messages_sent = Column(Integer, default=0)
    text_messages_received = Column(Integer, default=0)
    
    # Performance metrics - with defaults
    words_practiced = Column(JSON, default=list)
    words_learned = Column(JSON, default=list)
    completion_status = Column(String, default="in_progress")  # in_progress, completed, abandoned
    
    # Technical metrics - with defaults
    connection_quality = Column(Float, default=1.0)
    error_count = Column(Integer, default=0)
    response_times = Column(JSON, default=list)  # List of response times
    
    # Relationships
    user = relationship("User", back_populates="sessions")

# Simple database initialization without complex migrations
async def init_db(database_url: str):
    """Initialize database with simple approach"""
    try:
        logger.info("Initializing database...")
        engine = create_async_engine(database_url, echo=False)
        
        async with engine.begin() as conn:
            # Create all tables
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created successfully")
        
        logger.info("Database initialization completed")
        return engine
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        # Try to create a simple fallback database
        return await create_fallback_db(database_url)

async def create_fallback_db(database_url: str):
    """Create a simple fallback database if main creation fails"""
    try:
        logger.info("Creating fallback database...")
        
        # For SQLite, we can use synchronous operations as fallback
        if "sqlite" in database_url:
            import sqlite3
            import os
            
            # Extract database path
            db_path = database_url.replace("sqlite+aiosqlite:///", "").replace("./", "")
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            
            # Create SQLite database with basic tables
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Create users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    esp32_id TEXT UNIQUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_active DATETIME DEFAULT CURRENT_TIMESTAMP,
                    current_language TEXT DEFAULT 'spanish',
                    current_season INTEGER DEFAULT 1,
                    current_episode INTEGER DEFAULT 1,
                    total_conversation_time INTEGER DEFAULT 0,
                    total_words_learned INTEGER DEFAULT 0,
                    total_topics_learned INTEGER DEFAULT 0,
                    total_episodes_completed INTEGER DEFAULT 0,
                    current_streak_days INTEGER DEFAULT 0,
                    longest_streak_days INTEGER DEFAULT 0,
                    last_activity_date DATETIME,
                    preferred_difficulty TEXT DEFAULT 'beginner',
                    notification_enabled BOOLEAN DEFAULT 1
                )
            """)
            
            # Create user_progress table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_progress (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    language TEXT,
                    season INTEGER,
                    episode INTEGER,
                    completed BOOLEAN DEFAULT 0,
                    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    completed_at DATETIME,
                    vocabulary_learned TEXT DEFAULT '[]',
                    topics_learned TEXT DEFAULT '[]',
                    progress_data TEXT DEFAULT '{}',
                    completion_time INTEGER DEFAULT 0,
                    attempts INTEGER DEFAULT 1,
                    accuracy_score REAL DEFAULT 0.0,
                    confidence_score REAL DEFAULT 0.0,
                    interaction_count INTEGER DEFAULT 0,
                    audio_interactions INTEGER DEFAULT 0,
                    text_interactions INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            
            # Create learning_sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS learning_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    ended_at DATETIME,
                    duration INTEGER DEFAULT 0,
                    episode_info TEXT DEFAULT '{}',
                    language TEXT,
                    season INTEGER,
                    episode INTEGER,
                    interaction_count INTEGER DEFAULT 0,
                    audio_messages_sent INTEGER DEFAULT 0,
                    audio_messages_received INTEGER DEFAULT 0,
                    text_messages_sent INTEGER DEFAULT 0,
                    text_messages_received INTEGER DEFAULT 0,
                    words_practiced TEXT DEFAULT '[]',
                    words_learned TEXT DEFAULT '[]',
                    completion_status TEXT DEFAULT 'in_progress',
                    connection_quality REAL DEFAULT 1.0,
                    error_count INTEGER DEFAULT 0,
                    response_times TEXT DEFAULT '[]',
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_esp32_id ON users(esp32_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_progress_user_id ON user_progress(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_learning_sessions_user_id ON learning_sessions(user_id)")
            
            conn.commit()
            conn.close()
            
            logger.info("Fallback SQLite database created successfully")
            
            # Return async engine
            engine = create_async_engine(database_url, echo=False)
            return engine
        
        else:
            # For other databases, just return a basic engine
            engine = create_async_engine(database_url, echo=False)
            return engine
            
    except Exception as e:
        logger.error(f"Fallback database creation failed: {e}")
        # Return a basic engine anyway
        engine = create_async_engine(database_url, echo=False)
        return engine

# Database connection helper
async def get_database_session(database_url: str):
    """Get database session"""
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return async_session()