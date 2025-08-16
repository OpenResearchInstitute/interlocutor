#!/usr/bin/env python3
"""
Audio Transcription Module for Opulent Voice Radio System
Uses OpenAI Whisper for local, offline speech-to-text transcription

This module provides resilient transcription capabilities that don't interfere
with the core audio pipeline. It processes audio asynchronously and provides
transcriptions for both incoming and outgoing audio.

Design principles:
- Non-blocking: Audio pipeline continues even if transcription fails
- Resilient: Graceful degradation when Whisper is unavailable
- Accessible: Supports the system's accessibility goals
- Simple: Minimal configuration and maintenance
"""

import asyncio
import logging
import threading
import time
import numpy as np
from queue import Queue, Empty
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from datetime import datetime
import tempfile
import os
import wave

# Try to import Whisper, handle gracefully if not available
try:
    import whisper
    WHISPER_AVAILABLE = True
    print("✅ Whisper available for transcription")
except ImportError:
    WHISPER_AVAILABLE = False
    print("⚠️  Whisper not available - transcription disabled")


@dataclass
class AudioSegment:
    """Container for audio data to be transcribed"""
    audio_data: bytes  # PCM audio data
    station_id: str
    timestamp: str
    direction: str  # 'incoming' or 'outgoing'
    sample_rate: int = 48000
    channels: int = 1
    duration_ms: int = 40
    transmission_id: Optional[str] = None


@dataclass
class TranscriptionResult:
    """Container for transcription results"""
    text: str
    confidence: float
    language: str
    station_id: str
    timestamp: str
    direction: str
    transmission_id: Optional[str] = None
    processing_time_ms: int = 0


class ModelManager:
    """Manages Whisper model loading and provides fallback behavior"""
    
    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
        self.model = None
        self.model_loaded = False
        self.load_attempted = False
        self.logger = logging.getLogger(__name__)
        
    def load_model(self) -> bool:
        """Load Whisper model with error handling"""
        if self.load_attempted:
            return self.model_loaded
            
        self.load_attempted = True
        
        if not WHISPER_AVAILABLE:
            self.logger.warning("Whisper not available - transcription disabled")
            return False
            
        try:
            self.logger.info(f"Loading Whisper model: {self.model_size}")
            self.model = whisper.load_model(self.model_size)
            self.model_loaded = True
            self.logger.info(f"✅ Whisper model '{self.model_size}' loaded successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to load Whisper model: {e}")
            self.model_loaded = False
            return False
    
    def transcribe_audio(self, audio_path: str) -> Optional[Dict[str, Any]]:
        """Transcribe audio file using loaded model"""
        if not self.model_loaded:
            return None
            
        try:
            result = self.model.transcribe(audio_path)
            return result
        except Exception as e:
            self.logger.error(f"Transcription error: {e}")
            return None


