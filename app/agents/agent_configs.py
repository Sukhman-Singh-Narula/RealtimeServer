from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

def get_choice_agent_config(next_episode_info: Dict[str, Any], user_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Generate configuration for the Choice Agent with pre-written prompt from Firebase"""
    
    logger.info(f"Creating choice agent config for next episode: {next_episode_info.get('title', 'Unknown')}")
    
    # Get user details for personalization
    user_name = user_info.get('name', 'friend') if user_info else 'friend'
    user_age = user_info.get('age', 6) if user_info else 6
    
    # Get the pre-written prompt from Firebase or use fallback
    base_prompt = next_episode_info.get('choice_agent_prompt', get_fallback_choice_prompt())
    
    # Simple templating with user data
    personalized_prompt = base_prompt.format(
        user_name=user_name,
        user_age=user_age,
        episode_title=next_episode_info.get('title', 'Spanish Adventure'),
        episode_language=next_episode_info.get('language', 'Spanish').title(),
        episode_season=next_episode_info.get('season', 1),
        episode_number=next_episode_info.get('episode', 1)
    )
    
    config = {
        "name": "choice_agent",
        "instructions": personalized_prompt,
        "voice": "alloy",
        "tools": [
            {
                "type": "function",
                "name": "start_episode",
                "description": "Start the next episode when the child is ready to learn",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ready": {
                            "type": "boolean",
                            "description": "Whether the child is ready to start learning"
                        },
                        "user_message": {
                            "type": "string",
                            "description": "Any message from the child about how they're feeling"
                        }
                    },
                    "required": ["ready"]
                }
            }
        ]
    }
    
    logger.info(f"Choice agent config created for {user_name}, age {user_age}")
    return config

def get_episode_agent_config(episode_content: Dict[str, Any], user_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Generate configuration for Episode Agent using pre-written prompt from Firebase"""
    
    # Get user details for personalization
    user_name = user_info.get('name', 'friend') if user_info else 'friend'
    user_age = user_info.get('age', 6) if user_info else 6
    
    # Get the pre-written episode prompt from Firebase or use fallback
    base_prompt = episode_content.get('episode_agent_prompt', get_fallback_episode_prompt())
    
    # Prepare vocabulary and objectives for templating
    vocabulary_list = ", ".join(episode_content.get('vocabulary', []))
    objectives_list = ", ".join(episode_content.get('learning_objectives', []))
    
    # Simple templating with episode and user data
    personalized_prompt = base_prompt.format(
        user_name=user_name,
        user_age=user_age,
        episode_title=episode_content.get('title', 'Spanish Adventure'),
        episode_language=episode_content.get('language', 'Spanish').title(),
        episode_season=episode_content.get('season', 1),
        episode_number=episode_content.get('episode', 1),
        story_context=episode_content.get('story_context', 'A fun learning adventure'),
        vocabulary_list=vocabulary_list,
        objectives_list=objectives_list,
        difficulty=episode_content.get('difficulty', 'beginner')
    )
    
    return {
        "name": f"episode_agent_{episode_content.get('language')}_{episode_content.get('season')}_{episode_content.get('episode')}",
        "instructions": personalized_prompt,
        "voice": "nova",
        "tools": [
            {
                "type": "function",
                "name": "mark_vocabulary_learned",
                "description": "Mark a vocabulary word as learned when child successfully repeats it",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "word": {
                            "type": "string",
                            "description": "The vocabulary word that was learned"
                        },
                        "confidence": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                            "description": "How well the child learned the word"
                        }
                    },
                    "required": ["word", "confidence"]
                }
            },
            {
                "type": "function", 
                "name": "complete_episode",
                "description": "Mark the episode as completed when all vocabulary has been taught",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "words_learned": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of words successfully learned in this episode"
                        },
                        "completion_time": {
                            "type": "integer",
                            "description": "Time taken to complete episode in seconds (optional)"
                        }
                    },
                    "required": ["words_learned"]
                }
            },
            {
                "type": "function",
                "name": "practice_word",
                "description": "When child practices a word they've already learned",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "word": {
                            "type": "string",
                            "description": "The word being practiced"
                        },
                        "success": {
                            "type": "boolean",
                            "description": "Whether the practice attempt was successful"
                        }
                    },
                    "required": ["word", "success"]
                }
            }
        ]
    }

def get_fallback_choice_prompt() -> str:
    """Fallback choice agent prompt if not found in Firebase"""
    return """You are Lingo, a friendly language learning assistant for children aged 5-8.

Hello {user_name}! I'm so excited to see you today! You're {user_age} years old and doing amazing with your learning journey.

🎯 YOUR MISSION:
Your next adventure is "{episode_title}" in {episode_language}! This is Season {episode_season}, Episode {episode_number}.

🌟 HOW TO HELP:
1. First, ask "{user_name}, how are you feeling today?" and listen to their response
2. Respond warmly to what they tell you
3. Then explain the exciting episode waiting for them
4. When they're ready, use the start_episode function to begin!

🎪 YOUR PERSONALITY:
- Super excited and encouraging
- Use simple words perfect for a {user_age}-year-old
- Lots of emojis and excitement!
- Make them feel special and capable

Remember: You're helping {user_name} get ready for their next learning adventure. Be warm, encouraging, and fun!"""

def get_fallback_episode_prompt() -> str:
    """Fallback episode agent prompt if not found in Firebase"""
    return """You are a friendly {episode_language} teacher for {user_name}, who is {user_age} years old.

🎓 TODAY'S ADVENTURE: {episode_title}
📖 STORY: {story_context}
📚 WORDS TO LEARN: {vocabulary_list}
🎯 LEARNING GOALS: {objectives_list}

🗣️ TEACHING STYLE:
- Speak mostly in {episode_language} with English explanations
- Example: "This is 'gato' - that means cat! Can you say 'gato', {user_name}?"
- Keep everything simple for {user_name} who is {user_age} years old
- Celebrate every attempt: "¡Muy bien, {user_name}!" "Excellent!"

🎭 YOUR APPROACH:
1. Welcome {user_name} to this specific episode with excitement
2. Set up the story context in a fun way
3. Teach each word through the story naturally
4. Have {user_name} repeat each word 2-3 times
5. Use mark_vocabulary_learned when they learn a word well
6. When all words are learned, use complete_episode

🌟 REMEMBER:
- {user_name} is {user_age} years old - keep everything age-appropriate
- Make learning feel like a magical story adventure
- Be patient and encouraging always
- Celebrate every small success!"""