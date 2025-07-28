#!/usr/bin/env python3
"""
Enhanced AudioDeviceManager with CLI and Interactive modes
This replaces your existing audio_device_manager.py
"""

import os
import sys
import time
import yaml
import numpy as np
from enum import Enum
from typing import Optional, List, Tuple, Dict, Any
from pathlib import Path
from dataclasses import dataclass
import logging

# Try to import pyaudio, handle gracefully if not available
try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    print("⚠️  PyAudio not available - running in mock mode")

class AudioManagerMode(Enum):
    """Operating modes for the audio device manager"""
    CLI_DIAGNOSTIC = "cli_diagnostic"    # Non-interactive, for --list-audio, --test-audio
    INTERACTIVE = "interactive"          # Interactive mode for runtime setup
    AUTOMATED = "automated"              # Use saved config, minimal interaction

@dataclass
class AudioDevice:
    """Represents an audio device"""
    index: int
    name: str
    can_record: bool
    can_playback: bool
    default_sample_rate: float
    max_input_channels: int
    max_output_channels: int
    host_api: str = "Unknown"
    
    def __str__(self):
        capabilities = []
        if self.can_record:
            capabilities.append(f"{self.max_input_channels} in")
        if self.can_playback:
            capabilities.append(f"{self.max_output_channels} out")
        cap_str = f"({', '.join(capabilities)})" if capabilities else "(no capabilities)"
        return f"{self.name} [{self.host_api}] {cap_str}"

