from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, update
from app.models.database import User, UserProgress, LearningSession
from app.models.schemas import UserCreate
from typing import Optional, List
import uuid
from datetime import datetime

class DatabaseManager:
    def __init__(self, database_url: str):
        self.engine = create_async_engine(database_url, echo=True)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
    
    async def get_or_create_user(self, esp32_id: str) -> User:
        async with self.async_session() as session:
            result = await session.execute(
                select(User).where(User.esp32_id == esp32_id)
            )
            user = result.scalars().first()
            
            if not user:
                user = User(
                    id=str(uuid.uuid4()),
                    esp32_id=esp32_id
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
            else:
                user.last_active = datetime.utcnow()
                await session.commit()
            
            return user
    
    async def get_user_progress(self, user_id: str) -> List[UserProgress]:
        async with self.async_session() as session:
            result = await session.execute(
                select(UserProgress).where(UserProgress.user_id == user_id)
            )
            return result.scalars().all()
    
    async def update_progress(self, user_id: str, language: str, 
                            season: int, episode: int, progress_data: dict) -> UserProgress:
        async with self.async_session() as session:
            result = await session.execute(
                select(UserProgress).where(
                    UserProgress.user_id == user_id,
                    UserProgress.language == language,
                    UserProgress.season == season,
                    UserProgress.episode == episode
                )
            )
            progress = result.scalars().first()
            
            if not progress:
                progress = UserProgress(
                    user_id=user_id,
                    language=language,
                    season=season,
                    episode=episode,
                    progress_data=progress_data
                )
                session.add(progress)
            else:
                progress.progress_data = progress_data
                if progress_data.get("completed", False):
                    progress.completed = True
                    progress.completed_at = datetime.utcnow()
            
            await session.commit()
            return progress
    
    async def create_session(self, user_id: str, episode_info: dict) -> LearningSession:
        async with self.async_session() as session:
            learning_session = LearningSession(
                id=str(uuid.uuid4()),
                user_id=user_id,
                episode_info=episode_info
            )
            session.add(learning_session)
            await session.commit()
            return learning_session
    
    async def update_session_activity(self, session_id: str):
        async with self.async_session() as session:
            result = await session.execute(
                select(LearningSession).where(LearningSession.id == session_id)
            )
            learning_session = result.scalars().first()
            if learning_session:
                learning_session.interaction_count += 1
                await session.commit()
    
    async def end_session(self, session_id: str):
        async with self.async_session() as session:
            result = await session.execute(
                select(LearningSession).where(LearningSession.id == session_id)
            )
            learning_session = result.scalars().first()
            if learning_session:
                learning_session.ended_at = datetime.utcnow()
                learning_session.duration = int(
                    (learning_session.ended_at - learning_session.created_at).total_seconds()
                )
                await session.commit()