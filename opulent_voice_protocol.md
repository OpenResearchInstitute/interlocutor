# Opulent Voice Protocol Specification
## High-Fidelity Digital Voice and Data for Amateur Radio

**Version:** 1.0  
**Date:** July 2025  
**Status:** Implementation Draft  
**Organization:** Open Research Institute  

---

## Abstract

The Opulent Voice Protocol (OPV) is an open-source, high-fidelity digital voice and data communication protocol designed for amateur radio applications. Unlike existing low-bitrate digital voice modes, OPV prioritizes audio quality while providing seamless integration of voice, text chat, file transfer, and system control messages within a unified protocol framework.

OPV uses modern digital signal processing techniques including OPUS audio compression, robust forward error correction, and priority-based message queuing to deliver professional-quality communications over amateur radio spectrum.

This document explains why the protocol was written, what is required, and gives examples from ORI's reference design to show how it can be implemented. 

---

## 1. Introduction

### 1.1 Protocol Goals

**Primary Objectives:**
- Deliver high-fidelity voice quality surpassing existing amateur digital voice modes. OPV has a minimum of 16 kbps OPUS vs 3.2 kbps CODEC2 vs 3.4 kbps AMBE. 
- Seamlessly integrate multiple data types (voice, text, files, control) in a single protocol. No more switching to a clunky second packet mode for data. 
- Provide robust error correction and interference resilience using modern digital communications techniques. 
- Enable remote operation.
- Maintain compatibility with standard Internet protocols where beneficial.

**Design Philosophy:**
- **Voice Always Wins**: Voice transmission has absolute priority over all other data types.
- **Modern Codec Quality**: Leverage OPUS codec for superior audio fidelity (16 kbps baseline).
- **Unified Protocol**: Single protocol handles all current and future communication types without mode switching through priority queues and UDP port number assignments. 
- **Open Source**: Fully documented, patent-free implementation available to all. 
- **40ms Frame Timing**: Reference implementation is synchronized to 40ms audio callback timing from hardware.

### 1.2 Protocol Stack Overview

The Opulent Voice Protocol defines a complete digital voice and data communication system:

```
┌─────────────────────────────────────────┐
│           Application Layer             │
│     (Voice, Text, Data, Control)        │
├─────────────────────────────────────────┤
│         Opulent Voice Protocol          │
│ (COBS Framing, Priority, Encapsulation) │
├─────────────────────────────────────────┤
│           Transport Layer               │
│         (IP/UDP/RTP Headers)            │
├─────────────────────────────────────────┤
│           Physical Layer                │
│      (FEC, Modulation, RF)              │
└─────────────────────────────────────────┘
```

**Protocol Responsibilities:**
- **COBS Framing**: Consistent Overhead Byte Stuffing for boundary detection of the data types sent. Opus voice packets are consistent in size and occupy exactly one OPV frame. However, text, control, and data payloads are variable length. Some can be quite long. COBS framing keeps track of the boundaries of all data types. It does not matter whether the data takes less than an OPV frame, or multiple OPV frames. COBS keeps track of this so that no other networking or radio transmission will lose the edges of the data being transmitted. 
- **Priority Management**: Voice-first queuing and transmission ensures that the operator hears voice without delay.
- **Encapsulation**: Integration with standard Internet protocols provides immense opportunity and flexibility for integration into existing radio and networking products and services. 
- **Authentication**: Station identification and access control comply with regulatory and policy situations ranging from uncontrolled access to highly restricted access. Authentication can be done on a per-frame basis, when triggered or requested, or not at all. 

**Implementation Freedom:**
The protocol can be implemented in various ways - as separate modules, integrated systems, or distributed across different hardware platforms, but all implementations must use OPV headers, COBS encoding, IP headers, UDP headers, and RTP (for Opus payloads) for dataframe interoperability. For modem interoperability, the forward error correction, scrambling, whitening, and synchronization frames must be included. For transmission interoperability, the preamble, dummy frames, and end of transmission signals must be included. The reference implementations of Interlocutor and Locutus are given throughout this document as examples. 

---

## 2. Frame Structure

### 2.1 Opulent Voice Protocol Frame Format

The Opulent Voice Protocol uses fixed-size and fixed-timing frames for all data types:

