from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, update, func, and_, or_
from app.models.database import (
    User, UserProgress, LearningSession, DailyActivity, 
    WordLearned, TopicLearned, CurriculumProgress
)
from app.models.schemas import UserCreate
from typing import Optional, List, Dict, Any
import uuid
from datetime import datetime, date, timedelta
import logging

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, database_url: str):
        self.engine = create_async_engine(database_url, echo=False)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
    
    async def get_or_create_user(self, esp32_id: str) -> User:
        """Get or create user with initial curriculum setup"""
        async with self.async_session() as session:
            result = await session.execute(
                select(User).where(User.esp32_id == esp32_id)
            )
            user = result.scalars().first()
            
            if not user:
                user = User(
                    id=str(uuid.uuid4()),
                    esp32_id=esp32_id,
                    current_language="spanish",
                    current_season=1,
                    current_episode=1
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                
                # Initialize curriculum progress
                await self._initialize_curriculum_progress(user.id, "spanish")
                
            else:
                user.last_active = datetime.utcnow()
                await session.commit()
            
            return user
    
    async def _initialize_curriculum_progress(self, user_id: str, language: str):
        """Initialize curriculum progress for new user"""
        async with self.async_session() as session:
            curriculum = CurriculumProgress(
                user_id=user_id,
                language=language,
                current_season=1,
                current_episode=1,
                unlocked_seasons=[1]
            )
            session.add(curriculum)
            await session.commit()
    
    # === LEARNING SESSION MANAGEMENT ===
    
    async def create_session(self, user_id: str, episode_info: dict) -> LearningSession:
        """Create new learning session"""
        async with self.async_session() as session:
            learning_session = LearningSession(
                id=str(uuid.uuid4()),
                user_id=user_id,
                episode_info=episode_info,
                words_practiced=[],
                topics_covered=[]
            )
            session.add(learning_session)
            await session.commit()
            await session.refresh(learning_session)
            
            # Update daily activity
            await self._update_daily_activity(user_id, session_started=True)
            
            return learning_session
    
    async def update_session_conversation_time(self, session_id: str, additional_seconds: int):
        """Update conversation time for active session"""
        async with self.async_session() as session:
            result = await session.execute(
                select(LearningSession).where(LearningSession.id == session_id)
            )
            learning_session = result.scalars().first()
            
            if learning_session:
                learning_session.conversation_time += additional_seconds
                learning_session.interaction_count += 1
                
                # Update user's total conversation time
                await self._update_user_conversation_time(learning_session.user_id, additional_seconds)
                await session.commit()
    
    async def end_session(self, session_id: str) -> Optional[LearningSession]:
        """End learning session and update statistics"""
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
                
                # Update daily activity with session end
                await self._update_daily_activity(
                    learning_session.user_id, 
                    session_time=learning_session.duration,
                    conversation_time=learning_session.conversation_time
                )
                
                await session.commit()
                return learning_session
            
            return None
    
    # === WORDS AND TOPICS TRACKING ===
    
    async def add_word_learned(self, user_id: str, word: str, language: str, 
                              season: int, episode: int, episode_title: str,
                              confidence: str = "medium", context: str = None,
                              translation: str = None) -> WordLearned:
        """Add a learned word to tracking"""
        async with self.async_session() as session:
            # Check if word already exists for this user
            existing = await session.execute(
                select(WordLearned).where(
                    and_(
                        WordLearned.user_id == user_id,
                        WordLearned.word == word,
                        WordLearned.language == language
                    )
                )
            )
            word_learned = existing.scalars().first()
            
            if word_learned:
                # Update existing word
                word_learned.confidence_level = confidence
                word_learned.last_practiced_at = datetime.utcnow()
                word_learned.attempts_to_learn += 1
            else:
                # Create new word entry
                word_learned = WordLearned(
                    user_id=user_id,
                    word=word,
                    language=language,
                    season=season,
                    episode=episode,
                    episode_title=episode_title,
                    confidence_level=confidence,
                    context=context,
                    translation=translation
                )
                session.add(word_learned)
                
                # Update user's total words learned
                await self._increment_user_words_learned(user_id)
                
                # Update daily activity
                await self._update_daily_activity(user_id, words_learned=1)
            
            await session.commit()
            return word_learned
    
    async def add_topic_learned(self, user_id: str, topic: str, language: str,
                               season: int, episode: int, episode_title: str,
                               words_in_topic: List[str] = None,
                               mastery_level: str = "introduced") -> TopicLearned:
        """Add a learned topic to tracking"""
        async with self.async_session() as session:
            # Check if topic already exists
            existing = await session.execute(
                select(TopicLearned).where(
                    and_(
                        TopicLearned.user_id == user_id,
                        TopicLearned.topic == topic,
                        TopicLearned.language == language
                    )
                )
            )
            topic_learned = existing.scalars().first()
            
            if topic_learned:
                # Update existing topic
                topic_learned.mastery_level = mastery_level
                topic_learned.last_reviewed_at = datetime.utcnow()
                if words_in_topic:
                    topic_learned.words_in_topic = words_in_topic
            else:
                # Create new topic entry
                topic_learned = TopicLearned(
                    user_id=user_id,
                    topic=topic,
                    language=language,
                    season=season,
                    episode=episode,
                    episode_title=episode_title,
                    words_in_topic=words_in_topic or [],
                    mastery_level=mastery_level
                )
                session.add(topic_learned)
                
                # Update user's total topics learned
                await self._increment_user_topics_learned(user_id)
                
                # Update daily activity
                await self._update_daily_activity(user_id, topics_learned=1)
            
            await session.commit()
            return topic_learned
    
    # === EPISODE PROGRESS MANAGEMENT ===
    
    async def complete_episode(self, user_id: str, language: str, season: int, episode: int,
                              words_learned: List[str], topics_learned: List[str],
                              completion_time: int) -> UserProgress:
        """Mark episode as completed and update curriculum progress"""
        async with self.async_session() as session:
            # Update or create user progress
            result = await session.execute(
                select(UserProgress).where(
                    and_(
                        UserProgress.user_id == user_id,
                        UserProgress.language == language,
                        UserProgress.season == season,
                        UserProgress.episode == episode
                    )
                )
            )
            progress = result.scalars().first()
            
            if not progress:
                progress = UserProgress(
                    user_id=user_id,
                    language=language,
                    season=season,
                    episode=episode
                )
                session.add(progress)
            
            # Update progress data
            progress.completed = True
            progress.vocabulary_learned = words_learned
            progress.topics_learned = topics_learned
            progress.completion_time = completion_time
            progress.completed_at = datetime.utcnow()
            progress.attempts += 1
            
            await session.commit()
            
            # Update curriculum progress
            await self._update_curriculum_progress(user_id, language, season, episode)
            
            # Update user totals
            await self._increment_user_episodes_completed(user_id)
            
            # Update daily activity
            await self._update_daily_activity(user_id, episodes_completed=1)
            
            return progress
    
    async def _update_curriculum_progress(self, user_id: str, language: str, 
                                         season: int, episode: int):
        """Update curriculum progress after episode completion"""
        async with self.async_session() as session:
            result = await session.execute(
                select(CurriculumProgress).where(
                    and_(
                        CurriculumProgress.user_id == user_id,
                        CurriculumProgress.language == language
                    )
                )
            )
            curriculum = result.scalars().first()
            
            if curriculum:
                # Update total episodes completed
                curriculum.total_episodes_completed += 1
                
                # Check if season is completed (7 episodes per season)
                if episode == 7:
                    curriculum.seasons_completed += 1
                    curriculum.current_season += 1
                    curriculum.current_episode = 1
                    
                    # Unlock next season
                    unlocked = curriculum.unlocked_seasons or []
                    if curriculum.current_season not in unlocked:
                        unlocked.append(curriculum.current_season)
                        curriculum.unlocked_seasons = unlocked
                else:
                    curriculum.current_episode = episode + 1
                
                # Calculate progress percentages
                episodes_in_season = 7
                curriculum.season_progress = (episode / episodes_in_season)
                
                # Update user's current episode/season
                user_result = await session.execute(
                    select(User).where(User.id == user_id)
                )
                user = user_result.scalars().first()
                if user:
                    user.current_season = curriculum.current_season
                    user.current_episode = curriculum.current_episode
                
                await session.commit()
    
    # === DAILY ACTIVITY TRACKING ===
    
    async def _update_daily_activity(self, user_id: str, session_started: bool = False,
                                    session_time: int = 0, conversation_time: int = 0,
                                    words_learned: int = 0, topics_learned: int = 0,
                                    episodes_completed: int = 0):
        """Update daily activity statistics"""
        async with self.async_session() as session:
            today = datetime.utcnow().date()
            
            result = await session.execute(
                select(DailyActivity).where(
                    and_(
                        DailyActivity.user_id == user_id,
                        func.date(DailyActivity.activity_date) == today
                    )
                )
            )
            daily_activity = result.scalars().first()
            
            if not daily_activity:
                daily_activity = DailyActivity(
                    user_id=user_id,
                    activity_date=today,
                    first_activity=datetime.utcnow()
                )
                session.add(daily_activity)
            
            # Update statistics
            if session_started:
                daily_activity.sessions_count += 1
            
            daily_activity.total_session_time += session_time
            daily_activity.total_conversation_time += conversation_time
            daily_activity.words_learned_today += words_learned
            daily_activity.topics_learned_today += topics_learned
            daily_activity.episodes_completed_today += episodes_completed
            daily_activity.last_activity = datetime.utcnow()
            
            await session.commit()
    
    # === USER STATISTICS HELPERS ===
    
    async def _update_user_conversation_time(self, user_id: str, additional_seconds: int):
        """Update user's total conversation time"""
        async with self.async_session() as session:
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(total_conversation_time=User.total_conversation_time + additional_seconds)
            )
            await session.commit()
    
    async def _increment_user_words_learned(self, user_id: str):
        """Increment user's total words learned"""
        async with self.async_session() as session:
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(total_words_learned=User.total_words_learned + 1)
            )
            await session.commit()
    
    async def _increment_user_topics_learned(self, user_id: str):
        """Increment user's total topics learned"""
        async with self.async_session() as session:
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(total_topics_learned=User.total_topics_learned + 1)
            )
            await session.commit()
    
    async def _increment_user_episodes_completed(self, user_id: str):
        """Increment user's total episodes completed"""
        async with self.async_session() as session:
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(total_episodes_completed=User.total_episodes_completed + 1)
            )
            await session.commit()
    
    # === ANALYTICS QUERIES ===
    
    async def get_user_learning_analytics(self, user_id: str) -> Dict[str, Any]:
        """Get comprehensive learning analytics for user"""
        async with self.async_session() as session:
            # Get user basic info
            user_result = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = user_result.scalars().first()
            
            if not user:
                return {}
            
            # Get curriculum progress
            curriculum_result = await session.execute(
                select(CurriculumProgress).where(
                    CurriculumProgress.user_id == user_id
                )
            )
            curriculum = curriculum_result.scalars().first()
            
            # Get words learned
            words_result = await session.execute(
                select(WordLearned).where(WordLearned.user_id == user_id)
            )
            words_learned = words_result.scalars().all()
            
            # Get topics learned
            topics_result = await session.execute(
                select(TopicLearned).where(TopicLearned.user_id == user_id)
            )
            topics_learned = topics_result.scalars().all()
            
            # Get recent daily activity (last 30 days)
            thirty_days_ago = datetime.utcnow().date() - timedelta(days=30)
            activity_result = await session.execute(
                select(DailyActivity).where(
                    and_(
                        DailyActivity.user_id == user_id,
                        DailyActivity.activity_date >= thirty_days_ago
                    )
                ).order_by(DailyActivity.activity_date.desc())
            )
            daily_activities = activity_result.scalars().all()
            
            # Calculate analytics
            total_conversation_time = user.total_conversation_time
            total_words = len(words_learned)
            total_topics = len(topics_learned)
            
            # Group words by episode
            words_by_episode = {}
            for word in words_learned:
                key = f"{word.language}_S{word.season}E{word.episode}"
                if key not in words_by_episode:
                    words_by_episode[key] = {
                        "episode_title": word.episode_title,
                        "words": []
                    }
                words_by_episode[key]["words"].append({
                    "word": word.word,
                    "confidence": word.confidence_level,
                    "learned_at": word.first_learned_at.isoformat(),
                    "translation": word.translation
                })
            
            # Group topics by episode
            topics_by_episode = {}
            for topic in topics_learned:
                key = f"{topic.language}_S{topic.season}E{topic.episode}"
                if key not in topics_by_episode:
                    topics_by_episode[key] = {
                        "episode_title": topic.episode_title,
                        "topics": []
                    }
                topics_by_episode[key]["topics"].append({
                    "topic": topic.topic,
                    "mastery_level": topic.mastery_level,
                    "learned_at": topic.learned_at.isoformat(),
                    "words_count": len(topic.words_in_topic or [])
                })
            
            # Calculate streak and recent activity
            current_streak = self._calculate_learning_streak(daily_activities)
            
            return {
                "user_info": {
                    "user_id": user.id,
                    "esp32_id": user.esp32_id,
                    "created_at": user.created_at.isoformat(),
                    "last_active": user.last_active.isoformat()
                },
                "current_progress": {
                    "language": user.current_language,
                    "season": user.current_season,
                    "episode": user.current_episode,
                    "total_episodes_completed": user.total_episodes_completed,
                    "seasons_completed": curriculum.seasons_completed if curriculum else 0
                },
                "learning_statistics": {
                    "total_conversation_time_seconds": total_conversation_time,
                    "total_conversation_time_formatted": self._format_duration(total_conversation_time),
                    "total_words_learned": total_words,
                    "total_topics_learned": total_topics,
                    "total_episodes_completed": user.total_episodes_completed,
                    "current_streak_days": current_streak
                },
                "words_learned_by_episode": words_by_episode,
                "topics_learned_by_episode": topics_by_episode,
                "daily_activity": [
                    {
                        "date": activity.activity_date.isoformat(),
                        "session_time_seconds": activity.total_session_time,
                        "conversation_time_seconds": activity.total_conversation_time,
                        "sessions_count": activity.sessions_count,
                        "words_learned": activity.words_learned_today,
                        "topics_learned": activity.topics_learned_today,
                        "episodes_completed": activity.episodes_completed_today
                    }
                    for activity in daily_activities
                ]
            }
    
    def _calculate_learning_streak(self, daily_activities: List[DailyActivity]) -> int:
        """Calculate current learning streak"""
        if not daily_activities:
            return 0
        
        # Sort by date descending
        activities = sorted(daily_activities, key=lambda x: x.activity_date, reverse=True)
        
        streak = 0
        today = datetime.utcnow().date()
        check_date = today
        
        for activity in activities:
            activity_date = activity.activity_date
            if isinstance(activity_date, datetime):
                activity_date = activity_date.date()
            
            if activity_date == check_date and activity.sessions_count > 0:
                streak += 1
                check_date = check_date - timedelta(days=1)
            else:
                break
        
        return streak
    
    def _format_duration(self, seconds: int) -> str:
        """Format duration in human-readable format"""
        if seconds < 60:
            return f"{seconds} seconds"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes} minutes"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}h {minutes}m"
    
    # === EXISTING METHODS (kept for compatibility) ===
    
    async def get_user_progress(self, user_id: str) -> List[UserProgress]:
        async with self.async_session() as session:
            result = await session.execute(
                select(UserProgress).where(UserProgress.user_id == user_id)
            )
            return result.scalars().all()
    
    async def update_progress(self, user_id: str, language: str, 
                            season: int, episode: int, progress_data: dict) -> UserProgress:
        """Update progress - kept for backward compatibility"""
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