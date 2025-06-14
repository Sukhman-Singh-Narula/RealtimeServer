# app/managers/metrics_manager.py
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)

class ConversationMetrics:
    """Track metrics for a single conversation session"""
    
    def __init__(self, esp32_id: str, user_id: str):
        self.esp32_id = esp32_id
        self.user_id = user_id
        self.session_start = datetime.utcnow()
        self.session_end: Optional[datetime] = None
        
        # Audio metrics
        self.audio_chunks_received = 0
        self.audio_chunks_sent = 0
        self.total_audio_duration_received = 0.0
        self.total_audio_duration_sent = 0.0
        
        # Conversation metrics
        self.messages_sent = 0
        self.messages_received = 0
        self.text_messages_sent = 0
        self.text_messages_received = 0
        
        # Response metrics
        self.response_times = []
        self.last_user_input_time: Optional[datetime] = None
        
        # Learning metrics
        self.vocabulary_attempts = {}
        self.vocabulary_learned = []
        self.episodes_attempted = []
        self.episodes_completed = []
        
        # Error metrics
        self.connection_errors = 0
        self.audio_processing_errors = 0
        self.api_errors = 0
        
        # Engagement metrics
        self.silence_periods = []
        self.interaction_frequency = []
        self.last_interaction_time = self.session_start
        
    def record_audio_received(self, duration_seconds: float):
        """Record incoming audio from user"""
        self.audio_chunks_received += 1
        self.total_audio_duration_received += duration_seconds
        self._record_interaction()
        
    def record_audio_sent(self, duration_seconds: float):
        """Record outgoing audio to user"""
        self.audio_chunks_sent += 1
        self.total_audio_duration_sent += duration_seconds
        
    def record_text_message(self, from_user: bool = True):
        """Record text message sent or received"""
        if from_user:
            self.text_messages_received += 1
            self.messages_received += 1
            self._record_user_input()
        else:
            self.text_messages_sent += 1
            self.messages_sent += 1
            
    def record_vocabulary_attempt(self, word: str, confidence: str):
        """Record vocabulary learning attempt"""
        if word not in self.vocabulary_attempts:
            self.vocabulary_attempts[word] = []
        self.vocabulary_attempts[word].append({
            'timestamp': datetime.utcnow().isoformat(),
            'confidence': confidence
        })
        
        if confidence in ['medium', 'high'] and word not in self.vocabulary_learned:
            self.vocabulary_learned.append(word)
            
    def record_episode_attempt(self, episode_info: Dict[str, Any]):
        """Record episode attempt"""
        episode_key = f"{episode_info['language']}_{episode_info['season']}_{episode_info['episode']}"
        if episode_key not in self.episodes_attempted:
            self.episodes_attempted.append(episode_key)
            
    def record_episode_completion(self, episode_info: Dict[str, Any]):
        """Record episode completion"""
        episode_key = f"{episode_info['language']}_{episode_info['season']}_{episode_info['episode']}"
        if episode_key not in self.episodes_completed:
            self.episodes_completed.append(episode_key)
            
    def record_error(self, error_type: str):
        """Record various types of errors"""
        if error_type == 'connection':
            self.connection_errors += 1
        elif error_type == 'audio_processing':
            self.audio_processing_errors += 1
        elif error_type == 'api':
            self.api_errors += 1
            
    def _record_user_input(self):
        """Record when user provides input for response time calculation"""
        self.last_user_input_time = datetime.utcnow()
        self._record_interaction()
        
    def record_response_generated(self):
        """Record when system generates response"""
        if self.last_user_input_time:
            response_time = (datetime.utcnow() - self.last_user_input_time).total_seconds()
            self.response_times.append(response_time)
            self.last_user_input_time = None
            
    def _record_interaction(self):
        """Record user interaction for engagement tracking"""
        now = datetime.utcnow()
        if self.last_interaction_time:
            silence_duration = (now - self.last_interaction_time).total_seconds()
            if silence_duration > 5:  # Record silences longer than 5 seconds
                self.silence_periods.append(silence_duration)
                
        self.interaction_frequency.append(now.isoformat())
        self.last_interaction_time = now
        
    def end_session(self):
        """Mark session as ended"""
        self.session_end = datetime.utcnow()
        
    def get_session_duration(self) -> float:
        """Get session duration in seconds"""
        end_time = self.session_end or datetime.utcnow()
        return (end_time - self.session_start).total_seconds()
        
    def get_average_response_time(self) -> float:
        """Get average response time"""
        return sum(self.response_times) / len(self.response_times) if self.response_times else 0.0
        
    def get_engagement_score(self) -> float:
        """Calculate engagement score (0-100)"""
        duration = self.get_session_duration()
        if duration == 0:
            return 0.0
            
        # Factors that increase engagement score
        interaction_rate = len(self.interaction_frequency) / (duration / 60)  # interactions per minute
        audio_ratio = self.total_audio_duration_received / duration if duration > 0 else 0
        vocabulary_progress = len(self.vocabulary_learned)
        
        # Factors that decrease engagement score
        avg_silence = sum(self.silence_periods) / len(self.silence_periods) if self.silence_periods else 0
        error_rate = (self.connection_errors + self.audio_processing_errors + self.api_errors) / max(1, len(self.interaction_frequency))
        
        # Calculate score (simplified algorithm)
        score = min(100, max(0, 
            (interaction_rate * 20) + 
            (audio_ratio * 30) + 
            (vocabulary_progress * 15) - 
            (avg_silence * 2) - 
            (error_rate * 25)
        ))
        
        return score
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for storage"""
        return {
            'esp32_id': self.esp32_id,
            'user_id': self.user_id,
            'session_start': self.session_start.isoformat(),
            'session_end': self.session_end.isoformat() if self.session_end else None,
            'session_duration': self.get_session_duration(),
            'audio_metrics': {
                'chunks_received': self.audio_chunks_received,
                'chunks_sent': self.audio_chunks_sent,
                'duration_received': self.total_audio_duration_received,
                'duration_sent': self.total_audio_duration_sent
            },
            'conversation_metrics': {
                'messages_sent': self.messages_sent,
                'messages_received': self.messages_received,
                'text_messages_sent': self.text_messages_sent,
                'text_messages_received': self.text_messages_received
            },
            'response_metrics': {
                'response_times': self.response_times,
                'average_response_time': self.get_average_response_time()
            },
            'learning_metrics': {
                'vocabulary_attempts': self.vocabulary_attempts,
                'vocabulary_learned': self.vocabulary_learned,
                'episodes_attempted': self.episodes_attempted,
                'episodes_completed': self.episodes_completed
            },
            'error_metrics': {
                'connection_errors': self.connection_errors,
                'audio_processing_errors': self.audio_processing_errors,
                'api_errors': self.api_errors
            },
            'engagement_metrics': {
                'silence_periods': self.silence_periods,
                'interaction_frequency': len(self.interaction_frequency),
                'engagement_score': self.get_engagement_score()
            }
        }

class MetricsManager:
    """Manage metrics for all active sessions"""
    
    def __init__(self, cache_manager=None, database_manager=None):
        self.cache_manager = cache_manager
        self.database_manager = database_manager
        self.active_sessions: Dict[str, ConversationMetrics] = {}
        
    def start_session(self, esp32_id: str, user_id: str) -> ConversationMetrics:
        """Start tracking metrics for a new session"""
        metrics = ConversationMetrics(esp32_id, user_id)
        self.active_sessions[esp32_id] = metrics
        logger.info(f"Started metrics tracking for {esp32_id}")
        return metrics
        
    def get_session(self, esp32_id: str) -> Optional[ConversationMetrics]:
        """Get metrics for an active session"""
        return self.active_sessions.get(esp32_id)
        
    async def end_session(self, esp32_id: str):
        """End session and save metrics"""
        if esp32_id in self.active_sessions:
            metrics = self.active_sessions[esp32_id]
            metrics.end_session()
            
            # Save to database if available
            if self.database_manager:
                try:
                    await self.database_manager.save_session_metrics(metrics.to_dict())
                except Exception as e:
                    logger.error(f"Failed to save metrics to database: {e}")
            
            # Save to cache if available
            if self.cache_manager:
                try:
                    await self.cache_manager.save_metrics(esp32_id, metrics.to_dict())
                except Exception as e:
                    logger.error(f"Failed to save metrics to cache: {e}")
            
            # Remove from active sessions
            del self.active_sessions[esp32_id]
            logger.info(f"Ended metrics tracking for {esp32_id}")
            
    async def get_user_metrics_summary(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """Get metrics summary for a user over specified days"""
        if not self.database_manager:
            return {"error": "Database not available"}
            
        try:
            # Get historical metrics from database
            since_date = datetime.utcnow() - timedelta(days=days)
            metrics_data = await self.database_manager.get_user_metrics(user_id, since_date)
            
            if not metrics_data:
                return {"error": "No metrics found for user"}
            
            # Aggregate metrics
            total_sessions = len(metrics_data)
            total_duration = sum(m.get('session_duration', 0) for m in metrics_data)
            total_vocabulary_learned = sum(len(m.get('learning_metrics', {}).get('vocabulary_learned', [])) for m in metrics_data)
            total_episodes_completed = sum(len(m.get('learning_metrics', {}).get('episodes_completed', [])) for m in metrics_data)
            
            avg_engagement = sum(m.get('engagement_metrics', {}).get('engagement_score', 0) for m in metrics_data) / total_sessions
            avg_response_time = sum(m.get('response_metrics', {}).get('average_response_time', 0) for m in metrics_data) / total_sessions
            
            return {
                'user_id': user_id,
                'period_days': days,
                'summary': {
                    'total_sessions': total_sessions,
                    'total_duration_hours': total_duration / 3600,
                    'average_session_duration_minutes': (total_duration / total_sessions) / 60 if total_sessions > 0 else 0,
                    'total_vocabulary_learned': total_vocabulary_learned,
                    'total_episodes_completed': total_episodes_completed,
                    'average_engagement_score': avg_engagement,
                    'average_response_time_seconds': avg_response_time
                },
                'daily_breakdown': self._calculate_daily_breakdown(metrics_data)
            }
            
        except Exception as e:
            logger.error(f"Error getting user metrics summary: {e}")
            return {"error": str(e)}
            
    def _calculate_daily_breakdown(self, metrics_data: List[Dict]) -> List[Dict]:
        """Calculate daily breakdown of metrics"""
        daily_data = {}
        
        for session in metrics_data:
            session_date = session.get('session_start', '')[:10]  # Get YYYY-MM-DD
            
            if session_date not in daily_data:
                daily_data[session_date] = {
                    'date': session_date,
                    'sessions': 0,
                    'duration': 0,
                    'vocabulary_learned': 0,
                    'engagement_score': 0,
                    'engagement_count': 0
                }
            
            daily_data[session_date]['sessions'] += 1
            daily_data[session_date]['duration'] += session.get('session_duration', 0)
            daily_data[session_date]['vocabulary_learned'] += len(session.get('learning_metrics', {}).get('vocabulary_learned', []))
            
            engagement = session.get('engagement_metrics', {}).get('engagement_score', 0)
            if engagement > 0:
                daily_data[session_date]['engagement_score'] += engagement
                daily_data[session_date]['engagement_count'] += 1
        
        # Calculate averages
        for day_data in daily_data.values():
            if day_data['engagement_count'] > 0:
                day_data['average_engagement'] = day_data['engagement_score'] / day_data['engagement_count']
            else:
                day_data['average_engagement'] = 0
            del day_data['engagement_score']
            del day_data['engagement_count']
        
        return sorted(daily_data.values(), key=lambda x: x['date'])
        
    async def get_real_time_metrics(self) -> Dict[str, Any]:
        """Get real-time metrics for all active sessions"""
        active_metrics = {}
        
        for esp32_id, metrics in self.active_sessions.items():
            active_metrics[esp32_id] = {
                'session_duration': metrics.get_session_duration(),
                'audio_chunks_received': metrics.audio_chunks_received,
                'vocabulary_learned': len(metrics.vocabulary_learned),
                'engagement_score': metrics.get_engagement_score(),
                'last_interaction': metrics.last_interaction_time.isoformat() if metrics.last_interaction_time else None
            }
        
        return {
            'timestamp': datetime.utcnow().isoformat(),
            'active_sessions_count': len(self.active_sessions),
            'active_sessions': active_metrics
        }