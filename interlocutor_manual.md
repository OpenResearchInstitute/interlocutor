# Interlocutor Installation and Operator Manual
## Raspberry Pi Human Radio Interface for Opulent Voice

### Overview

**Interlocutor** is the human-radio interface component of the Open Research Institute's Opulent Voice digital communication system. Think of it as the "radio console" that transforms your Raspberry Pi into a sophisticated digital voice and data terminal. While traditional amateur radio digital modes often sacrifice audio quality for bandwidth efficiency, Interlocutor enables crystal-clear voice communications with seamless integration of keyboard chat, file transfer, and system control messages.

**What Interlocutor Does:**
- Provides high-quality digital voice communication using OPUS codec
- Enables keyboard chat that integrates seamlessly with voice
- Handles file transfer and system control messages
- Offers both command-line and web-based interfaces
- Manages audio devices with sophisticated conflict resolution
- Implements priority-based message queuing (voice always wins)

**System Architecture:**
Interlocutor acts as the bridge between human operators and radio equipment. It processes voice, text, and data into properly formatted frames that can be sent to any Opulent Voice-compatible modem via Ethernet, enabling remote operation and modular system design.

---

## Hardware Requirements

### Minimum Requirements
- **Raspberry Pi 4 or 5** (recommended: Pi 5 for best performance)
- **8GB+ microSD card** (Class 10 or better)
- **USB audio device** (headset or separate microphone/speakers)
- **Ethernet connection** (for connecting to radio equipment)

### Recommended Setup
- **USB headset with microphone** (dedicated for radio use)
- **HDMI output** (for browser audio, avoiding device conflicts)
- **GPIO PTT button** (for push-to-talk control)
- **LED indicator** (for transmission status)

### Audio Device Strategy
Think of audio device management like managing multiple receivers in a traditional radio shack. The key principle: **one application per audio device**.

**Best Configuration (No Conflicts):**
- Radio (Interlocutor): USB headset/microphone
- Browser/System: HDMI output to monitor/TV speakers
- Result: Both work simultaneously

**Alternative Hardware Solutions:**
- Two USB audio devices (one for radio, one for computer)
- USB hub with multiple audio interfaces
- 3.5mm splitter to share single headset between devices

---

## Software Installation

### Step 1: Prepare the Raspberry Pi Environment

Update your system and install Python environment tools:

```bash
# Update the system
sudo apt update && sudo apt upgrade -y

# Install pyenv for Python version management
curl https://pyenv.run | bash
```

### Step 2: Configure Python Environment

Add pyenv to your shell configuration:

```bash
sudo nano ~/.bashrc
```

Add these lines to the end of `.bashrc`:

```bash
# add pyenv to .bashrc
# this lets terminal know where to look for the pyenv
# versions of Python that we will be using. 
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"
```

Reload your shell:

```bash
exec $SHELL
```

### Step 3: Install Python Dependencies for pyenv

Install the recommended build dependencies:

```bash
sudo apt-get install --yes libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev llvm libncurses5-dev libncursesw5-dev xz-utils tk-dev libgdbm-dev lzma lzma-dev tcl-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev wget curl make build-essential openssl
```

### Step 4: Install Audio System Dependencies

```bash
sudo apt install python3-pyaudio build-essential portaudio19-dev python3-dev
```

### Step 5: Clone and Setup Interlocutor

```bash
# Clone the repository
git clone https://github.com/OpenResearchInstitute/interlocutor
cd interlocutor

# Install and activate Python 3.11.2 in a virtual environment
pyenv update
pyenv install 3.11.2
pyenv virtualenv 3.11.2 orbital
pyenv activate orbital

# Install Python packages
pip3 install -r requirements.txt
pip3 install lgpio
pip3 install opuslib_next
```

---

## Audio Device Configuration

### Understanding Audio Device Management

Just like a multi-radio station where each radio needs its own antenna connection, each application needs exclusive access to its audio device. Interlocutor includes sophisticated tools to help you manage this.

### Audio Setup Commands

```bash
# Show all available audio devices
python3 interlocutor.py YOUR_CALLSIGN --list-audio

# Interactive audio device selection
python3 interlocutor.py YOUR_CALLSIGN --setup-audio

# Test current audio configuration
python3 interlocutor.py YOUR_CALLSIGN --test-audio
```

### Audio Device Selection Guide

**Device Priority Recommendations:**
1. **USB devices** (better isolation, dedicated for radio use)
2. **Built-in devices** (adequate for testing, may have conflicts)

