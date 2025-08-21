#!/usr/bin/env python3
"""
Text-to-Speech Module for Opulent Voice Radio System
Provides text-to-speech capabilities for both incoming and outgoing text messages

This module provides resilient TTS capabilities that don't interfere
with the core audio pipeline. It processes text asynchronously and provides
speech synthesis for both incoming and outgoing text messages.

Design principles:
- Non-blocking: Audio pipeline continues even if TTS fails
- Resilient: Graceful degradation when TTS engines are unavailable
- Accessible: Supports the system's accessibility goals
- Simple: Minimal configuration and maintenance
"""

import asyncio
import logging
import threading
import time
import struct
from queue import Queue, Empty
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from datetime import datetime
import tempfile
import os

# Try to import TTS engines, handle gracefully if not available
try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
    print("✅ PyTTSx3 available for cross-platform TTS")
except ImportError:
    PYTTSX3_AVAILABLE = False
    print("⚠️ PyTTSx3 not available - install with: pip install pyttsx3")

# Check for system TTS availability
import platform
import subprocess
SYSTEM_TTS_AVAILABLE = False

if platform.system() == "Windows":
    try:
        subprocess.run(["powershell", "-Command", "Add-Type -AssemblyName System.Speech"], 
                      capture_output=True, check=True, timeout=5)
        SYSTEM_TTS_AVAILABLE = True
        print("✅ Windows SAPI TTS available")
    except:
        print("⚠️ Windows SAPI TTS not available")
elif platform.system() == "Darwin":  # macOS
    try:
        subprocess.run(["say", "--version"], capture_output=True, check=True, timeout=5)
        SYSTEM_TTS_AVAILABLE = True
        print("✅ macOS 'say' command available")
    except:
        print("⚠️ macOS 'say' command not available")
elif platform.system() == "Linux":
    try:
        subprocess.run(["espeak", "--version"], capture_output=True, check=True, timeout=5)
        SYSTEM_TTS_AVAILABLE = True
        print("✅ Linux espeak available")
    except:
        try:
            subprocess.run(["festival", "--version"], capture_output=True, check=True, timeout=5)
            SYSTEM_TTS_AVAILABLE = True
            print("✅ Linux festival available")
        except:
            print("⚠️ Linux TTS not available - install espeak or festival")


@dataclass
class TTSMessage:
    """Container for text to be spoken"""
    text: str
    station_id: str
    timestamp: str
    direction: str  # 'incoming' or 'outgoing'
    is_outgoing: bool = False
    priority: int = 3  # Lower than VOICE/CONTROL, higher than DATA
    delay_seconds: float = 0.0


@dataclass
class TTSResult:
    """Container for TTS completion results"""
    text: str
    station_id: str
    timestamp: str
    direction: str
    processing_time_ms: int = 0
    success: bool = True
    error_message: Optional[str] = None


