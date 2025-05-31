# interlocutor
## Raspberry Pi Human Radio Interface for Opulent Voice
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
   
