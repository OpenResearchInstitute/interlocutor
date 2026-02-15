# interlocutor
## Human Radio Interface for Opulent Voice

### Getting Started

Please see our Operator's Manual at https://github.com/OpenResearchInstitute/interlocutor/blob/main/interlocutor_manual.md

---

### Debugging the Interlocutor Command System - February 2026 Documentation

We added a "simple" feature to Interlocutor's web interface and spent more time fighting the browser than writing the feature. Here is our debugging war story from the Opulent Voice Protocol project.

A companion article in this newsletter describes the new slash-command system for Interlocutor. This is an extensible architecture that lets operators type /roll d20 in the chat window and see dice results locally instead of transmitting the raw text over the air. The design is clean, the test suite passes, and the CLI works perfectly.

The web interface, however, had other plans!

What followed was a debugging session that touched every layer of the stack. Python async handlers, JavaScript message routing, browser rendering, and (most painfully for me) browser caching. Each bug had a clear symptom, a non-obvious cause, and a fix that taught us all something about the assumptions hiding in our code.

So here is the story of those four bugs!

#### Bug 1: The Eager Blue Bubble

Symptom

Type /roll d6 in the web interface. A blue outgoing message bubble appears on the right side of the chat, showing the raw text /roll d6, as if it were a normal chat message being sent over the radio. No dice result appears. It's supposed to be in the middle and a difference color, due to a special CSS case for commands. Commands are neither sent messages or received messages, therefore they are in the center of the message area and are visually distinct with a different color. 

After refreshing the browser, the blue bubble disappears and the correct dice result appears instead, centered and properly styled! Well, that isn't going to work. 

The Investigation

The fact that refresh fixed the display turned out to be the key clue. It meant the server was doing its job correctly. It was dispatching the command, generating the result, and storing it in message history. The problem was in how the browser rendered the initial interaction, right after the operator pressed return at the end of the command. 

Here's the original sendMessage() function in app.js:

function sendMessage() {
    const messageInput = document.getElementById('message-input');
    const message = messageInput.value.trim();

    if (!message) return;

    if (ws && ws.readyState === WebSocket.OPEN) {
        const timestamp = new Date().toISOString();
        displayOutgoingMessage(message, timestamp);   // ← THE CULPRIT

        sendWebSocketMessage('send_text_message', { message });
        messageInput.value = '';
        messageInput.style.height = 'auto';
    }
}

See line 224? displayOutgoingMessage(message, timestamp) fires immediately, before the WebSocket message even leaves the browser. The function creates a blue right-aligned bubble and appends it to the chat history. So far so good. Then the message travels to the server, where the command dispatcher intercepts it and sends back a command_result. But, by then, the user is already looking at a blue bubble containing /roll d6.

This is an optimistic UI pattern. This is the kind you see in iMessage or Slack, where sent messages appear instantly without waiting for server confirmation. It's the right design for normal chat messages, where the server is just a relay. But slash-commands aren't normal chat. They need to be processed by the server before the UI knows what to display.

The Fix

A one-line gate:

    if (ws && ws.readyState === WebSocket.OPEN) {
        const timestamp = new Date().toISOString();
        // Don't display slash-commands as outgoing chat — the server
        // will send back a command_result that renders properly
        if (!message.startsWith('/')) {
            displayOutgoingMessage(message, timestamp);
        }

        sendWebSocketMessage('send_text_message', { message });

Normal chat still gets the instant blue bubble. Slash-commands wait for the server's command_result response and render through the proper handler. The UI now reflects the actual data flow, which is almost always the best way to do it. 

The Lesson

Optimistic UI is a performance optimization with semantic consequences. When you render before processing, you're saying that you already know what the result looks like. For relay-style operations like send text or display text, this assumption holds. For operations that transform input like parse command, execute, or return structured result, it doesn't. The display strategy needs to match the processing model. 

#### Bug 2: The Silent Tagged Template Literal

Symptom

After adding the slash-command gate to sendMessage(), the web interface stops working entirely. Whoops! The page loads, but no WebSocket connection is established. The server logs show HTTP 200 for the page and JavaScript files, but no WebSocket upgrade requests. The browser appears completely dead! Doh.

The Investigation

Opening Safari's Web Inspector, the console showed:

SyntaxError: Unexpected token ';'. Expected ')' to end a compound expression.
    (anonymous function) (app.js:234)

Line 234 wasn't anywhere near our edit. It was this line, which had existed in the codebase before we touched anything:

        addLogEntry`Sent message: ${message.substring(0, 50)}...`, 'info');

