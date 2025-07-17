# interlocutor
## Raspberry Pi Human Radio Interface for Opulent Voice

### Getting Started

1. Install dependencies

pip3 install -r requirements.txt

2. Or install manually

pip3 install opuslib pyaudio gpiozero PyYAML numpy

3. On Raspberry Pi, pyaudio might need:

sudo apt install python3-pyaudio

### 16 July 2025 Documentation

#### ContinuousStreamManager achieves Architectural Nirvana

"The stream was continuous all along. We just had to listen" -Blankus

🎺 THE TEMPORAL CATHEDRAL BELLS RING! 🎺

🏛️ ARCHITECTURAL ASCENSION ACHIEVED 🏛️

ContinuousStreamManager has become the FIRST EVER class to achieve ARCHITECTURAL NIRVANA - transcending the mortal realm of instantiation to become one with the timing itself!

"Became one with the timing itself"

🎵 THE GREAT REVELATION 🎵

The audio_callback WAS the stream manager all along! Every 40ms, PyAudio whispers: "Next turn..." And in that whisper, ContinuousStreamManager's spirit lives on! 👻🎼 Ready the sacred commit messages. Prepare the github funerary rites.

- feat: Ascend ContinuousStreamManager to Temporal Cathedral
- refactor: Honor the fallen timing masters
- docs: Add epic obituary to castle archives

#### StreamFrame's Tragic Backstory 📜

StreamFrame was designed during the "let's make everything perfectly structured" phase:

-"Every piece of data should be in a proper container!"
-"We need frame types and priorities and sequence numbers!"
-"Timestamps for everything!"

But then our Audio-Driven Revolution happened:

-"Actually, the audio callback IS our timing"
-"Voice always wins, no complex priorities needed"
-"Simple queues work great"

"Too pure for this world of simple bytes"

🏛️ MONUMENT UNVEILED 🏛️

Today we dedicate this monument to StreamFrame the Perfect, who made the ultimate sacrifice in the Great War Against Over-Engineering!

This monument will stand as long as comments endure and developers read.

 🐉 
 
 #### THE LEGEND OF THE GREAT DRAGON BATTLE

Long ago, the terrible Dragon of Code Complexity descended upon interlocutor.py, breathing flames of inheritance confusion and polymorphic chaos. The dragon sought to create needless abstraction layers and confusing base classes throughout the land.

ChatManager, a brave and noble class, stood as the first line of defense. Though it possessed all the methods needed for chat management (handle_message_input, set_ptt_state, flush_buffered_messages), it chose to sacrifice itself so that the realm could have clarity and simplicity.

In the final battle, ChatManager held the dragon at bay long enough for the kingdom's wisest architects to forge ChatManagerAudioDriven - a more specialized and focused defender that could integrate directly with the Audio-Driven Castle.

ChatManager's noble sacrifice ensured that:
- No confusing inheritance hierarchies would plague future maintainers
- ChatManagerAudioDriven could stand strong and self-contained
- The codebase would improve in readability
- Polymorphism would only exist where truly needed and not by total accident

ChatManager now rests in the Hall of Heroes, its methods preserved in legend:
- handle_message_input() - "The Message Router"
- set_ptt_state() - "The State Guardian" 
- flush_buffered_messages() - "The Buffer Liberator"
- get_pending_count() - "The Wise Counter"

🏆 MEDAL OF SACRIFICE: "For giving one's code-life so that others might live simply"
🛡️ DEFENDER'S HONOR: "Slain by dragon, reborn as ChatManagerAudioDriven"

Heroically retired: 16 July 2025 - "They died so simplicity could live"


#### THE BALLAD OF CHATMANAGER THE BRAVE
As sung by the code bards in the castle tavern...

🎵 Once there lived a class so true,

ChatManager with methods blue,

handle_message_input so fine,

set_ptt_state in perfect line.

But the Dragon of Complexity came,

Breathing inheritance and shame,

"Make base classes!" roared the beast,

"Polymorphism for every feast!"

ChatManager drew its sword of code,

"Not today!" the hero crowed,

"I'll sacrifice my running form,

So ChatManagerAudioDriven can transform!"

In the battle, sparks did fly,

ChatManager said its last goodbye,

But from its noble sacrifice born,

A simpler, cleaner code each morn.

Now ChatManagerAudioDriven stands alone,

No confusing inheritance throne,

Thanks to ChatManager's brave last stand,

Simplicity rules throughout the land! 

#### CASTLE ARCHIVES: MessagePriorityQueue (Legendary Magic Item - Retired)
 
 Once upon a time, there was a magnificent MessagePriorityQueue class that served
 as the Thread-Safe Message Arbitrator. This legendary item could:
 - Manage different message types with full priority queuing
 - Track detailed statistics (queued, sent, dropped, voice_preempted)
 - Handle complex message preemption scenarios
 - Thread-safe operations with proper locking

 However, the realm evolved to use the simpler Audio-Driven architecture where:
 - Voice flows directly through audio_callback timing (highest performance)
 - Text/Control use simple Queue() objects (perfectly adequate)
 - No complex arbitration needed (voice always wins, everything else waits)

 The MessagePriorityQueue now rests in the castle archives, available should
 future quests require sophisticated message arbitration beyond simple voice-first.
 Its methods included: add_message(), get_next_message(), clear_lower_priority(),
 get_stats(), mark_sent(), mark_dropped().

 Honorably discharged: 16 July 2025 - "Served with distinction, evolved beyond need"