**Visual Device Discovery Features:**
- Clear indicators showing USB vs built-in devices
- Live microphone level meters during testing
- Speaker test tones with user confirmation
- Smart recommendations based on device type

**Device Testing Process:**
1. Select input device and see real-time level meters
2. Test output device with confirmation tones
3. Save preferences for future sessions
4. Quick re-selection without restarting

---

## Configuration Management

### Web-Based Configuration System

Interlocutor features a modern glassmorphism-styled web interface for complete system configuration:

```bash
# Launch with web interface
python3 interlocutor.py YOUR_CALLSIGN --web-interface

# With specific config file
python3 interlocutor.py YOUR_CALLSIGN -c myconfig.yaml --web-interface
```

**Access URLs:**
- Main interface: http://localhost:8000
- Configuration: http://localhost:8000/config

### Configuration Sections

**Station Configuration:**
- Callsign and identification settings
- Operator preferences

**Network Settings:**
- IP addresses and port configuration
- Protocol settings and keepalive intervals
- Target equipment addresses

**Audio Settings:**
- Sample rates and device selection
- Input/output level adjustments
- Real-time testing capabilities

**GPIO Settings:**
- Raspberry Pi pin assignments
- PTT button and LED configuration

**Protocol Settings:**
- Frame types and priorities
- Authentication parameters

**Debug & Logging:**
- Verbose modes and diagnostic options
- Performance monitoring

### Configuration File Management

**Smart File Handling:**
- Saves back to original config file when specified with `-c`
- Auto-discovery follows CLI search order when no config specified
- Create/Load/Save/Export configurations through web interface
- Import existing config files via drag-and-drop

---

## Operation Modes

### Command Line Interface (CLI) Mode

Traditional terminal-based operation with full keyboard chat capabilities:

```bash
python3 interlocutor.py YOUR_CALLSIGN
```

**CLI Features:**
- Real-time voice transmission with PTT control
- Keyboard chat interface
- Message priority management
- Debug output and system status

### Web Interface Mode

Modern browser-based interface with visual controls:

```bash
python3 interlocutor.py YOUR_CALLSIGN --web-interface
```

**Web Interface Features:**
- Glassmorphism UI with responsive design
- Real-time configuration updates
- Live status indicators and progress feedback
- Audio waveform animations
- Notification system for important events

### Dual-Mode Operation

Both interfaces can run simultaneously, providing flexibility for different operational scenarios:
- Web interface for configuration and monitoring
- CLI for keyboard-to-keyboard chat operations
- Instant updates between interfaces via WebSocket communication

---

## Protocol and Network Configuration

### Understanding Opulent Voice Protocol

Interlocutor implements the Opulent Voice protocol with sophisticated frame management:

**Frame Types and Priorities:**
1. **VOICE** (Priority 1): OPUS-encoded audio, immediate transmission
2. **CONTROL** (Priority 2): PTT state changes, high priority queue
3. **TEXT** (Priority 3): Keyboard chat, normal priority queue
4. **DATA** (Priority 4): File transfers, low priority queue

**Network Ports:**
- **57372**: Network Transmitter port (configurable, connects to SDR/repeater)
- **57373**: Audio frames
- **57374**: Text frames  
- **57375**: Control frames

### Frame Structure

All frames follow the Opulent Voice protocol format:
- **Header**: 14 bytes (sync word + station ID + type + sequence + length + reserved)
- **Payload**: Variable length data specific to frame type
- **Encoding**: COBS (Consistent Overhead Byte Stuffing) framing
- **Transport**: UDP over IP with RTP headers for audio

### Network Integration

```bash
# Basic operation (connects to default target)
python3 interlocutor.py YOUR_CALLSIGN

# Specify target IP and port
python3 interlocutor.py YOUR_CALLSIGN --target-ip 192.168.1.100 --target-port 57372

# Load specific configuration
python3 interlocutor.py YOUR_CALLSIGN -c mystation.yaml
```

---

## Audio System Operation

### Voice Communication

**Push-to-Talk (PTT) Operation:**
- **GPIO Button**: Physical button connected to Raspberry Pi GPIO
- **Keyboard PTT**: Space bar or configured key in CLI mode
- **Web PTT**: Click/touch controls in web interface