class TranscriptionQueue:
    """Async queue for processing audio transcriptions"""
    
    def __init__(self, max_queue_size: int = 100):
        self.audio_queue = Queue(maxsize=max_queue_size)
        self.result_callbacks = []
        self.processing_thread = None
        self.running = False
        self.stats = {
            'segments_queued': 0,
            'segments_processed': 0,
            'segments_failed': 0,
            'queue_overruns': 0,
            'total_processing_time_ms': 0
        }
        self.logger = logging.getLogger(__name__)
        
    def add_result_callback(self, callback: Callable[[TranscriptionResult], None]):
        """Add callback to receive transcription results"""
        self.result_callbacks.append(callback)
        
    def start_processing(self, model_manager: ModelManager):
        """Start the background processing thread"""
        if self.running:
            return
            
        self.running = True
        self.model_manager = model_manager
        self.processing_thread = threading.Thread(
            target=self._process_audio_loop, 
            daemon=True,
            name="TranscriptionProcessor"
        )
        self.processing_thread.start()
        self.logger.info("Transcription processing started")
        
    def stop_processing(self):
        """Stop the background processing"""
        self.running = False
        if self.processing_thread:
            self.processing_thread.join(timeout=2.0)
        self.logger.info("Transcription processing stopped")
        
    def queue_audio_segment(self, segment: AudioSegment) -> bool:
        """Queue an audio segment for transcription"""
        try:
            self.audio_queue.put_nowait(segment)
            self.stats['segments_queued'] += 1
            self.logger.debug(f"Queued audio segment from {segment.station_id} ({segment.direction})")
            return True
        except:
            self.stats['queue_overruns'] += 1
            self.logger.warning(f"Transcription queue full - dropping segment from {segment.station_id}")
            return False
            
    def _process_audio_loop(self):
        """Main processing loop - runs in background thread"""
        self.logger.info("Transcription processing loop started")
        
        while self.running:
            try:
                # Get audio segment with timeout
                segment = self.audio_queue.get(timeout=1.0)
                
                # Process the segment
                result = self._transcribe_segment(segment)
                
                if result:
                    # Send result to all callbacks
                    for callback in self.result_callbacks:
                        try:
                            callback(result)
                        except Exception as e:
                            self.logger.error(f"Callback error: {e}")
                            
                    self.stats['segments_processed'] += 1
                    self.stats['total_processing_time_ms'] += result.processing_time_ms
                else:
                    self.stats['segments_failed'] += 1
                    
            except Empty:
                continue  # Normal timeout
            except Exception as e:
                self.logger.error(f"Processing loop error: {e}")
                self.stats['segments_failed'] += 1
                
    def _transcribe_segment(self, segment: AudioSegment) -> Optional[TranscriptionResult]:
        """Transcribe a single audio segment"""
        start_time = time.time()
        
        try:
            # Convert PCM data to temporary WAV file
            wav_path = self._create_temp_wav(segment)
            if not wav_path:
                return None
                
            # Transcribe using Whisper
            whisper_result = self.model_manager.transcribe_audio(wav_path)
            
            # Clean up temp file
            try:
                os.unlink(wav_path)
            except:
                pass
                
            if not whisper_result:
                return None
                
            # Extract results
            text = whisper_result.get('text', '').strip()
            language = whisper_result.get('language', 'unknown')
            
            # Calculate confidence (Whisper doesn't provide this directly)
            # Use segment-level confidence if available, otherwise estimate
            segments = whisper_result.get('segments', [])
            if segments:
                # Average confidence of all segments
                confidences = []
                for seg in segments:
                    if 'avg_logprob' in seg:
                        # Convert log probability to confidence estimate
                        confidence = min(1.0, max(0.0, np.exp(seg['avg_logprob'])))
                        confidences.append(confidence)
                avg_confidence = np.mean(confidences) if confidences else 0.5
            else:
                # Fallback confidence estimate based on text length and content
                avg_confidence = self._estimate_confidence(text)
                
            processing_time = int((time.time() - start_time) * 1000)
            
            result = TranscriptionResult(
                text=text,
                confidence=avg_confidence,
                language=language,
                station_id=segment.station_id,
                timestamp=segment.timestamp,
                direction=segment.direction,
                transmission_id=segment.transmission_id,
                processing_time_ms=processing_time
            )
            
            self.logger.debug(f"Transcribed: '{text}' (confidence: {avg_confidence:.2f})")
            return result
            
        except Exception as e:
            self.logger.error(f"Transcription failed for {segment.station_id}: {e}")
            return None
            
    def _create_temp_wav(self, segment: AudioSegment) -> Optional[str]:
        """Convert PCM data to temporary WAV file for Whisper"""
        try:
            # Create temporary file
            fd, wav_path = tempfile.mkstemp(suffix='.wav', prefix='opulent_voice_')
            os.close(fd)
            
            # Convert bytes to numpy array
            audio_np = np.frombuffer(segment.audio_data, dtype=np.int16)
            
            # Normalize to float32 for Whisper
            audio_float = audio_np.astype(np.float32) / 32768.0
            
            # Write WAV file
            with wave.open(wav_path, 'wb') as wav_file:
                wav_file.setnchannels(segment.channels)
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(segment.sample_rate)
                
                # Convert back to 16-bit for WAV
                audio_int16 = (audio_float * 32767).astype(np.int16)
                wav_file.writeframes(audio_int16.tobytes())
                
            return wav_path
            
        except Exception as e:
            self.logger.error(f"Failed to create temp WAV: {e}")
            return None
            
    def _estimate_confidence(self, text: str) -> float:
        """Estimate confidence based on text characteristics"""
        if not text:
            return 0.0
            
        # Simple heuristic based on text length and content
        base_confidence = 0.7
        
        # Longer text generally more reliable
        length_bonus = min(0.2, len(text) / 100)
        
        # Penalize very short text
        if len(text) < 5:
            base_confidence *= 0.5
            
        # Penalize text with many special characters (often transcription errors)
        special_chars = sum(1 for c in text if not c.isalnum() and c not in ' .,!?')
        special_penalty = min(0.3, special_chars / len(text))
        
        confidence = base_confidence + length_bonus - special_penalty
        return max(0.0, min(1.0, confidence))
        
    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics"""
        stats = self.stats.copy()
        stats['queue_size'] = self.audio_queue.qsize()
        stats['running'] = self.running
        
        if stats['segments_processed'] > 0:
            stats['avg_processing_time_ms'] = (
                stats['total_processing_time_ms'] / stats['segments_processed']
            )
        else:
            stats['avg_processing_time_ms'] = 0
            
        return stats


class WhisperTranscriber:
    """Main transcription class that integrates with Opulent Voice system"""
    
    def __init__(self, config=None):
        self.config = config
        self.enabled = self._get_transcription_enabled()
        self.model_size = self._get_model_size()
        self.confidence_threshold = self._get_confidence_threshold()
        
        self.model_manager = ModelManager(self.model_size)
        self.transcription_queue = TranscriptionQueue()
        self.result_cache = {}  # Cache recent results by transmission_id
        self.max_cache_size = 100
        
        self.logger = logging.getLogger(__name__)
        
        # Statistics
        self.stats = {
            'total_segments': 0,
            'successful_transcriptions': 0,
            'failed_transcriptions': 0,
            'cache_hits': 0
        }
        
    def initialize(self) -> bool:
        """Initialize the transcription system"""
        if not self.enabled:
            self.logger.info("Transcription disabled in configuration")
            return False
            
        # Load Whisper model
        if not self.model_manager.load_model():
            self.logger.warning("Whisper model failed to load - transcription disabled")
            self.enabled = False
            return False
            
        # Start processing queue
        self.transcription_queue.start_processing(self.model_manager)
        
        self.logger.info(f"✅ Transcription system initialized (model: {self.model_size})")
        return True
        
    def shutdown(self):
        """Shutdown the transcription system"""
        self.transcription_queue.stop_processing()
        self.logger.info("Transcription system shutdown")
        
    def process_audio_segment(self, audio_data: bytes, station_id: str, 
                            direction: str, transmission_id: Optional[str] = None) -> bool:
        """Process an audio segment for transcription"""
        if not self.enabled:
            return False
            
        segment = AudioSegment(
            audio_data=audio_data,
            station_id=station_id,
            timestamp=datetime.now().isoformat(),
            direction=direction,
            transmission_id=transmission_id
        )
        
        success = self.transcription_queue.queue_audio_segment(segment)
        if success:
            self.stats['total_segments'] += 1
            
        return success
        
    def add_result_callback(self, callback: Callable[[TranscriptionResult], None]):
        """Add callback to receive transcription results"""
        self.transcription_queue.add_result_callback(callback)
        
    def get_transcription_for_transmission(self, transmission_id: str) -> Optional[str]:
        """Get cached transcription for a transmission ID"""
        result = self.result_cache.get(transmission_id)
        if result:
            self.stats['cache_hits'] += 1
            return result.text
        return None
        
    def _cache_result(self, result: TranscriptionResult):
        """Cache a transcription result"""
        if result.transmission_id:
            self.result_cache[result.transmission_id] = result
            
            # Clean up old cache entries
            if len(self.result_cache) > self.max_cache_size:
                # Remove oldest entries (simple FIFO)
                oldest_keys = list(self.result_cache.keys())[:-self.max_cache_size//2]
                for key in oldest_keys:
                    del self.result_cache[key]
                    
    def _get_transcription_enabled(self) -> bool:
        """Get transcription enabled setting from config"""
        if not self.config:
            return False
            
        try:
            return getattr(self.config.gui.transcription, 'enabled', False)
        except AttributeError:
            return False
            
    def _get_model_size(self) -> str:
        """Get Whisper model size from config"""
        if not self.config:
            return "base"
            
        try:
            # Map config method to model size
            method = getattr(self.config.gui.transcription, 'method', 'auto')
            if method == 'disabled':
                return "base"  # Won't be used anyway
            else:
                # Could extend this to allow model size configuration
                return "base"  # Good balance of speed and accuracy
        except AttributeError:
            return "base"
            
    def _get_confidence_threshold(self) -> float:
        """Get confidence threshold from config"""
        if not self.config:
            return 0.7
            
        try:
            return getattr(self.config.gui.transcription, 'confidence_threshold', 0.7)
        except AttributeError:
            return 0.7
            
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive transcription statistics"""
        stats = {
            'enabled': self.enabled,
            'model_size': self.model_size,
            'confidence_threshold': self.confidence_threshold,
            'whisper_available': WHISPER_AVAILABLE,
            'model_loaded': self.model_manager.model_loaded,
            'cache_size': len(self.result_cache),
            'processing_stats': self.transcription_queue.get_stats(),
            **self.stats
        }
        
        return stats


