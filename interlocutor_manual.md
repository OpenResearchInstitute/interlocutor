# Interlocutor Installation and Operator Manual
## Human Radio Interface for Opulent Voice

### Overview

**Interlocutor** is the human-radio interface component of the Open Research Institute's Opulent Voice digital communication system. Think of it as the "radio console" that transforms your computing device (such as  Raspberry Pi or a laptop) into a sophisticated digital voice and data terminal. While traditional amateur radio digital modes often sacrifice audio quality for bandwidth efficiency, Interlocutor enables very high-quality voice communications with seamless integration of keyboard chat, file transfer, and system control messages.

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
# Raspberry Pi Installation

## Hardware Requirements

### Minimum Requirements
- **Raspberry Pi 4 or 5** (recommended: Pi 5 for best performance)
- **8GB+ microSD card** (Class 10 or better)
- **USB audio device** (headset or separate microphone/speakers)
- **Ethernet connection** (for connecting to radio equipment)

### Recommended Setup
- **USB headset with microphone** (dedicated for radio use)
- **HDMI output** (for browser audio, avoiding device conflicts)
- **GPIO PTT button** (momentary switch for push-to-talk control)
- **LED indicator** (for clear visual feedback on transmission status)

### Audio Device Strategy
Think of audio device management like managing multiple receivers in a traditional radio shack. The key principle: **one application per audio device**.

**Best Configuration (No Conflicts):**
- Radio (Interlocutor): USB headset/microphone
- Browser/System: HDMI output to monitor/TV speakers
- Result: Both can work simultaneously, depending on browser and operating system

**Alternative Hardware Solutions:**
- Two USB audio devices (one for radio, one for computer)
- USB hub with multiple audio interfaces
- 3.5mm splitter to share single headset between devices

There is audio device listing and audio device selection support in Interlocutor. Both the microphone and speaker are tested during the selection process. Audio device selection is saved to a local file called `audio_config.yaml`

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

# Install and activate Python 3.11.2 (or the version of your choice) in a virtual environment
pyenv update
pyenv install 3.11.2
pyenv virtualenv 3.11.2 your_environment_name
pyenv activate your_environment_name

# Install Python packages
pip3 install -r requirements.txt

There may be other Python packages required for your system. requirements.txt will be as updated as possible, but watch for any missing modules and install them. 

```

---


# macOS Installation

This guide walks through setting up the Interlocutor radio communication software on macOS systems.

## Prerequisites

Before starting, ensure you have the following installed:

- **Python 3.13+** (recommended via Homebrew)
- **Homebrew** package manager
- **Xcode Command Line Tools** (for compilation)

```bash
# Install Homebrew if you haven't already
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python 3.13 (or appropriate)
brew install python@3.13

# Install Xcode Command Line Tools
xcode-select --install
```

## System Dependencies

Install the required system-level audio libraries:

```bash
# Install PortAudio for PyAudio support
brew install portaudio

# Install Opus audio codec (if needed)
brew install opus
```

## Installation Steps

### 1. Clone the Repository

```bash
git clone https://github.com/OpenResearchInstitute/interlocutor
cd interlocutor
```

### 2. Create Virtual Environment

Create an isolated Python environment to avoid conflicts. Use this method or the virtual environment of your choice. 

```bash
python3 -m venv orbital
source orbital/bin/activate
```

> **Note**: The virtual environment name "orbital" is used here to match the project's space theme, but you can use any name you prefer.

### 3. Install Python Dependencies

Install the required packages step by step to handle build dependencies:

```bash
# Core dependencies that usually install cleanly
pip install pyyaml numpy sounddevice fastapi uvicorn

# Audio processing libraries
pip install opuslib_next

# GPIO library (will use mock mode on macOS)
pip install gpiozero

# Try to install PyAudio (may require portaudio)
pip install pyaudio
```

### 4. Configure GPIO Mock Mode

Since macOS doesn't have GPIO hardware, set the mock mode environment variable. Otherwise you'll be working a shift in the pin factory. 

```bash
export GPIOZERO_PIN_FACTORY=mock
```

To make this permanent, add it to your shell profile:

```bash
echo 'export GPIOZERO_PIN_FACTORY=mock' >> ~/.zshrc
source ~/.zshrc
```

## Running Interlocutor

### Basic Usage

```bash
# Activate virtual environment
source orbital/bin/activate

# Run with web interface
python3 interlocutor.py QUARTER --web-interface
```

Replace `QUARTER` with your desired station identification.

### Example Usage

```bash
python3 interlocutor.py QUARTER --web-interface --target-type modem -i 172.236.237.16
```
Here we launch our human radio interface with station ID of QUARTER, with a web interface at 127.0.0.1:8000, with the target type set to modem and the target IP address of 172.236.237.16, which is the demonstration Opulent Voice repeater at opulent.openresearch.institute. 

Use --help to see a list of all arguments in Interlocutor. 

### First Run Setup

On first run, you'll be prompted to:

1. **Select audio input device** - Choose your microphone
2. **Test audio input** - Speak to verify microphone works
3. **Select audio output device** - Choose your speakers/headphones
4. **Test audio output** - Listen for test tone

The web interface will be available at `http://localhost:8000`

