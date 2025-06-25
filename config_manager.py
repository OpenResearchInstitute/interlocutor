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
    sample_rate: int = 48000
    bitrate: int = 16000
    channels: int = 1
    frame_duration_ms: int = 40
    
    # Device selection
    input_device: Optional[str] = None  # Auto-detect if None
    prefer_usb_device: bool = True
    device_keywords: list = field(default_factory=lambda: ["Samson", "C01U", "USB"])

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
    """
    Debug and logging configuration:
    DEBUG, INFO, WARNING, ERROR
    """
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
    
    # Metadata
    config_version: str = "1.0"
    description: str = "Opulent Voice Protocol Configuration"

class ConfigurationManager:
    """Manages configuration loading, merging, and validation"""
    
    def __init__(self):
        self.config = OpulentVoiceConfig()
        self.config_file_path: Optional[Path] = None
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
            
            if 'audio' in yaml_data:
                config.audio = self._dict_to_dataclass(AudioConfig, yaml_data['audio'])
            
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
callsign: "W1ABC"  # Your station callsign - supports A-Z, 0-9, -, /, .

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
  sample_rate: 48000              # Audio sample rate (Hz)
  bitrate: 16000                  # OPUS bitrate (bps)
  channels: 1                     # Number of audio channels
  frame_duration_ms: 40           # Audio frame duration (milliseconds)
  
  # Audio device selection
  input_device: null              # Specific device name, or null for auto-detect
  prefer_usb_device: true         # Prefer USB audio devices
  device_keywords:                # Keywords to search for in device names
    - "Samson"
    - "C01U" 
    - "USB"

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

# Configuration metadata
config_version: "1.0"
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
        
        # Validate audio settings
        if self.config.audio.sample_rate not in [8000, 16000, 24000, 48000]:
            errors.append(f"Unsupported sample rate: {self.config.audio.sample_rate}")
        
        if self.config.audio.frame_duration_ms not in [20, 40, 60]:
            errors.append(f"Unsupported frame duration: {self.config.audio.frame_duration_ms}ms")
        
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

def create_enhanced_argument_parser() -> argparse.ArgumentParser:
    """Create argument parser that works with configuration system"""
    parser = argparse.ArgumentParser(
        description='Opulent Voice Protocol PTT Radio Interface with Chat',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Configuration file options
    parser.add_argument(
        '-c', '--config',
        help='Configuration file path (YAML format)'
    )
    
    parser.add_argument(
        '--create-config',
        metavar='FILE',
        help='Create sample configuration file and exit'
    )
    
    parser.add_argument(
        '--save-config',
        metavar='FILE', 
        help='Save current configuration to file and continue'
    )

    # Station identification (required if not in config)
    parser.add_argument(
        'callsign',
        nargs='?',  # Make optional if config file provides it
        help='Station callsign (supports A-Z, 0-9, -, /, . characters)'
    )

    # Network settings (override config file)
    net_group = parser.add_argument_group('Network Settings')
    net_group.add_argument('-i', '--ip', help='Target IP address')
    net_group.add_argument('-p', '--port', type=int, help='Target port')
    net_group.add_argument('-l', '--listen-port', type=int, help='Listen port')

    # GPIO settings (override config file)  
    gpio_group = parser.add_argument_group('GPIO Settings')
    gpio_group.add_argument('--ptt-pin', type=int, help='PTT button GPIO pin')
    gpio_group.add_argument('--led-pin', type=int, help='PTT LED GPIO pin')

    # Mode selection
    mode_group = parser.add_argument_group('Mode Selection')
    mode_group.add_argument('--chat-only', action='store_true', 
                           help='Run in chat-only mode (no GPIO/audio)')

    # Debug options
    debug_group = parser.add_argument_group('Debug Options')
    debug_group.add_argument('-v', '--verbose', action='store_true',
                            help='Enable verbose debug output')
    debug_group.add_argument('-q', '--quiet', action='store_true',
                            help='Quiet mode - minimal output')

    return parser

# Example usage and integration function
def setup_configuration(argv=None) -> tuple[OpulentVoiceConfig, bool]:
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
    
    # Merge CLI arguments (CLI overrides config file)
    config = manager.merge_cli_args(args)
    
    # Validate configuration
    is_valid, errors = manager.validate_config()
    if not is_valid:
        print("Configuration errors:")
        for error in errors:
            print(f"  ✗ {error}")
        return None, True
    
    # Save config if requested
    if args.save_config:
        if manager.save_config(args.save_config):
            print(f"Configuration saved to: {args.save_config}")
    
    # Ensure we have a callsign from somewhere
    if not config.callsign or config.callsign == "NOCALL":
        if not args.callsign:
            print("Error: Callsign required either in config file or command line")
            return None, True
        config.callsign = args.callsign
    
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