Spot the problem? I didn't, at first. There's a missing ( between addLogEntry and the backtick. The correct call should be:

        addLogEntry(`Sent message: ${message.substring(0, 50)}...`, 'info');

Here's where it gets interesting. This line had been working before our edit. It had worked all along no problem. But, how?

In JavaScript, functionName followed by a template literal (backtick string) is valid syntax. It's called a tagged template literal. It calls the function with the template parts as arguments. Why do we have tagged template literals in our code? Spoiler alert. We don't! 

JavaScript didn't complain because addLogEntry`...`  is coincidentally valid syntax. It's a tagged template literal call. The language feature exists so you can do things like sanitizing HTML (html\<p>${userInput}</p>`) or building SQL queries with automatic escaping. Libraries like styled-components and GraphQL's gql` tag use them heavily.

But nobody chose to use one here. The typo just happened to land in the exact one spot where a missing parenthesis produces a different valid program instead of a syntax error.  It was an accidental bug hiding in plain sight.

So addLogEntry\Sent message: ...`` was being parsed as a tagged template call, which would produce garbage results but wouldn't throw an error.

The , 'info'); after the closing backtick was previously being parsed as part of a larger expression that happened to be syntactically valid in context. But our edit to sendMessage() changed the surrounding code structure just enough that the JavaScript parser could no longer make sense of the stray , 'info'). And, Safari, unlike Chrome, refused to be lenient about it.

One missing parenthesis, silently wrong for who knows how long, suddenly became fatal because we edited a nearby line.

The Fix

