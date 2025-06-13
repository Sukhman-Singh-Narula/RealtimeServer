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
            logger.info("Firebase initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")
            self.db = None
    
    async def get_next_episode_for_user(self, user_id: str, user_progress: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get the next episode the user should take based on their progress"""
        
        # Get current progress from user data
        current_language = user_progress.get('current_language', 'spanish')
        current_season = user_progress.get('current_season', 1)
        current_episode = user_progress.get('current_episode', 1)
        
        logger.info(f"Finding next episode for user {user_id}: {current_language} S{current_season}E{current_episode}")
        
        # Get the episode content including the prompts
        episode_data = await self.get_episode_with_prompts(current_language, current_season, current_episode)
        
        if episode_data:
            # Add next episode information
            episode_data['is_next_episode'] = True
            episode_data['user_progress'] = {
                'season': current_season,
                'episode': current_episode,
                'language': current_language
            }
            
            logger.info(f"Next episode found: {episode_data.get('title')} for user {user_id}")
            return episode_data
        else:
            logger.warning(f"No next episode found for user {user_id}")
            return None
    
    async def get_episode_with_prompts(self, language: str, season: int, episode: int) -> Optional[Dict[str, Any]]:
        """Get episode content including both choice and episode agent prompts"""
        
        if not self.db:
            return self._get_mock_episode_with_prompts(language, season, episode)
            
        try:
            doc_id = f"{language}_{season}_{episode}"
            doc_ref = self.db.collection('episodes').document(doc_id)
            doc = doc_ref.get()
            
            if doc.exists:
                episode_data = doc.to_dict()
                
                # Ensure the episode has the required structure
                episode_data.update({
                    'language': language,
                    'season': season,
                    'episode': episode
                })
                
                logger.info(f"Retrieved episode with prompts: {doc_id}")
                return episode_data
            else:
                logger.warning(f"Episode not found in Firebase: {doc_id}")
                return self._get_mock_episode_with_prompts(language, season, episode)
                
        except Exception as e:
            logger.error(f"Error fetching episode with prompts: {e}")
            return self._get_mock_episode_with_prompts(language, season, episode)
    
    async def get_episode(self, language: str, season: int, episode: int) -> Optional[EpisodeContent]:
        """Get episode content for API compatibility (without prompts)"""
        episode_data = await self.get_episode_with_prompts(language, season, episode)
        
        if episode_data:
            return EpisodeContent(
                language=language,
                season=season,
                episode=episode,
                title=episode_data['title'],
                vocabulary=episode_data['vocabulary'],
                story_context=episode_data['story_context'],
                difficulty=episode_data['difficulty'],
                estimated_duration=episode_data['estimated_duration'],
                learning_objectives=episode_data['learning_objectives']
            )
        return None
    
    async def get_available_episodes(self, user_id: str) -> List[Dict[str, Any]]:
        """Get episodes available to the user (for backward compatibility)"""
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
                    # Remove prompts from public API
                    episode_data.pop('choice_agent_prompt', None)
                    episode_data.pop('episode_agent_prompt', None)
                    episodes.append(episode_data)
                    
            episodes.sort(key=lambda x: (x.get('language', ''), x.get('season', 0), x.get('episode', 0)))
            
        except Exception as e:
            logger.error(f"Error fetching episodes: {e}")
            return self._get_mock_episodes()
        
        return episodes
    
    def _get_mock_episode_with_prompts(self, language: str, season: int, episode: int) -> Optional[Dict[str, Any]]:
        """Return mock episode with prompts for development"""
        episodes = self._get_mock_episodes_with_prompts()
        
        for ep in episodes:
            if (ep['language'] == language and 
                ep['season'] == season and 
                ep['episode'] == episode):
                return ep
        return None
    
    def _get_mock_episodes_with_prompts(self) -> List[Dict[str, Any]]:
        """Return mock episodes with pre-written prompts for development"""
        return [
            {
                "language": "spanish",
                "season": 1,
                "episode": 1,
                "title": "Greetings and Family",
                "vocabulary": ["hola", "adiós", "familia", "mamá", "papá"],
                "story_context": "Meeting a Spanish family in their home. María introduces you to her family members and teaches you how to greet them properly.",
                "difficulty": "beginner",
                "estimated_duration": 300,
                "learning_objectives": ["Basic greetings", "Family members", "Polite expressions"],
                "vocabulary_translations": {
                    "hola": "hello",
                    "adiós": "goodbye", 
                    "familia": "family",
                    "mamá": "mom",
                    "papá": "dad"
                },
                "choice_agent_prompt": """¡Hola {user_name}! I'm Lingo, your Spanish learning friend! 🌟

I'm so excited to see you today! You're {user_age} years old and you're going to be AMAZING at Spanish!

How are you feeling today, {user_name}? Tell me all about it!

When you're ready, we have a super fun adventure waiting for you! We're going to meet a lovely Spanish family and learn how to say hello and talk about families. 

You'll learn words like "hola" (that means hello!) and "familia" (that means family!). 

Are you ready to start this exciting adventure, {user_name}? Just tell me when you want to begin! 🎉

Remember, learning Spanish is like going on a magical journey, and you're the brave explorer! 🗺️✨""",
                
                "episode_agent_prompt": """¡Hola {user_name}! Welcome to your Spanish family adventure! 👨‍👩‍👧‍👦

You're {user_age} years old and you're going to be fantastic at this!

🏠 TODAY'S STORY: We're visiting the García family in their cozy home in Spain! They're so excited to meet you, {user_name}!

📚 WORDS WE'LL LEARN: hola, adiós, familia, mamá, papá
🎯 WHAT YOU'LL MASTER: Saying hello, goodbye, and talking about family!

Let me introduce you to everyone! *knock knock* 

"¡Hola!" says María at the door. That means "hello" in Spanish! Can you say "hola" back to her, {user_name}? 

Say it with me: "HO-LA!" 🎵

When you say a word well, I'll cheer for you! When you learn all the words, we'll celebrate together!

Ready to meet the García family, {user_name}? Let's start with that beautiful "¡Hola!" 🌟""",
            },
            
            {
                "language": "spanish",
                "season": 1,
                "episode": 2,
                "title": "Farm Animals",
                "vocabulary": ["gato", "perro", "vaca", "caballo", "cerdo"],
                "story_context": "Adventure on a Spanish farm with friendly animals. Help farmer Carlos feed the animals and learn their names in Spanish.",
                "difficulty": "beginner",
                "estimated_duration": 400,
                "learning_objectives": ["Animal names", "Animal sounds", "Farm vocabulary"],
                "vocabulary_translations": {
                    "gato": "cat",
                    "perro": "dog",
                    "vaca": "cow", 
                    "caballo": "horse",
                    "cerdo": "pig"
                },
                "choice_agent_prompt": """¡Hola again, {user_name}! 🐄

You did so well learning about families! Now I have an even MORE exciting adventure for you!

How are you feeling today, my {user_age}-year-old Spanish superstar? 

We're going to visit Farmer Carlos's farm! 🚜 There are so many friendly animals waiting to meet you! We'll learn to say their names in Spanish!

You'll meet a "gato" (cat), a "perro" (dog), and even a big "vaca" (cow)! They all want to be your friends!

Are you ready to explore the farm and make animal friends, {user_name}? It's going to be so much fun! 🐮🐱🐶

Tell me when you're ready for this amazing farm adventure! 🌾""",
                
                "episode_agent_prompt": """¡Hola {user_name}! Welcome to Farmer Carlos's magical farm! 🚜

You're {user_age} years old and the animals are SO excited to meet you!

🐄 TODAY'S ADVENTURE: We're helping Farmer Carlos feed all his animal friends!
📚 ANIMAL WORDS: gato, perro, vaca, caballo, cerdo  
🎯 YOUR MISSION: Learn each animal's Spanish name and their sounds!

*Farmer Carlos waves* "¡Hola {user_name}! Welcome to my farm!"

Listen! Do you hear that "meow"? That's our first friend! 

"¡Mira!" (Look!) says Carlos. "Es un gato!" 

That's right - "gato" means cat in Spanish! Can you say "gato" for me, {user_name}?

Say it like this: "GA-TO!" 🐱

The gato is so happy when you say his name! Let's meet more animal friends! 🌟""",
            },
            
            {
                "language": "spanish",
                "season": 1,
                "episode": 3,
                "title": "Colors and Shapes",
                "vocabulary": ["rojo", "azul", "verde", "círculo", "cuadrado"],
                "story_context": "Painting a colorful mural in a Spanish art class with teacher Sofia. Create beautiful art while learning colors and shapes.",
                "difficulty": "beginner",
                "estimated_duration": 350,
                "learning_objectives": ["Basic colors", "Simple shapes", "Art vocabulary"],
                "vocabulary_translations": {
                    "rojo": "red",
                    "azul": "blue",
                    "verde": "green",
                    "círculo": "circle",
                    "cuadrado": "square"
                },
                "choice_agent_prompt": """¡Hola my artistic friend {user_name}! 🎨

You're becoming such a Spanish expert! I'm so proud of you!

How are you feeling today, {user_name}? Ready for something colorful and creative?

Today we're going to be artists! We'll paint with Señorita Sofia and learn colors in Spanish! 

We'll use "rojo" (red), "azul" (blue), and "verde" (green) to make beautiful art! Plus we'll paint "círculos" (circles) and "cuadrados" (squares)!

You're {user_age} years old and you're going to be an amazing Spanish artist! 

Are you ready to create colorful masterpieces, {user_name}? 🌈✨""",
                
                "episode_agent_prompt": """¡Hola {user_name}! Welcome to Señorita Sofia's art studio! 🎨

You're {user_age} years old and today you're going to be a Spanish artist!

🎨 TODAY'S CREATION: We're painting a beautiful mural together!
📚 COLOR WORDS: rojo, azul, verde, círculo, cuadrado
🎯 YOUR ARTISTIC MISSION: Learn colors and shapes while creating art!

*Señorita Sofia smiles* "¡Bienvenido {user_name}! Welcome to our art studio!"

Look at all these beautiful colors! "¡Mira los colores!" (Look at the colors!)

This bright color is "rojo" - that means red! Like a beautiful red apple! 🍎

Can you say "rojo" with me, {user_name}? 

"RO-JO!" 

¡Perfecto! Now let's paint something red together! What should we paint, {user_name}? 🎨✨""",
            }
        ]
    
    def _get_mock_episodes(self) -> List[Dict[str, Any]]:
        """Return mock episodes without prompts (for API compatibility)"""
        episodes = self._get_mock_episodes_with_prompts()
        # Remove prompts from the data
        clean_episodes = []
        for ep in episodes:
            clean_ep = ep.copy()
            clean_ep.pop('choice_agent_prompt', None)
            clean_ep.pop('episode_agent_prompt', None)
            clean_episodes.append(clean_ep)
        return clean_episodes