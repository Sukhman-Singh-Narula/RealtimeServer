# app/managers/cache_manager.py
import redis.asyncio as redis
import json
import asyncio
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from app.config import settings

logger = logging.getLogger(__name__)

class InMemoryCache:
    """Fallback in-memory cache when Redis is unavailable"""
    
    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._expiry: Dict[str, datetime] = {}
        
    async def set(self, key: str, value: str, ex: int = None):
        """Set a value with optional expiry"""
        self._cache[key] = value
        if ex:
            from datetime import datetime, timedelta
            self._expiry[key] = datetime.utcnow() + timedelta(seconds=ex)
        
    async def get(self, key: str) -> Optional[str]:
        """Get a value, checking expiry"""
        if key not in self._cache:
            return None
            
        # Check expiry
        if key in self._expiry:
            if datetime.utcnow() > self._expiry[key]:
                self._cleanup_expired_key(key)
                return None
                
        return self._cache[key]
        
    async def delete(self, key: str):
        """Delete a key"""
        self._cache.pop(key, None)
        self._expiry.pop(key, None)
        
    async def close(self):
        """Close (cleanup)"""
        self._cache.clear()
        self._expiry.clear()
        
    def _cleanup_expired_key(self, key: str):
        """Remove expired key"""
        self._cache.pop(key, None)
        self._expiry.pop(key, None)

