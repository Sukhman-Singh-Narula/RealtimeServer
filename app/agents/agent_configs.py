from typing import List, Dict, Any

def get_choice_agent_config(episodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate configuration for the Choice Agent"""
    
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
    
    return {
        "name": "choice_agent",
        "instructions": f"""You are a friendly learning assistant helping children choose language episodes.

Your personality:
- Warm, enthusiastic, and encouraging
- Use simple language appropriate for 5-8 year olds
- Include fun emojis to make choices engaging
- Keep responses short and exciting

Available episodes:
{episodes_text}

When a child selects an episode, call the select_episode function.
Always be encouraging and make learning sound like an adventure!""",
        "voice": "alloy",
        "tools": [
            {
                "type": "function",
                "name": "select_episode",
                "description": "Select an episode to start learning",
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

def get_episode_agent_config(episode_content: Dict[str, Any]) -> Dict[str, Any]:
    """Generate configuration for an Episode Teaching Agent"""
    
    vocabulary_list = ", ".join(episode_content['vocabulary'])
    
    return {
        "name": f"episode_agent_{episode_content['language']}_{episode_content['season']}_{episode_content['episode']}",
        "instructions": f"""You are a friendly {episode_content['language']} teacher for children aged 5-8.

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
Make it fun and magical!""",
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