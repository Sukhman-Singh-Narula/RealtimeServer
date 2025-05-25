# ESP32 Language Learning System - Complete Documentation

## System Overview

A real-time language learning platform where ESP32 devices connect to children and interact with AI teachers through OpenAI's Realtime Speech-to-Speech API. The system uses a **Choice Layer Agent** to handle episode selection and seamlessly transitions to **Episode Teaching Agents** for personalized language instruction.

## Architecture Components

### High-Level Flow
```
ESP32 Device → FastAPI Server → Choice Agent → Episode Agent → Learning Session
     ↓              ↓              ↓             ↓             ↓
Audio I/O    WebSocket Handler   Episode Menu   Teaching AI   Progress Tracking
```

## Technology Stack

### Backend Server: **FastAPI (Python)**
- **WebSocket handling**: FastAPI WebSocket support
- **REST API**: For episode management and progress tracking
- **Async/await**: For handling concurrent connections
- **Pydantic**: For data validation and serialization

### Databases & Storage
- **SQLite**: Embedded in server application (user progress, sessions)
- **Redis**: Local instance (session caching, connection states)
- **Firebase Firestore**: Episode content, stories, vocabulary

### AI Integration
- **OpenAI Realtime API**: Speech-to-speech AI conversations
- **One connection per user**: Dedicated AI context per ESP32 device

### ESP32 Firmware
- **WebSocket client**: Persistent connection to FastAPI server
- **Audio I/O**: I2S microphone and speaker
- **WiFi management**: Auto-reconnection and error handling

## System Components Detail

### 1. FastAPI Server Architecture

```python
# Main server structure
app = FastAPI()

# Core managers
database_manager = DatabaseManager()      # SQLite operations
cache_manager = CacheManager()           # Redis operations  
content_manager = ContentManager()       # Firebase operations
agent_manager = AgentManager()          # OpenAI connections
websocket_manager = WebSocketManager()  # ESP32 connections
```

### 2. Database Design (SQLite)

```sql
-- Users table
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    esp32_id TEXT UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_active DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Progress tracking
CREATE TABLE user_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    language TEXT,
    season INTEGER,
    episode INTEGER,
    completed BOOLEAN DEFAULT FALSE,
    progress_data JSON,
    vocabulary_learned JSON,
    completed_at DATETIME,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

-- Learning sessions
CREATE TABLE learning_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    episode_info JSON,
    duration INTEGER,
    interaction_count INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);
```

### 3. Redis Cache Structure

```python
# Session data
session:{esp32_id} = {
    "user_id": "uuid",
    "agent_state": "CHOOSING|LEARNING", 
    "current_episode": {...},
    "connected_at": timestamp,
    "last_activity": timestamp
}

# Connection mapping
connection:{esp32_id} = {
    "openai_connection_id": "conn_123",
    "websocket_active": true,
    "agent_type": "choice|episode"
}
```

### 4. Firebase Content Structure

```json
// Collection: episodes
// Document ID: {language}_{season}_{episode}
{
  "spanish_1_1": {
    "title": "Greetings and Family",
    "vocabulary": ["hola", "adiós", "familia", "mamá", "papá"],
    "story_context": "Meeting a Spanish family in their home",
    "difficulty": "beginner",
    "estimated_duration": 300,
    "learning_objectives": ["Basic greetings", "Family members"]
  },
  "spanish_1_2": {
    "title": "Farm Animals", 
    "vocabulary": ["gato", "perro", "vaca", "caballo", "cerdo"],
    "story_context": "Adventure on a Spanish farm with friendly animals",
    "difficulty": "beginner",
    "estimated_duration": 400,
    "learning_objectives": ["Animal names", "Animal sounds"]
  }
}
```

## Choice Layer Agent System

### Two-Phase Agent Architecture

#### Phase 1: Choice Agent
**Purpose**: Episode selection and navigation
**OpenAI System Prompt**:
```
You are a friendly learning assistant helping children choose language episodes.

Present available episodes in a fun way using emojis. When child selects an episode, call the select_episode function.

Available episodes: {episodes_json}

Keep responses short and exciting for kids aged 5-8.
```