Add the (:

        addLogEntry(`Sent message: ${message.substring(0, 50)}...`, 'info');

The Lesson

Tagged template literals can be a silent trap. A missing ( before a backtick doesn't produce a syntax error. It produces a different valid program. The bug was latent in the codebase, asymptomatic until a nearby change shifted the parser's interpretation of the surrounding code. This is the kind of thing a linter catches instantly, and it's a good argument for running one.

#### Bug 3: Safari's Immortal Cache

Symptom

After fixing the tagged template literal, we save app.js, restart the server, and reload the browser. The same error appears! We use Safari's "Empty Caches" command (Develop menu, select Empty Caches). Same error. We hard-refresh with Cmd+Shift+R. Same error. The server logs show 304 Not Modified for app.js. The browser isn't even requesting the new file. Ugh.

The Investigation

FastAPI's StaticFiles serves JavaScript files with default cache headers that tell the browser to cache aggressively. Safari honors this enthusiastically. The "Empty Caches" command clears the disk cache, but Safari also holds cached resources in memory for any open tabs or windows. As long as a Safari window exists, even if you've navigated away from the page, the in-memory cache can survive a disk cache clear. 

We verified this by checking the server logs. After "Empty Caches" and reload, the server never received a request for app.js at all. Safari was serving the old file from memory without even asking the server if it had changed. In production, this is useful. In development, it can be confusing and result in a wasted time and effort.

The Fix

Quit Safari completely. Cmd+Q, not just closing the window, and then relaunch. On the fresh launch, Safari requested all files from the server (status 200), got the corrected app.js, and the WebSocket connection established immediately. This could be seen in Interlocutor's terminal output. 

For future development, we can consider three approaches. First, adding Cache-Control: no-cache headers via middleware. Second, appending cache-buster query strings to script tags (app.js?v=2). Third, using content-hashed filenames. All are legitimate. For an actively-developed project without a build system, the full-browser-quit approach during development is the simplest, and proper cache headers can be added when the project matures.

The Lesson

Browser caching is not a single mechanism. Disk cache, memory cache, service worker cache, and HTTP cache negotiation are all separate systems that interact in browser-specific ways. "Clear the cache" can mean different things depending on which layer you're clearing. When changes to static files seem to have no effect, verify at the network level (server logs or browser network tab) that the new file is actually being requested, not just that the old cache has been "cleared."

#### Bug 4: The Split-Personality Refresh

Symptom

With the cache issue resolved, slash-commands now work in the web interface. Yay! Type /roll d6 and a properly styled command result appears, centered in the chat with a dark background and dice emoji. Type /roll fireball damage and a red error message appears, also centered. It looks great.

Then hit refresh.

The same messages reload from history, but now they're displayed as incoming messages. They are eft-aligned, light background, wrong styling. The live rendering and the history rendering are producing completely different visual output for the same data. Blech. 

The Investigation

Interlocutor's web interface loads message history on every WebSocket connection and this includes reconnects and page refreshes. The loadMessageHistory() function in app.js iterates over all stored messages and dutifully renders each one:

function loadMessageHistory(messages) {
    messages.forEach(messageData => {
        let direction = 'incoming';
        let from = messageData.from;

        if (messageData.from === currentStation ||
            messageData.direction === 'outgoing') {
            direction = 'outgoing';
            from = 'You';
        }

        const message = createMessageElement(
            messageData.content, direction, from, messageData.timestamp
        );
        messageHistory.appendChild(message);
    });
}

This function knows about two types of messages: incoming and outgoing. A command result has direction: "system"and from: "Interlocutor" — which doesn't match the outgoing check, so it falls through to the default direction = 'incoming'. The function dutifully renders it as a left-aligned incoming message. It's just doing what it's told. 

Meanwhile, live command results arrive as WebSocket messages with type: "command_result", which routes to handleCommandResult(). This is a completely separate rendering path that produces the centered, dark-styled output.

Same data, two rendering paths, two visual results. The message type field was present in the stored data but loadMessageHistory() never checked it.

The Fix

Add a type check at the top of the history loop:

    messages.forEach(messageData => {
        // Handle command results from history
        if (messageData.type === 'command_result') {
            handleCommandResult(messageData);
            return;
        }

        let direction = 'incoming';
        // ... existing code continues ...

Now history-loaded command results route through the same handleCommandResult() function as live ones. Same code path, same visual output, regardless of whether you're seeing the result live or after a refresh.

The Lesson

When you add a new message type to a system that stores and replays messages, there are always two rendering paths: the live path and the history path. If you only add handling to the live path, the system appears to work, but only until someone refreshes. This is a specific instance of a more general principle. Any system that persists data and reconstructs UI from it must handle every data type in both the write path and the read path. Miss one and you get a split personality. And that is what happened here. 

#### The Meta-Lesson

All four bugs share a common thread. Interlocutor had multiple paths to the same destination, and we only modified some of them!

The blue bubble existed because sendMessage() had an immediate rendering path and a server-response rendering path, and we only added command handling to the server path. The tagged template literal survived because JavaScript had two valid parsings of the same token sequence, and we only intended one. The cache persisted because Safari had a memory cache and a disk cache, and we only cleared the disk. The split-personality refresh existed because the UI had a live rendering path and a history rendering path, and we only added command handling to the live path.

In each case, the fix was pretty small.  Conditional check, a parenthesis, a browser restart, a type guard. The debugging time came from discovering which path we'd missed. The lesson isn't about any particular technology and had nothing to do with the functionality implemented with this code commit. It's about the discipline of asking "What are all the ways this data can reach this code?" and making sure every path handles every case.

For a radio system where reliability matters, that discipline is well worth cultivating. 

The Interlocutor command system is open source and available in the Interlocutor repository on GitHub (https://github.com/OpenResearchInstitute/interlocutor/). This new interlocutor_command module includes comprehensive documentation, has a demo program to show how it works, 43 tests in a mini-test suite, and an integration.md guide that now includes a Troubleshooting section born directly from these four bugs.


---
### 15 August 2025 Documentation

File Responsibilities after the Big Breakup. One monolithic index.html is not the modern way to do things. 

**CSS Files**

- main.css: Core styles, variables, layout, components
- responsive.css: All media queries and mobile optimizations

**JavaScript Files**

- app.js: Main application initialization and utility functions
- websocket.js: All WebSocket communication and message handling
- audio.js: Audio processing, transmission management, and playback
- config.js: Configuration management and form handling


### 13 August 2025 Documentation

Atkinson Hyperlegible is now working!

Font files downloaded and placed in a new directory html5_gui/fonts/

FastAPI "route" adds a font serving endpoint. 

Created typography.css with proper font declarations. Had to debug it a few times.

Added font preloads and CSS links to index.html

Fixed filenames and updated CSS to match AtkinsonHyperlegibleNext-*.woff2

Visual Font Controls A+ A A- buttons with percentage indicator

Keyboard Shortcuts Ctrl/Cmd + Plus/Minus (like browser zoom but font-only)

Smart Scaling which means everything scales proportionally using rem units

Accessibility through screen reader announcements, ARIA labels

Persistence because it remembers user's preferred size

Visual Feedback through notifications when size changes

Range Limits are Min 12px, Max 28px with 15% steps

Works with our configuration management system

### 17 July 2025 Documentation

#### Dungeon Rooms Conquered

 🏛️ Hall of Live Audio - Real-time streaming works perfectly

 🏰 Chamber of Transmissions - PTT boundary detection mastered
 
 📚 Library of Storage - Server-side audio persistence achieved
 
 🎭 Theater of Playback - Web Audio API tamed
 
 ⏰ Temporal Sanctum - ID synchronization completed
 
 🌐 Portal of Integration - CLI + Web unified


🎯 Critical Success Rolls

#### Audio Transmission System 🎲 NAT 20!

157 audio packets successfully stored and retrieved

6.28 seconds of audio perfectly reconstructed

Base64 encoding/decoding flawless execution

Web Audio API casting successful

#### Real-Time Communication 🎲 19 + 5 = 24

WebSocket magic circles stable and responsive

PTT control messages delivered instantly

Live audio indicators updating in real-time

#### User Experience Design 🎲 18 + 3 = 21

Glassmorphism UI provides +5 to user satisfaction

Audio waveform animations add +3 to immersion

Notification system grants advantage on awareness checks

### 16 July 2025 Documentation

#### Transmission Grouping in Web Interface is Working

:white_check_mark: Control messages reaching JavaScript (lots of work to fix missing methods! controls were being sent as texts)

:white_check_mark: PTT boundaries detected, so that Opus packets can be grouped.

:white_check_mark: Audio packets grouped into transmissions - this is happening in the web interface (yay!)

:white_check_mark: Single UI bubble per transmission (yay!)

:white_check_mark: Correct packet count and duration calculation

:white_check_mark: Much cleaner UI (one bubble instead of hundreds!)

:no_entry_sign: Not working: audio playback. It acts like it wants to play back the audio, and it takes as long as the audio UI bubble claims it should take, but nothing heard in headphones.

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