**Audio Processing Pipeline:**
1. Microphone input → PyAudio capture
2. Audio validation and level checking
3. OPUS encoding (40ms frames, configurable bitrate)
4. RTP header addition
5. Opulent Voice protocol framing
6. Network transmission via UDP

**Quality Settings:**
- Default: 32kbps OPUS encoding
- Protocol v1.0: 16kbps (legacy compatibility)
- Protocol v2.0: 32kbps (current standard)
- Frame size: 40ms (optimized for real-time performance)

### Chat Integration

**Message Priority Logic:**
- Voice transmission has absolute priority
- Text messages typed during PTT are buffered
- Buffered messages transmit immediately when PTT releases
- Control messages maintain high priority for system functions

**Chat Modes:**
- **Voice + Chat**: Normal operation with seamless integration
- **Chat Only**: Keyboard-to-keyboard communication (similar to RTTY)
- **Mixed Mode**: Operators can choose voice or text as appropriate

---

## Network Reconnection and Error Handling

### Automatic Reconnection System

Interlocutor implements intelligent reconnection logic for network resilience:

**Reconnection Timing:**
1. First retry: 1 second delay
2. Subsequent retries: Exponential backoff (1.5x increase)
3. Maximum delay: 30 seconds
4. Maximum attempts: 10 attempts
5. Total auto-retry time: 2-3 minutes

**Retry Sequence:**
```
Attempt 1: 1.0 seconds
Attempt 2: 1.5 seconds  
Attempt 3: 2.25 seconds
Attempt 4: 3.4 seconds
Attempt 5: 5.1 seconds
Attempt 6: 7.6 seconds
Attempt 7: 11.4 seconds
Attempt 8: 17.1 seconds
Attempt 9: 25.6 seconds
Attempt 10: 30.0 seconds (max reached)
```

**Manual Recovery Options:**
- Manual retry button (appears after auto-retry exhaustion)
- Page visibility recovery (switching browser tabs triggers reconnect)
- Browser refresh (restarts connection process)
- Connection timeout: 5 seconds per attempt

---

## Troubleshooting Guide

### Audio Issues

**Problem: No audio output/input**
- Check device selection with `--setup-audio`
- Verify device isn't in use by another application
- Test with `--test-audio` command
- Check USB device connections

**Problem: Browser audio conflicts**
- Use different audio devices for radio vs browser
- Set browser to HDMI output, radio to USB headset
- Stop radio application to release audio device
- Refresh browser tabs if audio doesn't resume

**Problem: Poor audio quality**
- Check microphone input levels
- Verify network connectivity to target
- Monitor for packet loss in debug mode
- Ensure adequate CPU resources

### Network Issues

**Problem: Connection failures**
- Verify target IP address and port settings
- Check network connectivity with ping
- Monitor firewall settings
- Review configuration file network settings

**Problem: Frame transmission errors**
- Enable verbose mode for detailed logging
- Check protocol version compatibility
- Verify station ID encoding
- Monitor frame statistics

### Configuration Issues

**Problem: Settings not saving**
- Check file permissions on configuration directory
- Verify YAML file syntax
- Use web interface for validated configuration
- Check for configuration file conflicts

---

## Advanced Features

### Real-time Monitoring

**Audio Statistics:**
- Packet transmission/reception counts
- Audio frame duration tracking
- Encoding/decoding performance metrics
- Network latency measurements

**System Health:**
- CPU usage monitoring
- Memory utilization tracking
- GPIO status indicators
- Network connection health

### Integration Capabilities

**Remote Operation:**
- Ethernet-based radio control
- Web interface for remote configuration
- Status monitoring over network
- Modular system architecture

**Extensibility:**
- Plugin architecture for additional protocols
- GPIO expansion for custom hardware
- API endpoints for external integration
- Configuration templates for different scenarios

---

## Getting Help and Contributing

### Documentation Resources
- Project repository: https://github.com/OpenResearchInstitute/interlocutor
- Open Research Institute: https://www.openresearch.institute/
- Opulent Voice protocol documentation
- Community forums and discussions

### Support Channels
- GitHub Issues for bug reports
- ORI community forums for general discussion
- Technical working groups for protocol development
- Amateur radio forums for operational questions

### Contributing
- Code contributions welcome via GitHub pull requests
- Documentation improvements encouraged
- Testing and feedback valuable for development
- Hardware testing on different platforms needed

---

*This manual represents the current state of Interlocutor development. The system is actively developed open-source software, and features may evolve. Check the project repository for the latest updates and documentation.*

**73 de Open Research Institute**