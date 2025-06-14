"""
Windows-compatible test client for ESP32 Language Learning System
"""

import asyncio
import websockets
import json
import logging
import sys
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class WindowsTestClient:
    def __init__(self, esp32_id="WINDOWS_TEST_001"):
        self.esp32_id = esp32_id
        self.uri = f"ws://localhost:8000/upload/{esp32_id}"
        self.websocket = None
        
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
        """Send a text message"""
        message = {
            "type": "text",
            "text": text
        }
        await self.websocket.send(json.dumps(message))
        logger.info(f"Sent text: {text}")
    
    async def send_test_audio(self):
        """Send simple test audio (sine wave or silence)"""
        try:
            # Try to import audio utilities
            from app.utils.audio import AudioProcessor
            
            # Create 2 seconds of silence
            audio_bytes = AudioProcessor.create_silence(2.0, 16000)
            
            if audio_bytes:
                await self.websocket.send(audio_bytes)
                logger.info(f"Sent test audio: {len(audio_bytes)} bytes")
            else:
                logger.warning("Could not create test audio")
                
        except Exception as e:
            logger.error(f"Failed to send audio: {e}")
    
    async def listen_for_messages(self):
        """Listen for server messages"""
        try:
            async for message in self.websocket:
                if isinstance(message, str):
                    try:
                        data = json.loads(message)
                        msg_type = data.get('type', 'unknown')
                        logger.info(f"Received: {msg_type}")
                        
                        if msg_type == 'connected':
                            logger.info(f"Server says: {data.get('message', '')}")
                        elif msg_type == 'text_response':
                            text = data.get('text', '')
                            is_final = data.get('is_final', False)
                            logger.info(f"Text {'(final)' if is_final else '(partial)'}: {text}")
                        elif msg_type == 'error':
                            logger.error(f"Server error: {data.get('message', '')}")
                        
                    except json.JSONDecodeError:
                        logger.error("Failed to parse JSON message")
                elif isinstance(message, bytes):
                    logger.info(f"Received binary data: {len(message)} bytes")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info("Connection closed")
        except Exception as e:
            logger.error(f"Error in message listener: {e}")
    
    async def run_simple_test(self):
        """Run a simple test scenario"""
        try:
            await self.connect()
            
            # Start listening for messages
            listen_task = asyncio.create_task(self.listen_for_messages())
            
            # Wait for connection to settle
            await asyncio.sleep(2)
            
            # Send greeting
            await self.send_text_message("Hello! I want to learn Spanish!")
            await asyncio.sleep(3)
            
            # Send response to day question
            await self.send_text_message("My day is going great!")
            await asyncio.sleep(3)
            
            # Make episode selection
            await self.send_text_message("I want to learn about farm animals")
            await asyncio.sleep(5)
            
            # Try vocabulary
            await self.send_text_message("gato")
            await asyncio.sleep(3)
            
            logger.info("Test completed successfully")
            
        except Exception as e:
            logger.error(f"Test failed: {e}")
        finally:
            if self.websocket:
                await self.websocket.close()

async def main():
    """Main test function"""
    print("Windows ESP32 Language Learning Test Client")
    print("=" * 50)
    
    client = WindowsTestClient()
    await client.run_simple_test()

if __name__ == "__main__":
    asyncio.run(main())