```
┌─────────────────────────────────────────┐
│          OPV Header (12 bytes)          │
├─────────────────────────────────────────┤
│                 Payload                 |
|   (12-byte header + 122-byte payload)   │
└─────────────────────────────────────────┘
```

**Frame Requirements:**
- **Header Size**: 12 bytes (aligned for Golay error correction).
- **Timing**: Frames must be transmitted at regular intervals.
- **Priority**: Voice frames have transmission priority over control frames, which have priority over text frames, which have priority over data frames.
- **Encapsulation**: Standard Internet protocols (COBS/IP/UDP/RTP) are used within the Opulent Voice payload.

**OPV Header Structure:**

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
├─────────────────────────────────────────────────────────────────┤
│                  Station Identifier (48 bits)                   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                    Token (24 bits)                              │
├─────────────────────────────────────────────────────────────────┤
│                   Reserved (24 bits)                            │
└─────────────────────────────────────────────────────────────────┘
```

**Header Fields:**

| Field | Size | Description |
|-------|------|-------------|
| Station ID | 48 bits (6 bytes) | Base-40 encoded amateur radio callsign or station ID |
| Token | 24 bits (3 bytes) | Implementation-specific identifier |
| Reserved | 24 bits (3 bytes) | Reserved for future protocol extensions |

#### Implementation Example: Interlocutor

The ORI reference implementation uses 134-byte total frames (12-byte header + 122-byte payload) synchronized to 40ms audio callback timing. The Token field contains `0xBBAADD` as a default frame identification pattern. The reserved field is not used.

### 2.2 Message Types and Priority

The protocol defines four message types with strict priority ordering:

| Type | Priority | Description |
|------|----------|-------------|
| VOICE | 1 (Highest) | OPUS-encoded audio data |
| CONTROL | 2 (High) | System commands and authentication |
| TEXT | 3 (Normal) | Keyboard chat and text messages |
| DATA | 4 (Low) | File transfers and bulk data |

**Priority Requirements:**
- **Voice Supremacy**: Voice messages must preempt all other types. Voice is sensistive to delay and the immediate experience of communicating with other people is prioritized in OPV. 
- **Real-time Constraint**: Voice must be transmitted within timing requirements. Frames are sent out every 40 ms. 
- **Queue Management**: Lower priority messages wait for higher priority completion in queues so that lower-priority messages are not lost. 
- **PTT Integration**: Push-to-talk control for voice transmissions affects message scheduling. It is an implementation decision whether or not to interrupt the current frame or wait for the beginning of the next frame to transmit higher priority data. 

#### Implementation Example: Interlocutor

The reference implementation uses enum values `VOICE = (1, "VOICE")`, `CONTROL = (2, "CONTROL")`, etc. Voice transmission bypasses all queues and is processed at the beginning of the next frame via the 40ms audio callback. Text messages typed during voice transmission are buffered and transmitted when PTT is released.

### 2.3 Callsign Encoding

**Protocol Requirements:**
- **Character Set:** Supports station identifications that include all amateur radio callsigns.
- **Efficiency:** Provides a compact representation.
- **Flexibility:** Allows common tactical and non-amateur station identification formats.
- **International:** Supports all national callsign formats.
- **Unique Identity:** Each transmission must uniquely identify the originating station.
- **Regulatory Compliance:** OPV meets amateur radio identification requirements as long as the station's callsign is unambiguously included in the station identifier.
- **Authentication Ready:** The protocol supports cryptographic verification when needed. 
- **Multiple Stations:** Allows multiple stations per license through secondary station identification (SSID).

**Base-40 Encoding Specification:**

Character mapping for efficient callsign encoding:

| Character | Value |
|------|-------|
| not used | 0 |
| A-Z | 1-26 |
| 0-9 | 27-36 |
| - | 37 |
| / | 38 |
| . | 39 |

**Encoding Process:**
1. Normalize callsign to uppercase
2. Convert each character to base-40 value
3. Pack into 48-bit field: `value = Σ(char[i] × 40^(position))`

#### Implementation Example: Interlocutor

Uses 6-byte station identifier field in OPV header with Base-40 encoding. Supports all combinations of uppercase letters, digits, and three special characters (hyphen, slash, and period) up to 9 characters, and many combinations of 10 characters. Validates character set during encoding. Example: `StationIdentifier` class handles encoding/decoding with error checking and provides `to_bytes()` and `from_bytes()` methods. Station identification format is validated and clearly communicated before saving the configuration file in the Configuration tab of the web interface and in the command line interface.

#### Test Cases

| Identifier | Encoding | Comment |
|------------|----------|---------|
| W1AW | 0x0000001680b7 | |
| KB5MU-11 | 0x0447b6864a5b | KB5MU with SSID of 11 |
| W5NYV.NCS | 0x71c06f55a697 | W5NYV, perhaps as Net Control Station |
| VE7ABC/W1 | 0xaa764d576f5e | VE7ABC operating in U.S. call area 1 |
| W3/G1ABC | 0x007463900847 | G1ABC operating in U.S. call area 3 |
| K0K | 0x000000004903 | Special event callsign K0K |
| A | 0x000000000001 | Lowest encoded value, not a valid callsign |
| OFD4BS.-BA | 0xffffffffffff | Highest encoded value |
------

## 3. Payload Specifications

### 3.1 Voice Payloads

Voice payloads carry OPUS-encoded audio data with streaming protocol integration provided by Real Time Protocol (RTP).

**Protocol Requirements:**
- **Codec:** OPUS compression
- **Bitrate:** 16 kbps minimum (higher bitrates permitted)
- **Frame Duration:** 40 ms per frame
- **Sample Rate:** 48 kHz
- **Channels:** Mono
- **Streaming:** Provided through RTP headers
- **Quality:** Must deliver a substantial improvement over existing amateur digital voice products.

**Voice Payload Structure:**
```
┌───────────────────────────────────────────┐
│           RTP Headers                     │
│     (Sequence, Timing, Streaming)         │
├───────────────────────────────────────────┤
│           OPUS Data                       │
│        (40ms encoded audio)               │
└───────────────────────────────────────────┘
```

#### Implementation Example: Interlocutor

Uses RTP headers for streaming management with OPUS payload. Structure: RTP Header (12 bytes) + OPUS data (80 bytes) = 92 bytes total. RTP provides sequence numbering, timestamps at 48 kHz sample rate, and the SSRC field takes the station identification value. The complete voice payload is then encapsulated in UDP/IP headers before COBS encoding into the OPV frame.

### 3.2 Text Payloads

Text payloads handle keyboard chat and text messaging.

**Protocol Requirements:**
- **Encoding:** UTF-8 should be used for international character support.
- **Maximum Size:** Implementation-dependent.
- **Priority:** Must yield to voice transmission.
- **Fragmentation:** COBS is used to mark boundaries of large messages that may span multiple frames.

**Payload Format:**
```
┌───────────────────────────────────────────┐
│           UTF-8 Encoded Text              │
│           (Variable Length)               │
└───────────────────────────────────────────┘
```

#### Implementation Example: Interlocutor

Text messages are UTF-8 encoded and encapsulated in UDP/IP headers, then COBS encoded. Messages typed during PTT are buffered in a priority queue and transmitted when voice transmission ends. Large text messages automatically fragment across multiple 134-byte frames.

### 3.3 Control Payloads

Control payloads manage system state, authentication, and protocol functions.

**Protocol Requirements:**
- **Authentication:** Control frames provide support for station verification.
- **PTT Signaling:** Push-to-talk state management is required, as voice pre-empts control frames.
- **System Commands:** Configuration and control functions can be communicated through this channel.
- **Priority:** High priority, may interrupt non-voice traffic.
- **Security:** Control fremas provide support for secure cryptographic authentication. This is not a required function of the protocol, but it is an option that provides significant additional value.

**Standard Control Messages:**

| Message Type | Purpose | Response Required |
|--------------|---------|-------------------|
| PTT_START | Voice transmission begins | No |
| PTT_STOP | Voice transmission ends | No |
| AUTH_REQUEST | Station authentication required | AUTH_RESPONSE |
| AUTH_RESPONSE | Cryptographic authentication | Result notification |
| STATION_ID | Station identification | No |
| KEEPALIVE | Connection maintenance | KEEPALIVE |

#### Implementation Example: Interlocutor

Control messages are ASCII-encoded strings like "PTT_START", "PTT_STOP" encapsulated in UDP/IP. Authentication uses LoTW certificates when available. Control frames use high-priority queuing and can preempt text/data transmission. Control frames are preempted by voice transmissions. 

### 3.4 Data Payloads

Data payloads enable file transfer and message passing.

**Protocol Requirements:**
- **Content:** Content is arbitrary binary data that the operator chooses to send.
- **Priority:** Lowest (background transmission).
- **Fragmentation:** COBS is used to mark boundaries of large transfers that may span multiple frames.
- **Sequencing:** Data needs proper reassembly of fragmented data.
- **Flow Control:** Must not interfere with real-time voice, text, or control messages. 

**Payload Format:**
```
┌───────────────────────────────────────────┐
│           Raw Binary Data                 │
│          (Variable Length)                │
└───────────────────────────────────────────┘
```

#### Implementation Example: Interlocutor

Raw binary data is passed through unchanged and encapsulated in UDP/IP. Large files are automatically fragmented across multiple frames using sequence numbers for reassembly. Data transmission uses the lowest priority queue and is suspended during voice transmission.

---

## 4. Transport Layer Integration

### 4.1 COBS Framing Requirement

The Opulent Voice Protocol mandates Consistent Overhead Byte Stuffing (COBS) for frame boundary detection. All payload data must be COBS-encoded before transmission. Use 0x00 bytes as frame delimiters. COBS costs minimal overhead (typically less than 1%) for frame boundary detection. COBS is self-synchronizing. Receivers can recover frame boundaries after errors. COBS is compatible with byte-oriented transmission interfaces. 0x00 bytes can only be frame delimiters in the encoded stream, making frame boundary detection trivial.

**COBS Algorithm:**

Every block of non-zero data gets prefixed with a length byte
This length byte tells us "the next N bytes are all non-zero, then there's either a zero or end-of-data marker". 
The length byte includes either the removed zero byte, or an end-of-data marker. Which, for us, is 0x00. 

So if we have input data values [0x41, 0x42, 0x00, 0x43, 0x44, 0x88]
COBS encoding would be [0x03, 0x41, 0x42, 0x04, 0x43, 0x44, 0x88, 0x00]

0x03: "We are encoding three bytes. The next 2 bytes are non-zero, then there was a zero byte"
0x41, 0x42: the non-zero data
0x03: "We are encoding four bytes. The next 3 bytes are non-zero, but we reached the end of the data, so we append the end-of-data marker"
0x43, 0x44, 0x88: the non-zero data
0x00: COBS frame delimiter reached! If we had come across a non-zero value, it would be how many more bytes were encoded. But, we have 0x00. This means we stop right here. We either start a new COBS frame or it's the end of transmission. 

The length bytes indicate where the zeros were. When you see a length byte, you know there's an implicit zero after that many data bytes (unless it's the end).

### 4.2 Protocol Encapsulation

The Opulent Voice Protocol integrates with standard Internet protocols for payload encapsulation.

**Encapsulation Requirements:**
- **Framing:** COBS provides a payload boundary detection mechanism.
- **Network Layer:** IP headers for routing and addressing.
- **Transport Layer:** UDP for low-latency datagram transmission.
- **Application Layer:** RTP headers for audio streaming functionality.

**Encapsulation Stack:**
```
┌─────────────────────────────────────────┐
│         OPV Frame Header                │
├─────────────────────────────────────────┤
│          COBS Encoding                  │
├─────────────────────────────────────────┤
│           IP Headers                    │
├─────────────────────────────────────────┤
│          UDP Headers                    │
├─────────────────────────────────────────┤
│  Application Headers (RTP for audio)    │
├─────────────────────────────────────────┤
│          Payload Data                   │
└─────────────────────────────────────────┘
```

### 4.2 Quality of Service

**Traffic Classification:**
Different message types receive appropriate network priority:

| Message Type | Priority Class | Typical ToS/DSCP |
|--------------|----------------|------------------|
| VOICE | Real-time | Expedited Forwarding |
| CONTROL | High | Assured Forwarding |
| TEXT | Normal | Assured Forwarding |
| DATA | Background | Assured Forwarding |

### 4.3 Port and Addressing

**Protocol Requirements:**
- **Addressing:** Support for point-to-point and and conference scenarios
- **Port Management:** Destination ports are used to indicate the data types. There is not a data type field in the protocol header. 
- **Network Integration:** Compatible with existing Internet infrastructure and services. 

#### Implementation Example: Interlocutor

Uses COBS (Consistent Overhead Byte Stuffing) for frame boundary detection of data distributed over multiple 122-byte payload frames. Standard IP/UDP headers with configurable port assignments: 57372 (Network Transmitter), 57373 (Audio), 57374 (Text), 57375 (Control). 

---

## 5. Priority and Queuing

### 5.1 Message Priority System

OPV implements strict priority queuing where higher priority messages always preempt lower priority messages:

**Priority Levels:**
1. **VOICE (Priority 1):** Immediate transmission, bypasses all queues
2. **CONTROL (Priority 2):** High priority queue, can interrupt text/data
3. **TEXT (Priority 3):** Normal priority queue, waits for voice/control completion. Can interrupt data.
4. **DATA (Priority 4):** Background transmission, lowest priority

### 5.2 PTT-Aware Buffering

**Voice Transmission Active (PTT Pressed):**
- Voice frames transmit immediately
- Text messages typed during transmission are buffered
- Control messages may interrupt voice for critical system functions
- Data transmission is suspended

**Voice Transmission Inactive (PTT Released):**
- Buffered text messages transmit immediately
- Control queue processes normally
- Data transmission resumes
- Chat input is live (not buffered)

### 5.3 Queue Management

**Buffer Overflow Handling:**
- Voice: Never buffered (real-time only) 
- Control: Larger buffer, user notification on overflow
- Text: Fixed size queue, oldest messages dropped
- Data: Flow control, transmission pauses when buffer full

Authentication and authorization failures need immediate user attention, while dropped chat messages are more of a usability issue than a system integrity issue.

---

## 6. Physical Layer Interface

### 6.1 COBS Framing

Consistent Overhead Byte Stuffing (COBS) provides frame boundaries for our data. Data may be smaller than the fixed-length payaload of a single frame, or it may be much larger, requiring many frames to transmit. We need to know where our data begins and ends, and COBS provides that knowledge. 

**COBS Benefits:**
- Guaranteed frame delimiters (0x00 bytes)
- Minimal overhead (typically <1%)
- Self-synchronizing frame recovery
- Compatible with byte-oriented interfaces

**Implementation:**
1. Apply COBS encoding to complete OPV frame
2. Append 0x00 delimiter
3. Transmit encoded frame + delimiter
4. Receiver uses 0x00 bytes to find frame boundaries

### 6.2 Supported Physical Layers

**Primary Target: MSK Modem**
- Minimum Shift Keying modulation
- PLUTO SDR implementation
- Over-the-air amateur radio transmission

**Development/Testing: Ethernet**
- Direct IP transmission for development
- Remote operation capabilities
- Internet gateway connections

**Future: Additional SDR Platforms**
- GNU Radio implementations
- Other SDR hardware platforms
- ASIC implementations planned

---

## 7. Authentication and Authorization

### 7.1 Authentication Framework

**Protocol Requirements:**
- **Station Verification:** Cryptographic verification of amateur radio license
- **Certificate Support:** Integration with existing amateur radio certificate systems
- **Challenge-Response:** Support for on-demand authentication
- **Replay Protection:** Prevent unauthorized reuse of authentication data

**Recommended Authentication Flow:**
```
1. Station includes callsign + token in every transmission
2. System stores (timestamp, callsign, token) for tracking
3. When authentication required:
   System → Station: Authentication challenge
   Station → System: Signed response + certificate
   System: Verify certificate chain and signature