class TTSEngineManager:
    """Manages TTS engine loading and provides fallback behavior"""
    
    def __init__(self, engine_type: str = "system"):
        self.engine_type = engine_type
        self.engine = None
        self.engine_loaded = False
        self.load_attempted = False
        self.logger = logging.getLogger(__name__)
        
        # ADD: Audio output manager for PCM playback
        self.audio_output_manager = None    
        

    def speak_text(self, text: str, voice: str = "default", rate: int = 200, volume: float = 0.8) -> bool:
        """Speak text using loaded engine"""
        if not self.engine_loaded:
            return False
            
        try:
            if self.engine_type == "pyttsx3" and self.engine:
                # Configure PyTTSx3
                self.engine.setProperty('rate', rate)
                self.engine.setProperty('volume', volume)
                
                # Set voice if specified
                if voice != "default":
                    voices = self.engine.getProperty('voices')
                    for v in voices:
                        if voice.lower() in v.name.lower():
                            self.engine.setProperty('voice', v.id)
                            break
                
                # Speak the text
                self.engine.say(text)
                self.engine.runAndWait()
                return True
                
            elif self.engine_type == "system":
                return self._system_speak(text, voice, rate, volume)
                
        except Exception as e:
            self.logger.error(f"TTS speaking error: {e}")
            return False
            
        return False



    def load_engine(self) -> bool:
        """Load TTS engine with error handling"""
        if self.load_attempted:
            return self.engine_loaded
            
        self.load_attempted = True
        
        try:
            if self.engine_type == "pyttsx3" and PYTTSX3_AVAILABLE:
                self.engine = pyttsx3.init()
                self.engine_loaded = True
                self.logger.info(f"✅ PyTTSx3 engine loaded successfully")
                return True
            elif self.engine_type == "system" and SYSTEM_TTS_AVAILABLE:
                # System TTS doesn't need initialization - we'll use subprocess
                self.engine_loaded = True
                self.logger.info(f"✅ System TTS engine ready")
                return True
            else:
                self.logger.warning(f"TTS engine '{self.engine_type}' not available")
                return False
                
        except Exception as e:
            self.logger.error(f"⚠️ Failed to load TTS engine: {e}")
            self.engine_loaded = False
            return False

    def _system_speak(self, text: str, voice: str, rate: int, volume: float) -> bool:
        """Use system TTS commands - UPDATED to use PCM audio pipeline"""
        try:
            system = platform.system()
            
            if system == "Windows":
                # Use PowerShell SAPI
                rate_percent = max(0, min(10, int((rate - 100) / 20)))  # Convert to 0-10 scale
                volume_percent = max(0, min(100, int(volume * 100)))
                
                ps_command = f"""
                Add-Type -AssemblyName System.Speech;
                $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer;
                $synth.Rate = {rate_percent};
                $synth.Volume = {volume_percent};
                $synth.Speak('{text.replace("'", "''")}');
                """
                subprocess.run(["powershell", "-Command", ps_command], 
                             capture_output=True, timeout=10)
                return True
                
            elif system == "Darwin":  # macOS
                # Use 'say' command
                rate_words_per_min = max(100, min(300, rate))
                cmd = ["say", "-r", str(rate_words_per_min)]
                
                if voice != "default":
                    cmd.extend(["-v", voice])
                    
                cmd.append(text)
                subprocess.run(cmd, capture_output=True, timeout=10)
                return True
                
            elif system == "Linux":
                # NEW: Generate PCM and play through existing audio system
                return self._linux_pcm_speak(text, voice, rate, volume)
                    
        except Exception as e:
            self.logger.error(f"System TTS error: {e}")
            return False
            
        return False





    def _linux_pcm_speak(self, text: str, voice: str, rate: int, volume: float) -> bool:
        """Generate PCM audio and play through existing audio system - FIXED SAMPLE RATE"""
        try:
            if not self.audio_output_manager:
                self.logger.warning("No audio output manager available for TTS")
                return False
            
            # CRITICAL FIX: espeak doesn't support -r option, so we need to resample
            # Your audio system expects 48kHz, but espeak defaults to 22kHz
            target_sample_rate = 48000  # Match your audio system's sample rate
            
            # Generate PCM audio using espeak (will be 22kHz by default)
            cmd = [
                "espeak", 
                "--stdout", 
                "-s", str(rate),
                "-a", str(int(volume * 100))  # Convert 0.0-1.0 to 0-100
            ]
            
            if voice != "default" and voice:
                cmd.extend(["-v", voice])
            cmd.append(text)
            
            print(f"🔊 TTS: Generating PCM audio with command: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, timeout=5)
            
            if result.returncode == 0 and result.stdout:
                # espeak --stdout gives us WAV format
                # Parse WAV header to get the ACTUAL sample rate
                if len(result.stdout) > 44:
                    wav_data = result.stdout
                    
                    # Parse WAV header to verify sample rate
                    # WAV header format: positions 24-27 contain sample rate (little-endian)
                    if wav_data[:4] == b'RIFF' and wav_data[8:12] == b'WAVE':
                        actual_sample_rate = struct.unpack('<I', wav_data[24:28])[0]
                        channels = struct.unpack('<H', wav_data[22:24])[0]
                        bits_per_sample = struct.unpack('<H', wav_data[34:36])[0]
                        
                        print(f"🔊 TTS: WAV header - {actual_sample_rate}Hz, {channels}ch, {bits_per_sample}bit")
                        
                        # Skip WAV header (44 bytes) to get raw PCM
                        pcm_data = wav_data[44:]
                        
                        # ALWAYS resample since espeak defaults to 22kHz and we need 48kHz
                        print(f"🔊 TTS: Converting {actual_sample_rate}Hz → {target_sample_rate}Hz")
                        pcm_data = self._resample_audio(pcm_data, actual_sample_rate, target_sample_rate)
                        
                        print(f"🔊 TTS: Generated {len(pcm_data)} bytes of PCM audio at {target_sample_rate}Hz")
                        
                        # Queue through existing audio system
                        self.audio_output_manager.queue_audio_for_playback(
                            pcm_data, 
                            "TTS_PLAYBACK"
                        )
                        
                        print(f"🔊 TTS: Queued PCM audio for playback")
                        return True
                    else:
                        print(f"🔊 TTS: Invalid WAV header")
                        return False
                else:
                    print(f"🔊 TTS: Generated audio too short ({len(result.stdout)} bytes)")
                    return False
            else:
                print(f"🔊 TTS: espeak failed with return code {result.returncode}")
                if result.stderr:
                    print(f"🔊 TTS: espeak stderr: {result.stderr.decode()}")
                return False
                
        except subprocess.TimeoutExpired:
            print(f"🔊 TTS: espeak timed out")
            return False
        except Exception as e:
            self.logger.error(f"Linux PCM TTS error: {e}")
            print(f"🔊 TTS: Exception: {e}")
            return False




    def _resample_audio(self, pcm_data: bytes, from_rate: int, to_rate: int) -> bytes:
        """Resample PCM audio data from one sample rate to another"""
        try:
            # Try scipy first for high-quality resampling
            import numpy as np
            from scipy import signal
            
            # Convert bytes to numpy array (assuming 16-bit mono)
            audio_samples = np.frombuffer(pcm_data, dtype=np.int16)
            
            # Calculate resampling ratio
            ratio = to_rate / from_rate
            
            # Resample using scipy
            resampled_samples = signal.resample(audio_samples, int(len(audio_samples) * ratio))
            
            # Convert back to 16-bit integers
            resampled_samples = np.clip(resampled_samples, -32768, 32767).astype(np.int16)
            
            print(f"🔊 TTS: High-quality resampling completed")
            return resampled_samples.tobytes()
            
        except ImportError:
            print("🔊 TTS: scipy not available - using numpy-only resampling")
            return self._numpy_resample(pcm_data, from_rate, to_rate)
        except Exception as e:
            print(f"🔊 TTS: Scipy resampling error: {e}")
            return self._numpy_resample(pcm_data, from_rate, to_rate)

    def _numpy_resample(self, pcm_data: bytes, from_rate: int, to_rate: int) -> bytes:
        """Numpy-only resampling using linear interpolation"""
        try:
            import numpy as np
            
            audio_samples = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32)
            
            # Calculate new length
            ratio = to_rate / from_rate
            new_length = int(len(audio_samples) * ratio)
            
            # Create new time indices
            old_indices = np.arange(len(audio_samples))
            new_indices = np.linspace(0, len(audio_samples) - 1, new_length)
            
            # Linear interpolation
            resampled = np.interp(new_indices, old_indices, audio_samples)
            
            # Convert back to 16-bit integers
            resampled = np.clip(resampled, -32768, 32767).astype(np.int16)
            
            print(f"🔊 TTS: Numpy resampling completed ({len(audio_samples)} → {len(resampled)} samples)")
            return resampled.tobytes()
            
        except Exception as e:
            print(f"🔊 TTS: Numpy resampling error: {e}")
            return self._simple_resample(pcm_data, from_rate, to_rate)

    def _simple_resample(self, pcm_data: bytes, from_rate: int, to_rate: int) -> bytes:
        """Simple resampling by duplication or decimation"""
        try:
            import numpy as np
            
            audio_samples = np.frombuffer(pcm_data, dtype=np.int16)
            ratio = to_rate / from_rate
            
            if ratio > 1:
                # Upsample by repeating samples
                repeat_count = int(ratio)
                resampled = np.repeat(audio_samples, repeat_count)
            else:
                # Downsample by taking every nth sample
                step = int(1 / ratio)
                resampled = audio_samples[::step]
            
            return resampled.tobytes()
            
        except Exception as e:
            print(f"🔊 TTS: Simple resampling error: {e}")
            return pcm_data











