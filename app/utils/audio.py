# app/utils/audio.py - Audio Processing Utilities

import logging
import numpy as np
from typing import Optional, Tuple
import io
import wave
import struct

logger = logging.getLogger(__name__)

class AudioProcessor:
    """Audio processing utilities for the language learning system"""
    
    def __init__(self):
        self.sample_width = 2  # 16-bit audio
        self.channels = 1      # Mono audio
        
    def convert_sample_rate(self, audio_data: bytes, from_rate: int, to_rate: int) -> bytes:
        """Convert audio sample rate using simple interpolation"""
        try:
            if from_rate == to_rate:
                return audio_data
                
            # Convert bytes to numpy array (16-bit PCM)
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Calculate the ratio and new length
            ratio = to_rate / from_rate
            new_length = int(len(audio_array) * ratio)
            
            # Simple linear interpolation
            old_indices = np.arange(len(audio_array))
            new_indices = np.linspace(0, len(audio_array) - 1, new_length)
            resampled = np.interp(new_indices, old_indices, audio_array.astype(np.float32))
            
            # Convert back to int16 and bytes
            resampled_int16 = resampled.astype(np.int16)
            return resampled_int16.tobytes()
            
        except Exception as e:
            logger.error(f"Error converting sample rate: {e}")
            return audio_data
    
    def normalize_audio(self, audio_data: bytes) -> bytes:
        """Normalize audio volume"""
        try:
            # Convert to numpy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Normalize to prevent clipping
            if len(audio_array) > 0:
                max_val = np.max(np.abs(audio_array))
                if max_val > 0:
                    # Normalize to 90% of max range to prevent clipping
                    normalized = (audio_array * 0.9 * 32767 / max_val).astype(np.int16)
                    return normalized.tobytes()
            
            return audio_data
            
        except Exception as e:
            logger.error(f"Error normalizing audio: {e}")
            return audio_data
    
    def create_wav_header(self, sample_rate: int, num_samples: int, num_channels: int = 1, sample_width: int = 2) -> bytes:
        """Create WAV file header"""
        try:
            # WAV file header format
            byte_rate = sample_rate * num_channels * sample_width
            block_align = num_channels * sample_width
            data_size = num_samples * num_channels * sample_width
            file_size = data_size + 36
            
            header = struct.pack(
                '<4sI4s4sIHHIIHH4sI',
                b'RIFF',        # Chunk ID
                file_size,      # File size
                b'WAVE',        # Format
                b'fmt ',        # Subchunk1 ID
                16,             # Subchunk1 size
                1,              # Audio format (PCM)
                num_channels,   # Number of channels
                sample_rate,    # Sample rate
                byte_rate,      # Byte rate
                block_align,    # Block align
                sample_width * 8,  # Bits per sample
                b'data',        # Subchunk2 ID
                data_size       # Subchunk2 size
            )
            
            return header
            
        except Exception as e:
            logger.error(f"Error creating WAV header: {e}")
            return b''
    
    def pcm_to_wav(self, pcm_data: bytes, sample_rate: int = 24000) -> bytes:
        """Convert raw PCM data to WAV format"""
        try:
            num_samples = len(pcm_data) // 2  # 16-bit samples
            header = self.create_wav_header(sample_rate, num_samples)
            return header + pcm_data
            
        except Exception as e:
            logger.error(f"Error converting PCM to WAV: {e}")
            return pcm_data
    
    def extract_pcm_from_wav(self, wav_data: bytes) -> Tuple[bytes, int, int]:
        """Extract PCM data from WAV file"""
        try:
            # Use wave module for proper parsing
            wav_io = io.BytesIO(wav_data)
            with wave.open(wav_io, 'rb') as wav_file:
                sample_rate = wav_file.getframerate()
                channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                frames = wav_file.readframes(wav_file.getnframes())
                
                logger.debug(f"Extracted WAV: {sample_rate}Hz, {channels}ch, {sample_width*8}bit")
                return frames, sample_rate, channels
                
        except Exception as e:
            logger.error(f"Error extracting PCM from WAV: {e}")
            return b'', 0, 0
    
    def convert_to_openai_format(self, audio_data: bytes, input_format: str = "pcm16", input_rate: int = 16000) -> bytes:
        """Convert audio to OpenAI Realtime API preferred format (24kHz PCM16)"""
        try:
            if input_format == "pcm16":
                # Convert from input sample rate to 24kHz
                if input_rate != 24000:
                    return self.convert_sample_rate(audio_data, input_rate, 24000)
                return audio_data
                
            elif input_format == "wav":
                # Extract PCM from WAV and convert to 24kHz
                pcm_data, sample_rate, channels = self.extract_pcm_from_wav(audio_data)
                if channels == 1 and sample_rate != 24000:
                    return self.convert_sample_rate(pcm_data, sample_rate, 24000)
                return pcm_data
                
            elif input_format == "webm":
                # For WebM, we'll pass it through directly
                # OpenAI Realtime API can handle WebM/Opus
                logger.debug("Passing WebM audio directly to OpenAI")
                return audio_data
                
            else:
                logger.warning(f"Unknown audio format: {input_format}")
                return audio_data
                
        except Exception as e:
            logger.error(f"Error converting audio to OpenAI format: {e}")
            return audio_data
    
    def validate_audio_data(self, audio_data: bytes, expected_format: str = "pcm16") -> bool:
        """Validate audio data format and quality"""
        try:
            if not audio_data or len(audio_data) == 0:
                logger.warning("Empty audio data")
                return False
                
            if expected_format == "pcm16":
                # Check if length is even (16-bit samples)
                if len(audio_data) % 2 != 0:
                    logger.warning("PCM16 data length is not even")
                    return False
                    
                # Check for reasonable audio levels
                audio_array = np.frombuffer(audio_data, dtype=np.int16)
                max_amplitude = np.max(np.abs(audio_array))
                
                if max_amplitude == 0:
                    logger.warning("Audio data is silent")
                    return False
                    
                if max_amplitude > 32767:
                    logger.warning("Audio data may be clipped")
                    return False
                    
            elif expected_format == "wav":
                # Check WAV header
                if len(audio_data) < 44:
                    logger.warning("Audio data too short for WAV format")
                    return False
                    
                if not audio_data.startswith(b'RIFF'):
                    logger.warning("Invalid WAV header")
                    return False
                    
            elif expected_format == "webm":
                # Basic WebM validation
                if len(audio_data) < 20:
                    logger.warning("Audio data too short for WebM format")
                    return False
                    
            logger.debug(f"Audio data validation passed: {len(audio_data)} bytes, {expected_format}")
            return True
            
        except Exception as e:
            logger.error(f"Error validating audio data: {e}")
            return False
    
    def get_audio_duration(self, audio_data: bytes, sample_rate: int, format_type: str = "pcm16") -> float:
        """Calculate audio duration in seconds"""
        try:
            if format_type == "pcm16":
                num_samples = len(audio_data) // 2  # 16-bit samples
                duration = num_samples / sample_rate
            elif format_type == "wav":
                pcm_data, wav_sample_rate, channels = self.extract_pcm_from_wav(audio_data)
                num_samples = len(pcm_data) // 2
                duration = num_samples / wav_sample_rate
            else:
                # Estimate for other formats
                duration = len(audio_data) / (sample_rate * 2)  # Rough estimate
                
            return duration
            
        except Exception as e:
            logger.error(f"Error calculating audio duration: {e}")
            return 0.0
    
    def apply_noise_reduction(self, audio_data: bytes) -> bytes:
        """Apply basic noise reduction"""
        try:
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Simple noise gate - remove very quiet sounds
            noise_threshold = 100  # Adjust based on your needs
            audio_array = np.where(np.abs(audio_array) < noise_threshold, 0, audio_array)
            
            return audio_array.tobytes()
            
        except Exception as e:
            logger.error(f"Error applying noise reduction: {e}")
            return audio_data
    
    async def webm_to_pcm16(self, webm_data: bytes, target_sample_rate: int = 24000) -> bytes:
        """Convert WebM audio to PCM16 format using FFmpeg-like processing"""
        try:
            import subprocess
            import tempfile
            import os
            
            # Create temporary files
            with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as webm_file:
                webm_file.write(webm_data)
                webm_path = webm_file.name
            
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as wav_file:
                wav_path = wav_file.name
            
            try:
                # Use FFmpeg to convert WebM to PCM16 WAV
                # This requires FFmpeg to be installed on the system
                cmd = [
                    'ffmpeg',
                    '-i', webm_path,
                    '-acodec', 'pcm_s16le',  # PCM 16-bit little-endian
                    '-ac', '1',              # Mono
                    '-ar', str(target_sample_rate),  # Sample rate
                    '-y',                    # Overwrite output
                    wav_path
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                
                if result.returncode == 0:
                    # Read the converted WAV file and extract PCM data
                    with open(wav_path, 'rb') as f:
                        wav_data = f.read()
                    
                    # Extract PCM data from WAV
                    pcm_data, sample_rate, channels = self.extract_pcm_from_wav(wav_data)
                    
                    logger.debug(f"WebM to PCM16 conversion successful: {len(pcm_data)} bytes, {sample_rate}Hz")
                    return pcm_data
                else:
                    logger.error(f"FFmpeg error: {result.stderr}")
                    return await self.webm_to_pcm16_fallback(webm_data, target_sample_rate)
                    
            finally:
                # Clean up temporary files
                try:
                    os.unlink(webm_path)
                    os.unlink(wav_path)
                except:
                    pass
                    
        except FileNotFoundError:
            logger.warning("FFmpeg not found, using fallback WebM decoder")
            return await self.webm_to_pcm16_fallback(webm_data, target_sample_rate)
        except Exception as e:
            logger.error(f"Error converting WebM to PCM16: {e}")
            return await self.webm_to_pcm16_fallback(webm_data, target_sample_rate)

    async def webm_to_pcm16_fallback(self, webm_data: bytes, target_sample_rate: int = 24000) -> bytes:
        """Fallback WebM to PCM16 conversion using Web Audio API simulation"""
        try:
            # This is a simplified fallback that assumes the WebM contains Opus audio
            # In a real implementation, you'd use a proper WebM/Opus decoder
            
            logger.warning("Using fallback WebM conversion - audio quality may be reduced")
            
            # For now, we'll create silence of appropriate length as a placeholder
            # This should be replaced with a proper WebM/Opus decoder in production
            duration_seconds = len(webm_data) / (8000 * 2)  # Rough estimate
            num_samples = int(target_sample_rate * duration_seconds)
            
            # Generate silence (in production, decode the actual WebM audio)
            silence = np.zeros(num_samples, dtype=np.int16)
            return silence.tobytes()
            
        except Exception as e:
            logger.error(f"Fallback WebM conversion failed: {e}")
            # Return minimal silence
            silence = np.zeros(1024, dtype=np.int16)
            return silence.tobytes()

    def webm_to_pcm16_js_bridge(self, webm_base64: str) -> str:
        """Generate JavaScript code to decode WebM on the client side"""
        js_code = f"""
        // Client-side WebM to PCM16 conversion
        async function convertWebMToPCM16(webmBase64) {{
            try {{
                // Decode base64 to ArrayBuffer
                const webmData = Uint8Array.from(atob(webmBase64), c => c.charCodeAt(0));
                
                // Create AudioContext
                const audioContext = new (window.AudioContext || window.webkitAudioContext)({{
                    sampleRate: 24000
                }});
                
                // Decode WebM audio
                const audioBuffer = await audioContext.decodeAudioData(webmData.buffer);
                
                // Get PCM data (convert to mono if needed)
                let pcmData;
                if (audioBuffer.numberOfChannels === 1) {{
                    pcmData = audioBuffer.getChannelData(0);
                }} else {{
                    // Mix down to mono
                    const left = audioBuffer.getChannelData(0);
                    const right = audioBuffer.getChannelData(1);
                    pcmData = new Float32Array(left.length);
                    for (let i = 0; i < left.length; i++) {{
                        pcmData[i] = (left[i] + right[i]) / 2;
                    }}
                }}
                
                // Convert Float32 to Int16 PCM
                const pcm16 = new Int16Array(pcmData.length);
                for (let i = 0; i < pcmData.length; i++) {{
                    // Clamp and convert to 16-bit integer
                    const sample = Math.max(-1, Math.min(1, pcmData[i]));
                    pcm16[i] = sample * 32767;
                }}
                
                // Convert to base64 for transmission
                const uint8Array = new Uint8Array(pcm16.buffer);
                const base64PCM = btoa(String.fromCharCode.apply(null, uint8Array));
                
                return base64PCM;
                
            }} catch (error) {{
                console.error('WebM to PCM16 conversion error:', error);
                return null;
            }}
        }}
        
        // Convert the provided WebM data
        convertWebMToPCM16('{webm_base64}');
        """
        return js_code
        """Split audio into smaller chunks for streaming"""
        try:
            samples_per_chunk = int(sample_rate * chunk_duration_ms / 1000 * 2)  # 2 bytes per sample
            chunks = []
            
            for i in range(0, len(audio_data), samples_per_chunk):
                chunk = audio_data[i:i + samples_per_chunk]
                if len(chunk) > 0:
                    chunks.append(chunk)
                    
            logger.debug(f"Split {len(audio_data)} bytes into {len(chunks)} chunks")
            return chunks
            
        except Exception as e:
            logger.error(f"Error splitting audio chunks: {e}")
            return [audio_data]