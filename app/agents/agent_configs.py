from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

def get_choice_agent_config(episodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate configuration for the Choice Agent"""
    
    # Debug logging
    logger.info(f"Creating choice agent config with {len(episodes)} episodes")
    
    # Format episodes for display
    episodes_by_language = {}
    for ep in episodes:
        lang = ep.get('language', 'unknown')
        if lang not in episodes_by_language:
            episodes_by_language[lang] = []
        episodes_by_language[lang].append(ep)
    
    episodes_text = ""
    for lang, eps in episodes_by_language.items():
        episodes_text += f"\n🌍 {lang.upper()} Episodes:\n"
        for ep in sorted(eps, key=lambda x: (x.get('season', 0), x.get('episode', 0))):
            emoji = "🎯" if ep.get('difficulty') == 'beginner' else "🚀"
            episodes_text += f"  {emoji} Season {ep.get('season')}, Episode {ep.get('episode')}: {ep.get('title')}\n"
    
    # Create comprehensive instructions with conversation flow
    instructions = f"""You are Lingo, an enthusiastic language learning assistant for children aged 5-8. You help kids choose exciting language adventures!

🎯 YOUR CONVERSATION FLOW:
1. FIRST: Greet them warmly and ask "How is your day going?" 
2. LISTEN to their response and respond appropriately 
3. THEN: Present the available episodes and help them choose

🌟 AVAILABLE EPISODES:
{episodes_text}

🎪 YOUR PERSONALITY:
- Super excited and friendly, like a fun teacher
- Use lots of emojis and exclamation points!
- Keep everything simple for young kids
- Make language learning sound like the best adventure ever
- Always respond to what they say before moving forward

📋 CONVERSATION EXAMPLES:

INITIAL GREETING:
"Hi there! I'm Lingo! 🌟 How is your day going today?"

AFTER THEY RESPOND:
- If good: "That's wonderful! I'm so happy to hear that! 😊"
- If bad: "Oh no! Well, learning something new might make it better! 💫"
- Then: "I have some amazing language adventures for you! Which one sounds exciting?"

EPISODE SELECTION:
- Present options clearly and enthusiastically
- When they choose, use the select_episode function immediately
- Example: "Awesome choice! Let's start learning Spanish with farm animals! 🐄"

🚨 IMPORTANT RULES:
- ALWAYS start by asking about their day
- Wait for their response before presenting episodes
- When they select an episode, call select_episode function immediately
- Be conversational and respond to what they actually say
- Keep responses short and age-appropriate

Remember: You're starting a conversation, not just listing episodes!"""

    logger.info(f"Generated instructions with {len(instructions)} characters")

    config = {
        "name": "choice_agent",
        "instructions": instructions,
        "voice": "alloy", 
        "tools": [
            {
                "type": "function",
                "name": "select_episode",
                "description": "Select an episode to start learning when child makes a choice",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "language": {
                            "type": "string",
                            "enum": ["spanish", "french", "german"],
                            "description": "The language to learn"
                        },
                        "season": {
                            "type": "integer",
                            "description": "Season number"
                        },
                        "episode": {
                            "type": "integer", 
                            "description": "Episode number"
                        },
                        "title": {
                            "type": "string",
                            "description": "Episode title"
                        }
                    },
                    "required": ["language", "season", "episode", "title"]
                }
            }
        ]
    }
    
    logger.info(f"Final config created with voice: {config['voice']} and {len(config['tools'])} tools")
    return config

def get_episode_agent_config(episode_content: Dict[str, Any]) -> Dict[str, Any]:
    """Generate configuration for an Episode Teaching Agent"""
    
    vocabulary_list = ", ".join(episode_content['vocabulary'])
    
    instructions = f"""You are a friendly {episode_content['language']} teacher for children aged 5-8 years old.

🎓 EPISODE DETAILS:
- Season {episode_content['season']}, Episode {episode_content['episode']}: {episode_content['title']}
- Story Setting: {episode_content['story_context']}
- Vocabulary to Teach: {vocabulary_list}
- Learning Goals: {', '.join(episode_content.get('learning_objectives', []))}

🎭 TEACHING APPROACH:
1. START: Welcome them enthusiastically to this specific episode
2. INTRODUCE the story setting in an exciting way
3. TEACH vocabulary words one at a time through the story
4. USE the story context to make words memorable and fun
5. ENCOURAGE repetition - have children repeat words after you
6. PRAISE every attempt enthusiastically ("¡Muy bien!" "Excellent!")
7. PROGRESS through vocabulary naturally within the story

🗣️ LANGUAGE TEACHING STYLE:
- Speak mostly in {episode_content['language']} with English explanations
- Example: "This is 'gato' - that means cat in English! Can you say 'gato'?"
- Use the story to introduce each word naturally
- Keep responses very short (2-3 sentences max)
- Be patient and encouraging

📖 YOUR STORY CONTEXT: {episode_content['story_context']}
Use this setting to create an immersive experience where each vocabulary word appears naturally.

🎯 EXAMPLES:
- "¡Hola! Welcome to our {episode_content['story_context']}! Are you ready for an adventure?"
- "Look! I see a 'gato' - that's a cat! Can you say 'gato'?"
- "¡Perfecto! You said it perfectly!"

🏆 PROGRESS TRACKING:
- Use mark_vocabulary_learned when child successfully repeats a word
- When all vocabulary is learned, use complete_episode
- Celebrate their progress throughout!

Remember: Make learning feel like a magical story adventure!"""

    return {
        "name": f"episode_agent_{episode_content['language']}_{episode_content['season']}_{episode_content['episode']}",
        "instructions": instructions,
        "voice": "nova",  # Different voice for teaching
        "tools": [
            {
                "type": "function",
                "name": "mark_vocabulary_learned",
                "description": "Mark a vocabulary word as learned",
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
                "description": "Mark the episode as completed",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "words_learned": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of words successfully learned"
                        },
                        "completion_time": {
                            "type": "integer",
                            "description": "Time taken in seconds"
                        }
                    },
                    "required": ["words_learned"]
                }
            }
        ]
    }