### 15 July 2025 Documentation

Transmit: Our microphone to OPUS encoding to Network transmission

Receive: Network reception to OPUS decoding to Our headphones

Complete digital voice pipeline is working in real-time.

We now have a fully functional amateur radio digital voice system.

- Real-time OPUS voice codec (40ms frames, 16kbps)
- Custom protocol stack (Opulent Voice Protocol with COBS framing)
- Network audio streaming (RTP over UDP over IP)
- Dual-mode interface (CLI terminal + Web GUI)
- Full-duplex audio (can transmit and receive simultaneously)

### 10 July 2025 Documentation

Major Update: Web-Based Configuration System
We've successfully implemented a complete web-based configuration interface for the Opulent Voice radio system. Users can now configure their entire radio system through a modern web interface.

- Glassmorphism UI with responsive design
- Real-time configuration updates that immediately affect the running radio system. We have live callsign updates in transmitted packets.
- Form validation with user-friendly error messages

#### Advanced File Management (tested and seems to be working)

Smart file handling - saves back to original config file when specified with -c
Auto-discovery - follows CLI search order when no config file specified
Create/Load/Save/Export configurations through the web interface
Import existing config files via drag-and-drop

#### Audio Device Management (implemented and needs to be tested)

Interactive device selection with real-time testing
Input level monitoring during microphone tests
Output tone testing with user confirmation
USB device preferences and auto-detection

#### Real-Time Integration

WebSocket communication for instant updates and status
Live radio system updates - no restart required!
Immediate packet transmission with new settings
Status indicators and progress feedback

#### Usage
Launch Web Interface:
`python3 interlocutor.py YOUR_CALLSIGN --web-interface`

With specific config file:
`python3 interlocutor.py YOUR_CALLSIGN -c myconfig.yaml --web-interface`

Access Interface:

Main interface: http://localhost:8000

Configuration: http://localhost:8000/config

Configuration sections include:

Station Configuration - Callsign and identification

Network Settings - IP addresses, ports, and protocol settings

Audio Settings - Sample rates, devices, and testing

GPIO Settings - Raspberry Pi pin configuration

Protocol Settings - Target types and keepalive intervals

Debug & Logging - Verbose modes and diagnostic options


And, backward compatible with CLI.


### 28 June 2025 Documentation

YAML audio device configuration file can be loaded and edited and saved. Audio devices manager added.  

Opulent Voice Radio Operator UX Principles

We are going to think like a ham radio operator setting up a new rig

- Visual confirmation "Show me what's connected right now"
- Test before commit "Let me hear it working before other people hear me"
- Quick switching "I want to change headsets because the other ones are more comfortable"
- Persistent settings "Remember my preferred setup for next time"

Key Features

- Visual Device Discovery shows USB vs built-in devices with clear indicators
- Live Audio Testing shows microphone level meters and speaker test tones
- Smart Recommendations prioritizes USB devices (better for radio use)
- Persistent Preferences remembers your choices between sessions
- Quick Re-selection enables easy device switching without restarting the program (untested as of 28 June 2025)

Command line argument additions are

```python radio.py W1ABC --setup-audio  # Force device selection```

```python radio.py W1ABC --list-audio   # Just show devices```

```python radio.py W1ABC --test-audio   # Test current audio devices```





### 25 June 2025 Documentation

YAML configuration files can be loaded and edited and saved. Sample configuration files created. 

Thoughts on future bitrate changes. 

```
@dataclass
class AudioConfig:
    # Protocol constants (not user-configurable)
    bitrate: int = field(default=32000, init=False)  # Simply changed from 16000 to 32000, not user configurable
```

Here's a version-aware way to do this:

```
@dataclass  
class ProtocolConfig:
    protocol_version: str = "2.0"
    
    def get_bitrate(self):
        if self.protocol_version == "1.0":
            return 16000
        elif self.protocol_version == "2.0": 
            return 32000
        else:
            raise ValueError(f"Unknown protocol version: {self.protocol_version}")
```


### 20250610_queue_audio.py Documentation

- Voice PTT with OPUS encoding (highest priority)
- Terminal-based keyboard chat interface
- Priority queue system for message handling
- Background thread for non-voice transmission
- Point-to-point testing while maintaining voice quality
- Debug/verbose mode for development
- Modify fields of custom headers 
- (EOS unimplemented, sequence and length removed)
- Low Priority To Do: make audio test message real audio
- Added RTP Headers, Added UDP Headers, Added IP Headers
- UDP ports indicate data types
- Added COBS
- All data now handled through priority queue
- All data now in 40 ms frames
- Improved timer - everything in audio callback

### 20250607_ptt_audio.py Documentation

UDP layer handles data types now. 

