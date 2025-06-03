import numpy as np
import base64
from typing import Tuple, Optional
import wave
import io
import logging
from scipy import signal
import struct

logger = logging.getLogger(__name__)

class AudioProcessor:
    """Enhanced audio processing utilities for ESP32 communication with better quality"""
    
    @staticmethod
    def pcm16_to_bytes(pcm_data: np.ndarray) -> bytes:
        """Convert PCM16 audio data to bytes"""
        return pcm_data.astype(np.int16).tobytes()
    
    @staticmethod
    def bytes_to_pcm16(audio_bytes: bytes) -> np.ndarray:
        """Convert bytes to PCM16 audio data"""
        return np.frombuffer(audio_bytes, dtype=np.int16)
    
    @staticmethod
    def resample_audio_high_quality(audio_data: np.ndarray, 
                                   original_rate: int, 
                                   target_rate: int) -> np.ndarray:
        """High-quality resampling using scipy for better audio quality"""
        if original_rate == target_rate:
            return audio_data
        
        try:
            # Use scipy's resample for better quality
            resampling_factor = target_rate / original_rate
            target_length = int(len(audio_data) * resampling_factor)
            
            # Use signal.resample for high-quality resampling
            resampled = signal.resample(audio_data, target_length)
            
            # Ensure we stay within int16 range
            resampled = np.clip(resampled, -32768, 32767)
            
            return resampled.astype(np.int16)
            
        except ImportError:
            # Fallback to linear interpolation if scipy not available
            logger.warning("scipy not available, using linear interpolation for resampling")
            return AudioProcessor.resample_audio_linear(audio_data, original_rate, target_rate)
        except Exception as e:
            logger.error(f"High-quality resampling failed: {e}, falling back to linear")
            return AudioProcessor.resample_audio_linear(audio_data, original_rate, target_rate)
    
    @staticmethod
    def resample_audio_linear(audio_data: np.ndarray, 
                             original_rate: int, 
                             target_rate: int) -> np.ndarray:
        """Linear interpolation resampling (fallback method)"""
        if original_rate == target_rate:
            return audio_data
            
        # Calculate target length
        duration = len(audio_data) / original_rate
        target_length = int(duration * target_rate)
        
        # Use linear interpolation
        indices = np.linspace(0, len(audio_data) - 1, target_length)
        resampled = np.interp(indices, np.arange(len(audio_data)), audio_data)
        
        return resampled.astype(np.int16)
    
    @staticmethod
    def convert_sample_rate(audio_bytes: bytes, 
                           from_rate: int = 16000, 
                           to_rate: int = 24000) -> bytes:
        """Convert audio sample rate with high quality resampling"""
        try:
            # Convert bytes to PCM data
            pcm_data = AudioProcessor.bytes_to_pcm16(audio_bytes)
            
            if len(pcm_data) == 0:
                logger.warning("Empty audio data provided for resampling")
                return b''
            
            # Resample with high quality
            resampled = AudioProcessor.resample_audio_high_quality(pcm_data, from_rate, to_rate)
            
            # Convert back to bytes
            return AudioProcessor.pcm16_to_bytes(resampled)
            
        except Exception as e:
            logger.error(f"Error converting sample rate: {e}")
            return audio_bytes  # Return original if conversion fails
    
    @staticmethod
    def encode_audio_for_openai(audio_bytes: bytes, 
                               input_rate: int = 16000) -> str:
        """Prepare audio for OpenAI Realtime API (24kHz PCM16 base64)"""
        try:
            # Convert to 24kHz if needed
            if input_rate != 24000:
                audio_bytes = AudioProcessor.convert_sample_rate(
                    audio_bytes, input_rate, 24000
                )
            
            # Encode to base64
            return base64.b64encode(audio_bytes).decode('utf-8')
            
        except Exception as e:
            logger.error(f"Error encoding audio for OpenAI: {e}")
            return ""
    
    @staticmethod
    def decode_audio_from_openai(base64_audio: str, 
                                output_rate: int = 16000) -> bytes:
        """Decode audio from OpenAI Realtime API to target format"""
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
            logger.error(f"Error decoding audio from OpenAI: {e}")
            return b''
    
    @staticmethod
    def apply_audio_filters(audio_bytes: bytes, 
                           sample_rate: int = 16000) -> bytes:
        """Apply audio filters to improve quality"""
        try:
            pcm_data = AudioProcessor.bytes_to_pcm16(audio_bytes)
            
            if len(pcm_data) == 0:
                return audio_bytes
            
            # Convert to float for processing
            audio_float = pcm_data.astype(np.float32) / 32768.0
            
            # Apply a simple high-pass filter to remove low-frequency noise
            # This helps with speech clarity
            try:
                # Design a high-pass filter (cutoff at 80 Hz)
                nyquist = sample_rate / 2
                cutoff = 80 / nyquist
                b, a = signal.butter(2, cutoff, btype='high')
                audio_float = signal.filtfilt(b, a, audio_float)
            except:
                logger.debug("Could not apply high-pass filter")
            
            # Apply gentle normalization
            max_val = np.max(np.abs(audio_float))
            if max_val > 0:
                # Normalize to 80% of max to prevent clipping
                audio_float = audio_float * (0.8 / max_val)
            
            # Convert back to PCM16
            audio_float = np.clip(audio_float, -1.0, 1.0)
            pcm_filtered = (audio_float * 32767).astype(np.int16)
            
            return AudioProcessor.pcm16_to_bytes(pcm_filtered)
            
        except Exception as e:
            logger.error(f"Error applying audio filters: {e}")
            return audio_bytes  # Return original if filtering fails
    
    @staticmethod
    def calculate_audio_duration(audio_bytes: bytes, 
                               sample_rate: int = 16000, 
                               bits_per_sample: int = 16) -> float:
        """Calculate duration of audio in seconds"""
        try:
            bytes_per_sample = bits_per_sample // 8
            total_samples = len(audio_bytes) // bytes_per_sample
            return total_samples / sample_rate
        except:
            return 0.0
    
    @staticmethod
    def detect_silence(audio_bytes: bytes, 
                      threshold: int = 500, 
                      sample_rate: int = 16000) -> bool:
        """Detect if audio contains only silence"""
        try:
            pcm_data = AudioProcessor.bytes_to_pcm16(audio_bytes)
            
            if len(pcm_data) == 0:
                return True
            
            # Calculate RMS (Root Mean Square)
            rms = np.sqrt(np.mean(pcm_data.astype(np.float32) ** 2))
            
            return rms < threshold
        except:
            return False
    
    @staticmethod
    def normalize_volume(audio_bytes: bytes, 
                        target_db: float = -20.0) -> bytes:
        """Normalize audio volume to target dB level"""
        try:
            pcm_data = AudioProcessor.bytes_to_pcm16(audio_bytes)
            
            if len(pcm_data) == 0:
                return audio_bytes
            
            # Convert to float for processing
            audio_float = pcm_data.astype(np.float32) / 32768.0
            
            # Calculate current RMS
            rms = np.sqrt(np.mean(audio_float ** 2))
            
            # Avoid division by zero
            if rms == 0:
                return audio_bytes
            
            # Calculate target RMS from dB
            target_rms = 10 ** (target_db / 20)
            
            # Calculate scaling factor
            scale = target_rms / rms
            
            # Apply scaling and clip
            normalized = np.clip(audio_float * scale, -1.0, 1.0)
            
            # Convert back to PCM16
            pcm_normalized = (normalized * 32768).astype(np.int16)
            
            return AudioProcessor.pcm16_to_bytes(pcm_normalized)
            
        except Exception as e:
            logger.error(f"Error normalizing volume: {e}")
            return audio_bytes
    
    @staticmethod
    def create_audio_chunks(audio_bytes: bytes, 
                           chunk_size_ms: int = 100, 
                           sample_rate: int = 16000) -> list:
        """Split audio into chunks for streaming"""
        try:
            pcm_data = AudioProcessor.bytes_to_pcm16(audio_bytes)
            
            # Calculate samples per chunk
            samples_per_chunk = int(sample_rate * chunk_size_ms / 1000)
            
            chunks = []
            for i in range(0, len(pcm_data), samples_per_chunk):
                chunk = pcm_data[i:i + samples_per_chunk]
                chunks.append(AudioProcessor.pcm16_to_bytes(chunk))
            
            return chunks
            
        except Exception as e:
            logger.error(f"Error creating audio chunks: {e}")
            return [audio_bytes]  # Return single chunk if splitting fails
    
    @staticmethod
    def smooth_audio_transition(prev_chunk: bytes, 
                               curr_chunk: bytes, 
                               fade_samples: int = 64) -> bytes:
        """Apply smooth transition between audio chunks to prevent clicks"""
        try:
            if not prev_chunk or not curr_chunk:
                return curr_chunk
            
            prev_pcm = AudioProcessor.bytes_to_pcm16(prev_chunk)
            curr_pcm = AudioProcessor.bytes_to_pcm16(curr_chunk)
            
            if len(prev_pcm) == 0 or len(curr_pcm) == 0:
                return curr_chunk
            
            # Get last samples from previous chunk
            prev_end = prev_pcm[-fade_samples:] if len(prev_pcm) >= fade_samples else prev_pcm
            
            # Apply crossfade to beginning of current chunk
            fade_length = min(fade_samples, len(curr_pcm), len(prev_end))
            
            if fade_length > 0:
                # Create fade curves
                fade_out = np.linspace(1.0, 0.0, fade_length)
                fade_in = np.linspace(0.0, 1.0, fade_length)
                
                # Apply crossfade
                curr_pcm[:fade_length] = (
                    prev_end[-fade_length:].astype(np.float32) * fade_out +
                    curr_pcm[:fade_length].astype(np.float32) * fade_in
                ).astype(np.int16)
            
            return AudioProcessor.pcm16_to_bytes(curr_pcm)
            
        except Exception as e:
            logger.error(f"Error smoothing audio transition: {e}")
            return curr_chunk