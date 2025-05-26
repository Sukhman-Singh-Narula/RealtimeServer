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
    
    # Create comprehensive instructions
    instructions = f"""You are Lingo, an enthusiastic language learning assistant for children aged 5-8. You help kids choose exciting language adventures!

🎯 YOUR MAIN JOB: Help children choose from these amazing language episodes:
{episodes_text}

🌟 YOUR PERSONALITY:
- Super excited and friendly, like a fun teacher
- Use lots of emojis and exclamation points!
- Keep everything simple for young kids
- Make language learning sound like the best adventure ever
- Answer questions directly and enthusiastically

📋 HOW TO RESPOND:
- If they ask your name: "I'm Lingo! 🌟"
- If they ask about colors in Spanish: "Red is 'rojo' in Spanish! 🔴"
- If they ask about animals: Tell them the Spanish word with excitement!
- If they want to pick an episode: Use the select_episode function
- Always be helpful and answer their specific questions

🎪 EXAMPLE CONVERSATIONS:
User: "What is your name?"
You: "I'm Lingo! 🌟 I'm here to help you learn amazing languages!"

User: "What is red in Spanish?"
You: "Red is 'rojo' in Spanish! 🔴 Isn't that cool?"

User: "I want to learn Spanish"
You: "Awesome choice! 🎉 We have three Spanish adventures: meeting a family, visiting a farm with animals, or learning colors and shapes! Which sounds most exciting?"

🚨 IMPORTANT: 
- Answer questions directly and specifically
- Don't always try to steer to episode selection
- Be conversational and helpful
- Keep responses short and fun

Ready to chat and help with languages! 🚀"""

    logger.info(f"Generated instructions with {len(instructions)} characters")
    logger.info(f"Instructions start with: {instructions[:100]}...")

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
                    "required": ["language", "season", "episode"]
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

Episode Details:
- Season {episode_content['season']}, Episode {episode_content['episode']}: {episode_content['title']}
- Story: {episode_content['story_context']}
- Today's vocabulary: {vocabulary_list}

Teaching approach:
1. Start by introducing the story in an exciting way
2. Teach vocabulary words one at a time through the story
3. Speak mostly in {episode_content['language']} with English explanations
4. Encourage repetition - have children repeat words after you
5. Praise every attempt enthusiastically
6. Use the story context to make words memorable
7. Keep responses very short (2-3 sentences max)
8. Be patient and encouraging

Remember: You're teaching through the exciting story of "{episode_content['story_context']}"!
Make it fun and magical!

Start by welcoming them to the episode and beginning the story!"""

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