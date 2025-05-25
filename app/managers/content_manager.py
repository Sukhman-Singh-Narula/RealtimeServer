import firebase_admin
from firebase_admin import credentials, firestore
from typing import List, Dict, Any, Optional
from app.models.schemas import EpisodeContent
import logging

logger = logging.getLogger(__name__)

class ContentManager:
    def __init__(self, credentials_path: str):
        try:
            cred = credentials.Certificate(credentials_path)
            firebase_admin.initialize_app(cred)
            self.db = firestore.client()
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")
            self.db = None
    
    async def get_available_episodes(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all available episodes for user"""
        if not self.db:
            return self._get_mock_episodes()
            
        episodes = []
        try:
            episodes_ref = self.db.collection('episodes')
            docs = episodes_ref.stream()
            
            for doc in docs:
                episode_data = doc.to_dict()
                episode_id = doc.id
                parts = episode_id.split('_')
                if len(parts) == 3:
                    episode_data['language'] = parts[0]
                    episode_data['season'] = int(parts[1])
                    episode_data['episode'] = int(parts[2])
                    episodes.append(episode_data)
        except Exception as e:
            logger.error(f"Error fetching episodes: {e}")
            return self._get_mock_episodes()
        
        return episodes
    
    async def get_episode(self, language: str, season: int, episode: int) -> Optional[EpisodeContent]:
        """Get specific episode content"""
        if not self.db:
            return self._get_mock_episode(language, season, episode)
            
        try:
            doc_id = f"{language}_{season}_{episode}"
            doc_ref = self.db.collection('episodes').document(doc_id)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                return EpisodeContent(
                    language=language,
                    season=season,
                    episode=episode,
                    title=data['title'],
                    vocabulary=data['vocabulary'],
                    story_context=data['story_context'],
                    difficulty=data['difficulty'],
                    estimated_duration=data['estimated_duration'],
                    learning_objectives=data['learning_objectives']
                )
        except Exception as e:
            logger.error(f"Error fetching episode: {e}")
            
        return self._get_mock_episode(language, season, episode)
    
    def _get_mock_episodes(self) -> List[Dict[str, Any]]:
        """Return mock episodes for development"""
        return [
            {
                "language": "spanish",
                "season": 1,
                "episode": 1,
                "title": "Greetings and Family",
                "vocabulary": ["hola", "adiós", "familia", "mamá", "papá"],
                "story_context": "Meeting a Spanish family in their home",
                "difficulty": "beginner",
                "estimated_duration": 300,
                "learning_objectives": ["Basic greetings", "Family members"]
            },
            {
                "language": "spanish",
                "season": 1,
                "episode": 2,
                "title": "Farm Animals",
                "vocabulary": ["gato", "perro", "vaca", "caballo", "cerdo"],
                "story_context": "Adventure on a Spanish farm with friendly animals",
                "difficulty": "beginner",
                "estimated_duration": 400,
                "learning_objectives": ["Animal names", "Animal sounds"]
            },
            {
                "language": "spanish",
                "season": 1,
                "episode": 3,
                "title": "Colors and Shapes",
                "vocabulary": ["rojo", "azul", "verde", "círculo", "cuadrado"],
                "story_context": "Painting a colorful mural in a Spanish art class",
                "difficulty": "beginner",
                "estimated_duration": 350,
                "learning_objectives": ["Basic colors", "Simple shapes"]
            }
        ]
    
    def _get_mock_episode(self, language: str, season: int, episode: int) -> Optional[EpisodeContent]:
        """Return mock episode for development"""
        episodes = self._get_mock_episodes()
        for ep in episodes:
            if ep['language'] == language and ep['season'] == season and ep['episode'] == episode:
                return EpisodeContent(**ep)
        return None