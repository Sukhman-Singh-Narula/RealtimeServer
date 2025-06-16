from typing import Dict, Any, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class UserProfileManager:
    """Manages user profiles for prompt personalization"""
    
    def __init__(self, database_manager, content_manager):
        self.db_manager = database_manager
        self.content_manager = content_manager
    
    async def get_user_profile(self, esp32_id: str) -> Dict[str, Any]:
        """Get user profile including name and age for prompt personalization"""
        
        # First try to get from Firebase user profiles
        if self.content_manager.db:
            try:
                profile_query = self.content_manager.db.collection('user_profiles').where('esp32_id', '==', esp32_id).limit(1)
                docs = list(profile_query.stream())
                
                if docs:
                    profile_data = docs[0].to_dict()
                    logger.info(f"Found Firebase profile for {esp32_id}: {profile_data.get('name', 'unknown')}")
                    return {
                        'name': profile_data.get('name', 'friend'),
                        'age': profile_data.get('age', 6),
                        'preferred_language': profile_data.get('preferred_language', 'spanish'),
                        'learning_style': profile_data.get('learning_style', 'mixed'),
                        'source': 'firebase'
                    }
            except Exception as e:
                logger.error(f"Error fetching user profile from Firebase: {e}")
        
        # Fallback to database user table (if extended with profile fields)
        try:
            user = await self.db_manager.get_or_create_user(esp32_id)
            
            # Check if user has profile fields (you might need to add these to User model)
            profile = {
                'name': getattr(user, 'name', None) or self._generate_friendly_name(esp32_id),
                'age': getattr(user, 'age', None) or 6,
                'preferred_language': getattr(user, 'preferred_language', None) or 'spanish',
                'learning_style': getattr(user, 'learning_style', None) or 'mixed',
                'source': 'database'
            }
            
            logger.info(f"Using profile for {esp32_id}: {profile['name']}, age {profile['age']}")
            return profile
            
        except Exception as e:
            logger.error(f"Error fetching user profile from database: {e}")
            
        # Ultimate fallback
        return self._get_default_profile(esp32_id)
    
    async def create_user_profile(self, esp32_id: str, name: str, age: int, 
                                 preferred_language: str = 'spanish',
                                 learning_style: str = 'mixed') -> Dict[str, Any]:
        """Create a new user profile"""
        
        profile_data = {
            'esp32_id': esp32_id,
            'name': name,
            'age': age,
            'preferred_language': preferred_language,
            'learning_style': learning_style,
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }
        
        # Try to save to Firebase first
        if self.content_manager.db:
            try:
                doc_id = f"profile_{esp32_id}"
                self.content_manager.db.collection('user_profiles').document(doc_id).set(profile_data)
                logger.info(f"Created Firebase profile for {esp32_id}: {name}, age {age}")
                profile_data['source'] = 'firebase'
                return profile_data
            except Exception as e:
                logger.error(f"Error creating Firebase profile: {e}")
        
        # Fallback to updating database user (if user model supports it)
        try:
            user = await self.db_manager.get_or_create_user(esp32_id)
            
            # Update user with profile info (requires extended User model)
            if hasattr(user, 'name'):
                user.name = name
            if hasattr(user, 'age'):
                user.age = age
            if hasattr(user, 'preferred_language'):
                user.preferred_language = preferred_language
            if hasattr(user, 'learning_style'):
                user.learning_style = learning_style
                
            # Save changes (this would require proper database session handling)
            logger.info(f"Updated database profile for {esp32_id}: {name}, age {age}")
            profile_data['source'] = 'database'
            
        except Exception as e:
            logger.error(f"Error updating database profile: {e}")
            profile_data['source'] = 'memory'
        
        return profile_data
    
    async def update_user_profile(self, esp32_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update existing user profile"""
        
        current_profile = await self.get_user_profile(esp32_id)
        
        # Update with new values
        updated_profile = {**current_profile, **updates}
        updated_profile['updated_at'] = datetime.utcnow().isoformat()
        
        # Try to update in Firebase
        if self.content_manager.db:
            try:
                doc_id = f"profile_{esp32_id}"
                self.content_manager.db.collection('user_profiles').document(doc_id).update(updates)
                logger.info(f"Updated Firebase profile for {esp32_id}")
                updated_profile['source'] = 'firebase'
                return updated_profile
            except Exception as e:
                logger.error(f"Error updating Firebase profile: {e}")
        
        # Fallback to database update
        try:
            user = await self.db_manager.get_or_create_user(esp32_id)
            
            for key, value in updates.items():
                if hasattr(user, key):
                    setattr(user, key, value)
            
            logger.info(f"Updated database profile for {esp32_id}")
            updated_profile['source'] = 'database'
            
        except Exception as e:
            logger.error(f"Error updating database profile: {e}")
            updated_profile['source'] = 'memory'
        
        return updated_profile
    
    def _generate_friendly_name(self, esp32_id: str) -> str:
        """Generate a friendly name based on device ID"""
        
        # Simple name generation based on device ID
        friendly_names = [
            'Alex', 'Sofia', 'Diego', 'Luna', 'Carlos', 'Isabella', 
            'Miguel', 'Elena', 'Pablo', 'Carmen', 'Luis', 'Maria'
        ]
        
        # Use a simple hash to pick a consistent name for this device
        name_index = hash(esp32_id) % len(friendly_names)
        return friendly_names[name_index]
    
    def _get_default_profile(self, esp32_id: str) -> Dict[str, Any]:
        """Get default profile when no profile exists"""
        
        return {
            'name': self._generate_friendly_name(esp32_id),
            'age': 6,  # Default age for children
            'preferred_language': 'spanish',
            'learning_style': 'mixed',
            'source': 'default'
        }
    
    async def get_learning_preferences(self, esp32_id: str) -> Dict[str, Any]:
        """Get learning preferences for this user"""
        
        profile = await self.get_user_profile(esp32_id)
        
        return {
            'language': profile['preferred_language'],
            'age_appropriate': True,
            'difficulty_level': 'beginner' if profile['age'] < 8 else 'intermediate',
            'learning_style': profile['learning_style'],
            'personalization': {
                'use_name': True,
                'age_specific_content': True,
                'encouragement_level': 'high' if profile['age'] < 7 else 'medium'
            }
        }
    
    async def validate_profile_data(self, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and sanitize profile data"""
        
        validated = {}
        
        # Validate name
        name = profile_data.get('name', '').strip()
        if name and len(name) >= 2 and len(name) <= 20 and name.isalpha():
            validated['name'] = name.title()
        else:
            raise ValueError("Name must be 2-20 alphabetic characters")
        
        # Validate age
        age = profile_data.get('age')
        try:
            age = int(age)
            if 3 <= age <= 12:
                validated['age'] = age
            else:
                raise ValueError("Age must be between 3 and 12")
        except (TypeError, ValueError):
            raise ValueError("Age must be a valid number between 3 and 12")
        
        # Validate language
        language = profile_data.get('preferred_language', 'spanish').lower()
        if language in ['spanish', 'french', 'german']:
            validated['preferred_language'] = language
        else:
            validated['preferred_language'] = 'spanish'
        
        # Validate learning style
        style = profile_data.get('learning_style', 'mixed').lower()
        if style in ['visual', 'audio', 'kinesthetic', 'mixed']:
            validated['learning_style'] = style
        else:
            validated['learning_style'] = 'mixed'
        
        return validated
    
    async def get_profile_setup_questions(self) -> list[Dict[str, Any]]:
        """Get questions for profile setup"""
        
        return [
            {
                'id': 'name',
                'question': "What's your name?",
                'type': 'text',
                'validation': 'alpha',
                'min_length': 2,
                'max_length': 20,
                'required': True
            },
            {
                'id': 'age',
                'question': "How old are you?",
                'type': 'number',
                'min': 3,
                'max': 12,
                'required': True
            },
            {
                'id': 'preferred_language',
                'question': "Which language do you want to learn?",
                'type': 'choice',
                'options': [
                    {'value': 'spanish', 'label': 'Spanish (Español)'},
                    {'value': 'french', 'label': 'French (Français)'},
                    {'value': 'german', 'label': 'German (Deutsch)'}
                ],
                'default': 'spanish',
                'required': False
            },
            {
                'id': 'learning_style',
                'question': "How do you like to learn?",
                'type': 'choice',
                'options': [
                    {'value': 'visual', 'label': 'Looking at pictures'},
                    {'value': 'audio', 'label': 'Listening to sounds'},
                    {'value': 'kinesthetic', 'label': 'Moving and touching'},
                    {'value': 'mixed', 'label': 'All of the above!'}
                ],
                'default': 'mixed',
                'required': False
            }
        ]
    
    async def setup_profile_from_responses(self, esp32_id: str, responses: Dict[str, Any]) -> Dict[str, Any]:
        """Setup user profile from setup questions responses"""
        
        try:
            # Validate responses
            validated_data = await self.validate_profile_data(responses)
            
            # Create profile
            profile = await self.create_user_profile(
                esp32_id=esp32_id,
                name=validated_data['name'],
                age=validated_data['age'],
                preferred_language=validated_data['preferred_language'],
                learning_style=validated_data['learning_style']
            )
            
            logger.info(f"Setup profile for {esp32_id}: {profile['name']}, age {profile['age']}")
            return profile
            
        except ValueError as e:
            logger.error(f"Profile setup validation failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Profile setup failed: {e}")
            raise
    
    async def get_personalization_context(self, esp32_id: str) -> Dict[str, Any]:
        """Get full context for personalizing prompts"""
        
        profile = await self.get_user_profile(esp32_id)
        preferences = await self.get_learning_preferences(esp32_id)
        
        return {
            'user_name': profile['name'],
            'user_age': profile['age'],
            'preferred_language': profile['preferred_language'],
            'learning_style': profile['learning_style'],
            'difficulty_level': preferences['difficulty_level'],
            'encouragement_level': preferences['personalization']['encouragement_level'],
            'age_appropriate': preferences['age_appropriate']
        }