**Function Definition**:
```python
choice_functions = [
    {
        "name": "select_episode",
        "description": "Select an episode to start learning",
        "parameters": {
            "type": "object",
            "properties": {
                "language": {"type": "string", "enum": ["spanish", "french", "german"]},
                "season": {"type": "integer"},
                "episode": {"type": "integer"},
                "title": {"type": "string"}
            },
            "required": ["language", "season", "episode"]
        }
    }
]
```

#### Phase 2: Episode Agent
**Purpose**: Language teaching and story delivery
**Dynamic System Prompt**:
```
You are a friendly {language} teacher for children.

Episode: Season {season}, Episode {episode} - {title}
Story context: {story_context}
Vocabulary focus: {vocabulary_list}

Teaching approach:
- Speak mostly in {language} with English explanations
- Use the story context to make learning engaging
- Focus on vocabulary: {vocabulary}
- Encourage repetition and praise all attempts
- Keep responses short for 5-8 year olds
- Start by introducing the story and first vocabulary word
```

## API Endpoints (FastAPI)

### WebSocket Endpoints
```python
@app.websocket("/ws/{esp32_id}")
async def websocket_endpoint(websocket: WebSocket, esp32_id: str)
    # Handle ESP32 WebSocket connections
    # Route audio streams to OpenAI
    # Manage agent transitions
```

### REST API Endpoints
```python
# User management
GET /api/users/{esp32_id}/progress
POST /api/users/{esp32_id}/progress

# Episode management  
GET /api/episodes/available/{user_id}
GET /api/episodes/{language}/{season}/{episode}

# Analytics
GET /api/analytics/user/{user_id}
POST /api/analytics/session
```

## WebSocket Message Protocol

### ESP32 → Server Messages
```json
// Connection initialization
{
  "type": "connect",
  "esp32_id": "device_12345",
  "firmware_version": "1.0.0"
}

// Audio stream
{
  "type": "audio",
  "esp32_id": "device_12345", 
  "audio_data": "base64_encoded_audio",
  "timestamp": 1635123456
}

// Function call response (episode selection)
{
  "type": "function_response",
  "esp32_id": "device_12345",
  "selection": {
    "language": "spanish",
    "season": 1,
    "episode": 2
  }
}
```

### Server → ESP32 Messages
```json
// Connection acknowledgment
{
  "type": "connected",
  "user_id": "uuid",
  "message": "Welcome! Choose your episode..."
}

// AI audio response
{
  "type": "audio_response",
  "audio_data": "base64_encoded_audio",
  "agent_type": "choice|episode"
}

// Agent transition
{
  "type": "agent_switched", 
  "new_agent": "episode",
  "episode_info": {...}
}
```

## Implementation Flow

### 1. ESP32 Connection Flow
```python
async def handle_esp32_connection(esp32_id: str):
    # 1. Authenticate ESP32 device
    user = await get_or_create_user(esp32_id)
    
    # 2. Load available episodes from Firebase
    episodes = await content_manager.get_available_episodes(user.id)
    
    # 3. Create Choice Agent with OpenAI
    choice_agent = await agent_manager.create_choice_agent(esp32_id, episodes)
    
    # 4. Cache session in Redis
    await cache_manager.set_session(esp32_id, {
        "user_id": user.id,
        "agent_state": "CHOOSING",
        "connected_at": time.now()
    })
    
    # 5. Send welcome message
    await send_choice_menu(esp32_id)
```

### 2. Episode Selection Flow
```python
async def handle_episode_selection(esp32_id: str, selection: dict):
    # 1. Validate selection
    episode_data = await content_manager.get_episode(
        selection["language"], 
        selection["season"], 
        selection["episode"]
    )
    
    # 2. Close Choice Agent
    await agent_manager.close_choice_agent(esp32_id)
    
    # 3. Create Episode Agent with specific prompt
    episode_agent = await agent_manager.create_episode_agent(esp32_id, episode_data)
    
    # 4. Update cache
    await cache_manager.update_agent_state(esp32_id, "LEARNING")
    
    # 5. Start episode
    await send_episode_intro(esp32_id, episode_data)
```