class TTSQueue:
    """Async queue for processing text-to-speech requests"""
    
    def __init__(self, max_queue_size: int = 50):
        self.tts_queue = Queue(maxsize=max_queue_size)
        self.result_callbacks = []
        self.processing_thread = None
        self.running = False
        self.config = None  # so we have access to live changes
        self.stats = {
            'messages_queued': 0,
            'messages_processed': 0,
            'messages_failed': 0,
            'queue_overruns': 0,
            'total_processing_time_ms': 0
        }
        self.logger = logging.getLogger(__name__)
        
    def set_config(self, config):
        """Set config reference for live TTS settings"""
        self.config = config

    def add_result_callback(self, callback: Callable[[TTSResult], None]):
        """Add callback to receive TTS completion results"""
        self.result_callbacks.append(callback)
        
    def start_processing(self, engine_manager: TTSEngineManager):
        """Start the background processing thread"""
        if self.running:
            return
            
        self.running = True
        self.engine_manager = engine_manager
        self.processing_thread = threading.Thread(
            target=self._process_tts_loop, 
            daemon=True,
            name="TTSProcessor"
        )
        self.processing_thread.start()
        self.logger.info("TTS processing started")
        
    def stop_processing(self):
        """Stop the background processing"""
        self.running = False
        if self.processing_thread:
            self.processing_thread.join(timeout=2.0)
        self.logger.info("TTS processing stopped")
        
    def queue_tts_message(self, message: TTSMessage) -> bool:
        """Queue a text message for TTS"""
        try:
            # Apply delay if specified
            if message.delay_seconds > 0:
                def delayed_queue():
                    time.sleep(message.delay_seconds)
                    try:
                        self.tts_queue.put_nowait(message)
                        self.stats['messages_queued'] += 1
                    except:
                        self.stats['queue_overruns'] += 1
                
                threading.Thread(target=delayed_queue, daemon=True).start()
            else:
                self.tts_queue.put_nowait(message)
                self.stats['messages_queued'] += 1
                
            self.logger.debug(f"Queued TTS message from {message.station_id} ({message.direction})")
            return True
        except:
            self.stats['queue_overruns'] += 1
            self.logger.warning(f"TTS queue full - dropping message from {message.station_id}")
            return False
            
    def _process_tts_loop(self):
        """Main processing loop - runs in background thread"""
        self.logger.info("TTS processing loop started")
        
        while self.running:
            try:
                # Get TTS message with timeout
                message = self.tts_queue.get(timeout=1.0)
                
                # Process the message
                result = self._speak_message(message)
                
                if result:
                    # Send result to all callbacks
                    for callback in self.result_callbacks:
                        try:
                            callback(result)
                        except Exception as e:
                            self.logger.error(f"TTS callback error: {e}")
                            
                    self.stats['messages_processed'] += 1
                    self.stats['total_processing_time_ms'] += result.processing_time_ms
                else:
                    self.stats['messages_failed'] += 1
                    
            except Empty:
                continue  # Normal timeout
            except Exception as e:
                self.logger.error(f"TTS processing loop error: {e}")
                self.stats['messages_failed'] += 1
                
    def _speak_message(self, message: TTSMessage) -> Optional[TTSResult]:
        """Speak a single message - FIXED to use config values"""
        start_time = time.time()
        
        try:
            # Get settings from config if available, otherwise use defaults
            if self.config and hasattr(self.config, 'gui') and hasattr(self.config.gui, 'tts'):
                voice = getattr(self.config.gui.tts, 'voice', 'default')
                rate = getattr(self.config.gui.tts, 'rate', 200)
                volume = getattr(self.config.gui.tts, 'volume', 0.8)
            else:
                # Fallback to defaults if no config
                voice = "default"
                rate = 200
                volume = 0.8
            
            print(f"🔊 TTS: Using config values - rate={rate}, voice={voice}, volume={volume}")
            
            # Speak using engine with live config values
            success = self.engine_manager.speak_text(
                message.text,
                voice=voice,
                rate=rate,
                volume=volume
            )
            
            processing_time = int((time.time() - start_time) * 1000)
            
            result = TTSResult(
                text=message.text,
                station_id=message.station_id,
                timestamp=message.timestamp,
                direction=message.direction,
                processing_time_ms=processing_time,
                success=success,
                error_message=None if success else "TTS engine failed"
            )
            
            self.logger.debug(f"TTS completed: '{message.text[:50]}...' (success: {success})")
            return result
            
        except Exception as e:
            processing_time = int((time.time() - start_time) * 1000)
            self.logger.error(f"TTS failed for {message.station_id}: {e}")
            
            return TTSResult(
                text=message.text,
                station_id=message.station_id,
                timestamp=message.timestamp,
                direction=message.direction,
                processing_time_ms=processing_time,
                success=False,
                error_message=str(e)
            )
            
    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics"""
        stats = self.stats.copy()
        stats['queue_size'] = self.tts_queue.qsize()
        stats['running'] = self.running
        
        if stats['messages_processed'] > 0:
            stats['avg_processing_time_ms'] = (
                stats['total_processing_time_ms'] / stats['messages_processed']
            )
        else:
            stats['avg_processing_time_ms'] = 0
            
        return stats


class OpulentVoiceTTS:
    """Main TTS class that integrates with Opulent Voice system"""

    def __init__(self, config=None):
        self.config = config
        
        # Initialize with current config, but allow live changes
        current_engine = self._get_engine_type()
        self.engine_manager = TTSEngineManager(current_engine)
        self.tts_queue = TTSQueue()
        self.result_cache = {}  # Cache recent results
        self.max_cache_size = 50
        
        # ADD: Audio output manager for PCM playback
        self.audio_output_manager = None
    
        self.logger = logging.getLogger(__name__)
    
        # Statistics
        self.stats = {
            'total_messages': 0,
            'successful_tts': 0,
            'failed_tts': 0,
            'cache_hits': 0
        }        


    def initialize(self) -> bool:
        """Initialize the TTS system"""
        if not self._get_tts_enabled():
            self.logger.info("TTS disabled in configuration")
            return True
            
        # Load TTS engine
        if not self.engine_manager.load_engine():
            self.logger.warning("TTS engine failed to load - TTS disabled")
            return False
            
        # Start processing queue
        self.tts_queue.start_processing(self.engine_manager)
        
        # IMPORTANT: Give queue access to config for live settings
        self.tts_queue.set_config(self.config)

        current_engine = self._get_engine_type()        
        self.logger.info(f"✅ TTS system initialized (engine: {current_engine})")
        return True

    def update_config(self, new_config):
        """Update configuration and handle engine changes if needed"""
        old_config = self.config
        self.config = new_config
        
        # IMPORTANT: Update the queue's config reference too
        if hasattr(self, 'tts_queue') and self.tts_queue:
            self.tts_queue.set_config(new_config)
    
        # Check if engine changed
        old_engine = self._get_engine_type_from_config(old_config) if old_config else "system"
        new_engine = self._get_engine_type()
    
        if old_engine != new_engine:
            self.logger.info(f"TTS engine changed from {old_engine} to {new_engine}")
            # For engine changes, we'd need to reload - but for now, log it
            self.logger.info("TTS engine changes require restart")

        # Log the current state
        enabled = self._get_tts_enabled()
        incoming_enabled = self._get_incoming_enabled()
        outgoing_enabled = self._get_outgoing_enabled()
        include_station_id = self._get_include_station_id()
        include_confirmation = self._get_include_confirmation()
        self.logger.info(f"🔧 TTS config updated: enabled={enabled}, incoming={incoming_enabled}, outgoing={outgoing_enabled}, include_station_id={include_station_id}, include_confirmation={include_confirmation}")

    def set_audio_output_manager(self, audio_output_manager):
        """Connect to the app's audio output system for PCM playback"""
        self.audio_output_manager = audio_output_manager
        # Also give it to the engine manager
        self.engine_manager.audio_output_manager = audio_output_manager
        self.logger.info("TTS connected to audio output system for PCM playback")


    def _get_engine_type_from_config(self, config) -> str:
        """Get engine type from specific config object"""
        if not config:
            return "system"
        
        try:
            return getattr(config.gui.tts, 'engine', 'system')
        except AttributeError:
            return "system"
        
    def shutdown(self):
        """Shutdown the TTS system"""
        self.tts_queue.stop_processing()
        self.logger.info("TTS system shutdown")

    def queue_text_message(self, station_id: str, text: str, is_outgoing: bool = False) -> bool:
        """Queue text message for TTS (incoming or outgoing)"""
        if not self._get_tts_enabled():
            return False

        # Check if this message type should be spoken
        if is_outgoing and not self._get_outgoing_enabled():
            return False
        if not is_outgoing and not self._get_incoming_enabled():
            return False

        # ENSURE SYSTEM IS INITIALIZED when enabled
        if not self.tts_queue.running:
            print("🔧 TTS enabled but not running - initializing...")
            if not self.initialize():
                print("⚠️ Failed to initialize TTS system")
                return False

        # Format message appropriately
        if is_outgoing:
            if self._get_include_confirmation():
                formatted_text = f"Message sent: {text}"
            else:
                formatted_text = text
        else:
            # Incoming message
            if self._get_include_station_id():
                formatted_text = f"Message from {station_id}: {text}"
            else:
                formatted_text = text

        # Get delay for outgoing messages
        delay = self._get_outgoing_delay() if is_outgoing else 0.0

        message = TTSMessage(
            text=formatted_text,
            station_id=station_id,
            timestamp=datetime.now().isoformat(),
            direction="outgoing" if is_outgoing else "incoming",
            is_outgoing=is_outgoing,
            delay_seconds=delay
        )
        
        success = self.tts_queue.queue_tts_message(message)
        if success:
            self.stats['total_messages'] += 1
            
        return success
        

    def add_result_callback(self, callback: Callable[[TTSResult], None]):
        """Add callback to receive TTS completion results"""
        self.tts_queue.add_result_callback(callback)
        
    def _cache_result(self, result: TTSResult):
        """Cache a TTS result"""
        cache_key = f"{result.station_id}_{result.direction}_{result.timestamp}"
        self.result_cache[cache_key] = result
        
        # Clean up old cache entries
        if len(self.result_cache) > self.max_cache_size:
            # Remove oldest entries (simple FIFO)
            oldest_keys = list(self.result_cache.keys())[:-self.max_cache_size//2]
            for key in oldest_keys:
                del self.result_cache[key]
                
    def _get_tts_enabled(self) -> bool:
        """Get TTS enabled setting from config"""
        if not self.config:
            return False
            
        try:
            return getattr(self.config.gui.tts, 'enabled', False)
        except AttributeError:
            return False

    def _get_incoming_enabled(self) -> bool:
        """Get incoming messages enabled setting from config"""
        if not self.config:
            return True
            
        try:
            return getattr(self.config.gui.tts, 'incoming_enabled', True)
        except AttributeError:
            return True

    def _get_outgoing_enabled(self) -> bool:
        """Get outgoing messages enabled setting from config"""
        if not self.config:
            return False
            
        try:
            return getattr(self.config.gui.tts, 'outgoing_enabled', False)
        except AttributeError:
            return False

    def _get_include_station_id(self) -> bool:
        """Get include station ID setting from config"""
        if not self.config:
            return True
            
        try:
            return getattr(self.config.gui.tts, 'include_station_id', True)
        except AttributeError:
            return True

    def _get_include_confirmation_old(self) -> bool:
        """Get include confirmation setting from config"""
        if not self.config:
            return True
            
        try:
            return getattr(self.config.gui.tts, 'include_confirmation', True)
        except AttributeError:
            return True


    def _get_include_confirmation(self) -> bool:
        """Get include confirmation setting from config"""
        if not self.config:
            print(f"🔊 TTS DEBUG: No config available, defaulting to False")
            return False  # ← Fixed: default to False
        
        try:
            value = getattr(self.config.gui.tts, 'include_confirmation', False)  # ← Fixed: fallback to False
            print(f"🔊 TTS DEBUG: Read include_confirmation from config: {value}")
            return value
        except AttributeError as e:
            print(f"🔊 TTS DEBUG: Config attribute error: {e}, defaulting to False")
            return False  # ← Fixed: error fallback to False




    def _get_outgoing_delay(self) -> float:
        """Get outgoing message delay from config"""
        if not self.config:
            return 1.0
            
        try:
            return getattr(self.config.gui.tts, 'outgoing_delay_seconds', 1.0)
        except AttributeError:
            return 1.0
            
    def _get_engine_type(self) -> str:
        """Get TTS engine type from config"""
        if not self.config:
            return "system"
        
        try:
            return getattr(self.config.gui.tts, 'engine', 'system')
        except AttributeError:
            return "system"
            
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive TTS statistics"""
        stats = {
            'enabled': self._get_tts_enabled(),
            'engine_type': self._get_engine_type(),
            'incoming_enabled': self._get_incoming_enabled(),
            'outgoing_enabled': self._get_outgoing_enabled(),
            'pyttsx3_available': PYTTSX3_AVAILABLE,
            'system_tts_available': SYSTEM_TTS_AVAILABLE,
            'engine_loaded': self.engine_manager.engine_loaded,
            'cache_size': len(self.result_cache),
            'processing_stats': self.tts_queue.get_stats(),
            **self.stats
        }
        
        return stats


# Utility functions for integration
def create_tts_manager(config=None) -> Optional[OpulentVoiceTTS]:
    """Factory function to create and initialize TTS manager"""
    try:
        tts_manager = OpulentVoiceTTS(config)
        if tts_manager.initialize():
            return tts_manager
        else:
            return None
    except Exception as e:
        logging.error(f"Failed to create TTS manager: {e}")
        return None


# Example result callback for CLI mode
def cli_tts_callback(result: TTSResult):
    """Example callback for displaying TTS results in CLI mode"""
    if result.success:
        direction_indicator = "📤" if result.direction == "outgoing" else "📥"
        print(f"🔊 {direction_indicator} TTS: \"{result.text}\" ({result.processing_time_ms}ms)")
    else:
        print(f"🔇 TTS failed for {result.station_id}: {result.error_message}")


if __name__ == "__main__":
    # Basic test of the TTS system
    import sys
    
    print("🧪 Testing Opulent Voice TTS Module")
    
    # Test engine availability
    print(f"PyTTSx3 available: {PYTTSX3_AVAILABLE}")
    print(f"System TTS available: {SYSTEM_TTS_AVAILABLE}")
    
    if not PYTTSX3_AVAILABLE and not SYSTEM_TTS_AVAILABLE:
        print("⚠️ No TTS engines available")
        sys.exit(1)
        
    # Create test TTS manager
    tts_manager = create_tts_manager()
    if not tts_manager:
        print("⚠️ Failed to initialize TTS manager")
        sys.exit(1)
        
    # Add CLI callback
    tts_manager.add_result_callback(cli_tts_callback)
    
    # Test message
    test_result = tts_manager.queue_text_message("W1ABC", "Hello, this is a test message", is_outgoing=False)
    if test_result:
        print("✅ Test message queued for TTS")
        time.sleep(2)  # Give it time to process
    else:
        print("⚠️ Failed to queue test message")
    
    print("📊 TTS Stats:", tts_manager.get_stats())
    
    # Cleanup
    tts_manager.shutdown()
    print("✅ TTS system test completed")