## Troubleshooting

### PyAudio Installation Issues

If PyAudio fails to build with "portaudio.h not found":

```bash
# Ensure PortAudio is installed
brew install portaudio

# Try installing PyAudio again
pip install pyaudio
```

### SWIG/lgpio Errors

These can be safely ignored on macOS since they're Linux-specific libraries:

```bash
# These errors are expected and non-fatal on macOS:
# - "swig command failed"
# - "No module named 'lgpio'"
# - "No module named 'RPi'"
```

### Audio Device Selection

If you need to change audio devices later, delete any saved configuration and restart Interlocutor.

```bash
# Remove saved config (if it exists)
rm -f ~/.audio_config.yaml

# Restart with fresh device selection
python3 interlocutor.py QUARTER --web-interface
```

Or run interlocutor.py with --setup-audio command line argument. See the Audio Device Configuration section below for more information on audio configuration. 


## Network Configuration

For actual radio communication, you'll need to configure network targets. The default configuration attempts to connect to `192.168.2.152:57372`. Modify the configuration through the web interface or command-line arguments as needed.

## Optional: Development Setup

For development work, install additional dependencies:

```bash
pip install -r requirements.txt
```

Note: Some dependencies in `requirements.txt` may fail on macOS (like `lgpio`) but the core functionality will work. Some systems may require manual installation of the packages listed in requirements.txt.

## Success Indicators

When properly installed, you should see:

```
✅ Static files mounted from html5_gui
opuslib ready
pyaudio ready
gpiozero ready and standing by
📡 Station: QUARTER
🌐 Starting Enhanced Opulent Voice Web Interface on http://0.0.0.0:8000
```

The web interface provides a complete control panel for configuration and communication.

## Support

For additional help:
- Check the main project documentation
- Review the `interlocutor_manual.md` file
- Open issues on the GitHub repository

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
The purpose of the Configuration System is to create, validate, and save one or more configuration files so that an operator can start the radio in a fully configured state. 

**Access URLs:**
- Main interface: http://localhost:8000
- Configuration: http://localhost:8000/config

### Configuration Sections

**Station Configuration:**
- Callsign and identification settings
- Operator preferences

**Network Settings:**
- IP addresses and port configuration
- Protocol settings

**GPIO Settings:**
- Raspberry Pi pin assignments
- PTT button and LED configuration

**Debug & Logging:**
- Verbose modes and diagnostic options
- Performance monitoring

### Configuration File Management

**Smart File Handling:**
- Saves back to original config file when specified with `-c`
- Auto-discovery follows CLI search order when no config specified
- Create/Load/Save/Test configurations through web interface

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
- Detailed configuration management in Configuration tab
- Live status indicators
- Real-time voice transmission with PTT control
- Keyboard chat interface
- Message priority management
- Debug output and system status
- Sent and received audio can be replayed from the message history window
- Notification system for important events

### Dual-Mode Operation

Both interfaces can run simultaneously, providing flexibility for different operational scenarios:
- Web interface for configuration, audio replay, and monitoring
- CLI for keyboard-to-keyboard chat operations
- Instant updates between interfaces via WebSocket communication

---

## Protocol and Network Configuration

### Understanding Opulent Voice Protocol

Interlocutor implements the Opulent Voice protocol with sophisticated frame management:

**Frame Types and Priorities:**
1. **VOICE** (Priority 1): OPUS-encoded audio, immediate transmission
2. **CONTROL** (Priority 2): PTT state changes, high priority queue, A5 messages
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
- **Payload**: Variable length data loaded up in 40 ms frames
- **Encoding**: COBS (Consistent Overhead Byte Stuffing) framing
- **Transport**: UDP over IP with RTP headers for audio, UDP over IP for control, text, and data

### Network Integration

```bash
# Basic operation (connects to default target with default values)
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
- **Web PTT**: Additional click/touch controls in web interface

**Audio Processing Pipeline:**
1. Microphone input → PyAudio capture
2. Audio validation and level checking
3. OPUS encoding (40ms frames, 16,000 bps bitrate)
4. RTP header addition
5. UDP header addition
6. IP header addition
7. COBS encoding
8. Opulent Voice header addition
9. Network transmission

**Quality Settings:**
- Default: 16kbps OPUS encoding (path to 32kbps in future version)
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

Interlocutor implements intelligent reconnection logic for the web interface.

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

## Getting Help and Contributing

### Documentation Resources
- Project repository: https://github.com/OpenResearchInstitute/interlocutor
- Open Research Institute: https://www.openresearch.institute/getting-started
- Community forums and discussions on our Slack (see getting-started above)
- Opulent Voice Protocol documentation: 

### Support Channels
- GitHub Issues for bug reports
- ORI community forums (ORI Slack) for general discussion

### Contributing
- Code contributions welcome via GitHub pull requests
- Documentation improvements welcome and encouraged
- Testing and feedback valuable for development
- Hardware testing on different platforms welcome and encouraged

---

*This manual represents the current state of Interlocutor development. The system is actively developed open-source software, and features may evolve. Check the project repository for the latest updates and documentation.*

**73 de Open Research Institute**