# Utility functions for integration
def create_transcriber(config=None) -> Optional[WhisperTranscriber]:
    """Factory function to create and initialize transcriber"""
    try:
        transcriber = WhisperTranscriber(config)
        if transcriber.initialize():
            return transcriber
        else:
            return None
    except Exception as e:
        logging.error(f"Failed to create transcriber: {e}")
        return None


# Example result callback for CLI mode
def cli_transcription_callback(result: TranscriptionResult):
    """Example callback for displaying transcriptions in CLI mode"""
    if result.confidence >= 0.5:  # Only show high-confidence results
        direction_indicator = "📤" if result.direction == "outgoing" else "📥"
        print(f"\n🗨️  {direction_indicator} [{result.station_id}]: \"{result.text}\" (confidence: {result.confidence:.1%})")


if __name__ == "__main__":
    # Basic test of the transcription system
    import sys
    
    print("🧪 Testing Opulent Voice Transcription Module")
    
    # Test model availability
    if not WHISPER_AVAILABLE:
        print("❌ Whisper not available - install with: pip install openai-whisper")
        sys.exit(1)
        
    # Create test transcriber
    transcriber = create_transcriber()
    if not transcriber:
        print("❌ Failed to initialize transcriber")
        sys.exit(1)
        
    # Add CLI callback
    transcriber.add_result_callback(cli_transcription_callback)
    
    print("✅ Transcription system test passed")
    print(f"📊 Stats: {transcriber.get_stats()}")
    
    # Cleanup
    transcriber.shutdown()