4. Authentication result communicated to all participants
```

### 7.2 Authorization Framework

**Protocol Requirements:**
- **Access Levels:** Support for different privilege levels
- **Emergency Override:** Critical traffic must bypass normal restrictions
- **Policy Flexibility:** Configurable access control policies
- **Graceful Degradation:** Maintain basic functionality when control systems offline

**Access Control Concepts:**
- **Deny Lists:** Stations temporarily or permanently restricted
- **Allow Lists:** Stations with enhanced privileges
- **Tiered Access:** Different capabilities (text-only, voice, full bandwidth)
- **Emergency Access:** Unrestricted access for emergency communications

### 7.3 Security Considerations

**Threat Model:**
- **Primary Threat:** Unauthorized use overwhelming system capacity
- **Secondary Threats:** Interference, identity spoofing, denial of service
- **Design Principle:** Security should not impede emergency communications

#### Implementation Example: Interlocutor

Supports ARRL Logbook of the World (LoTW) certificate authentication. Station callsign embedded in every frame header using Base-40 encoding. Implements challenge-response authentication using ASCII control messages ("AUTH_REQUEST", "AUTH_RESPONSE"). Default policy allows initial access without authentication (emergency consideration) with on-demand verification available.

---

## 8. Physical Layer Requirements

### 8.1 Forward Error Correction

**Protocol Requirements:**
- **Header Protection:** Error correction suitable for frame headers
- **Payload Protection:** Robust coding for data payload
- **Burst Protection:** Interleaving to handle burst errors
- **Performance:** Sufficient correction for target channel conditions

**Protocol Approach:**
- Header: Golay codes (work well with 12-byte headers)
- Payload: 1/2 rate convolutional coding
- Interleaving: Spread errors across frame boundaries

### 8.2 Modulation

**Protocol Requirements:**
- **Spectral Efficiency:** Efficient use of amateur radio spectrum
- **Phase Continuity:** Minimal adjacent channel interference
- **Demodulator Compatibility:** Feasible implementation in SDR
- **Performance:** Suitable for amateur     radio channel conditions

**Required Modulation:**
- Minimum Shift Keying (MSK) for phase continuity and spectral efficiency

### 8.3 Frame Synchronization

**Protocol Requirements:**
- **Preamble:** "Lighthouse Signal" pattern for receiver acquisition
- **Sync Words:** Frame boundary identification. This helps receivers readjust their clocks every frame, so that the difference between sender and local clocks doesn't cause temporal drift and receiver failure.
- **End of Transmission:** Clean transmission termination. We know we're done with the transmission. 
- **Interleaving:** Spreads burst errors across frame boundaries for better error correction. Executed with a quadratic permutation polynomial f(x) = 63x + 128x² (mod 2048)
- **Randomizing:** XOR with pseudo-random sequence to break up bit patterns and flatten signal spectrum. 

XOR with this decimal data: 163 129 92 196 201 8 14 83 204 161 251 41 158 79 22 224 151 78 43 87 18 167 63 194 77 107 15 8 48 70 17 86 13 26 19 231 80 151 97 243 190 227 153 176 100 57 34 44 240 9 225 134 207 115 89 194 92 142 227 215 63 112 212 39 194 224 129 146 218 252 202 90 128 66 131 21 15 162 158 21 156 139 219 164 70 28 16 159 179 71 108 94 21 18 31 173 56 61 3 186 144 141 190 211 101 35 50 184 171 16 98 126 198 38 124 19 201 101 61 21 21 237 53 244 87 245 88 17 157 142 232 52 201 89 248 214 182 55 4 54 137 28 218 233 86 120 1 80 124 67 175 233 146 68 237 17 160 242 132 244 70 135 233 55 211 36 112 224 180 127 156 20 62 7 216 4 141 31 150 159 191 80 234 200 26

This sequence whitens the 1480-bit Opulent Voice frames (185 bytes × 8 bits = 1480 bits).  

#### Implementation Example: Locutus Modem

ORI's Locutus modem implements MSK modulation targeting PLUTO SDR hardware. (TBD) Uses Golay codes for 12-byte header protection and 1/2 rate convolutional codes for payload. (TBD) Provides preamble, sync frames, and end-of-transmission signaling. Includes interleaving and whitening for improved transmission characteristics.

---

## 9. Performance and Quality

### 9.1 Audio Quality Requirements

**Protocol Targets:**
Keeping open for KB5MU contributions

### 9.2 Network Performance

**Bandwidth Requirements:**
- **Voice:** 16 kbps + protocol overhead (approximately 20 kbps total)
- **Text:** Minimal bandwidth (burst transmission as needed)
- **Control:** Very low bandwidth for system management
- **Data:** Variable bandwidth (background priority, yield to voice)
- **RF:** Complex baseband at 27,100 symbols/second carries 2 bits per symbol. The result is 54,200 bps. 1.5x the bit rate, typical for unfiltered MSK, results in an 80 kHz RF bandwidth. 

**Latency Tolerance:**
- **Voice:** <200 ms for good user experience
- **Text:** <2 seconds for responsive chat
- **Control:** <500 ms for system responsiveness
- **Data:** No specific latency requirements

### 9.3 Error Resilience

**Protocol Requirements:**
- **Forward Error Correction:** Sufficient coding for target bit error rate performance.
- **Graceful Degradation:** Maintain basic functionality under poor conditions.
- **Burst Error Protection:** Interleaving required for fast fading channel resilience.

#### Implementation Example: Interlocutor + Locutus

Achieves target audio quality using 16 kbps OPUS encoding with 40ms frames. Network overhead approximately 25% (134-byte frames carrying 80-byte OPUS payload). Golay + convolutional forward error correction provides robust error correction.

---

## 10. Reference Implementation

### 10.1 ORI Implementation Architecture

The Open Research Institute provides a complete reference implementation split across two main components:

**Interlocutor (Human-Radio Interface):**
- **Platform:** Raspberry Pi with Python implementation
- **Function:** User interface, audio processing, frame creation
- **Features:** Web GUI, CLI interface, priority queuing, COBS encoding
- **Integration:** Creates 134-byte OPV frames for transmission to modem.

https://github.com/OpenResearchInstitute/interlocutor

**Locutus (Modem Layer):**
- **Platform:** PLUTO SDR with FPGA implementation
- **Function:** Physical layer processing and RF transmission
- **Features:** MSK modulation, FEC, interleaving, synchronization
- **Integration:** Processes OPV frames from Interlocutor

https://github.com/OpenResearchInstitute/pluto_msk

### 10.2 Interlocutor Implementation Details

**Key Software Components:**
- `OpulentVoiceProtocolWithIP`: Core frame creation and processing
- `StationIdentifier`: Base-40 callsign encoding/decoding
- `RTPAudioFrameBuilder`: RTP header generation for voice streams
- `MessagePriorityQueue`: Voice-first priority queuing system
- `COBSEncoder`: Frame boundary detection encoding
- `NetworkTransmitter`: UDP transmission to modem

**Frame Processing Pipeline:**
1. Audio: PyAudio → OPUS → RTP → UDP → IP → COBS → OPV Frame
2. Text: UTF-8 → UDP → IP → COBS → OPV Frame (with fragmentation)
3. Control: ASCII → UDP → IP → COBS → OPV Frame
4. All frames: 134 bytes total (12-byte header + 122-byte payload)

**Audio Callback Architecture:**
- 40ms PyAudio callback drives all timing
- Voice transmission bypasses all queues (immediate)
- Other message types processed when voice queue empty
- PTT-aware buffering for seamless operation

### 10.3 Integration and Testing

**Interoperability Validation:**
- Frame format compliance testing
- Audio quality measurement (16 kbps OPUS)
- Priority behavior verification
- Network performance assessment

**Development Tools:**
- COBS encoder/decoder test suite
- Frame validation utilities
- Audio quality measurement tools
- Network simulation capabilities

**Future Extensions:**
- Additional SDR platform support (via Locutus variants)
- Alternative hardware implementations
- Performance optimization for different use cases
- Enhanced authentication mechanisms

## 11. Future Protocol Evolution

### 11.1 Planned Enhancements

**Audio Quality Improvements:**
- Higher bitrate options (32 kbps) for additional fidelity
- Adaptive bitrate (Opus VBR used instead of CBR). Based on voice characteristics such as lots of gaps between words and syllables, we can take advantage of the additional space for moving data more quickly through the system.
- Enhanced audio preprocessing options

**Protocol Extensions:**
- Version negotiation mechanisms
- Backward compatibility frameworks
- Advanced error correction algorithms
- Mesh networking capabilities

### 11.2 Application Domains

**Satellite Communications:**
- Native uplink protocol for amateur satellites
- Doppler shift compensation integration
- Orbital mechanics-aware scheduling

**Emergency Communications:**
- Priority messaging for disaster response
- Gateway integration with traditional modes
- Interoperability with served agency systems

**Experimental Applications:**
- Software-defined radio research platform
- Educational protocol development
- Amateur radio experimentation framework

---

## 12. Regulatory Compliance

### 12.1 Amateur Radio Regulations

**Technical Compliance:**
- Open protocol specification
- Station identification in every transmission
- Bandwidth appropriate for global amateur allocations
- Complete technical documentation publicly available

**International Compatibility:**
- ITU Region compliance
- IARU band plan compatibility
- National regulatory variation support

### 12.2 Spectrum Efficiency

**Bandwidth Optimization:**
- Efficient digital modulation (MSK)
- Superior spectral efficiency vs. analog modes
- Minimal adjacent channel interference

**Interference Mitigation:**
- Clean modulation characteristics
- Access control for harmful interference reduction
- Shared spectrum operation design

---

## Appendices

### Appendix A: Frame Format Examples

**Voice Frame (Interlocutor Implementation):**
```
OPV Header:   [12 bytes]
  Station ID: 0x123456789ABC (6 bytes)
  Token:      0xBBAADD (3 bytes)
  Reserved:   0x000000 (3 bytes)
