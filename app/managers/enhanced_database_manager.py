# app/managers/enhanced_database_manager.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, update, func, desc
from app.models.database import User, UserProgress, LearningSession
from app.models.schemas import UserCreate
from typing import Optional, List, Dict, Any
import uuid
from datetime import datetime, timedelta
import json
import logging

logger = logging.getLogger(__name__)

class EnhancedDatabaseManager:
    def __init__(self, database_url: str):
        self.engine = create_async_engine(database_url, echo=False)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
    
    async def get_or_create_user(self, esp32_id: str) -> User:
        """Get or create user with enhanced tracking"""
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
                logger.info(f"Created new user for ESP32 {esp32_id}: {user.id}")
            else:
                user.last_active = datetime.utcnow()
                await session.commit()
                logger.debug(f"Updated last_active for user {user.id}")
            
            return user
    
    async def get_user_progress(self, user_id: str) -> List[UserProgress]:
        """Get all progress for a user"""
        async with self.async_session() as session:
            result = await session.execute(
                select(UserProgress)
                .where(UserProgress.user_id == user_id)
                .order_by(UserProgress.language, UserProgress.season, UserProgress.episode)
            )
            return result.scalars().all()
    
    async def get_user_progress_summary(self, user_id: str) -> Dict[str, Any]:
        """Get comprehensive progress summary for user"""
        async with self.async_session() as session:
            # Get all progress records
            result = await session.execute(
                select(UserProgress).where(UserProgress.user_id == user_id)
            )
            progress_records = result.scalars().all()
            
            # Calculate summary statistics
            total_episodes = len(progress_records)
            completed_episodes = len([p for p in progress_records if p.completed])
            
            # Group by language
            by_language = {}
            total_vocabulary = 0
            
            for progress in progress_records:
                lang = progress.language
                if lang not in by_language:
                    by_language[lang] = {
                        'total_episodes': 0,
                        'completed_episodes': 0,
                        'vocabulary_learned': 0,
                        'completion_rate': 0.0
                    }
                
                by_language[lang]['total_episodes'] += 1
                if progress.completed:
                    by_language[lang]['completed_episodes'] += 1
                
                vocab_count = len(progress.vocabulary_learned or [])
                by_language[lang]['vocabulary_learned'] += vocab_count
                total_vocabulary += vocab_count
            
            # Calculate completion rates
            for lang_data in by_language.values():
                if lang_data['total_episodes'] > 0:
                    lang_data['completion_rate'] = lang_data['completed_episodes'] / lang_data['total_episodes']
            
            return {
                'user_id': user_id,
                'summary': {
                    'total_episodes': total_episodes,
                    'completed_episodes': completed_episodes,
                    'overall_completion_rate': completed_episodes / total_episodes if total_episodes > 0 else 0,
                    'total_vocabulary_learned': total_vocabulary
                },
                'by_language': by_language,
                'recent_activity': await self._get_recent_activity(user_id)
            }
    
    async def _get_recent_activity(self, user_id: str, days: int = 7) -> List[Dict[str, Any]]:
        """Get recent learning activity for user"""
        async with self.async_session() as session:
            since_date = datetime.utcnow() - timedelta(days=days)
            
            result = await session.execute(
                select(UserProgress)
                .where(
                    UserProgress.user_id == user_id,
                    UserProgress.completed_at >= since_date
                )
                .order_by(desc(UserProgress.completed_at))
                .limit(10)
            )
            
            recent_progress = result.scalars().all()
            
            return [
                {
                    'date': p.completed_at.isoformat(),
                    'language': p.language,
                    'season': p.season,
                    'episode': p.episode,
                    'vocabulary_learned': len(p.vocabulary_learned or [])
                }
                for p in recent_progress
            ]
    
    async def update_progress(self, user_id: str, language: str, 
                            season: int, episode: int, progress_data: dict) -> UserProgress:
        """Update user progress with enhanced metrics"""
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
                logger.info(f"Created new progress record for {user_id}: {language} S{season}E{episode}")
            else:
                progress.progress_data = progress_data
                logger.info(f"Updated progress record for {user_id}: {language} S{season}E{episode}")
            
            # Update completion status and vocabulary
            if progress_data.get("completed", False):
                progress.completed = True
                progress.completed_at = datetime.utcnow()
                progress.vocabulary_learned = progress_data.get("words_learned", [])
            
            await session.commit()
            await session.refresh(progress)
            return progress
    
    async def create_session(self, user_id: str, episode_info: dict) -> LearningSession:
        """Create learning session with enhanced tracking"""
        async with self.async_session() as session:
            learning_session = LearningSession(
                id=str(uuid.uuid4()),
                user_id=user_id,
                episode_info=episode_info
            )
            session.add(learning_session)
            await session.commit()
            await session.refresh(learning_session)
            
            logger.info(f"Created learning session {learning_session.id} for user {user_id}")
            return learning_session
    
    async def update_session_activity(self, session_id: str):
        """Update session activity counter"""
        async with self.async_session() as session:
            result = await session.execute(
                select(LearningSession).where(LearningSession.id == session_id)
            )
            learning_session = result.scalars().first()
            if learning_session:
                learning_session.interaction_count += 1
                await session.commit()
                logger.debug(f"Updated interaction count for session {session_id}")
    
    async def end_session(self, session_id: str):
        """End learning session with duration calculation"""
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
                logger.info(f"Ended learning session {session_id} with duration {learning_session.duration}s")
    
    async def save_session_metrics(self, metrics_data: Dict[str, Any]):
        """Save detailed session metrics to database"""
        async with self.async_session() as session:
            # For now, we'll store metrics as JSON in the learning session
            # In a production system, you might want a separate metrics table
            
            session_id = metrics_data.get('session_id')
            if session_id:
                result = await session.execute(
                    select(LearningSession).where(LearningSession.id == session_id)
                )
                learning_session = result.scalars().first()
                
                if learning_session:
                    # Store metrics in episode_info JSON field (or create a metrics field)
                    if not learning_session.episode_info:
                        learning_session.episode_info = {}
                    learning_session.episode_info['metrics'] = metrics_data
                    await session.commit()
                    logger.info(f"Saved metrics for session {session_id}")
    
    async def get_user_metrics(self, user_id: str, since_date: datetime) -> List[Dict[str, Any]]:
        """Get user metrics since specified date"""
        async with self.async_session() as session:
            result = await session.execute(
                select(LearningSession)
                .where(
                    LearningSession.user_id == user_id,
                    LearningSession.created_at >= since_date
                )
                .order_by(desc(LearningSession.created_at))
            )
            
            sessions = result.scalars().all()
            metrics_list = []
            
            for session in sessions:
                if session.episode_info and 'metrics' in session.episode_info:
                    metrics_list.append(session.episode_info['metrics'])
                else:
                    # Create basic metrics from session data if detailed metrics not available
                    metrics_list.append({
                        'session_start': session.created_at.isoformat(),
                        'session_end': session.ended_at.isoformat() if session.ended_at else None,
                        'session_duration': session.duration or 0,
                        'interaction_count': session.interaction_count,
                        'episode_info': session.episode_info
                    })
            
            return metrics_list
    
    async def get_learning_analytics(self, user_id: str = None, days: int = 30) -> Dict[str, Any]:
        """Get comprehensive learning analytics"""
        async with self.async_session() as session:
            since_date = datetime.utcnow() - timedelta(days=days)
            
            # Base query
            query = select(LearningSession).where(LearningSession.created_at >= since_date)
            if user_id:
                query = query.where(LearningSession.user_id == user_id)
            
            result = await session.execute(query.order_by(desc(LearningSession.created_at)))
            sessions = result.scalars().all()
            
            # Calculate analytics
            total_sessions = len(sessions)
            total_duration = sum(s.duration or 0 for s in sessions)
            total_interactions = sum(s.interaction_count for s in sessions)
            
            # User engagement
            user_sessions = {}
            for session in sessions:
                uid = session.user_id
                if uid not in user_sessions:
                    user_sessions[uid] = {'sessions': 0, 'duration': 0, 'interactions': 0}
                user_sessions[uid]['sessions'] += 1
                user_sessions[uid]['duration'] += session.duration or 0
                user_sessions[uid]['interactions'] += session.interaction_count
            
            # Language popularity
            language_stats = {}
            for session in sessions:
                if session.episode_info and 'language' in session.episode_info:
                    lang = session.episode_info['language']
                    if lang not in language_stats:
                        language_stats[lang] = {'sessions': 0, 'completion_rate': 0}
                    language_stats[lang]['sessions'] += 1
            
            return {
                'period_days': days,
                'summary': {
                    'total_sessions': total_sessions,
                    'total_duration_hours': total_duration / 3600,
                    'total_interactions': total_interactions,
                    'unique_users': len(user_sessions),
                    'average_session_duration_minutes': (total_duration / total_sessions / 60) if total_sessions > 0 else 0,
                    'average_interactions_per_session': total_interactions / total_sessions if total_sessions > 0 else 0
                },
                'user_engagement': user_sessions,
                'language_popularity': language_stats,
                'daily_activity': await self._get_daily_activity_stats(since_date)
            }
    
    async def _get_daily_activity_stats(self, since_date: datetime) -> List[Dict[str, Any]]:
        """Get daily activity statistics"""
        async with self.async_session() as session:
            # Group sessions by date
            result = await session.execute(
                select(
                    func.date(LearningSession.created_at).label('date'),
                    func.count(LearningSession.id).label('session_count'),
                    func.sum(LearningSession.duration).label('total_duration'),
                    func.count(func.distinct(LearningSession.user_id)).label('unique_users')
                )
                .where(LearningSession.created_at >= since_date)
                .group_by(func.date(LearningSession.created_at))
                .order_by(func.date(LearningSession.created_at))
            )
            
            daily_stats = []
            for row in result:
                daily_stats.append({
                    'date': row.date.isoformat(),
                    'session_count': row.session_count,
                    'total_duration_minutes': (row.total_duration or 0) / 60,
                    'unique_users': row.unique_users
                })
            
            return daily_stats
    
    async def get_leaderboard(self, metric: str = 'vocabulary', limit: int = 10) -> List[Dict[str, Any]]:
        """Get user leaderboard based on specified metric"""
        async with self.async_session() as session:
            if metric == 'vocabulary':
                # Get users with most vocabulary learned
                result = await session.execute(
                    select(User.esp32_id, func.sum(
                        func.json_array_length(UserProgress.vocabulary_learned)
                    ).label('total_vocabulary'))
                    .join(UserProgress, User.id == UserProgress.user_id)
                    .where(UserProgress.vocabulary_learned.isnot(None))
                    .group_by(User.id, User.esp32_id)
                    .order_by(desc('total_vocabulary'))
                    .limit(limit)
                )
            elif metric == 'episodes':
                # Get users with most episodes completed
                result = await session.execute(
                    select(User.esp32_id, func.count(UserProgress.id).label('episodes_completed'))
                    .join(UserProgress, User.id == UserProgress.user_id)
                    .where(UserProgress.completed == True)
                    .group_by(User.id, User.esp32_id)
                    .order_by(desc('episodes_completed'))
                    .limit(limit)
                )
            elif metric == 'duration':
                # Get users with most learning time
                result = await session.execute(
                    select(User.esp32_id, func.sum(LearningSession.duration).label('total_duration'))
                    .join(LearningSession, User.id == LearningSession.user_id)
                    .where(LearningSession.duration.isnot(None))
                    .group_by(User.id, User.esp32_id)
                    .order_by(desc('total_duration'))
                    .limit(limit)
                )
            else:
                return []
            
            leaderboard = []
            for i, row in enumerate(result):
                entry = {
                    'rank': i + 1,
                    'esp32_id': row.esp32_id,
                    'value': getattr(row, list(row._asdict().keys())[1])
                }
                leaderboard.append(entry)
            
            return leaderboard