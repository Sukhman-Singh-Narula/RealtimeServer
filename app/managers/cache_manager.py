import redis.asyncio as redis
import json
from typing import Optional, Dict, Any
from datetime import datetime

class CacheManager:
    def __init__(self, host: str, port: int, db: int):
        self.redis = redis.Redis(host=host, port=port, db=db, decode_responses=True)
    
    async def set_session(self, esp32_id: str, session_data: Dict[str, Any]):
        """Store session data in Redis"""
        key = f"session:{esp32_id}"
        session_data["last_activity"] = datetime.utcnow().isoformat()
        await self.redis.set(key, json.dumps(session_data, default=str), ex=86400)  # 24 hour expiry
    
    async def get_session(self, esp32_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve session data from Redis"""
        key = f"session:{esp32_id}"
        data = await self.redis.get(key)
        return json.loads(data) if data else None
    
    async def update_agent_state(self, esp32_id: str, state: str, current_agent: str = None):
        """Update agent state in session"""
        session = await self.get_session(esp32_id)
        if session:
            session["agent_state"] = state
            session["current_agent"] = current_agent
            session["last_activity"] = datetime.utcnow().isoformat()
            await self.set_session(esp32_id, session)
    
    async def set_realtime_connection(self, esp32_id: str, connection_data: Dict[str, Any]):
        """Store OpenAI Realtime connection info"""
        key = f"realtime:{esp32_id}"
        await self.redis.set(key, json.dumps(connection_data), ex=3600)  # 1 hour expiry
    
    async def get_realtime_connection(self, esp32_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve Realtime connection info"""
        key = f"realtime:{esp32_id}"
        data = await self.redis.get(key)
        return json.loads(data) if data else None
    
    async def delete_connection(self, esp32_id: str):
        """Remove connection data"""
        await self.redis.delete(f"realtime:{esp32_id}")
        await self.redis.delete(f"session:{esp32_id}")