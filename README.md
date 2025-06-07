# interlocutor
## Raspberry Pi Human Radio Interface for Opulent Voice

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

