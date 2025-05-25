import asyncio
import websockets
import json
import base64
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TestESP32Client:
    def __init__(self, esp32_id="TEST_DEVICE_001"):
        self.esp32_id = esp32_id
        self.uri = f"ws://localhost:8000/ws/{esp32_id}"
        self.websocket = None
        
    async def connect(self):
        """Connect to the server"""
        logger.info(f"Connecting to {self.uri}")
        self.websocket = await websockets.connect(self.uri)
        logger.info("Connected successfully")
        
    async def send_connection_message(self):
        """Send initial connection message"""
        message = {
            "type": "connect",
            "esp32_id": self.esp32_id,
            "firmware_version": "1.0.0"
        }
        await self.websocket.send(json.dumps(message))
        logger.info("Sent connection message")
        
    async def send_audio(self, duration_seconds=2):
        """Send test audio (silence) for specified duration"""
        # Generate silence audio (16kHz, 16-bit PCM)
        sample_rate = 16000
        bytes_per_sample = 2
        chunk_size = 1024
        
        total_samples = sample_rate * duration_seconds
        chunks_to_send = total_samples // chunk_size
        
        logger.info(f"Sending {duration_seconds} seconds of audio...")
        
        for i in range(chunks_to_send):
            # Create silence audio chunk
            audio_chunk = bytes([0] * (chunk_size * bytes_per_sample))
            
            message = {
                "type": "audio",
                "esp32_id": self.esp32_id,
                "audio_data": audio_chunk.hex(),
                "timestamp": int(datetime.now().timestamp() * 1000)
            }
            
            await self.websocket.send(json.dumps(message))
            
            # Small delay between chunks to simulate real audio streaming
            await asyncio.sleep(chunk_size / sample_rate)
            
            if i % 10 == 0:
                logger.debug(f"Sent audio chunk {i+1}/{chunks_to_send}")
        
        logger.info("Finished sending audio")
        
    async def listen_for_messages(self):
        """Listen for messages from server"""
        try:
            async for message in self.websocket:
                data = json.loads(message)
                msg_type = data.get('type', 'unknown')
                
                logger.info(f"Received message type: {msg_type}")
                
                if msg_type == 'connected':
                    logger.info(f"Server welcome: {data.get('message', '')}")
                    
                elif msg_type == 'audio_response':
                    audio_data = data.get('audio_data', '')
                    if audio_data:
                        audio_bytes = base64.b64decode(audio_data)
                        logger.info(f"Received audio response: {len(audio_bytes)} bytes")
                    else:
                        logger.warning("Received empty audio response")
                        
                elif msg_type == 'text_response':
                    text = data.get('text', '')
                    is_final = data.get('is_final', False)
                    logger.info(f"Text {'(final)' if is_final else '(partial)'}: {text}")
                    
                elif msg_type == 'agent_switched':
                    logger.info(f"Agent switched to: {data.get('new_agent', 'unknown')}")
                    
                elif msg_type == 'error':
                    logger.error(f"Server error: {data.get('message', 'Unknown error')}")
                    
                elif msg_type == 'heartbeat_ack':
                    logger.debug("Heartbeat acknowledged")
                    
                else:
                    logger.debug(f"Full message: {json.dumps(data, indent=2)}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info("Connection closed by server")
        except Exception as e:
            logger.error(f"Error in message listener: {e}")
            
    async def send_heartbeat(self):
        """Send periodic heartbeat"""
        while True:
            await asyncio.sleep(30)
            if self.websocket and not self.websocket.closed:
                message = {
                    "type": "heartbeat",
                    "esp32_id": self.esp32_id
                }
                await self.websocket.send(json.dumps(message))
                logger.debug("Sent heartbeat")
                
    async def run_test(self):
        """Run the test client"""
        try:
            # Connect to server
            await self.connect()
            
            # Send connection message
            await self.send_connection_message()
            
            # Start heartbeat task
            heartbeat_task = asyncio.create_task(self.send_heartbeat())
            
            # Start listening for messages
            listen_task = asyncio.create_task(self.listen_for_messages())
            
            # Wait a bit for initial response
            await asyncio.sleep(2)
            
            # Send some test audio
            await self.send_audio(duration_seconds=3)
            
            # Keep listening for responses
            logger.info("Waiting for responses... (Press Ctrl+C to stop)")
            await listen_task
            
        except KeyboardInterrupt:
            logger.info("Stopping test client...")
        except Exception as e:
            logger.error(f"Test failed: {e}")
        finally:
            if self.websocket:
                await self.websocket.close()
                logger.info("Connection closed")

async def main():
    """Main function"""
    # Test with properly formatted device ID
    client = TestESP32Client("TEST_DEVICE_001")
    await client.run_test()

if __name__ == "__main__":
    print("ESP32 Language Learning - Test Client")
    print("=" * 50)
    asyncio.run(main())