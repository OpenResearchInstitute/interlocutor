#!/usr/bin/env python3
"""
Configuration system for Opulent Voice Protocol
Supports YAML files, CLI overrides, and programmatic access for GUI
"""

import yaml
import argparse
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass, asdict, field
from copy import deepcopy
import logging



@dataclass
class AudioReplayConfig:
    """Audio replay configuration for GUI"""
    enabled: bool = True
    max_stored_messages: int = 100
    storage_duration_hours: int = 24
    auto_cleanup: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML serialization"""
        return {
            'enabled': self.enabled,
            'max_stored_messages': self.max_stored_messages,
            'storage_duration_hours': self.storage_duration_hours,
            'auto_cleanup': self.auto_cleanup
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AudioReplayConfig':
        """Create from dictionary (YAML loading)"""
        return cls(
            enabled=data.get('enabled', True),
            max_stored_messages=data.get('max_stored_messages', 100),
            storage_duration_hours=data.get('storage_duration_hours', 24),
            auto_cleanup=data.get('auto_cleanup', True)
        )




@dataclass
class TranscriptionConfig:
    """Transcription configuration (Phase 3)"""
    enabled: bool = True
    method: str = "auto"  # auto, client-only, server-only, disabled
    language: str = "en-US"
    confidence_threshold: float = 0.7
    server_endpoint: str = "http://localhost:8001/transcribe"
    
    def __post_init__(self):
        """Validate configuration values"""
        valid_methods = ["auto", "client-only", "server-only", "disabled"]
        if self.method not in valid_methods:
            raise ValueError(f"Invalid transcription method: {self.method}. Must be one of {valid_methods}")
        
        if not (0.0 <= self.confidence_threshold <= 1.0):
            raise ValueError(f"Confidence threshold must be between 0.0 and 1.0, got {self.confidence_threshold}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML serialization"""
        return {
            'enabled': self.enabled,
            'method': self.method,
            'language': self.language,
            'confidence_threshold': self.confidence_threshold,
            'server_endpoint': self.server_endpoint
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TranscriptionConfig':
        """Create from dictionary (YAML loading)"""
        return cls(
            enabled=data.get('enabled', True),
            method=data.get('method', 'auto'),
            language=data.get('language', 'en-US'),
            confidence_threshold=data.get('confidence_threshold', 0.7),
            server_endpoint=data.get('server_endpoint', 'http://localhost:8001/transcribe')
        )






@dataclass
class AccessibilityConfig:
    """Accessibility configuration"""
    high_contrast: bool = False
    reduced_motion: bool = False
    screen_reader_optimized: bool = False
    keyboard_shortcuts: bool = True
    announce_new_messages: bool = True
    focus_management: bool = True
    font_family: str = "Atkinson Hyperlegible"
    font_size: str = "medium"  # small, medium, large, x-large, xx-large
    line_height: float = 1.6
    character_spacing: str = "normal"  # normal, wide
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML serialization"""
        return {
            'high_contrast': self.high_contrast,
            'reduced_motion': self.reduced_motion,
            'screen_reader_optimized': self.screen_reader_optimized,
            'keyboard_shortcuts': self.keyboard_shortcuts,
            'announce_new_messages': self.announce_new_messages,
            'focus_management': self.focus_management,
            'font_family': self.font_family,
            'font_size': self.font_size,
            'line_height': self.line_height,
            'character_spacing': self.character_spacing
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AccessibilityConfig':
        """Create from dictionary (YAML loading)"""
        return cls(
            high_contrast=data.get('high_contrast', False),
            reduced_motion=data.get('reduced_motion', False),
            screen_reader_optimized=data.get('screen_reader_optimized', False),
            keyboard_shortcuts=data.get('keyboard_shortcuts', True),
            announce_new_messages=data.get('announce_new_messages', True),
            focus_management=data.get('focus_management', True),
            font_family=data.get('font_family', 'Atkinson Hyperlegible'),
            font_size=data.get('font_size', 'medium'),
            line_height=data.get('line_height', 1.6),
            character_spacing=data.get('character_spacing', 'normal')
        )





@dataclass
class GUIConfig:
    """GUI-specific configuration"""
    audio_replay: AudioReplayConfig = field(default_factory=AudioReplayConfig)
    transcription: TranscriptionConfig = field(default_factory=TranscriptionConfig)
    accessibility: AccessibilityConfig = field(default_factory=AccessibilityConfig)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML serialization"""
        return {
            'audio_replay': self.audio_replay.to_dict(),
            'transcription': self.transcription.to_dict(),
            'accessibility': self.accessibility.to_dict()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GUIConfig':
        """Create from dictionary (YAML loading)"""
        return cls(
            audio_replay=AudioReplayConfig.from_dict(data.get('audio_replay', {})),
            transcription=TranscriptionConfig.from_dict(data.get('transcription', {})),
            accessibility=AccessibilityConfig.from_dict(data.get('accessibility', {}))
        )







# Update the existing UIConfig class below with this, later
@dataclass
class UIConfig:
    """User Interface configuration - extends your existing UI config"""
    chat_only_mode: bool = False
    web_interface_enabled: bool = False
    web_interface_port: int = 8000
    web_interface_host: str = "0.0.0.0"
    auto_open_browser: bool = True
    
    def __post_init__(self):
        """Validate configuration values"""
        if not (1 <= self.web_interface_port <= 65535):
            raise ValueError(f"Invalid port number: {self.web_interface_port}. Must be between 1 and 65535")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML serialization"""
        return {
            'chat_only_mode': self.chat_only_mode,
            'web_interface_enabled': self.web_interface_enabled,
            'web_interface_port': self.web_interface_port,
            'web_interface_host': self.web_interface_host,
            'auto_open_browser': self.auto_open_browser
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UIConfig':
        """Create from dictionary (YAML loading)"""
        return cls(
            chat_only_mode=data.get('chat_only_mode', False),
            web_interface_enabled=data.get('web_interface_enabled', False),
            web_interface_port=data.get('web_interface_port', 8000),
            web_interface_host=data.get('web_interface_host', '0.0.0.0'),
            auto_open_browser=data.get('auto_open_browser', True)
        )












@dataclass
class NetworkConfig:
    """Network configuration settings"""
    target_ip: str = "192.168.2.152"
    target_port: int = 57372
    listen_port: int = 57372
    
    # Protocol-specific ports
    voice_port: int = 57373
    text_port: int = 57374
    control_port: int = 57375

@dataclass
class AudioConfig:
    """Audio system configuration"""
    
    # Device selection
    input_device: Optional[str] = None  # Auto-detect if None
    
    # Protocol constants (not user-configurable)
    bitrate: int = field(default=16000, init=False)  # OPUS bitrate - protocol requirement
    sample_rate: int = 48000
    frame_duration_ms: int = 40
    device_keywords: list = field(default_factory=lambda: ["Samson", "C01U", "USB"])
    channels: int = 1


@dataclass
class GPIOConfig:
    """GPIO pin configuration"""
    ptt_pin: int = 23
    led_pin: int = 17
    button_bounce_time: float = 0.02
    led_brightness: float = 1.0

@dataclass
class ProtocolConfig:
    """Protocol-specific settings"""
    frame_size: int = 133
    header_size: int = 12
    payload_size: int = 121
    
    # Frame generation settings
    continuous_stream: bool = True      # Always generate 40ms frames when active
    keepalive_interval: float = 2.0     # Interval for keepalive frames (LAN mode)
    
    # Target type affects behavior
    target_type: str = "computer"       # "computer" or "modem"

@dataclass
class DebugConfig:
    """Debug and logging configuration"""
    verbose: bool = False
    quiet: bool = False
    log_level: str = "INFO"
    log_file: Optional[str] = None
    show_frame_details: bool = False
    show_timing_info: bool = False

@dataclass
class UserInterfaceConfig:
    """UI configuration for terminal and future GUI"""
    chat_enabled: bool = True
    chat_only_mode: bool = False
    show_statistics: bool = True
    auto_scroll: bool = True
    
    # Future GUI settings
    theme: str = "dark"
    window_width: int = 800
    window_height: int = 600
    always_on_top: bool = False















@dataclass
class OpulentVoiceConfig:
    """Complete configuration for Opulent Voice system"""
    # Station identification
    callsign: str = "NOCALL"
    
    # Configuration sections
    network: NetworkConfig = field(default_factory=NetworkConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    gpio: GPIOConfig = field(default_factory=GPIOConfig)
    protocol: ProtocolConfig = field(default_factory=ProtocolConfig)
    debug: DebugConfig = field(default_factory=DebugConfig)
    ui: UserInterfaceConfig = field(default_factory=UserInterfaceConfig)
    gui: GUIConfig = field(default_factory=GUIConfig)
    # If you don't already have a UI field, add this too:
    # ui: UIConfig = field(default_factory=UIConfig)
    
    # Metadata
    config_version: str = "1.0"
    description: str = "Opulent Voice Protocol Configuration"


    # Provide a to_dict() method in OpulentVoiceConfig
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML serialization"""
        return {
            # ... your existing fields ...
            'gui': self.gui.to_dict(),
            # Add 'ui': self.ui.to_dict() if you're adding UI config
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OpulentVoiceConfig':
        """Create from dictionary (YAML loading)"""
        return cls(
            # ... your existing field loading ...
            gui=GUIConfig.from_dict(data.get('gui', {})),
            # Add ui=UIConfig.from_dict(data.get('ui', {})) if you're adding UI config
        )












class ConfigurationManager:
    """
    Manages configuration loading, merging, and validation
    Enhanced configuration manager with GUI support
    """
    
    def __init__(self, config_file: str = "opulent_voice_config.yaml"):
        self.config_file = config_file
        self.config = None
        self.gui_overrides = {}  # For live GUI changes

        # Create self.logger
        self.logger = logging.getLogger(__name__)
        
        # Standard config file locations (in order of preference)
        self.config_search_paths = [
            Path.cwd() / "opulent_voice.yaml",  # Current directory
            Path.cwd() / "config" / "opulent_voice.yaml",  # Config subdirectory
            Path.home() / ".config" / "opulent_voice" / "config.yaml",  # User config
            Path("/etc/opulent_voice/config.yaml"),  # System config (Linux)
        ]





    
    def load_config(self, config_file: Optional[str] = None) -> OpulentVoiceConfig:
        """
        Load configuration from file with fallback chain
        
        Args:
            config_file: Specific config file path, or None for auto-discovery
            
        Returns:
            Loaded configuration object
        """
        if config_file:
            # Use specified file
            config_path = Path(config_file)
            if config_path.exists():
                self.config = self._load_yaml_file(config_path)
                self.config_file_path = config_path
                self.logger.info(f"Loaded config from: {config_path}")
            else:
                self.logger.warning(f"Config file not found: {config_path}")
                self.logger.info("Using default configuration")
        else:
            # Auto-discover config file
            for path in self.config_search_paths:
                if path.exists():
                    self.config = self._load_yaml_file(path)
                    self.config_file_path = path
                    self.logger.info(f"Auto-discovered config: {path}")
                    break
            else:
                self.logger.info("No config file found, using defaults")
        
        return self.config
    
    def _load_yaml_file(self, file_path: Path) -> OpulentVoiceConfig:
        """Load configuration from YAML file"""
        try:
            with open(file_path, 'r') as f:
                yaml_data = yaml.safe_load(f) or {}
            
            # Convert flat YAML to nested config object
            config = OpulentVoiceConfig()
            
            # Direct callsign assignment
            if 'callsign' in yaml_data:
                config.callsign = yaml_data['callsign']
            
            # Load each section
            if 'network' in yaml_data:
                config.network = self._dict_to_dataclass(NetworkConfig, yaml_data['network'])
            
            # MODIFIED: Audio config now uses defaults only - no user overrides
            if 'audio' in yaml_data:
                # Only load input_device if specified, ignore other audio settings
                audio_data = yaml_data['audio']
                if 'input_device' in audio_data:
                    config.audio.input_device = audio_data['input_device']
                    # All other audio settings use developer defaults

            if 'gpio' in yaml_data:
                config.gpio = self._dict_to_dataclass(GPIOConfig, yaml_data['gpio'])
            
            if 'protocol' in yaml_data:
                config.protocol = self._dict_to_dataclass(ProtocolConfig, yaml_data['protocol'])
            
            if 'debug' in yaml_data:
                config.debug = self._dict_to_dataclass(DebugConfig, yaml_data['debug'])
            
            if 'ui' in yaml_data:
                config.ui = self._dict_to_dataclass(UserInterfaceConfig, yaml_data['ui'])
            
            return config
            
        except Exception as e:
            self.logger.error(f"Error loading config file {file_path}: {e}")
            return OpulentVoiceConfig()
    
    def _dict_to_dataclass(self, dataclass_type, data_dict):
        """Convert dictionary to dataclass, preserving defaults for missing keys"""
        # Start with default instance
        instance = dataclass_type()
        
        # Update only the keys that exist in the YAML
        for key, value in data_dict.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
            else:
                self.logger.warning(f"Unknown config key '{key}' in {dataclass_type.__name__}")
        
        return instance










    def merge_cli_args(self, args: argparse.Namespace) -> OpulentVoiceConfig:
        """
        Merge CLI arguments into configuration (CLI takes precedence)
    
            Args:
            args: Parsed command line arguments
        
        Returns:
            Updated configuration
        """
        # Make sure we have a config to work with
        if self.config is None:
            self.config = OpulentVoiceConfig()
    
        # Station callsign
        if hasattr(args, 'callsign') and args.callsign:
            self.config.callsign = args.callsign
    
        # Network settings
        if hasattr(args, 'ip') and args.ip:
            self.config.network.target_ip = args.ip
        if hasattr(args, 'port') and args.port:
            self.config.network.target_port = args.port
        if hasattr(args, 'listen_port') and args.listen_port:
            self.config.network.listen_port = args.listen_port
    
        # GPIO settings
        if hasattr(args, 'ptt_pin') and args.ptt_pin is not None:
            self.config.gpio.ptt_pin = args.ptt_pin
        if hasattr(args, 'led_pin') and args.led_pin is not None:
            self.config.gpio.led_pin = args.led_pin
    
        # Debug settings
        if hasattr(args, 'verbose') and args.verbose:
            self.config.debug.verbose = True
        if hasattr(args, 'quiet') and args.quiet:
            self.config.debug.quiet = True
    
        # UI settings
        if hasattr(args, 'chat_only') and args.chat_only:
            self.config.ui.chat_only_mode = True
    
        # IMPORTANT: Always return the config object
        return self.config



















    
    def merge_cli_args_old(self, args: argparse.Namespace) -> OpulentVoiceConfig:
        """
        Merge CLI arguments into configuration (CLI takes precedence)
        
        Args:
            args: Parsed command line arguments
            
        Returns:
            Updated configuration
        """
        # Station callsign
        if hasattr(args, 'callsign') and args.callsign:
            self.config.callsign = args.callsign
        
        # Network settings
        if hasattr(args, 'ip') and args.ip:
            self.config.network.target_ip = args.ip
        if hasattr(args, 'port') and args.port:
            self.config.network.target_port = args.port
        if hasattr(args, 'listen_port') and args.listen_port:
            self.config.network.listen_port = args.listen_port
        
        # GPIO settings
        if hasattr(args, 'ptt_pin') and args.ptt_pin is not None:
            self.config.gpio.ptt_pin = args.ptt_pin
        if hasattr(args, 'led_pin') and args.led_pin is not None:
            self.config.gpio.led_pin = args.led_pin
        
        # Debug settings
        if hasattr(args, 'verbose') and args.verbose:
            self.config.debug.verbose = True
        if hasattr(args, 'quiet') and args.quiet:
            self.config.debug.quiet = True
        
        # UI settings
        if hasattr(args, 'chat_only') and args.chat_only:
            self.config.ui.chat_only_mode = True
        
        return self.config
    
    def save_config(self, file_path: Optional[str] = None) -> bool:
        """
        Save current configuration to YAML file
        
        Args:
            file_path: Target file path, or None to use loaded file path
            
        Returns:
            True if saved successfully
        """
        if file_path:
            target_path = Path(file_path)
        elif self.config_file_path:
            target_path = self.config_file_path
        else:
            target_path = Path("opulent_voice.yaml")
        
        try:
            # Ensure directory exists
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert config to dictionary
            config_dict = asdict(self.config)
            
            # Write YAML with comments
            with open(target_path, 'w') as f:
                f.write("# Opulent Voice Protocol Configuration\n")
                f.write(f"# Generated configuration file\n")
                f.write(f"# Version: {self.config.config_version}\n\n")
                
                yaml.dump(config_dict, f, 
                         default_flow_style=False, 
                         sort_keys=False,
                         indent=2)
            
            self.logger.info(f"Configuration saved to: {target_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error saving config to {target_path}: {e}")
            return False
    
    def create_sample_config(self, file_path: str = "opulent_voice_sample.yaml") -> bool:
        """Create a sample configuration file with comments"""
        try:
            with open(file_path, 'w') as f:
                f.write(self._generate_sample_yaml())
            
            print(f"Sample configuration created: {file_path}")
            return True
            
        except Exception as e:
            print(f"Error creating sample config: {e}")
            return False
    
    def _generate_sample_yaml(self) -> str:
        """Generate sample YAML with extensive comments"""
        return """# Opulent Voice Protocol Configuration File
# This file configures all aspects of the Opulent Voice radio system
# CLI arguments will override these settings when provided

# Station identification (required)
callsign: "N0CALL"  # Your station callsign - supports A-Z, 0-9, -, /, .

# Network configuration
network:
  target_ip: "192.168.2.152"      # Target IP for transmission
  target_port: 57372              # Target port for transmission
  listen_port: 57372              # Local port for receiving
  
  # Protocol-specific UDP ports (usually don't need to change)
  voice_port: 57373               # Port for voice (RTP) traffic
  text_port: 57374                # Port for text/chat traffic  
  control_port: 57375             # Port for control messages

# Audio system configuration
audio:
  # Audio device selection (optional)
  input_device: null              # Specific device name, or null for auto-detect

# GPIO pin configuration (Raspberry Pi)
gpio:
  ptt_pin: 23                     # GPIO pin for PTT button
  led_pin: 17                     # GPIO pin for PTT LED
  button_bounce_time: 0.02        # Button debounce time (seconds)
  led_brightness: 1.0             # LED brightness (0.0 - 1.0)

# Protocol settings
protocol:
  frame_size: 133                 # Opulent Voice frame size (bytes)
  header_size: 12                 # Header size (bytes) 
  payload_size: 121               # Payload size (bytes)
  
  # Frame generation behavior
  continuous_stream: true         # Generate continuous 40ms frames when active
  keepalive_interval: 2.0         # Keepalive interval for computer targets (seconds)
  
  # Target configuration - affects timeout behavior
  target_type: "computer"         # "computer" (LAN/Internet) or "modem" (SDR/Radio)
                                  # computer: keepalives maintain stream
                                  # modem: no keepalives, modem handles hang-time
                                  
  # Notes:
  # - Voice always preempts all other traffic (protocol requirement)
  # - UDP delivery is fire-and-forget (no retries possible)

# Debug and logging
debug:
  verbose: false                  # Enable verbose debug output
  quiet: false                    # Quiet mode (minimal output)
  log_level: "INFO"               # Logging level: DEBUG, INFO, WARNING, ERROR
  log_file: null                  # Log file path, or null for console only
  show_frame_details: false       # Show detailed frame information
  show_timing_info: false         # Show timing/performance information

# User interface configuration
ui:
  chat_enabled: true              # Enable chat interface
  chat_only_mode: false           # Run in chat-only mode (no GPIO/audio)
  show_statistics: true           # Show transmission statistics
  auto_scroll: true               # Auto-scroll chat messages
  
  # Future GUI settings (for HTML5 interface)
  theme: "dark"                   # UI theme: dark, light
  window_width: 800               # Default window width
  window_height: 600              # Default window height
  always_on_top: false            # Keep window always on top

# GUI-specific configuration
gui:
  # Audio replay settings
  audio_replay:
    enabled: true                 # Enable audio message replay
    max_stored_messages: 100      # Maximum stored audio messages
    storage_duration_hours: 24    # How long to keep audio (hours)
    auto_cleanup: true            # Automatically clean old messages

  # Transcription settings  
  transcription:
    enabled: true                 # Enable audio transcription
    method: "auto"                # auto, client-only, server-only, disabled
    language: "en-US"             # Language for transcription
    confidence_threshold: 0.7     # Minimum confidence for display

  # Accessibility and typography settings
  accessibility:
    high_contrast: false          # Enable high contrast mode
    reduced_motion: false         # Reduce animations and motion
    screen_reader_optimized: false # Optimize for screen readers
    keyboard_shortcuts: true      # Enable keyboard shortcuts
    announce_new_messages: true   # Announce new messages
    focus_management: true        # Manage focus for accessibility
    
    # Typography settings (Atkinson Hyperlegible font)
    font_family: "Atkinson Hyperlegible"  # Primary font family
    font_size: "medium"           # small, medium, large, x-large, xx-large
    line_height: 1.6              # Line spacing multiplier
    character_spacing: "normal"   # normal, wide

# Configuration metadata
config_version: "1.2"
description: "Opulent Voice Protocol Configuration"
"""











    def validate_config(self) -> tuple[bool, list[str]]:
        """
        Validate configuration for common issues
        
        Returns:
            (is_valid, list_of_errors)
        """
        errors = []
        
        # Validate callsign
        if not self.config.callsign or self.config.callsign == "NOCALL":
            errors.append("Callsign must be set")
        
        # Validate network ports
        if not (1 <= self.config.network.target_port <= 65535):
            errors.append(f"Invalid target port: {self.config.network.target_port}")
        
        if not (1 <= self.config.network.listen_port <= 65535):
            errors.append(f"Invalid listen port: {self.config.network.listen_port}")
        
        # Validate GPIO pins
        if not (2 <= self.config.gpio.ptt_pin <= 27):
            errors.append(f"Invalid PTT pin: {self.config.gpio.ptt_pin}")
        
        if not (2 <= self.config.gpio.led_pin <= 27):
            errors.append(f"Invalid LED pin: {self.config.gpio.led_pin}")
        
        if self.config.gpio.ptt_pin == self.config.gpio.led_pin:
            errors.append("PTT pin and LED pin cannot be the same")
        
        # Validate target type
        if self.config.protocol.target_type not in ["computer", "modem"]:
            errors.append(f"Invalid target_type: {self.config.protocol.target_type}. Must be 'computer' or 'modem'")
        
        return len(errors) == 0, errors
    
    def get_config(self) -> OpulentVoiceConfig:
        """Get current configuration"""
        return deepcopy(self.config)
    
    def update_config(self, updates: Dict[str, Any]) -> bool:
        """
        Update configuration programmatically (for GUI)
        
        Args:
            updates: Dictionary of configuration updates in dot notation
                    e.g., {"network.target_ip": "192.168.1.100", "audio.bitrate": 32000}
        
        Returns:
            True if all updates applied successfully
        """
        try:
            for key, value in updates.items():
                self._set_nested_attr(self.config, key, value)
            return True
        except Exception as e:
            self.logger.error(f"Error updating config: {e}")
            return False
    
    def _set_nested_attr(self, obj, attr_path: str, value):
        """Set nested attribute using dot notation"""
        parts = attr_path.split('.')
        for part in parts[:-1]:
            obj = getattr(obj, part)
        setattr(obj, parts[-1], value)


    def set_gui_override(self, key: str, value: Any):
        """Set a GUI override value (for live changes)"""
        self.gui_overrides[key] = value
        self._notify_gui_change(key, value)
    
    def get_gui_override(self, key: str, default=None):
        """Get a GUI override value"""
        return self.gui_overrides.get(key, default)
    
    def clear_gui_overrides(self):
        """Clear all GUI overrides"""
        self.gui_overrides.clear()
    
    def get_effective_value(self, key: str):
        """Get effective value considering GUI overrides"""
        # Check GUI overrides first (highest priority)
        if key in self.gui_overrides:
            return self.gui_overrides[key]
        
        # Fall back to regular config resolution
        return self._get_config_value(key)
    
    def _get_config_value(self, key: str):
        """Get value from config using dot notation (e.g., 'gui.audio_replay.enabled')"""
        keys = key.split('.')
        value = self.config
        
        try:
            for k in keys:
                if hasattr(value, k):
                    value = getattr(value, k)
                else:
                    return None
            return value
        except (AttributeError, TypeError):
            return None
    
    def _notify_gui_change(self, key: str, value: Any):
        """Notify GUI of configuration change (if web interface is running)"""
        # This will be used by the web interface to broadcast changes
        pass
    
    def save_current_config(self):
        """Save current configuration including GUI overrides to file"""
        if not self.config:
            return False
        
        try:
            # Apply GUI overrides to config before saving
            self._apply_gui_overrides_to_config()
            
            # Convert to dictionary
            config_dict = self.config.to_dict()
            
            # Write to YAML file
            with open(self.config_file, 'w') as f:
                yaml.dump(config_dict, f, default_flow_style=False, indent=2)
            
            return True
        except Exception as e:
            print(f"Error saving configuration: {e}")
            return False
    
    def _apply_gui_overrides_to_config(self):
        """Apply GUI overrides to the actual config object"""
        for key, value in self.gui_overrides.items():
            self._set_config_value(key, value)
    
    def _set_config_value(self, key: str, value: Any):
        """Set value in config using dot notation"""
        keys = key.split('.')
        obj = self.config
        
        try:
            # Navigate to the parent object
            for k in keys[:-1]:
                obj = getattr(obj, k)
            
            # Set the final value
            setattr(obj, keys[-1], value)
        except (AttributeError, TypeError) as e:
            print(f"Warning: Could not set config value {key}: {e}")

















# Add these functions to handle CLI argument integration

def apply_gui_cli_overrides(config: OpulentVoiceConfig, args) -> OpulentVoiceConfig:
    """Apply GUI-related CLI argument overrides to configuration"""
    
    # Web interface overrides
    if hasattr(args, 'web_interface') and args.web_interface:
        config.ui.web_interface_enabled = True
    
    if hasattr(args, 'web_port') and args.web_port:
        config.ui.web_interface_port = args.web_port
        
    if hasattr(args, 'web_host') and args.web_host:
        config.ui.web_interface_host = args.web_host
    
    # Audio replay overrides
    if hasattr(args, 'disable_audio_replay') and args.disable_audio_replay:
        config.gui.audio_replay.enabled = False
        
    if hasattr(args, 'max_audio_messages') and args.max_audio_messages:
        config.gui.audio_replay.max_stored_messages = args.max_audio_messages
    
    # Transcription overrides
    if hasattr(args, 'disable_transcription') and args.disable_transcription:
        config.gui.transcription.enabled = False
        
    if hasattr(args, 'transcription_language') and args.transcription_language:
        config.gui.transcription.language = args.transcription_language
    
    # Accessibility overrides
    if hasattr(args, 'high_contrast') and args.high_contrast:
        config.gui.accessibility.high_contrast = True
        
    if hasattr(args, 'reduce_motion') and args.reduce_motion:
        config.gui.accessibility.reduced_motion = True
        
    if hasattr(args, 'screen_reader_mode') and args.screen_reader_mode:
        config.gui.accessibility.screen_reader_optimized = True
    
    return config







def apply_gui_cli_overrides(config: OpulentVoiceConfig, args) -> OpulentVoiceConfig:
    """Apply GUI-related CLI argument overrides to configuration"""
    
    # Web interface overrides
    if hasattr(args, 'web_interface') and args.web_interface:
        config.ui.web_interface_enabled = True
    
    if hasattr(args, 'web_port') and args.web_port:
        config.ui.web_interface_port = args.web_port
        
    if hasattr(args, 'web_host') and args.web_host:
        config.ui.web_interface_host = args.web_host
    
    # Audio replay overrides
    if hasattr(args, 'disable_audio_replay') and args.disable_audio_replay:
        config.gui.audio_replay.enabled = False
        
    if hasattr(args, 'max_audio_messages') and args.max_audio_messages:
        config.gui.audio_replay.max_stored_messages = args.max_audio_messages
    
    # Transcription overrides
    if hasattr(args, 'disable_transcription') and args.disable_transcription:
        config.gui.transcription.enabled = False
        
    if hasattr(args, 'transcription_language') and args.transcription_language:
        config.gui.transcription.language = args.transcription_language
    
    # Accessibility overrides
    if hasattr(args, 'high_contrast') and args.high_contrast:
        config.gui.accessibility.high_contrast = True
        
    if hasattr(args, 'reduce_motion') and args.reduce_motion:
        config.gui.accessibility.reduced_motion = True
        
    if hasattr(args, 'screen_reader_mode') and args.screen_reader_mode:
        config.gui.accessibility.screen_reader_optimized = True
    
    return config




def create_default_gui_config_section() -> Dict[str, Any]:
    """Create default GUI configuration section for YAML file generation"""
    return {
        'gui': {
            'audio_replay': {
                'enabled': True,
                'max_stored_messages': 100,
                'storage_duration_hours': 24,
                'auto_cleanup': True
            },
            'transcription': {
                'enabled': True,
                'method': 'auto',
                'language': 'en-US',
                'confidence_threshold': 0.7,
                'server_endpoint': 'http://localhost:8001/transcribe'
            },
            'accessibility': {
                'high_contrast': False,
                'reduced_motion': False,
                'screen_reader_optimized': False,
                'keyboard_shortcuts': True,
                'announce_new_messages': True,
                'focus_management': True
            }
        },
        'ui': {
            'chat_only_mode': False,
            'web_interface_enabled': False,
            'web_interface_port': 8000,
            'web_interface_host': '0.0.0.0',
            'auto_open_browser': True
        }
    }










def create_enhanced_argument_parser():
    """Enhanced argument parser with GUI options"""
    parser = argparse.ArgumentParser(
        description='Opulent Voice Radio System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s W1ABC                           # Use callsign W1ABC with default settings
  %(prog)s W1ABC -i 192.168.1.100         # Target specific IP
  %(prog)s W1ABC --web-interface           # Start with web GUI
  %(prog)s W1ABC --chat-only               # Chat mode only (no GPIO/audio)
  %(prog)s --list-audio                    # List available audio devices
  %(prog)s --setup-audio                   # Interactive audio device setup
  %(prog)s -c my_config.yaml W1ABC         # Use specific config file
  %(prog)s --create-config sample.yaml    # Create sample config file

Configuration:
  Configuration is loaded in this order (later overrides earlier):
  1. Built-in defaults
  2. Configuration file (YAML)
  3. Command line arguments
  
  Config file search order:
  - opulent_voice.yaml (current directory)
  - config/opulent_voice.yaml 
  - ~/.config/opulent_voice/config.yaml
  - /etc/opulent_voice/config.yaml
        """
    )
    
    # Positional arguments
    parser.add_argument(
        'callsign',
        nargs='?',
        help='Station callsign (supports A-Z, 0-9, -, /, .)'
    )
    
    # Configuration file handling
    config_group = parser.add_argument_group('Configuration')
    config_group.add_argument(
        '-c', '--config',
        type=str,
        help='Configuration file path (YAML format)'
    )
    config_group.add_argument(
        '--create-config',
        type=str,
        metavar='FILE',
        help='Create sample configuration file and exit'
    )
    config_group.add_argument(
        '--save-config',
        type=str,
        metavar='FILE',
        help='Save current configuration to file'
    )
    
    # Network settings
    network_group = parser.add_argument_group('Network Settings')
    network_group.add_argument(
        '-i', '--ip',
        type=str,
        help='Target IP address for transmission'
    )
    network_group.add_argument(
        '-p', '--port',
        type=int,
        help='Target port for transmission'
    )
    network_group.add_argument(
        '--listen-port',
        type=int,
        help='Local port for receiving messages'
    )
    
    # GPIO settings
    gpio_group = parser.add_argument_group('GPIO Settings (Raspberry Pi)')
    gpio_group.add_argument(
        '--ptt-pin',
        type=int,
        help='GPIO pin for PTT button'
    )
    gpio_group.add_argument(
        '--led-pin',
        type=int,
        help='GPIO pin for PTT LED'
    )
    
    # Audio settings
    audio_group = parser.add_argument_group('Audio Settings')
    audio_group.add_argument(
        '--list-audio',
        action='store_true',
        help='List available audio devices and exit'
    )
    audio_group.add_argument(
        '--test-audio',
        action='store_true',
        help='Test audio devices and exit'
    )
    audio_group.add_argument(
        '--setup-audio',
        action='store_true',
        help='Interactive audio device setup and exit'
    )
    
    # Protocol settings
    protocol_group = parser.add_argument_group('Protocol Settings')
    protocol_group.add_argument(
        '--target-type',
        choices=['computer', 'modem'],
        help='Target type: computer (LAN/Internet) or modem (SDR/Radio)'
    )
    protocol_group.add_argument(
        '--keepalive-interval',
        type=float,
        help='Keepalive interval in seconds (computer targets only)'
    )
    
    # UI/Mode settings
    ui_group = parser.add_argument_group('User Interface')
    ui_group.add_argument(
        '--chat-only',
        action='store_true',
        help='Run in chat-only mode (no GPIO/audio)'
    )
    
    # Debug settings
    debug_group = parser.add_argument_group('Debug Options')
    debug_group.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose debug output'
    )
    debug_group.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='Quiet mode (minimal output)'
    )
    debug_group.add_argument(
        '--log-file',
        type=str,
        help='Log file path'
    )
    
    # GUI argument group
    gui_group = parser.add_argument_group('GUI Options')
    
    gui_group.add_argument(
        '--web-interface',
        action='store_true',
        help='Enable web interface mode'
    )
    
    gui_group.add_argument(
        '--web-port',
        type=int,
        default=8000,
        help='Port for web interface (default: 8000)'
    )
    
    gui_group.add_argument(
        '--web-host',
        type=str,
        default='0.0.0.0', # this is the one that worked to change from localhost
        help='Host for web interface (default: 0.0.0.0)'
    )
    
    gui_group.add_argument(
        '--disable-audio-replay',
        action='store_true',
        help='Disable audio message replay feature'
    )
    
    gui_group.add_argument(
        '--max-audio-messages',
        type=int,
        help='Maximum number of audio messages to store'
    )
    
    gui_group.add_argument(
        '--disable-transcription',
        action='store_true',
        help='Disable audio transcription'
    )
    
    gui_group.add_argument(
        '--transcription-language',
        type=str,
        help='Language for transcription (e.g., en-US, es-ES)'
    )
    
    # Accessibility options
    accessibility_group = parser.add_argument_group('Accessibility Options')
    
    accessibility_group.add_argument(
        '--high-contrast',
        action='store_true',
        help='Enable high contrast mode'
    )
    
    accessibility_group.add_argument(
        '--reduce-motion',
        action='store_true',
        help='Reduce animations and motion'
    )
    
    accessibility_group.add_argument(
        '--screen-reader-mode',
        action='store_true',
        help='Optimize for screen readers'
    )
    
    return parser










# In config_manager.py, replace the setup_configuration function with this:

def setup_configuration(argv=None) -> tuple[OpulentVoiceConfig, bool, ConfigurationManager]:
    """
    Setup configuration system with CLI integration
    
    Args:
        argv: Command line arguments (None for sys.argv)
        
    Returns:
        (config_object, should_exit, config_manager)
    """
    print("DEBUG: Starting setup_configuration")
    
    parser = create_enhanced_argument_parser()
    args = parser.parse_args(argv)
    print(f"DEBUG: Parsed args, callsign = {getattr(args, 'callsign', 'NOT_SET')}")
    
    # Handle special commands first
    if args.create_config:
        print("DEBUG: Handling create_config command")
        manager = ConfigurationManager()
        if manager.create_sample_config(args.create_config):
            print(f"Sample configuration created: {args.create_config}")
            print("Edit the file and run again with: -c {args.create_config}")
        return None, True, None
    
    print("DEBUG: Loading configuration")
    # Load configuration
    manager = ConfigurationManager()
    config = manager.load_config(args.config)
    print(f"DEBUG: config after load_config = {type(config)}")
    
    # If config loading failed, create default config
    if config is None:
        print("DEBUG: Config was None, creating default")
        config = OpulentVoiceConfig()
    
    print(f"DEBUG: config after None check = {type(config)}")
    
    # Merge CLI arguments (CLI overrides config file)
    config = manager.merge_cli_args(args)
    print(f"DEBUG: config after merge_cli_args = {type(config)}")

    # Apply GUI overrides 
    config = apply_gui_cli_overrides(config, args)
    print(f"DEBUG: config after apply_gui_cli_overrides = {type(config)}")

    # Initialize configuration manager with GUI support
    manager.config = config

    # Validate configuration
    is_valid, errors = manager.validate_config()
    if not is_valid:
        print("Configuration errors:")
        for error in errors:
            print(f"  ✗ {error}")
        # Return a default config instead of exiting directly
        return OpulentVoiceConfig(), True, None
    
    # Save config if requested
    if args.save_config:
        if manager.save_config(args.save_config):
            print(f"Configuration saved to: {args.save_config}")
    
    # Ensure we have a callsign from somewhere
    print(f"DEBUG: About to check callsign, config.callsign = {getattr(config, 'callsign', 'MISSING_ATTR')}")
    if not config.callsign or config.callsign == "NOCALL":
        if not args.callsign:
            print("Error: Callsign required either in config file or command line")
            # Return a default config instead of exiting directly
            return OpulentVoiceConfig(), True, None
        config.callsign = args.callsign
    
    print(f"DEBUG: Returning config = {type(config)}, should_exit = False, manager = {type(manager)}")
    # Return the config, exit flag, and the config manager
    return config, False, manager














def setup_configuration_temp_replaced(argv=None) -> tuple[OpulentVoiceConfig, bool]:
    """
    Setup configuration system with CLI integration
    
    Args:
        argv: Command line arguments (None for sys.argv)
        
    Returns:
        (config_object, should_exit)
    """
    parser = create_enhanced_argument_parser()
    args = parser.parse_args(argv)
    
    # Handle special commands first
    if args.create_config:
        manager = ConfigurationManager()
        if manager.create_sample_config(args.create_config):
            print(f"Sample configuration created: {args.create_config}")
            print("Edit the file and run again with: -c {args.create_config}")
        return None, True
    
    # Load configuration
    manager = ConfigurationManager()
    config = manager.load_config(args.config)
    
    # If config loading failed, create default config
    if config is None:
        config = OpulentVoiceConfig()
    
    # Merge CLI arguments (CLI overrides config file)
    config = manager.merge_cli_args(args)

    # Apply GUI overrides 
    config = apply_gui_cli_overrides(config, args)

    # Initialize configuration manager with GUI support
    config_manager = ConfigurationManager()
    config_manager.config = config

    # Validate configuration
    is_valid, errors = manager.validate_config()
    if not is_valid:
        print("Configuration errors:")
        for error in errors:
            print(f"  ✗ {error}")
        # Return a default config instead of exiting directly
        return OpulentVoiceConfig(), True
    
    # Save config if requested
    if args.save_config:
        if manager.save_config(args.save_config):
            print(f"Configuration saved to: {args.save_config}")
    
    # Ensure we have a callsign from somewhere
    if not config.callsign or config.callsign == "NOCALL":
        if not args.callsign:
            print("Error: Callsign required either in config file or command line")
            # Return a default config instead of exiting directly
            return OpulentVoiceConfig(), True
        config.callsign = args.callsign
    
    # Return the config and indicate we should continue (not exit)
    return config, False
















if __name__ == "__main__":
    # Example usage
    config, should_exit = setup_configuration()
    
    if should_exit:
        sys.exit(0 if config is None else 1)
    
    print(f"Configuration loaded successfully!")
    print(f"Station: {config.callsign}")
    print(f"Target: {config.network.target_ip}:{config.network.target_port}")
    print(f"Audio: {config.audio.sample_rate}Hz, {config.audio.bitrate}bps")
    print(f"GPIO: PTT=GPIO{config.gpio.ptt_pin}, LED=GPIO{config.gpio.led_pin}")