Payload:      [122 bytes]
  COBS data:  IP(120) + RTP(12) + OPUS(80) encoded
Total:        134 bytes
```

**Text Frame Example:**
```
OPV Header:   [12 bytes]
  Station ID: W1ABC encoded in Base-40
  Token:      0xBBAADD
  Reserved:   0x000000
Payload:      [122 bytes]
  COBS data:  "Hello, world!" in UTF-8
Total:        134 bytes
```

### Appendix B: Complete Base-40 Encoding Table

| Value | Char | Value | Char | Value | Char | Value | Char |
|-------|------|-------|------|-------|------|-------|------|
| 0-9 | 0-9 | 10-35 | A-Z | 36 | / | 37 | - |
| 38 | (space) | 39 | (unused) | | | | |

**Encoding Example:**
`W1ABC` → W(32) + 1(1) + A(10) + B(11) + C(12)
Base-40 calculation: 32×40⁴ + 1×40³ + 10×40² + 11×40¹ + 12×40⁰

### Appendix C: Standard Control Messages

| Message | Format | Response | Purpose |
|---------|--------|----------|---------|
| PTT_START | `PTT_START` | None | Voice transmission begins |
| PTT_STOP | `PTT_STOP` | None | Voice transmission ends |
| AUTH_REQUEST | `AUTH_REQUEST` | `AUTH_RESPONSE` | Challenge for authentication |
| AUTH_RESPONSE | `AUTH_RESPONSE + cert` | Result notification | Authentication data |
| STATION_ID | `STATION_ID:<call>` | None | Station identification |
| KEEPALIVE | `KEEPALIVE:<time>` | `KEEPALIVE` | Connection maintenance |

### Appendix D: Implementation Compliance Checklist (!!! needs work)

**Mandatory Protocol Features:**
- [ ] 12-byte OPV header format
- [ ] Base-40 station identifier encoding
- [ ] Voice priority over all other traffic
- [ ] OPUS codec support (16 kbps minimum)
- [ ] UTF-8 text message support
- [ ] Basic control message handling

**Recommended Features:**
- [ ] RTP headers for voice streams
- [ ] COBS or equivalent frame boundary detection
- [ ] IP/UDP encapsulation
- [ ] Forward error correction
- [ ] Authentication framework support

**Optional Features:**
- [ ] Web-based configuration interface
- [ ] Multiple audio device support
- [ ] Network reconnection logic
- [ ] LoTW certificate integration

---

**Document Status:** This specification defines the Opulent Voice Protocol for high-fidelity amateur radio digital communications. It serves as both documentation of the existing ORI implementation and a specification enabling development of compatible systems.

**Contributing:** This is an open-source protocol developed by the amateur radio community. Contributions, feedback, and alternative implementations are encouraged through the Open Research Institute community channels.

**License:** This specification is released under open-source terms compatible with amateur radio experimental use and commercial implementation. We use CERN 2.0 license for hardware and GPL 2.0 license for software.

---

*Opulent Voice Protocol Specification - Open Research Institute - 2025*
