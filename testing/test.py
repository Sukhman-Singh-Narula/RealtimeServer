import asyncio
import websockets
import json
import base64
import logging
from datetime import datetime
import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TestESP32Client:
    def __init__(self, esp32_id="TEST_DEVICE_001"):
        self.esp32_id = esp32_id
        # Fix URI to match your actual WebSocket endpoint
        self.uri = f"ws://localhost:8000/upload/{esp32_id}"
        self.websocket = None
        self.conversation_active = False
        
    async def connect(self):
        """Connect to the server"""
        logger.info(f"Connecting to {self.uri}")
        try:
            self.websocket = await websockets.connect(self.uri)
            logger.info("Connected successfully")
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            raise
        
    async def send_text_message(self, text):
        """Send a text message to the server"""
        message = {
            "type": "text",
            "text": text
        }
        await self.websocket.send(json.dumps(message))
        logger.info(f"Sent text: {text}")
        
    async def generate_test_audio(self, frequency=440, duration=2.0, sample_rate=16000):
        """Generate test audio (sine wave) instead of silence"""
        samples = int(sample_rate * duration)
        t = np.linspace(0, duration, samples, False)
        # Generate a sine wave
        wave = np.sin(frequency * 2 * np.pi * t)
        # Convert to 16-bit PCM
        audio_data = (wave * 32767).astype(np.int16)
        return audio_data.tobytes()
        
    async def send_binary_audio(self, duration_seconds=2):
        """Send test audio as binary data"""
        logger.info(f"Generating and sending {duration_seconds} seconds of test audio...")
        
        # Generate test audio
        audio_bytes = await self.generate_test_audio(frequency=440, duration=duration_seconds)
        
        # Send as binary WebSocket message
        await self.websocket.send(audio_bytes)
        logger.info(f"Sent binary audio: {len(audio_bytes)} bytes")
        
    async def send_hex_audio(self, duration_seconds=2):
        """Send test audio as hex-encoded JSON message"""
        logger.info(f"Generating and sending {duration_seconds} seconds of hex audio...")
        
        # Generate test audio
        audio_bytes = await self.generate_test_audio(frequency=440, duration=duration_seconds)
        
        message = {
            "type": "audio",
            "audio_data": audio_bytes.hex()
        }
        
        await self.websocket.send(json.dumps(message))
        logger.info(f"Sent hex audio: {len(audio_bytes)} bytes")
        
    async def start_conversation(self):
        """Start conversation"""
        message = {"type": "start_conversation"}
        await self.websocket.send(json.dumps(message))
        logger.info("Started conversation")
        
    async def end_conversation(self):
        """End conversation"""
        message = {"type": "end_conversation"}
        await self.websocket.send(json.dumps(message))
        logger.info("Ended conversation")
        
    async def listen_for_messages(self):
        """Listen for messages from server"""
        try:
            async for message in self.websocket:
                if isinstance(message, str):
                    # JSON message
                    try:
                        data = json.loads(message)
                        await self.handle_json_message(data)
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse JSON: {message[:100]}")
                elif isinstance(message, bytes):
                    # Binary message (audio)
                    logger.info(f"Received binary audio: {len(message)} bytes")
                else:
                    logger.warning(f"Unknown message type: {type(message)}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info("Connection closed by server")
        except Exception as e:
            logger.error(f"Error in message listener: {e}")
            
    async def handle_json_message(self, data):
        """Handle JSON messages from server"""
        msg_type = data.get('type', 'unknown')
        
        logger.info(f"Received message type: {msg_type}")
        
        if msg_type == 'connected':
            logger.info(f"Server welcome: {data.get('message', '')}")
            self.conversation_active = True
            
        elif msg_type == 'audio_response':
            audio_data = data.get('audio_data', '')
            if audio_data:
                try:
                    audio_bytes = base64.b64decode(audio_data)
                    logger.info(f"Received audio response: {len(audio_bytes)} bytes")
                except Exception as e:
                    logger.error(f"Failed to decode audio: {e}")
            else:
                logger.warning("Received empty audio response")
                
        elif msg_type == 'audio_start':
            logger.info("Audio stream started from server")
            
        elif msg_type == 'audio_complete':
            logger.info("Audio stream completed from server")
            
        elif msg_type == 'text_response':
            text = data.get('text', '')
            is_final = data.get('is_final', False)
            logger.info(f"Text {'(final)' if is_final else '(partial)'}: {text}")
            
        elif msg_type == 'agent_switched':
            logger.info(f"Agent switched to: {data.get('new_agent', 'unknown')}")
            episode_info = data.get('episode_info', {})
            if episode_info:
                logger.info(f"Episode: {episode_info.get('title', 'Unknown')}")
                
        elif msg_type == 'response_complete':
            status = data.get('status', 'unknown')
            logger.info(f"Response completed with status: {status}")
            
        elif msg_type == 'error':
            logger.error(f"Server error: {data.get('message', 'Unknown error')}")
            
        elif msg_type == 'heartbeat_ack':
            logger.debug("Heartbeat acknowledged")
            
        else:
            logger.debug(f"Full message: {json.dumps(data, indent=2)}")
            
    async def send_heartbeat(self):
        """Send periodic heartbeat"""
        while self.websocket and not self.websocket.closed:
            await asyncio.sleep(30)
            try:
                message = {"type": "heartbeat"}
                await self.websocket.send(json.dumps(message))
                logger.debug("Sent heartbeat")
            except Exception as e:
                logger.error(f"Failed to send heartbeat: {e}")
                break
                
    async def interactive_test(self):
        """Interactive test mode"""
        logger.info("Interactive mode - Type commands:")
        logger.info("  'text <message>' - Send text message")
        logger.info("  'audio' - Send test audio")
        logger.info("  'start' - Start conversation")
        logger.info("  'end' - End conversation") 
        logger.info("  'quit' - Exit")
        
        while True:
            try:
                command = input("\n> ").strip()
                
                if command == 'quit':
                    break
                elif command == 'start':
                    await self.start_conversation()
                elif command == 'end':
                    await self.end_conversation()
                elif command == 'audio':
                    await self.send_binary_audio(2)
                elif command.startswith('text '):
                    message = command[5:]
                    await self.send_text_message(message)
                else:
                    logger.info("Unknown command")
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Error processing command: {e}")
                
    async def automated_test(self):
        """Automated test scenario"""
        logger.info("Running automated test scenario...")
        
        # Wait for initial connection
        await asyncio.sleep(2)
        
        # Test 1: Send greeting text
        await self.send_text_message("Hello, I want to learn Spanish!")
        await asyncio.sleep(3)
        
        # Test 2: Send audio
        await self.send_binary_audio(2)
        await asyncio.sleep(2)
        
        # Test 3: Make episode selection
        await self.send_text_message("I want to learn about farm animals")
        await asyncio.sleep(5)
        
        # Test 4: Try to repeat vocabulary
        await self.send_text_message("gato")
        await asyncio.sleep(3)
        
        logger.info("Automated test completed")
        
    async def run_test(self, interactive=False):
        """Run the test client"""
        try:
            # Connect to server
            await self.connect()
            
            # Start heartbeat task
            heartbeat_task = asyncio.create_task(self.send_heartbeat())
            
            # Start listening for messages
            listen_task = asyncio.create_task(self.listen_for_messages())
            
            if interactive:
                # Run interactive test
                await self.interactive_test()
            else:
                # Run automated test
                await self.automated_test()
                
                # Keep listening for a bit more
                logger.info("Listening for final responses...")
                await asyncio.sleep(10)
            
        except KeyboardInterrupt:
            logger.info("Stopping test client...")
        except Exception as e:
            logger.error(f"Test failed: {e}")
        finally:
            # Cleanup
            if heartbeat_task and not heartbeat_task.done():
                heartbeat_task.cancel()
            if listen_task and not listen_task.done():
                listen_task.cancel()
                
            if self.websocket:
                await self.websocket.close()
                logger.info("Connection closed")

async def main():
    """Main function"""
    import sys
    
    # Check if interactive mode requested
    interactive = len(sys.argv) > 1 and sys.argv[1] == 'interactive'
    
    # Test with properly formatted device ID
    client = TestESP32Client("TEST_DEVICE_001")
    await client.run_test(interactive=interactive)

if __name__ == "__main__":
    print("ESP32 Language Learning - Test Client")
    print("=" * 50)
    print("Usage: python test.py [interactive]")
    print()
    asyncio.run(main())