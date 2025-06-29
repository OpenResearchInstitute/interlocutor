#!/usr/bin/env python3
"""
Audio Device Manager for Opulent Voice Radio
Provides radio operator-friendly audio device selection and testing
"""

import pyaudio
import wave
import tempfile
import threading
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
import yaml


@dataclass
class AudioDevice:
    """Represents an audio device with radio-relevant info"""
    index: int
    name: str
    max_input_channels: int
    max_output_channels: int
    default_sample_rate: float
    is_usb: bool
    is_default_input: bool
    is_default_output: bool
    api_name: str
    
    def __str__(self):
        usb_indicator = "🎧" if self.is_usb else "🔌"
        default_in = " [DEFAULT IN]" if self.is_default_input else ""
        default_out = " [DEFAULT OUT]" if self.is_default_output else ""
        return f"{usb_indicator} {self.name}{default_in}{default_out}"
    
    @property
    def can_record(self) -> bool:
        return self.max_input_channels > 0
    
    @property
    def can_playback(self) -> bool:
        return self.max_output_channels > 0
    
    @property
    def supports_48khz(self) -> bool:
        """Check if device likely supports 48kHz (our target rate)"""
        return self.default_sample_rate >= 48000 or self.is_usb


class AudioDeviceManager:
    """
    Radio operator-friendly audio device manager
    
    Like a radio's front panel - clear, simple, and reliable
    """
    
    def __init__(self, config_file: str = "audio_config.yaml", radio_config=None):
        self.config_file = Path(config_file)
        self.audio = pyaudio.PyAudio()
        self.current_input_device = None
        self.current_output_device = None
        self.test_tone_playing = False
        
        # Get audio parameters - robust fallback chain
        self.audio_params = self._get_audio_params(radio_config)
        
        # Load saved preferences
        self.load_config()
    
    def _get_audio_params(self, radio_config) -> Dict:
        """
        Get audio parameters with robust fallback chain
        Ensures consistency between testing and actual radio operation
        """
        try:
            if radio_config and hasattr(radio_config, 'audio'):
                # Use actual radio config if available
                return {
                    'sample_rate': radio_config.audio.sample_rate,
                    'channels': radio_config.audio.channels,
                    'frame_duration_ms': radio_config.audio.frame_duration_ms,
                    'frames_per_buffer': int(radio_config.audio.sample_rate * 
                                           radio_config.audio.frame_duration_ms / 1000)
                }
        except (AttributeError, TypeError) as e:
            print(f"⚠ Radio config issue ({e}), using Opulent Voice defaults")
        
        # Import defaults from your main config system if possible
        try:
            from config_manager import OpulentVoiceConfig
            default_config = OpulentVoiceConfig()  # Get system defaults
            return {
                'sample_rate': default_config.audio.sample_rate,
                'channels': default_config.audio.channels, 
                'frame_duration_ms': default_config.audio.frame_duration_ms,
                'frames_per_buffer': int(default_config.audio.sample_rate * 
                                       default_config.audio.frame_duration_ms / 1000)
            }
        except ImportError:
            print("⚠ Config manager not available, using hardcoded Opulent Voice defaults")
        
        # Final fallback - hardcoded Opulent Voice Protocol defaults
        # These MUST match your protocol specification
        return {
            'sample_rate': 48000,      # Opulent Voice Protocol requirement
            'channels': 1,             # Mono for radio
            'frame_duration_ms': 40,   # Opulent Voice Protocol requirement  
            'frames_per_buffer': 1920  # 48000 * 0.040 = 1920 samples
        }
    
    def discover_devices(self) -> List[AudioDevice]:
        """Discover all audio devices with radio-relevant info"""
        devices = []
        default_input = self.audio.get_default_input_device_info()
        default_output = self.audio.get_default_output_device_info()
        
        for i in range(self.audio.get_device_count()):
            try:
                info = self.audio.get_device_info_by_index(i)
                
                # Detect USB devices (common radio interfaces)
                is_usb = self._is_usb_device(info['name'])
                
                device = AudioDevice(
                    index=i,
                    name=info['name'],
                    max_input_channels=info['maxInputChannels'],
                    max_output_channels=info['maxOutputChannels'],
                    default_sample_rate=info['defaultSampleRate'],
                    is_usb=is_usb,
                    is_default_input=(i == default_input['index']),
                    is_default_output=(i == default_output['index']),
                    api_name=self.audio.get_host_api_info_by_index(info['hostApi'])['name']
                )
                devices.append(device)
                
            except Exception as e:
                print(f"Warning: Could not query device {i}: {e}")
        
        return devices
    
    def _is_usb_device(self, device_name: str) -> bool:
        """Detect if a device is likely USB-connected"""
        usb_indicators = [
            'usb', 'headset', 'webcam', 'logitech', 'plantronics', 
            'jabra', 'sennheiser', 'audio-technica', 'blue', 'samson',
            'focusrite', 'scarlett', 'behringer', 'zoom', 'tascam'
        ]
        name_lower = device_name.lower()
        return any(indicator in name_lower for indicator in usb_indicators)
    
    def show_device_menu(self) -> None:
        """Display radio operator-friendly device selection menu"""
        devices = self.discover_devices()
        
        print("\n" + "="*70)
        print("🎧 AUDIO DEVICE SELECTION - Opulent Voice Radio")
        print("="*70)
        
        # Separate by capability for easier selection
        input_devices = [d for d in devices if d.can_record]
        output_devices = [d for d in devices if d.can_playback]
        
        print("\n📡 INPUT DEVICES (Microphones):")
        print("   (Choose your microphone/headset input)")
        for i, device in enumerate(input_devices):
            rate_info = f"@{device.default_sample_rate:.0f}Hz"
            selected = "👈 CURRENT" if self.current_input_device == device.index else ""
            print(f"   {i+1:2d}. {device} {rate_info} {selected}")
        
        print("\n🔊 OUTPUT DEVICES (Speakers/Headphones):")
        print("   (Choose your speaker/headset output)")
        for i, device in enumerate(output_devices):
            rate_info = f"@{device.default_sample_rate:.0f}Hz"
            selected = "👈 CURRENT" if self.current_output_device == device.index else ""
            print(f"   {i+1:2d}. {device} {rate_info} {selected}")
        
        print("\n💡 RADIO OPERATOR TIPS:")
        print("   🎧 USB devices are typically best for radio use")
        print("   📻 48kHz sample rate is ideal for digital voice")
        print("   🔌 Built-in audio works but may have more latency")
        
        return input_devices, output_devices
    
    def select_devices_interactive(self) -> Tuple[Optional[int], Optional[int]]:
        """Interactive device selection with testing"""
        input_devices, output_devices = self.show_device_menu()
        
        # Select input device
        print(f"\n🎤 SELECT INPUT DEVICE:")
        while True:
            try:
                choice = input("Enter input device number (1-{}, or 's' to skip): ".format(len(input_devices)))
                if choice.lower() == 's':
                    input_device = None
                    break
                
                idx = int(choice) - 1
                if 0 <= idx < len(input_devices):
                    input_device = input_devices[idx].index
                    print(f"✓ Selected: {input_devices[idx]}")
                    
                    # Test the input device
                    if self.test_input_device(input_device):
                        break
                    else:
                        print("❌ Device test failed. Try another device.")
                else:
                    print(f"Please enter 1-{len(input_devices)}")
            except ValueError:
                print("Please enter a valid number")
        
        # Select output device
        print(f"\n🔊 SELECT OUTPUT DEVICE:")
        while True:
            try:
                choice = input("Enter output device number (1-{}, or 's' to skip): ".format(len(output_devices)))
                if choice.lower() == 's':
                    output_device = None
                    break
                
                idx = int(choice) - 1
                if 0 <= idx < len(output_devices):
                    output_device = output_devices[idx].index
                    print(f"✓ Selected: {output_devices[idx]}")
                    
                    # Test the output device
                    print("🔊 Testing output device... (you should hear a tone)")
                    if self.test_output_device(output_device):
                        user_confirm = input("Did you hear the test tone? (y/n): ").lower()
                        if user_confirm in ['y', 'yes']:
                            break
                        else:
                            print("❌ Let's try another device.")
                    else:
                        print("❌ Device test failed. Try another device.")
                else:
                    print(f"Please enter 1-{len(output_devices)}")
            except ValueError:
                print("Please enter a valid number")
        
        return input_device, output_device
    
    def test_input_device(self, device_index: int, duration: float = 2.0) -> bool:
        """Test input device with EXACT radio system parameters"""
        try:
            params = self.audio_params
            print(f"🎤 Testing with Opulent Voice settings:")
            print(f"   📊 {params['sample_rate']}Hz, {params['frame_duration_ms']}ms frames")
            print(f"   📦 {params['frames_per_buffer']} samples per buffer")
            print(f"   🎙️ Speak into microphone for {duration} seconds...")
            
            stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=params['channels'],
                rate=params['sample_rate'],
                input=True,
                input_device_index=device_index,
                frames_per_buffer=params['frames_per_buffer']  # EXACT radio settings
            )
            
            # Monitor audio levels for visual feedback
            max_level = 0
            start_time = time.time()
            
            while time.time() - start_time < duration:
                try:
                    data = stream.read(params['frames_per_buffer'], exception_on_overflow=False)
                    # Simple level detection (convert bytes to approximate dB)
                    level = max(abs(int.from_bytes(data[i:i+2], 'little', signed=True)) 
                               for i in range(0, len(data), 2))
                    max_level = max(max_level, level)
                    
                    # Visual level meter (simplified)
                    bars = int((level / 32768.0) * 20)
                    meter = "█" * bars + "░" * (20 - bars)
                    print(f"\r   Level: [{meter}] {level/32768.0:.1%}", end="", flush=True)
                except Exception as e:
                    print(f"\r   Audio read error: {e}", end="", flush=True)
                    
            print()  # New line after meter
            stream.close()
            
            # Check if we got reasonable audio levels
            if max_level > 1000:  # Arbitrary threshold
                print(f"✓ Input test successful! Max level: {max_level/32768.0:.1%}")
                return True
            else:
                print(f"⚠ Low audio levels detected. Check microphone connection.")
                return False
                
        except Exception as e:
            print(f"❌ Input test failed: {e}")
            return False
    
    def test_output_device(self, device_index: int, duration: float = 1.0) -> bool:
        """Test output device with 1kHz tone using exact radio parameters"""
        try:
            import numpy as np
            
            params = self.audio_params
            print(f"🔊 Testing output with radio settings: {params['sample_rate']}Hz")
            
            # Generate 1kHz test tone
            frames = int(params['sample_rate'] * duration)
            tone = np.sin(2 * np.pi * 1000 * np.linspace(0, duration, frames))
            tone = (tone * 16384).astype(np.int16)  # Scale to 16-bit
            
            stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=params['channels'],
                rate=params['sample_rate'],
                output=True,
                output_device_index=device_index,
                frames_per_buffer=params['frames_per_buffer']  # EXACT radio settings
            )
            
            # Play the tone
            stream.write(tone.tobytes())
            stream.close()
            
            return True
            
        except ImportError:
            print("⚠ numpy not available for tone generation, skipping audio test")
            return True  # Assume it works
        except Exception as e:
            print(f"❌ Output test failed: {e}")
            return False
    
    def save_config(self, input_device: Optional[int], output_device: Optional[int]) -> None:
        """Save device preferences to config file"""
        config = {
            'audio_devices': {
                'input_device_index': input_device,
                'output_device_index': output_device,
                'last_updated': time.strftime('%Y-%m-%d %H:%M:%S')
            }
        }
        
        try:
            with open(self.config_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False)
            print(f"✓ Audio preferences saved to {self.config_file}")
        except Exception as e:
            print(f"⚠ Could not save config: {e}")
    
    def load_config(self) -> None:
        """Load device preferences from config file"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    config = yaml.safe_load(f)
                
                audio_config = config.get('audio_devices', {})
                self.current_input_device = audio_config.get('input_device_index')
                self.current_output_device = audio_config.get('output_device_index')
                
                print(f"✓ Loaded audio preferences from {self.config_file}")
        except Exception as e:
            print(f"⚠ Could not load config: {e}")
    
    def get_recommended_devices(self) -> Tuple[Optional[int], Optional[int]]:
        """Get smart device recommendations for radio use"""
        devices = self.discover_devices()
        
        # Prioritize USB devices for radio use
        usb_input = None
        usb_output = None
        
        for device in devices:
            if device.is_usb and device.can_record and device.supports_48khz:
                if usb_input is None:
                    usb_input = device.index
            
            if device.is_usb and device.can_playback and device.supports_48khz:
                if usb_output is None:
                    usb_output = device.index
        
        # Fall back to defaults if no USB devices
        if usb_input is None:
            for device in devices:
                if device.is_default_input and device.can_record:
                    usb_input = device.index
                    break
        
        if usb_output is None:
            for device in devices:
                if device.is_default_output and device.can_playback:
                    usb_output = device.index
                    break
        
        return usb_input, usb_output
    
    def setup_audio_devices(self, force_selection: bool = False) -> Tuple[Optional[int], Optional[int]]:
        """
        Main entry point for audio device setup
        
        Returns: (input_device_index, output_device_index)
        """
        print("\n🎧 OPULENT VOICE AUDIO SETUP")
        print("Setting up audio devices for radio operation...")
        
        # Check if we have saved preferences and they still exist
        if not force_selection and self.current_input_device is not None:
            if self._device_still_exists(self.current_input_device):
                print(f"✓ Using saved input device: {self._get_device_name(self.current_input_device)}")
                use_saved = input("Use saved audio settings? (y/n, or 'c' to change): ").lower()
                
                if use_saved in ['y', 'yes', '']:
                    return self.current_input_device, self.current_output_device
                elif use_saved == 'c':
                    pass  # Continue to selection
                else:
                    # Show recommendations
                    rec_input, rec_output = self.get_recommended_devices()
                    if rec_input or rec_output:
                        print("\n💡 RECOMMENDED DEVICES FOR RADIO:")
                        if rec_input:
                            print(f"   Input: {self._get_device_name(rec_input)}")
                        if rec_output:
                            print(f"   Output: {self._get_device_name(rec_output)}")
                        
                        use_rec = input("Use recommended devices? (y/n): ").lower()
                        if use_rec in ['y', 'yes']:
                            self.save_config(rec_input, rec_output)
                            return rec_input, rec_output
        
        # Interactive selection
        input_device, output_device = self.select_devices_interactive()
        
        # Save preferences
        self.save_config(input_device, output_device)
        
        print(f"\n✅ Audio setup complete!")
        if input_device:
            print(f"   🎤 Input: {self._get_device_name(input_device)}")
        if output_device:
            print(f"   🔊 Output: {self._get_device_name(output_device)}")
        
        return input_device, output_device
    
    def _device_still_exists(self, device_index: int) -> bool:
        """Check if a saved device index still exists"""
        try:
            self.audio.get_device_info_by_index(device_index)
            return True
        except:
            return False
    
    def _get_device_name(self, device_index: int) -> str:
        """Get device name by index"""
        try:
            return self.audio.get_device_info_by_index(device_index)['name']
        except:
            return "Unknown Device"
    
    def cleanup(self):
        """Clean up PyAudio resources"""
        self.audio.terminate()


# Integration example for your existing code
class AudioDeviceIntegration:
    """
    Example of how to integrate this into your existing GPIOZeroPTTHandler
    """
    
    @staticmethod
    def setup_audio_with_device_selection(config):
        """
        Replace the existing setup_audio method in GPIOZeroPTTHandler
        """
        device_manager = AudioDeviceManager()
        
        # Get device selection
        input_device, output_device = device_manager.setup_audio_devices()
        
        # Update config with selected devices
        if hasattr(config.audio, 'input_device_index'):
            config.audio.input_device_index = input_device
        if hasattr(config.audio, 'output_device_index'):
            config.audio.output_device_index = output_device
        
        device_manager.cleanup()
        return input_device, output_device


if __name__ == "__main__":
    # Demo/test the audio device manager
    manager = AudioDeviceManager()
    
    try:
        input_dev, output_dev = manager.setup_audio_devices()
        print(f"\nSelected devices: Input={input_dev}, Output={output_dev}")
    finally:
        manager.cleanup()
