import asyncio
import websockets
import json
import base64

async def test_connection():
    esp32_id = "TEST_ESP32_001"
    uri = f"ws://localhost:8000/ws/{esp32_id}"
    
    async with websockets.connect(uri) as websocket:
        print(f"Connected as {esp32_id}")
        
        # Send connection message
        await websocket.send(json.dumps({
            "type": "connect",
            "esp32_id": esp32_id,
            "firmware_version": "1.0.0"
        }))
        
        # Listen for messages
        while True:
            message = await websocket.recv()
            data = json.loads(message)
            print(f"Received: {data['type']}")
            
            if data['type'] == 'connected':
                print("Successfully connected!")
                # Send test audio (silence)
                await websocket.send(json.dumps({
                    "type": "audio",
                    "esp32_id": esp32_id,
                    "audio_data": "00" * 1024,  # Hex encoded silence
                    "timestamp": 12345
                }))
            elif data['type'] == 'audio_response':
                print("Received audio response")
            elif data['type'] == 'text_response':
                print(f"Text: {data.get('text', '')}")

if __name__ == "__main__":
    asyncio.run(test_connection())