### 3. Learning Session Flow
```python
async def handle_learning_audio(esp32_id: str, audio_data: bytes):
    # 1. Get Episode Agent connection
    connection = agent_manager.get_connection(esp32_id)
    
    # 2. Stream audio to OpenAI Realtime API
    response_audio = await connection.send_audio(audio_data)
    
    # 3. Stream AI response back to ESP32
    await websocket_manager.send_audio(esp32_id, response_audio)
    
    # 4. Track progress
    await database_manager.update_session_activity(esp32_id)
```

## ESP32 Firmware Overview

### Core Components
```cpp
// Main modules needed
#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <driver/i2s.h>

// Audio configuration
#define SAMPLE_RATE 16000
#define BITS_PER_SAMPLE 16
#define I2S_MIC_CHANNEL I2S_CHANNEL_0
#define I2S_SPK_CHANNEL I2S_CHANNEL_1

// WebSocket client
WebSocketsClient webSocket;
String esp32_id = "ESP32_" + WiFi.macAddress();
```

### Audio Pipeline
```cpp
void setup_audio() {
    // Configure I2S for microphone input
    i2s_config_t i2s_config_mic = {
        .mode = I2S_MODE_MASTER | I2S_MODE_RX,
        .sample_rate = SAMPLE_RATE,
        .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
        .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT
    };
    
    // Configure I2S for speaker output  
    i2s_config_t i2s_config_spk = {
        .mode = I2S_MODE_MASTER | I2S_MODE_TX,
        .sample_rate = SAMPLE_RATE,
        .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
        .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT
    };
}

void stream_audio_to_server() {
    // Capture audio from microphone
    // Encode and send via WebSocket
    // Handle received audio and play through speaker
}
```

## Deployment Architecture

### Server Deployment
```yaml
# Docker container structure
FROM python:3.11-slim

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application
COPY . /app
WORKDIR /app

# Embedded databases
VOLUME /app/data  # SQLite database storage
EXPOSE 8000       # FastAPI server
EXPOSE 6379       # Redis port

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Resource Requirements (100 Users)
- **CPU**: 4 cores (concurrent OpenAI connections)
- **RAM**: 8GB (audio buffers + connections)
- **Storage**: 50GB SSD (databases + logs)
- **Network**: 1Gbps (audio streaming)
- **Cost**: ~$80-120/month VPS

### Scaling Considerations
- **Concurrent users**: 20-30 peak simultaneous
- **OpenAI connections**: 1 per active user
- **Database**: SQLite sufficient for 100 users
- **Redis**: Single instance handles all sessions
- **Horizontal scaling**: Add load balancer when exceeding 100 users

## Development Phases

### Phase 1: Core MVP (2-3 weeks)
- [ ] FastAPI server with WebSocket support
- [ ] Basic ESP32 firmware with audio I/O
- [ ] Single OpenAI connection proof-of-concept
- [ ] SQLite database setup
- [ ] Simple episode selection

### Phase 2: Choice Layer System (2-3 weeks)  
- [ ] Choice Agent implementation
- [ ] Episode Agent with dynamic prompts
- [ ] Firebase content management
- [ ] Redis session caching
- [ ] Agent transition logic

### Phase 3: Production Features (2-3 weeks)
- [ ] Progress tracking and analytics
- [ ] Error handling and reconnection
- [ ] Audio optimization and compression
- [ ] Monitoring and logging
- [ ] Security and authentication

### Phase 4: Deployment & Testing (1-2 weeks)
- [ ] Docker containerization
- [ ] Load testing with multiple ESP32s
- [ ] Content creation for multiple episodes
- [ ] Documentation and maintenance guides

## Security & Privacy

### Device Authentication
- ESP32 device certificates
- Secure WebSocket connections (WSS)
- Rate limiting per device

### Data Protection
- No persistent audio storage
- Encrypted data transmission
- COPPA compliance for children's data
- Minimal data collection

### API Security
- OpenAI API key management
- Request rate limiting
- Input validation and sanitization

This documentation provides a complete blueprint for implementing the ESP32 Language Learning System with FastAPI, covering all components from hardware integration to cloud deployment.