# Sample Configuration Files

## Basic Home Station Configuration

```yaml
# home_station.yaml - Basic setup for home operation
callsign: "W1ABC"

network:
  target_ip: "192.168.1.100"
  target_port: 57372
  listen_port: 57372

audio:
  sample_rate: 48000
  bitrate: 16000
  prefer_usb_device: true
  device_keywords: ["USB", "Samson", "Blue"]

gpio:
  ptt_pin: 23
  led_pin: 17

protocol:
  target_type: "computer"       # Computer-to-computer over LAN/Internet
  keepalive_interval: 2.0

debug:
  verbose: false
  quiet: false

ui:
  chat_enabled: true
  show_statistics: true
```

## Portable/Field Configuration

```yaml
# portable.yaml - Optimized for battery/mobile operation
callsign: "W1ABC/P"

network:
  target_ip: "192.168.43.100"  # Mobile hotspot network
  target_port: 57372

audio:
  sample_rate: 48000           # Protocol requirement - do not change
  prefer_usb_device: false     # Use built-in audio in field

gpio:
  ptt_pin: 23
  led_pin: 17
  led_brightness: 0.5          # Dimmer LED to save battery

protocol:
  target_type: "computer"       # Still computer target for portable ops
  keepalive_interval: 5.0      # Longer interval to save bandwidth

debug:
  quiet: true                  # Less verbose for field use

ui:
  chat_enabled: true
  auto_scroll: true
```

## Development/Testing Configuration

```yaml
# development.yaml - For development and testing
callsign: "TEST1"

network:
  target_ip: "127.0.0.1"       # Localhost testing
  target_port: 57372

audio:
  sample_rate: 48000
  bitrate: 16000

protocol:
  target_type: "computer"       # Computer target for development
  keepalive_interval: 2.0

debug:
  verbose: true                # Full debug output
  show_frame_details: true     # Show protocol details
  show_timing_info: true       # Performance monitoring
  log_file: "debug.log"        # Log to file

ui:
  chat_only_mode: false        # Test full system
```

## Chat-Only Configuration

```yaml
# chat_only.yaml - Text messaging without audio/GPIO
callsign: "W1ABC"

network:
  target_ip: "192.168.1.100"
  target_port: 57372

protocol:
  target_type: "computer"       # Computer target for chat
  keepalive_interval: 3.0

debug:
  verbose: false
  quiet: false

ui:
  chat_only_mode: true         # No GPIO or audio
  chat_enabled: true
  show_statistics: false       # No audio stats to show
```

## SDR/Modem Configuration

```yaml
# sdr_modem.yaml - For PlutoSDR, USRP, or other radio modems
callsign: "W1ABC"

network:
  target_ip: "192.168.1.50"    # PlutoSDR or modem IP
  target_port: 57372

audio:
  sample_rate: 48000
  bitrate: 16000
  prefer_usb_device: true

gpio:
  ptt_pin: 23
  led_pin: 17

protocol:
  target_type: "modem"          # Modem handles RF timing
  keepalive_interval: 2.0       # Set but not used for modems

debug:
  verbose: false
  show_frame_details: false

ui:
  chat_enabled: true
  show_statistics: true
```

## Audio Troubleshooting Configuration

```yaml
# audio_debug.yaml - For debugging audio issues
callsign: "W1ABC"

network:
  target_ip: "192.168.1.100"
  target_port: 57372

audio:
  sample_rate: 44100            # Match USB device native rate
  bitrate: 16000
  prefer_usb_device: true
  device_keywords: ["Samson", "C01U", "USB"]

protocol:
  target_type: "computer"
  keepalive_interval: 2.0

debug:
  verbose: true
  show_timing_info: true        # Monitor audio performance
  log_file: "audio_debug.log"

ui:
  chat_enabled: true
```

## Multi-Network Configuration

```yaml
# repeater.yaml - Configuration for repeater/network node
callsign: "W1ABC-R"

network:
  target_ip: "10.0.1.100"      # Network backbone
  target_port: 57372
  listen_port: 57372

audio:
  sample_rate: 48000
  bitrate: 16000

protocol:
  target_type: "computer"       # Network node to network node
  keepalive_interval: 1.0      # Frequent keepalives for network presence

debug:
  verbose: false
  show_frame_details: false
  log_file: "/var/log/opulent_voice.log"

ui:
  chat_enabled: true
  show_statistics: true
```

## Configuration File Locations

The system searches for configuration files in this order:

1. **Current Directory**: `./opulent_voice.yaml`
2. **Config Subdirectory**: `./config/opulent_voice.yaml`  
3. **User Config**: `~/.config/opulent_voice/config.yaml`
4. **System Config**: `/etc/opulent_voice/config.yaml`

## Configuration Validation

The system validates:
- **Callsign format** (base-40 compatible characters)
- **Network ports** (1-65535 range)
- **GPIO pins** (valid Raspberry Pi GPIO numbers)
- **Audio settings** (supported sample rates and frame durations)
- **Pin conflicts** (PTT and LED can't use same pin)

## CLI Override Examples

```bash
# Use config file but override target IP
python queue_audio.py -c home_station.yaml --ip 192.168.2.100

# Use config file but enable verbose mode
python queue_audio.py -c portable.yaml --verbose

# Use config file but change to chat-only mode
python queue_audio.py -c development.yaml --chat-only

# Override multiple settings
python queue_audio.py -c home_station.yaml --ip 10.0.1.50 --port 8080 --verbose
```

## Future HTML5 GUI Integration

The configuration system is designed to easily support a web-based GUI:

```javascript
// Example of how HTML5 GUI would interact with config
const config = await fetch('/api/config').then(r => r.json());

// Update configuration from web form
await fetch('/api/config', {
    method: 'POST',
    body: JSON.stringify({
        'network.target_ip': '192.168.1.200',
        'audio.bitrate': 32000,
        'debug.verbose': true
    })
});

// Validate configuration
const validation = await fetch('/api/config/validate').then(r => r.json());
if (!validation.valid) {
    console.log('Config errors:', validation.errors);
}
```