class AudioDeviceManager:
    """Enhanced audio device manager with context-aware behavior"""
    
    def __init__(self, mode: AudioManagerMode = AudioManagerMode.AUTOMATED, 
                 config_file="audio_config.yaml", radio_config=None):
        self.mode = mode
        self.config_file = config_file
        self.radio_config = radio_config
        self.current_input_device = None
        self.current_output_device = None
        self.logger = logging.getLogger(__name__)
        
        # Test mode detection
        self.test_mode = os.environ.get('OPULENT_VOICE_TEST_MODE') == '1'

        # UPDATED: Audio parameters - ALWAYS use protocol requirements
        # Ignore any user config values for sample_rate and frame_duration_ms
        self.audio_params = {
            'sample_rate': 48000,  # PROTOCOL REQUIREMENT - not configurable
            'channels': 1,
            'frames_per_buffer': 1920,  # 40ms at 48kHz - PROTOCOL REQUIREMENT
            'frame_duration_ms': 40  # PROTOCOL REQUIREMENT - not configurable
        }
    
        # Log that we're enforcing protocol requirements
        if radio_config and hasattr(radio_config, 'audio'):
            if (radio_config.audio.sample_rate != 48000 or 
                radio_config.audio.frame_duration_ms != 40):
                self.logger.warning("Overriding user audio config with protocol requirements")
    
        self.logger.debug(f"AudioDeviceManager: Protocol requirements enforced (48kHz, 40ms)")


        
        self.logger.debug(f"AudioDeviceManager initialized in {mode.value} mode")
    
    def discover_devices(self) -> List[AudioDevice]:
        """Discover audio devices - behavior depends on mode"""
        if self.test_mode:
            return self._create_mock_devices()
        
        if not PYAUDIO_AVAILABLE:
            self.logger.warning("PyAudio not available, using mock devices")
            return self._create_mock_devices()
        
        if self.mode == AudioManagerMode.CLI_DIAGNOSTIC:
            # CLI mode: Just discover and return, no user interaction
            return self._discover_devices_non_interactive()
        else:
            # Normal discovery
            return self._discover_devices_full()
    
    def setup_audio_devices(self, force_selection=False) -> Tuple[Optional[int], Optional[int]]:
        """Setup audio devices with mode-aware behavior"""
        
        if self.test_mode:
            return self._setup_mock_devices()
        
        if self.mode == AudioManagerMode.CLI_DIAGNOSTIC:
            # CLI mode: Use defaults or saved config, no interaction
            return self._setup_devices_non_interactive()
        
        elif self.mode == AudioManagerMode.INTERACTIVE:
            # Interactive mode: Show menus, ask for input
            return self._setup_devices_interactive(force_selection)
        
        else:  # AUTOMATED mode
            # Try saved config first, fall back to smart defaults
            return self._setup_devices_automated(force_selection)
    
    def test_audio_devices(self, input_device: int = None, output_device: int = None) -> bool:
        """Test audio devices - mode-aware"""
        
        if self.test_mode:
            return self._test_mock_devices()
        
        if not PYAUDIO_AVAILABLE:
            print("⚠️  PyAudio not available - cannot test real devices")
            return False
        
        if self.mode == AudioManagerMode.CLI_DIAGNOSTIC:
            # CLI mode: Quick test, minimal output
            return self._test_devices_cli(input_device, output_device)
        else:
            # Interactive/automated: Full test with feedback
            return self._test_devices_full(input_device, output_device)
    
    def list_devices_cli_format(self) -> None:
        """List devices in CLI-friendly format (for --list-audio)"""
        devices = self.discover_devices()
        
        input_devices = [d for d in devices if d.can_record]
        output_devices = [d for d in devices if d.can_playback]
        
        print("🎧 Available Audio Devices:")
        print("\n📡 INPUT DEVICES (Microphones):")
        
        if not input_devices:
            print("   No input devices found")
        else:
            for device in input_devices:
                rate_info = f"@{device.default_sample_rate:.0f}Hz"
                print(f"   {device.index:2d}. {device.name} {rate_info}")
                if self.mode == AudioManagerMode.CLI_DIAGNOSTIC and hasattr(device, 'host_api'):
                    print(f"       Host API: {device.host_api}")
        
        print("\n🔊 OUTPUT DEVICES (Speakers/Headphones):")
        
        if not output_devices:
            print("   No output devices found")
        else:
            for device in output_devices:
                rate_info = f"@{device.default_sample_rate:.0f}Hz"
                print(f"   {device.index:2d}. {device.name} {rate_info}")
                if self.mode == AudioManagerMode.CLI_DIAGNOSTIC and hasattr(device, 'host_api'):
                    print(f"       Host API: {device.host_api}")
        
        # Show current selection if available
        self.load_config()
        if self.current_input_device is not None or self.current_output_device is not None:
            print(f"\n💾 Current Selection:")
            print(f"   Input:  {self.current_input_device}")
            print(f"   Output: {self.current_output_device}")
    
    def test_audio_cli_format(self) -> bool:
        """Test audio in CLI-friendly format (for --test-audio)"""
        print("🎧 Testing Audio Devices:")
        
        # Load or determine devices to test
        self.load_config()
        input_device = self.current_input_device
        output_device = self.current_output_device
        
        if input_device is None or output_device is None:
            print("📝 No saved audio config found, using recommended devices...")
            rec_input, rec_output = self.get_recommended_devices()
            input_device = input_device or rec_input or 0
            output_device = output_device or rec_output or 0
        
        print(f"📋 Testing devices:")
        print(f"   Input device: {input_device}")
        print(f"   Output device: {output_device}")
        print()
        
        success = True
        
        # Test input
        print(f"🎤 Testing input device {input_device}...")
        try:
            input_result = self.test_input_device(input_device, duration=3.0, verbose=False)
            if input_result:
                print("✅ Input device test PASSED")
            else:
                print("❌ Input device test FAILED (low audio levels)")
                success = False
        except Exception as e:
            print(f"❌ Input device test FAILED: {e}")
            success = False
        
        print()
        
        # Test output
        print(f"🔊 Testing output device {output_device}...")
        try:
            output_result = self.test_output_device(output_device, duration=2.0, verbose=False)
            if output_result:
                print("✅ Output device test PASSED (you should have heard a 1kHz tone)")
            else:
                print("❌ Output device test FAILED")
                success = False
        except Exception as e:
            print(f"❌ Output device test FAILED: {e}")
            success = False
        
        return success
    
    def test_input_device(self, device_index: int, duration: float = 3.0, verbose: bool = True) -> bool:
        """Test an input device by recording audio"""
        if self.test_mode or not PYAUDIO_AVAILABLE:
            if verbose:
                print(f"Mock input test for device {device_index}")
            return True
        
        try:
            audio = pyaudio.PyAudio()
            
            if verbose:
                print(f"Recording from device {device_index} for {duration}s...")
            
            # Open stream
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=self.audio_params['channels'],
                rate=self.audio_params['sample_rate'],
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.audio_params['frames_per_buffer']
            )
            
            # Record audio
            frames = []
            for i in range(int(self.audio_params['sample_rate'] / self.audio_params['frames_per_buffer'] * duration)):
                data = stream.read(self.audio_params['frames_per_buffer'])
                frames.append(data)
            
            stream.stop_stream()
            stream.close()
            audio.terminate()
            
            # Analyze audio level
            audio_data = b''.join(frames)
            audio_np = np.frombuffer(audio_data, dtype=np.int16)
            rms = np.sqrt(np.mean(audio_np.astype(np.float32) ** 2))
            
            if verbose:
                print(f"Audio level (RMS): {rms:.1f}")
            
            # Consider test passed if RMS > 100 (some audio detected)
            return rms > 100
            
        except Exception as e:
            if verbose:
                print(f"Input test error: {e}")
            return False
    
    def test_output_device(self, device_index: int, duration: float = 2.0, verbose: bool = True) -> bool:
        """Test an output device by playing a tone"""
        if self.test_mode or not PYAUDIO_AVAILABLE:
            if verbose:
                print(f"Mock output test for device {device_index}")
            return True
        
        try:
            audio = pyaudio.PyAudio()
            
            if verbose:
                print(f"Playing 1kHz tone on device {device_index} for {duration}s...")
            
            # Generate 1kHz sine wave
            sample_rate = self.audio_params['sample_rate']
            frames_per_buffer = self.audio_params['frames_per_buffer']
            
            t = np.linspace(0, duration, int(sample_rate * duration), False)
            tone = np.sin(2 * np.pi * 1000 * t) * 0.3  # 1kHz at 30% volume
            tone = (tone * 32767).astype(np.int16)
            
            # Open stream
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=self.audio_params['channels'],
                rate=sample_rate,
                output=True,
                output_device_index=device_index,
                frames_per_buffer=frames_per_buffer
            )
            
            # Play tone
            for i in range(0, len(tone), frames_per_buffer):
                chunk = tone[i:i+frames_per_buffer]
                if len(chunk) < frames_per_buffer:
                    # Pad the last chunk
                    chunk = np.pad(chunk, (0, frames_per_buffer - len(chunk)), 'constant')
                stream.write(chunk.tobytes())
            
            stream.stop_stream()
            stream.close()
            audio.terminate()
            
            return True
            
        except Exception as e:
            if verbose:
                print(f"Output test error: {e}")
            return False
    
    def get_recommended_devices(self) -> Tuple[Optional[int], Optional[int]]:
        """Get recommended input and output devices"""
        devices = self.discover_devices()
        
        # Look for USB devices first (preference from config)
        usb_keywords = ["USB", "Samson", "C01U"]
        
        best_input = None
        best_output = None
        
        # Find best input device
        for device in devices:
            if device.can_record:
                # Prefer USB devices
                if any(keyword.lower() in device.name.lower() for keyword in usb_keywords):
                    best_input = device.index
                    break
                # Fallback to first available input
                elif best_input is None:
                    best_input = device.index
        
        # Find best output device
        for device in devices:
            if device.can_playback:
                # Prefer devices with "Speakers" or "Headphones" in name
                if any(keyword.lower() in device.name.lower() for keyword in ["speakers", "headphones"]):
                    best_output = device.index
                    break
                # Fallback to first available output
                elif best_output is None:
                    best_output = device.index
        
        return best_input, best_output
    
    def load_config(self) -> bool:
        """Load saved audio configuration"""
        try:
            if Path(self.config_file).exists():
                with open(self.config_file, 'r') as f:
                    config = yaml.safe_load(f)
                    
                audio_devices = config.get('audio_devices', {})
                self.current_input_device = audio_devices.get('input_device_index')
                self.current_output_device = audio_devices.get('output_device_index')
                
                return True
        except Exception as e:
            self.logger.debug(f"Error loading audio config: {e}")
        
        return False
    
    def save_config(self) -> bool:
        """Save current audio configuration"""
        try:
            config = {
                'audio_devices': {
                    'input_device_index': self.current_input_device,
                    'output_device_index': self.current_output_device,
                    'last_updated': time.strftime('%Y-%m-%d %H:%M:%S')
                }
            }
            
            with open(self.config_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False)
            
            return True
        except Exception as e:
            self.logger.error(f"Error saving audio config: {e}")
            return False
    
    def cleanup(self):
        """Cleanup resources"""
        pass
    
    # Private implementation methods
    
    def _discover_devices_non_interactive(self) -> List[AudioDevice]:
        """Non-interactive device discovery for CLI mode"""
        try:
            audio = pyaudio.PyAudio()
            devices = []
            
            for i in range(audio.get_device_count()):
                try:
                    info = audio.get_device_info_by_index(i)
                    host_api_info = audio.get_host_api_info_by_index(info['hostApi'])
                    
                    device = AudioDevice(
                        index=i,
                        name=info['name'],
                        can_record=info['maxInputChannels'] > 0,
                        can_playback=info['maxOutputChannels'] > 0,
                        default_sample_rate=info['defaultSampleRate'],
                        max_input_channels=info['maxInputChannels'],
                        max_output_channels=info['maxOutputChannels'],
                        host_api=host_api_info['name']
                    )
                    devices.append(device)
                except Exception:
                    continue  # Skip problematic devices
            
            audio.terminate()
            return devices
            
        except Exception as e:
            self.logger.warning(f"Error discovering devices: {e}")
            return self._create_mock_devices()
    
    def _discover_devices_full(self) -> List[AudioDevice]:
        """Full device discovery with error handling"""
        return self._discover_devices_non_interactive()  # Same implementation for now
    
    def _setup_devices_non_interactive(self) -> Tuple[Optional[int], Optional[int]]:
        """Non-interactive device setup for CLI mode"""
        # Try to load saved config
        self.load_config()
        
        if self.current_input_device is not None and self.current_output_device is not None:
            return self.current_input_device, self.current_output_device
        
        # Fall back to recommended devices
        rec_input, rec_output = self.get_recommended_devices()
        return rec_input or 0, rec_output or 0
    
    def _setup_devices_interactive(self, force_selection=False) -> Tuple[Optional[int], Optional[int]]:
        """Interactive device setup with user prompts"""
        # Load existing config
        self.load_config()
        
        if not force_selection and self.current_input_device is not None and self.current_output_device is not None:
            print(f"📱 Current audio devices:")
            print(f"   Input:  {self.current_input_device}")
            print(f"   Output: {self.current_output_device}")
            
            response = input("Do you want to change these? (y/N): ").strip().lower()
            if response not in ['y', 'yes']:
                return self.current_input_device, self.current_output_device
        
        # Interactive device selection
        devices = self.discover_devices()
        return self._interactive_device_selection(devices)





















    def _interactive_device_selection(self, devices: List[AudioDevice]) -> Tuple[Optional[int], Optional[int]]:
        """Interactive device selection menu with level indicators and testing"""
        input_devices = [d for d in devices if d.can_record]
        output_devices = [d for d in devices if d.can_playback]
    
        # === INPUT DEVICE SELECTION ===
        print("\n🎤 Select Input Device:")
        for i, device in enumerate(input_devices):
            print(f"   {i+1}. {device}")
    
        selected_input = None
        while selected_input is None:
            try:
                choice = input(f"\nChoose input device to test (1-{len(input_devices)}): ").strip()
                if choice.isdigit() and 1 <= int(choice) <= len(input_devices):
                    device_to_test = input_devices[int(choice)-1]
                    print(f"\n🎤 Testing: {device_to_test.name}")
                
                    # Test the input device with level indicator
                    if self._test_input_device_with_level_indicator(device_to_test.index):
                        confirm = input(f"✅ Use this input device? (Y/n): ").strip().lower()
                        if confirm in ['', 'y', 'yes']:
                            selected_input = device_to_test.index
                        else:
                            print("👍 Try another device...")
                            continue
                    else:
                        print("❌ Device test failed or no audio detected.")
                        retry = input("Try this device again? (y/N): ").strip().lower()
                        if retry not in ['y', 'yes']:
                            print("👍 Try another device...")
                            continue
                else:
                    print("Invalid choice. Please try again.")
            except (ValueError, KeyboardInterrupt):
                print("Selection cancelled.")
                return None, None
    
        # === OUTPUT DEVICE SELECTION ===
        print("\n🔊 Select Output Device:")
        for i, device in enumerate(output_devices):
            print(f"   {i+1}. {device}")
    
        selected_output = None
        while selected_output is None:
            try:
                choice = input(f"\nChoose output device to test (1-{len(output_devices)}): ").strip()
                if choice.isdigit() and 1 <= int(choice) <= len(output_devices):
                    device_to_test = output_devices[int(choice)-1]
                    print(f"\n🔊 Testing: {device_to_test.name}")
                
                    # Test the output device
                    if self._test_output_device_with_confirmation(device_to_test.index):
                        confirm = input(f"✅ Use this output device? (Y/n): ").strip().lower()
                        if confirm in ['', 'y', 'yes']:
                            selected_output = device_to_test.index
                        else:
                            print("👍 Try another device...")
                            continue
                    else:
                        print("❌ Device test failed.")
                        retry = input("Try this device again? (y/N): ").strip().lower()
                        if retry not in ['y', 'yes']:
                            print("👍 Try another device...")
                            continue
                else:
                    print("Invalid choice. Please try again.")
            except (ValueError, KeyboardInterrupt):
                print("Selection cancelled.")
                return None, None
    
        # Save the selection
        self.current_input_device = selected_input
        self.current_output_device = selected_output
        self.save_config()
    
        print(f"\n🎉 Audio setup complete!")
        print(f"   Input device:  {selected_input}")
        print(f"   Output device: {selected_output}")
    
        return selected_input, selected_output

    def _test_input_device_with_level_indicator(self, device_index: int, duration: float = 4.0) -> bool:
        """Test input device with real-time level indicator"""
        if self.test_mode or not PYAUDIO_AVAILABLE:
            print("🧪 Mock level test: ████████░░ (80%)")
            return True
    
        try:
            import threading
            import sys
        
            audio = pyaudio.PyAudio()
        
            print(f"🎤 Speak into microphone for {duration:.0f} seconds...")
            print("🔊 Level indicator:")
        
            # Open stream
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=self.audio_params['channels'],
                rate=self.audio_params['sample_rate'],
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.audio_params['frames_per_buffer']
            )
        
            # Variables for level monitoring
            max_level = 0
            frame_count = int(self.audio_params['sample_rate'] / self.audio_params['frames_per_buffer'] * duration)
            level_history = []
        
            print("", end="", flush=True)  # Prepare for level indicator updates
          
            # Record and show level in real-time
            for i in range(frame_count):
                try:
                    data = stream.read(self.audio_params['frames_per_buffer'], exception_on_overflow=False)
                
                    # Calculate audio level
                    audio_np = np.frombuffer(data, dtype=np.int16)
                    rms = np.sqrt(np.mean(audio_np.astype(np.float32) ** 2))
                    level_history.append(rms)
                    max_level = max(max_level, rms)
                
                    # Create level indicator bar
                    level_percent = min(100, int((rms / 1000) * 100))  # Scale for display
                    bar_length = 20
                    filled_length = int(bar_length * level_percent / 100)
                    bar = "█" * filled_length + "░" * (bar_length - filled_length)
                
                    # Update level indicator on same line
                    sys.stdout.write(f"\r🎤 Level: {bar} ({level_percent:3d}%)")
                    sys.stdout.flush()
                
                except Exception as e:
                    # Continue on overflow or other errors
                    continue
        
            stream.stop_stream()
            stream.close()
            audio.terminate()
        
            print()  # New line after level indicator
        
            # Analyze results
            avg_level = np.mean(level_history) if level_history else 0
        
            print(f"📊 Test results:")
            print(f"   Average level: {avg_level:.1f}")
            print(f"   Peak level: {max_level:.1f}")
        
            # Consider test passed if we detected some audio
            success = max_level > 100  # Threshold for "some audio detected"
        
            if success:
                print("✅ Audio detected - microphone is working!")
            else:
                print("⚠️  Very low audio levels - check microphone connection")
        
            return success
        
        except Exception as e:
            print(f"❌ Input test error: {e}")
            return False

    def _test_output_device_with_confirmation(self, device_index: int, duration: float = 2.0) -> bool:
        """Test output device and ask user if they heard it"""
        if self.test_mode or not PYAUDIO_AVAILABLE:
            print("🧪 Mock output test - playing imaginary 1kHz tone")
            heard = input("Did you hear the test tone? (Y/n): ").strip().lower()
            return heard in ['', 'y', 'yes']
    
        try:
            audio = pyaudio.PyAudio()
        
            print(f"🔊 Playing 1kHz test tone for {duration:.0f} seconds...")
        
            # Generate 1kHz sine wave
            sample_rate = self.audio_params['sample_rate']
            frames_per_buffer = self.audio_params['frames_per_buffer']
        
            t = np.linspace(0, duration, int(sample_rate * duration), False)
            tone = np.sin(2 * np.pi * 1000 * t) * 0.3  # 1kHz at 30% volume
            tone = (tone * 32767).astype(np.int16)
        
            # Open stream
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=self.audio_params['channels'],
                rate=sample_rate,
                output=True,
                output_device_index=device_index,
                frames_per_buffer=frames_per_buffer
            )
        
            # Play tone with progress indicator
            total_frames = len(tone)
            for i in range(0, total_frames, frames_per_buffer):
                chunk = tone[i:i+frames_per_buffer]
                if len(chunk) < frames_per_buffer:
                    chunk = np.pad(chunk, (0, frames_per_buffer - len(chunk)), 'constant')
            
                stream.write(chunk.tobytes())
            
                # Show progress
                progress = int((i / total_frames) * 20)
                bar = "█" * progress + "░" * (20 - progress)
                percent = int((i / total_frames) * 100)
                print(f"\r🔊 Playing: {bar} ({percent:3d}%)", end="", flush=True)
        
            print(f"\r🔊 Playing: {'█' * 20} (100%)")  # Complete the progress bar
        
            stream.stop_stream()
            stream.close()
            audio.terminate()
        
            # Ask user if they heard it
            heard = input("Did you hear the test tone? (Y/n): ").strip().lower()
        
            if heard in ['', 'y', 'yes']:
                print("✅ Output device is working!")
                return True
            else:
                print("❌ Test tone not heard")
                return False
            
        except Exception as e:
            print(f"❌ Output test error: {e}")
            return False
























    def _setup_devices_automated(self, force_selection=False) -> Tuple[Optional[int], Optional[int]]:
        """Automated device setup for normal runtime"""
        # Try saved config first
        self.load_config()
        
        if self.current_input_device is not None and self.current_output_device is not None:
            if self._validate_saved_devices():
                return self.current_input_device, self.current_output_device
        
        # Fall back to recommended devices
        print("📝 Auto-selecting recommended audio devices...")
        rec_input, rec_output = self.get_recommended_devices()
        
        if rec_input is not None and rec_output is not None:
            # Save the auto-selected devices
            self.current_input_device = rec_input
            self.current_output_device = rec_output
            self.save_config()
            print(f"✅ Selected: Input={rec_input}, Output={rec_output}")
            return rec_input, rec_output
        
        # Last resort: use defaults
        return 0, 0
    
    def _validate_saved_devices(self) -> bool:
        """Validate that saved devices still exist"""
        try:
            devices = self.discover_devices()
            device_indices = {d.index for d in devices}
            
            input_valid = self.current_input_device in device_indices
            output_valid = self.current_output_device in device_indices
            
            return input_valid and output_valid
        except Exception:
            return False
    
    def _test_devices_cli(self, input_device=None, output_device=None) -> bool:
        """Quick CLI test without verbose output"""
        try:
            input_device = input_device or self.current_input_device or 0
            output_device = output_device or self.current_output_device or 0
            
            # Quick, non-verbose tests
            input_ok = self.test_input_device(input_device, duration=2.0, verbose=False)
            output_ok = self.test_output_device(output_device, duration=1.0, verbose=False)
            
            return input_ok and output_ok
            
        except Exception:
            return False
    
    def _test_devices_full(self, input_device=None, output_device=None) -> bool:
        """Full device test with verbose output"""
        try:
            input_device = input_device or self.current_input_device or 0
            output_device = output_device or self.current_output_device or 0
            
            # Full tests with verbose output
            input_ok = self.test_input_device(input_device, duration=3.0, verbose=True)
            output_ok = self.test_output_device(output_device, duration=2.0, verbose=True)
            
            return input_ok and output_ok
            
        except Exception as e:
            print(f"Device test error: {e}")
            return False
    
    def _create_mock_devices(self) -> List[AudioDevice]:
        """Create mock devices for testing"""
        return [
            AudioDevice(
                index=0,
                name='Default Input Device',
                can_record=True,
                can_playback=False,
                default_sample_rate=48000.0,
                max_input_channels=2,
                max_output_channels=0,
                host_api='Mock'
            ),
            AudioDevice(
                index=1,
                name='Default Output Device',
                can_record=False,
                can_playback=True,
                default_sample_rate=48000.0,
                max_input_channels=0,
                max_output_channels=2,
                host_api='Mock'
            ),
            AudioDevice(
                index=2,
                name='USB Audio Device (Mock)',
                can_record=True,
                can_playback=True,
                default_sample_rate=48000.0,
                max_input_channels=1,
                max_output_channels=2,
                host_api='Mock'
            )
        ]
    
    def _setup_mock_devices(self) -> Tuple[int, int]:
        """Setup mock devices for testing"""
        return 0, 1  # Mock input and output device indices
    
    def _test_mock_devices(self) -> bool:
        """Mock device testing always succeeds"""
        return True


def create_audio_manager_for_cli():
    return AudioDeviceManager(mode=AudioManagerMode.CLI_DIAGNOSTIC)

def create_audio_manager_for_interactive():
    return AudioDeviceManager(mode=AudioManagerMode.INTERACTIVE)

def create_audio_manager_for_runtime(radio_config):
    return AudioDeviceManager(mode=AudioManagerMode.AUTOMATED, radio_config=radio_config)
