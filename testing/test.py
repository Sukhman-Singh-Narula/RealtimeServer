#!/usr/bin/env python3
"""
ESP32 Language Learning - Simplified System Test

Tests the simplified system where:
1. Prompts are stored in Firebase
2. Only name and age are templated into prompts
3. No dynamic prompt generation
4. Simple episode progression

Usage:
    python simplified_system_test.py [command] [options]

Commands:
    test-profiles       Test user profile management
    test-prompts        Test prompt personalization  
    test-episodes       Test episode flow
    test-full-flow     Test complete learning flow
    setup-demo-user     Setup a demo user profile
"""

import asyncio
import json
import logging
import argparse
import httpx
import websockets
from datetime import datetime
from typing import Dict, Any, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SimplifiedSystemTester:
    """Test the simplified prompt system"""
    
    def __init__(self, base_url: str = "http://localhost:8000", ws_url: str = "ws://localhost:8000"):
        self.base_url = base_url
        self.ws_url = ws_url
        self.test_device = "TEST_SIMPLIFIED_001"
        
    async def test_user_profiles(self) -> Dict[str, Any]:
        """Test user profile management system"""
        logger.info("🧪 Testing user profile management...")
        
        async with httpx.AsyncClient() as client:
            results = {
                "setup_questions": False,
                "create_profile": False,
                "get_profile": False,
                "update_profile": False,
                "personalization_context": False
            }
            
            try:
                # 1. Test setup questions
                logger.info("  📋 Testing setup questions...")
                response = await client.get(f"{self.base_url}/api/profiles/setup-questions")
                if response.status_code == 200:
                    questions = response.json()
                    logger.info(f"     ✅ Got {len(questions)} setup questions")
                    results["setup_questions"] = True
                    
                    # Print sample questions
                    for q in questions[:2]:
                        logger.info(f"     Q: {q['question']} (type: {q['type']})")
                else:
                    logger.error(f"     ❌ Failed to get setup questions: {response.status_code}")
                
                # 2. Test creating a profile
                logger.info("  👤 Testing profile creation...")
                profile_data = {
                    "name": "Sofia",
                    "age": 7,
                    "preferred_language": "spanish",
                    "learning_style": "visual"
                }
                
                response = await client.post(
                    f"{self.base_url}/api/profiles/{self.test_device}",
                    json=profile_data
                )
                
                if response.status_code == 200:
                    profile = response.json()
                    logger.info(f"     ✅ Created profile: {profile['name']}, age {profile['age']}")
                    results["create_profile"] = True
                else:
                    logger.error(f"     ❌ Failed to create profile: {response.status_code}")
                
                # 3. Test getting profile
                logger.info("  📖 Testing profile retrieval...")
                response = await client.get(f"{self.base_url}/api/profiles/{self.test_device}")
                
                if response.status_code == 200:
                    profile = response.json()
                    logger.info(f"     ✅ Retrieved profile: {profile['name']}, age {profile['age']}")
                    results["get_profile"] = True
                else:
                    logger.error(f"     ❌ Failed to get profile: {response.status_code}")
                
                # 4. Test updating profile
                logger.info("  ✏️ Testing profile update...")
                update_data = {"age": 8}
                
                response = await client.put(
                    f"{self.base_url}/api/profiles/{self.test_device}",
                    json=update_data
                )
                
                if response.status_code == 200:
                    profile = response.json()
                    logger.info(f"     ✅ Updated profile: age now {profile['age']}")
                    results["update_profile"] = True
                else:
                    logger.error(f"     ❌ Failed to update profile: {response.status_code}")
                
                # 5. Test personalization context
                logger.info("  🎯 Testing personalization context...")
                response = await client.get(f"{self.base_url}/api/profiles/{self.test_device}/personalization-context")
                
                if response.status_code == 200:
                    context = response.json()
                    logger.info(f"     ✅ Got context: {context['user_name']}, age {context['user_age']}")
                    results["personalization_context"] = True
                else:
                    logger.error(f"     ❌ Failed to get context: {response.status_code}")
                
            except Exception as e:
                logger.error(f"Error in profile testing: {e}")
        
        success_count = sum(results.values())
        logger.info(f"📊 Profile tests: {success_count}/5 passed")
        
        return {
            "success": success_count == 5,
            "details": results,
            "passed": success_count,
            "total": 5
        }
    
    async def test_prompt_personalization(self) -> Dict[str, Any]:
        """Test prompt personalization with user data"""
        logger.info("🧪 Testing prompt personalization...")
        
        async with httpx.AsyncClient() as client:
            results = {
                "firebase_prompts": False,
                "personalization_applied": False,
                "template_variables": False
            }
            
            try:
                # First ensure we have a profile
                await self._ensure_test_profile(client)
                
                # Test getting personalized prompts for an episode
                logger.info("  📝 Testing prompt personalization...")
                response = await client.get(
                    f"{self.base_url}/api/profiles/{self.test_device}/test-prompts/spanish/1/1"
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Check if we have original prompts from Firebase
                    original_choice = data.get('original_prompts', {}).get('choice_agent_prompt', '')
                    if original_choice and '{user_name}' in original_choice:
                        logger.info("     ✅ Firebase prompts contain template variables")
                        results["firebase_prompts"] = True
                    
                    # Check if personalization was applied
                    personalized_choice = data.get('personalized_prompts', {}).get('choice_agent_prompt', '')
                    if personalized_choice and '{user_name}' not in personalized_choice:
                        logger.info("     ✅ Template variables were replaced")
                        results["personalization_applied"] = True
                        
                        # Show example of personalization
                        context = data.get('personalization_context', {})
                        logger.info(f"     📋 Context: {context['user_name']}, age {context['user_age']}")
                        
                        # Show snippet of personalized prompt
                        snippet = personalized_choice[:100] + "..." if len(personalized_choice) > 100 else personalized_choice
                        logger.info(f"     💬 Snippet: {snippet}")
                    
                    # Check template variables
                    if data.get('personalization_context'):
                        context = data['personalization_context']
                        required_vars = ['user_name', 'user_age']
                        has_all_vars = all(var in context for var in required_vars)
                        if has_all_vars:
                            logger.info(f"     ✅ All required template variables present")
                            results["template_variables"] = True
                
                else:
                    logger.error(f"     ❌ Failed to get personalized prompts: {response.status_code}")
                
            except Exception as e:
                logger.error(f"Error in prompt testing: {e}")
        
        success_count = sum(results.values())
        logger.info(f"📊 Prompt tests: {success_count}/3 passed")
        
        return {
            "success": success_count == 3,
            "details": results,
            "passed": success_count,
            "total": 3
        }
    
    async def test_episode_flow(self) -> Dict[str, Any]:
        """Test the simplified episode flow"""
        logger.info("🧪 Testing episode flow...")
        
        async with httpx.AsyncClient() as client:
            results = {
                "next_episode_fetch": False,
                "choice_agent_ready": False,
                "episode_agent_ready": False
            }
            
            try:
                # Ensure test profile
                await self._ensure_test_profile(client)
                
                # 1. Test getting next episode
                logger.info("  🎯 Testing next episode retrieval...")
                response = await client.get(
                    f"{self.base_url}/api/profiles/{self.test_device}/next-episode-with-prompts"
                )
                
                if response.status_code == 200:
                    data = response.json()
                    episode = data.get('episode', {})
                    
                    if episode and data.get('personalization_applied'):
                        logger.info(f"     ✅ Next episode: {episode.get('title')} (S{episode.get('season')}E{episode.get('episode')})")
                        results["next_episode_fetch"] = True
                        
                        # Check if choice agent prompt is ready
                        if 'choice_agent_prompt' in episode:
                            choice_prompt = episode['choice_agent_prompt']
                            # Should not contain template variables after personalization
                            if '{user_name}' not in choice_prompt and '{user_age}' not in choice_prompt:
                                logger.info("     ✅ Choice agent prompt personalized")
                                results["choice_agent_ready"] = True
                            else:
                                logger.warning("     ⚠️ Choice agent prompt still has template variables")
                        
                        # Check if episode agent prompt is ready
                        if 'episode_agent_prompt' in episode:
                            episode_prompt = episode['episode_agent_prompt']
                            if '{user_name}' not in episode_prompt and '{user_age}' not in episode_prompt:
                                logger.info("     ✅ Episode agent prompt personalized")
                                results["episode_agent_ready"] = True
                            else:
                                logger.warning("     ⚠️ Episode agent prompt still has template variables")
                else:
                    logger.error(f"     ❌ Failed to get next episode: {response.status_code}")
                
            except Exception as e:
                logger.error(f"Error in episode flow testing: {e}")
        
        success_count = sum(results.values())
        logger.info(f"📊 Episode flow tests: {success_count}/3 passed")
        
        return {
            "success": success_count == 3,
            "details": results,
            "passed": success_count,
            "total": 3
        }
    
    async def test_full_learning_flow(self) -> Dict[str, Any]:
        """Test the complete learning flow with WebSocket"""
        logger.info("🧪 Testing full learning flow...")
        
        results = {
            "websocket_connection": False,
            "choice_agent_start": False,
            "episode_transition": False,
            "learning_completion": False
        }
        
        try:
            # Ensure test profile
            async with httpx.AsyncClient() as client:
                await self._ensure_test_profile(client)
            
            # Test WebSocket connection with simplified system
            logger.info("  🔌 Testing WebSocket connection...")
            uri = f"{self.ws_url}/upload/{self.test_device}"
            
            async with websockets.connect(uri, timeout=15) as websocket:
                logger.info("     ✅ WebSocket connected")
                results["websocket_connection"] = True
                
                # Wait for welcome message
                try:
                    welcome_msg = await asyncio.wait_for(websocket.recv(), timeout=10)
                    welcome_data = json.loads(welcome_msg)
                    
                    if welcome_data.get('type') == 'connected':
                        logger.info(f"     ✅ Welcome message: {welcome_data.get('message', '')[:50]}...")
                        next_episode = welcome_data.get('next_episode', {})
                        if next_episode:
                            logger.info(f"     📚 Next episode ready: {next_episode.get('title')}")
                            results["choice_agent_start"] = True
                    
                except asyncio.TimeoutError:
                    logger.warning("     ⚠️ No welcome message received")
                
                # Send a simple interaction to test the choice agent
                logger.info("  💬 Testing choice agent interaction...")
                test_message = {
                    "type": "text",
                    "text": "I'm feeling great today! I'm ready to learn Spanish!",
                    "esp32_id": self.test_device
                }
                
                await websocket.send(json.dumps(test_message))
                
                # Listen for responses
                response_count = 0
                agent_responses = []
                
                try:
                    while response_count < 5:  # Listen for up to 5 responses
                        response = await asyncio.wait_for(websocket.recv(), timeout=5)
                        response_data = json.loads(response)
                        agent_responses.append(response_data)
                        response_count += 1
                        
                        msg_type = response_data.get('type')
                        logger.info(f"     📨 Received: {msg_type}")
                        
                        # Check for agent transitions
                        if msg_type == 'agent_switched':
                            new_agent = response_data.get('new_agent')
                            if new_agent == 'episode':
                                logger.info("     ✅ Transitioned to episode agent")
                                results["episode_transition"] = True
                        
                        # Check for learning progress
                        if msg_type == 'response_complete':
                            session_stats = response_data.get('session_stats', {})
                            if session_stats.get('words_learned_this_session', 0) > 0:
                                logger.info("     ✅ Learning progress detected")
                                results["learning_completion"] = True
                
                except asyncio.TimeoutError:
                    logger.info("     ⏰ Response timeout (expected)")
                
                logger.info(f"     📊 Collected {len(agent_responses)} responses")
                
        except Exception as e:
            logger.error(f"Error in full flow testing: {e}")
        
        success_count = sum(results.values())
        logger.info(f"📊 Full flow tests: {success_count}/4 passed")
        
        return {
            "success": success_count >= 2,  # At least connection and choice agent
            "details": results,
            "passed": success_count,
            "total": 4
        }
    
    async def setup_demo_user(self, name: str = "Sofia", age: int = 7) -> Dict[str, Any]:
        """Setup a demo user profile for testing"""
        logger.info(f"👤 Setting up demo user: {name}, age {age}")
        
        async with httpx.AsyncClient() as client:
            try:
                profile_data = {
                    "name": name,
                    "age": age,
                    "preferred_language": "spanish",
                    "learning_style": "visual"
                }
                
                response = await client.post(
                    f"{self.base_url}/api/profiles/{self.test_device}",
                    json=profile_data
                )
                
                if response.status_code == 200:
                    profile = response.json()
                    logger.info(f"✅ Demo user created: {profile['name']}, age {profile['age']}")
                    
                    # Test the personalization
                    response = await client.get(
                        f"{self.base_url}/api/profiles/{self.test_device}/test-prompts/spanish/1/1"
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        prompt_snippet = data.get('personalized_prompts', {}).get('choice_agent_prompt', '')[:150]
                        logger.info(f"📝 Prompt preview: {prompt_snippet}...")
                    
                    return {
                        "success": True,
                        "profile": profile,
                        "device_id": self.test_device
                    }
                else:
                    logger.error(f"❌ Failed to create demo user: {response.status_code}")
                    return {"success": False, "error": f"HTTP {response.status_code}"}
                    
            except Exception as e:
                logger.error(f"❌ Error setting up demo user: {e}")
                return {"success": False, "error": str(e)}
    
    async def _ensure_test_profile(self, client: httpx.AsyncClient):
        """Ensure test profile exists"""
        try:
            # Check if profile exists
            response = await client.get(f"{self.base_url}/api/profiles/{self.test_device}")
            
            if response.status_code != 200:
                # Create test profile
                profile_data = {
                    "name": "TestUser",
                    "age": 7,
                    "preferred_language": "spanish",
                    "learning_style": "mixed"
                }
                
                response = await client.post(
                    f"{self.base_url}/api/profiles/{self.test_device}",
                    json=profile_data
                )
                
                if response.status_code == 200:
                    logger.info(f"✅ Created test profile for {self.test_device}")
                else:
                    logger.warning(f"⚠️ Could not create test profile: {response.status_code}")
                    
        except Exception as e:
            logger.warning(f"⚠️ Error ensuring test profile: {e}")
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all simplified system tests"""
        logger.info("🚀 Running all simplified system tests...")
        logger.info("=" * 60)
        
        test_results = {}
        
        # Test categories
        tests = [
            ("User Profiles", self.test_user_profiles),
            ("Prompt Personalization", self.test_prompt_personalization),
            ("Episode Flow", self.test_episode_flow),
            ("Full Learning Flow", self.test_full_learning_flow)
        ]
        
        for test_name, test_func in tests:
            logger.info(f"\n🧪 Running: {test_name}")
            try:
                result = await test_func()
                test_results[test_name] = result
                status = "✅ PASSED" if result["success"] else "❌ FAILED"
                logger.info(f"{status} - {result['passed']}/{result['total']} tests passed")
            except Exception as e:
                test_results[test_name] = {
                    "success": False,
                    "error": str(e),
                    "passed": 0,
                    "total": 1
                }
                logger.error(f"❌ ERROR in {test_name}: {e}")
        
        # Calculate overall results
        total_passed = sum(result.get('passed', 0) for result in test_results.values())
        total_tests = sum(result.get('total', 0) for result in test_results.values())
        overall_success = sum(1 for result in test_results.values() if result.get('success', False))
        
        logger.info("\n" + "=" * 60)
        logger.info("📊 SIMPLIFIED SYSTEM TEST SUMMARY")
        logger.info(f"✅ Test Categories Passed: {overall_success}/{len(tests)}")
        logger.info(f"✅ Individual Tests Passed: {total_passed}/{total_tests}")
        logger.info(f"📈 Success Rate: {(total_passed / total_tests * 100):.1f}%")
        
        return {
            "overall_success": overall_success == len(tests),
            "categories_passed": overall_success,
            "total_categories": len(tests),
            "tests_passed": total_passed,
            "total_tests": total_tests,
            "success_rate": total_passed / total_tests if total_tests > 0 else 0,
            "details": test_results
        }

async def main():
    """Main test function"""
    parser = argparse.ArgumentParser(description="ESP32 Language Learning Simplified System Tests")
    parser.add_argument(
        "command",
        choices=["test-profiles", "test-prompts", "test-episodes", "test-full-flow", "setup-demo-user", "test-all"],
        help="Test command to run"
    )
    parser.add_argument("--base-url", default="http://localhost:8000", help="Base URL for API")
    parser.add_argument("--ws-url", default="ws://localhost:8000", help="WebSocket URL")
    parser.add_argument("--device-id", default="TEST_SIMPLIFIED_001", help="Test device ID")
    parser.add_argument("--name", default="Sofia", help="Demo user name")
    parser.add_argument("--age", type=int, default=7, help="Demo user age")
    parser.add_argument("--output", help="Output file for test results")
    
    args = parser.parse_args()
    
    # Create test suite
    tester = SimplifiedSystemTester(args.base_url, args.ws_url)
    tester.test_device = args.device_id
    
    logger.info("🧪 ESP32 Language Learning - Simplified System Tests")
    logger.info("=" * 60)
    logger.info(f"🎯 Testing simplified prompt system with Firebase storage")
    logger.info(f"📱 Device ID: {args.device_id}")
    logger.info(f"🌐 API URL: {args.base_url}")
    logger.info("")
    
    # Run specified command
    if args.command == "test-all":
        results = await tester.run_all_tests()
    elif args.command == "test-profiles":
        results = await tester.test_user_profiles()
    elif args.command == "test-prompts":
        results = await tester.test_prompt_personalization()
    elif args.command == "test-episodes":
        results = await tester.test_episode_flow()
    elif args.command == "test-full-flow":
        results = await tester.test_full_learning_flow()
    elif args.command == "setup-demo-user":
        results = await tester.setup_demo_user(args.name, args.age)
    
    # Output results
    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"📄 Results saved to {args.output}")
    else:
        print("\n" + "=" * 60)
        print("📋 DETAILED RESULTS:")
        print(json.dumps(results, indent=2))

if __name__ == "__main__":
    asyncio.run(main())