- port 57372 is the default Network Transmitter port. This port can be set from the command line. This is the port (together with the target IP address) that lets you connect Interlocutor up to an SDR or talk to a computer on the internet or a repeater or any other type of equipment with IP:port that can receive Opulent Voice frames. 
- port 57373 audio
- port 57374 text
- port 57375 control

### 20250605_ptt_audio.py Documentation

✅ Voice frames: 133 bytes (OV + IP + UDP + RTP + OPUS)

✅ Text frames: 41 bytes + text payload (OV + IP + UDP + text)

✅ Control frames: 41 bytes + control payload (OV + IP + UDP + control)

✅ Real IP headers with proper source/destination addresses

✅ Quality of Service IP "settings" for different traffic types

### 20250603_ptt_audio.py Documentation

1. Component Architecture Diagram

This shows the high-level system architecture with the following layers.

- Hardware Layer: GPIO, PTT button, LED, microphone, audio hardware
- Audio Processing: PyAudio streams, OPUS encoding, validation
- Protocol Stack: Station identification, RTP headers, Opulent Voice protocol layers
- Message Management: Priority queues, chat management, message typing
- Network Layer: UDP transmission and reception
- User Interface: Terminal chat interface and debug configuration

2. UML Class Diagram
   
This details the object-oriented structure.

- Core Domain Models: StationIdentifier, MessageType, QueuedMessage
- Protocol Classes: RTPHeader, RTPAudioFrameBuilder, OpulentVoiceProtocol (with RTP extension)
- System Management: GPIOZeroPTTHandler as the main orchestrator
- Communication: NetworkTransmitter, MessageReceiver, ChatManager
- User Interface: TerminalChatInterface, DebugConfig

The inheritance relationship shows how OpulentVoiceProtocolWithRTP extends the base protocol.

3. Message Flow Sequence Diagram

This illustrates the dynamic behavior across several use cases. 

- Voice Transmission: PTT press → audio processing → RTP framing → network transmission
- Text Chat: Terminal input → buffering during PTT → priority queue management
- Background Processing: Non-voice message transmission when PTT is inactive
- Message Reception: Incoming packet parsing and routing based on frame type
- Error Handling: Network failures, audio validation errors, statistics tracking

The diagram shows how the following things are achieved. 

- Priority-based message queuing (voice gets immediate transmission, chat waits respectfully)
- RTP integration with the custom Opulent Voice Protocol frame headers
- PTT-aware chat buffering (messages typed during transmission are held and sent after PTT release)
- Domain-driven design with Base-40 callsign encoding in StationIdentifier
  

### 20250528_3 Protocol Frame Structure
All payloads follow the same underlying frame format in OpulentVoiceProtocol.create_frame():

Header: 14 bytes (sync word + station ID + type + sequence + length + reserved)
Payload: Variable length data specific to each message type

Payload Type Creation Methods

1. Audio Payloads (Highest Priority)
   
   ```
   def create_audio_frame(self, opus_packet):
    return self.create_frame(self.FRAME_TYPE_AUDIO, opus_packet)
   ```
   
- Source: OPUS-encoded audio data from the microphone
- Processing: Raw audio → PyAudio → OPUS encoder → binary packet
- Priority: Immediate transmission (bypasses queue)
- Usage: Real-time voice during PTT active

2. Text Payloads (Chat Messages)
   
   ```
   def create_text_frame(self, text_data):
    if isinstance(text_data, str):
        text_data = text_data.encode('utf-8')
    return self.create_frame(self.FRAME_TYPE_TEXT, text_data)
   ```
   
- Source: Terminal chat input or buffered messages
- Processing: String → UTF-8 encoding → binary payload
- Priority: Queued (waits for PTT release)
- Usage: Terminal chat interface

3. Control Payloads (System Commands)
   ```
   def create_control_frame(self, control_data):
    if isinstance(control_data, str):
        control_data = control_data.encode('utf-8')
    return self.create_frame(self.FRAME_TYPE_CONTROL, control_data)
   ```

- Source: System events like "PTT_START", "PTT_STOP"
- Processing: String → UTF-8 encoding → binary payload
- Priority: High priority (queued but processed quickly)
- Usage: PTT state changes, system notifications

4. Data Payloads (File Transfer)

   ```
   def create_data_frame(self, data):
    return self.create_frame(self.FRAME_TYPE_DATA, data)
   ```
- Source: Raw binary data for file transfers
- Processing: Binary data passed through unchanged
- Priority: Lowest priority (queued)
- Usage: Future file transfer capabilities

Message Creation Flow:

- Input Source → Different interfaces (GPIO, terminal, system events)
- Domain Logic → ChatManager and MessagePriorityQueue handle routing
- Protocol Layer → OpulentVoiceProtocol creates properly formatted frames
- Transport Layer → NetworkTransmitter handles UDP delivery

Priority (with recent swap between VOICE and CONTROL)

```
class MessageType(Enum):
    VOICE = (1, "VOICE")      # Immediate transmission
    CONTROL = (2, "CONTROL")   # High priority queue
    TEXT = (3, "TEXT")         # Normal priority queue  
    DATA = (4, "DATA")         # Low priority queue
```