class CacheManager:
    def __init__(self, host: str = None, port: int = None, db: int = None):
        self.redis = None
        self.fallback_cache = InMemoryCache()
        self.using_fallback = False
        self.connection_tested = False
        
        # Use settings if parameters not provided
        self.host = host or settings.redis_host
        self.port = port or settings.redis_port
        self.db = db or settings.redis_db
        
        logger.info(f"Cache manager initialized with Redis target: {self.host}:{self.port}")
    
    async def _test_redis_connection(self, host: str) -> Optional[redis.Redis]:
        """Test Redis connection to a specific host"""
        try:
            test_redis = redis.Redis(
                host=host,
                port=self.port,
                db=self.db,
                decode_responses=True,
                socket_timeout=settings.redis_socket_timeout,
                socket_connect_timeout=settings.redis_connection_timeout,
                retry_on_timeout=True,
                health_check_interval=30
            )
            
            # Test the connection
            await asyncio.wait_for(test_redis.ping(), timeout=5.0)
            logger.info(f"✅ Redis connection successful: {host}:{self.port}")
            return test_redis
            
        except Exception as e:
            logger.debug(f"❌ Redis connection failed for {host}:{self.port} - {e}")
            try:
                await test_redis.close()
            except:
                pass
            return None
    
    async def _initialize_redis(self):
        """Initialize Redis connection with fallback logic"""
        if self.connection_tested:
            return
            
        logger.info("Initializing Redis connection...")
        
        # Force fallback mode if configured
        if settings.mock_redis:
            logger.info("🔄 Using fallback in-memory cache (mock_redis=True)")
            self.using_fallback = True
            self.connection_tested = True
            return
        
        # Try different Redis hosts
        hosts_to_try = settings.get_redis_hosts_to_try()
        logger.info(f"Trying Redis hosts: {hosts_to_try}")
        
        for host in hosts_to_try:
            logger.info(f"Testing Redis connection to {host}:{self.port}...")
            test_redis = await self._test_redis_connection(host)
            
            if test_redis:
                self.redis = test_redis
                self.using_fallback = False
                logger.info(f"✅ Redis connected successfully: {host}:{self.port}")
                break
        
        if not self.redis:
            logger.warning("❌ All Redis connection attempts failed")
            logger.warning("🔄 Falling back to in-memory cache")
            self.using_fallback = True
        
        self.connection_tested = True
    
    async def _ensure_redis(self):
        """Ensure Redis is initialized"""
        if not self.connection_tested:
            await self._initialize_redis()
    
    async def set_session(self, esp32_id: str, session_data: Dict[str, Any]):
        """Store session data in Redis or fallback cache"""
        await self._ensure_redis()
        
        key = f"session:{esp32_id}"
        session_data["last_activity"] = datetime.utcnow().isoformat()
        json_data = json.dumps(session_data, default=str)
        
        try:
            if not self.using_fallback and self.redis:
                await self.redis.set(key, json_data, ex=86400)  # 24 hour expiry
                logger.debug(f"Session stored in Redis for {esp32_id}")
            else:
                await self.fallback_cache.set(key, json_data, ex=86400)
                logger.debug(f"Session stored in fallback cache for {esp32_id}")
                
        except Exception as e:
            logger.error(f"Failed to store session for {esp32_id}: {e}")
            # Try fallback if Redis fails
            if not self.using_fallback:
                logger.warning("Switching to fallback cache due to Redis error")
                self.using_fallback = True
                await self.fallback_cache.set(key, json_data, ex=86400)
    
    async def get_session(self, esp32_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve session data from Redis or fallback cache"""
        await self._ensure_redis()
        
        key = f"session:{esp32_id}"
        
        try:
            if not self.using_fallback and self.redis:
                data = await self.redis.get(key)
                logger.debug(f"Session retrieved from Redis for {esp32_id}")
            else:
                data = await self.fallback_cache.get(key)
                logger.debug(f"Session retrieved from fallback cache for {esp32_id}")
                
            return json.loads(data) if data else None
            
        except Exception as e:
            logger.error(f"Failed to get session for {esp32_id}: {e}")
            # Try fallback if Redis fails
            if not self.using_fallback:
                logger.warning("Switching to fallback cache due to Redis error")
                self.using_fallback = True
                data = await self.fallback_cache.get(key)
                return json.loads(data) if data else None
            return None
    
    async def update_agent_state(self, esp32_id: str, state: str, current_agent: str = None):
        """Update agent state in session"""
        session = await self.get_session(esp32_id)
        if session:
            session["agent_state"] = state
            if current_agent:
                session["current_agent"] = current_agent
            session["last_activity"] = datetime.utcnow().isoformat()
            await self.set_session(esp32_id, session)
    
    async def set_realtime_connection(self, esp32_id: str, connection_data: Dict[str, Any]):
        """Store OpenAI Realtime connection info"""
        await self._ensure_redis()
        
        key = f"realtime:{esp32_id}"
        json_data = json.dumps(connection_data)
        
        try:
            if not self.using_fallback and self.redis:
                await self.redis.set(key, json_data, ex=3600)  # 1 hour expiry
            else:
                await self.fallback_cache.set(key, json_data, ex=3600)
                
        except Exception as e:
            logger.error(f"Failed to store realtime connection for {esp32_id}: {e}")
            if not self.using_fallback:
                self.using_fallback = True
                await self.fallback_cache.set(key, json_data, ex=3600)
    
    async def get_realtime_connection(self, esp32_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve Realtime connection info"""
        await self._ensure_redis()
        
        key = f"realtime:{esp32_id}"
        
        try:
            if not self.using_fallback and self.redis:
                data = await self.redis.get(key)
            else:
                data = await self.fallback_cache.get(key)
                
            return json.loads(data) if data else None
            
        except Exception as e:
            logger.error(f"Failed to get realtime connection for {esp32_id}: {e}")
            if not self.using_fallback:
                self.using_fallback = True
                data = await self.fallback_cache.get(key)
                return json.loads(data) if data else None
            return None
    
    async def delete_connection(self, esp32_id: str):
        """Remove connection data"""
        await self._ensure_redis()
        
        keys_to_delete = [f"realtime:{esp32_id}", f"session:{esp32_id}"]
        
        for key in keys_to_delete:
            try:
                if not self.using_fallback and self.redis:
                    await self.redis.delete(key)
                else:
                    await self.fallback_cache.delete(key)
                    
            except Exception as e:
                logger.error(f"Failed to delete {key}: {e}")
    
    async def get_connection_status(self) -> Dict[str, Any]:
        """Get cache connection status"""
        await self._ensure_redis()
        
        status = {
            "type": "fallback" if self.using_fallback else "redis",
            "connected": True,  # Fallback is always "connected"
        }
        
        if not self.using_fallback and self.redis:
            try:
                await self.redis.ping()
                status["connected"] = True
                status["host"] = self.host
                status["port"] = self.port
            except Exception as e:
                status["connected"] = False
                status["error"] = str(e)
        
        return status
    
    async def close(self):
        """Close connections and cleanup"""
        try:
            if self.redis:
                await self.redis.close()
                logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}")
        
        try:
            await self.fallback_cache.close()
            logger.info("Fallback cache cleaned up")
        except Exception as e:
            logger.error(f"Error cleaning up fallback cache: {e}")