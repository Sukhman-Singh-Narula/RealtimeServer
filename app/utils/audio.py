import numpy as np
import base64
from typing import Tuple, Optional
import wave
import io

class AudioProcessor:
    """Audio processing utilities for ESP32 communication"""
    
    @staticmethod
    def pcm16_to_bytes(pcm_data: np.ndarray) -> bytes:
        """Convert PCM16 audio data to bytes"""
        return pcm_data.astype(np.int16).tobytes()
    
    @staticmethod
    def bytes_to_pcm16(audio_bytes: bytes) -> np.ndarray:
        """Convert bytes to PCM16 audio data"""
        return np.frombuffer(audio_bytes, dtype=np.int16)
    
    @staticmethod
    def resample_audio(audio_data: np.ndarray, 
                      original_rate: int, 
                      target_rate: int) -> np.ndarray:
        """Resample audio to target sample rate"""
        if original_rate == target_rate:
            return audio_data
            
        # Simple resampling using numpy
        duration = len(audio_data) / original_rate
        target_length = int(duration * target_rate)
        
        indices = np.linspace(0, len(audio_data) - 1, target_length)
        resampled = np.interp(indices, np.arange(len(audio_data)), audio_data)
        
        return resampled.astype(np.int16)
    
    @staticmethod
    def convert_sample_rate(audio_bytes: bytes, 
                           from_rate: int = 16000, 
                           to_rate: int = 24000) -> bytes:
        """Convert audio sample rate for OpenAI Realtime API (expects 24kHz)"""
        pcm_data = AudioProcessor.bytes_to_pcm16(audio_bytes)
        resampled = AudioProcessor.resample_audio(pcm_data, from_rate, to_rate)
        return AudioProcessor.pcm16_to_bytes(resampled)
    
    @staticmethod
    def encode_audio_for_openai(audio_bytes: bytes, 
                               input_rate: int = 16000) -> str:
        """Prepare audio for OpenAI Realtime API (24kHz PCM16 base64)"""
        # Convert to 24kHz if needed
        if input_rate != 24000:
            audio_bytes = AudioProcessor.convert_sample_rate(
                audio_bytes, input_rate, 24000
            )
        
        # Encode to base64
        return base64.b64encode(audio_bytes).decode('utf-8')
    
    @staticmethod
    def decode_audio_from_openai(base64_audio: str, 
                                output_rate: int = 16000) -> bytes:
        """Decode audio from OpenAI Realtime API to ESP32 format"""
        # Decode from base64
        audio_bytes = base64.b64decode(base64_audio)
        
        # Convert from 24kHz to target rate if needed
        if output_rate != 24000:
            audio_bytes = AudioProcessor.convert_sample_rate(
                audio_bytes, 24000, output_rate
            )
        
        return audio_bytes
    
    @staticmethod
    def create_wav_header(audio_bytes: bytes, 
                         sample_rate: int = 16000, 
                         channels: int = 1, 
                         bits_per_sample: int = 16) -> bytes:
        """Create WAV file header for audio data"""
        byte_rate = sample_rate * channels * bits_per_sample // 8
        block_align = channels * bits_per_sample // 8
        
        header = b'RIFF'
        header += (36 + len(audio_bytes)).to_bytes(4, 'little')
        header += b'WAVE'
        header += b'fmt '
        header += (16).to_bytes(4, 'little')  # Subchunk1Size
        header += (1).to_bytes(2, 'little')   # AudioFormat (PCM)
        header += channels.to_bytes(2, 'little')
        header += sample_rate.to_bytes(4, 'little')
        header += byte_rate.to_bytes(4, 'little')
        header += block_align.to_bytes(2, 'little')
        header += bits_per_sample.to_bytes(2, 'little')
        header += b'data'
        header += len(audio_bytes).to_bytes(4, 'little')
        
        return header
    
    @staticmethod
    def audio_to_wav(audio_bytes: bytes, 
                    sample_rate: int = 16000) -> bytes:
        """Convert raw PCM audio to WAV format"""
        header = AudioProcessor.create_wav_header(audio_bytes, sample_rate)
        return header + audio_bytes
    
    @staticmethod
    def calculate_audio_duration(audio_bytes: bytes, 
                               sample_rate: int = 16000, 
                               bits_per_sample: int = 16) -> float:
        """Calculate duration of audio in seconds"""
        bytes_per_sample = bits_per_sample // 8
        total_samples = len(audio_bytes) // bytes_per_sample
        return total_samples / sample_rate
    
    @staticmethod
    def detect_silence(audio_bytes: bytes, 
                      threshold: int = 500, 
                      sample_rate: int = 16000) -> bool:
        """Detect if audio contains only silence"""
        pcm_data = AudioProcessor.bytes_to_pcm16(audio_bytes)
        
        # Calculate RMS (Root Mean Square)
        rms = np.sqrt(np.mean(pcm_data.astype(np.float32) ** 2))
        
        return rms < threshold
    
    @staticmethod
    def normalize_audio(audio_bytes: bytes, 
                       target_db: float = -20.0) -> bytes:
        """Normalize audio volume to target dB level"""
        pcm_data = AudioProcessor.bytes_to_pcm16(audio_bytes)
        
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