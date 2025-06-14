"""
Minimal audio processing utilities for Windows compatibility
Falls back gracefully when scipy/numpy are not available
"""

import logging
import base64
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import numpy and scipy, fall back if not available
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    logger.warning("numpy not available - using basic audio processing")

try:
    from scipy import signal
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    logger.warning("scipy not available - using basic audio resampling")

class AudioProcessor:
    """Audio processing with Windows compatibility and fallbacks"""
    
    @staticmethod
    def convert_sample_rate(audio_bytes: bytes, 
                           from_rate: int = 16000, 
                           to_rate: int = 24000) -> bytes:
        """Convert audio sample rate with fallback for missing scipy"""
        try:
            if not HAS_NUMPY:
                # If no numpy, return original audio
                logger.debug("No numpy available, returning original audio")
                return audio_bytes
            
            if len(audio_bytes) == 0:
                return b''
            
            if from_rate == to_rate:
                return audio_bytes
            
            # Convert bytes to numpy array
            audio_data = np.frombuffer(audio_bytes, dtype=np.int16)
            
            if len(audio_data) == 0:
                return b''
            
            if HAS_SCIPY:
                # Use scipy for high-quality resampling
                duration = len(audio_data) / from_rate
                target_length = int(duration * to_rate)
                resampled = signal.resample(audio_data, target_length)
            else:
                # Use linear interpolation as fallback
                duration = len(audio_data) / from_rate
                target_length = int(duration * to_rate)
                
                if target_length == 0:
                    return b''
                
                # Linear interpolation
                indices = np.linspace(0, len(audio_data) - 1, target_length)
                resampled = np.interp(indices, np.arange(len(audio_data)), audio_data)
            
            # Ensure we stay within int16 range and convert back to bytes
            resampled = np.clip(resampled, -32768, 32767).astype(np.int16)
            return resampled.tobytes()
            
        except Exception as e:
            logger.error(f"Audio conversion failed: {e}, returning original")
            return audio_bytes
    
    @staticmethod
    def encode_audio_for_openai(audio_bytes: bytes, input_rate: int = 16000) -> str:
        """Encode audio for OpenAI API"""
        try:
            # Convert to 24kHz if needed
            if input_rate != 24000:
                audio_bytes = AudioProcessor.convert_sample_rate(
                    audio_bytes, input_rate, 24000
                )
            
            # Encode to base64
            return base64.b64encode(audio_bytes).decode('utf-8')
            
        except Exception as e:
            logger.error(f"Error encoding audio: {e}")
            return ""
    
    @staticmethod
    def decode_audio_from_openai(base64_audio: str, output_rate: int = 16000) -> bytes:
        """Decode audio from OpenAI API"""
        try:
            # Decode from base64
            audio_bytes = base64.b64decode(base64_audio)
            
            # Convert from 24kHz to target rate if needed
            if output_rate != 24000:
                audio_bytes = AudioProcessor.convert_sample_rate(
                    audio_bytes, 24000, output_rate
                )
            
            return audio_bytes
            
        except Exception as e:
            logger.error(f"Error decoding audio: {e}")
            return b''
    
    @staticmethod
    def calculate_audio_duration(audio_bytes: bytes, 
                               sample_rate: int = 16000) -> float:
        """Calculate audio duration in seconds"""
        try:
            if not HAS_NUMPY:
                # Fallback calculation
                bytes_per_sample = 2  # 16-bit = 2 bytes
                total_samples = len(audio_bytes) // bytes_per_sample
                return total_samples / sample_rate
            
            audio_data = np.frombuffer(audio_bytes, dtype=np.int16)
            return len(audio_data) / sample_rate
        except:
            return 0.0
    
    @staticmethod
    def create_silence(duration_seconds: float, sample_rate: int = 16000) -> bytes:
        """Create silence audio for testing"""
        try:
            if HAS_NUMPY:
                samples = int(duration_seconds * sample_rate)
                silence = np.zeros(samples, dtype=np.int16)
                return silence.tobytes()
            else:
                # Fallback: create silence manually
                samples = int(duration_seconds * sample_rate)
                return bytes(samples * 2)  # 2 bytes per sample
        except:
            return b''
