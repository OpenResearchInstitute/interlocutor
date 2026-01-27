# Opulent Voice Protocol Specification
## High-Fidelity Digital Voice and Data for Amateur Radio

**Version:** 1.1  
**Date:** January 2026  
**Status:** Implementation Draft  
**Organization:** Open Research Institute  

---

## Abstract

The Opulent Voice Protocol (OPV) is an open-source, high-fidelity digital voice and data communication protocol designed for amateur radio applications. Unlike existing low-bitrate digital voice modes, OPV prioritizes audio quality while providing seamless integration of voice, text chat, file transfer, and system control messages within a unified protocol framework.

OPV uses modern digital signal processing techniques including Opus (https://opus-codec.org/) audio compression, robust forward error correction, and priority-based message queuing to deliver professional-quality communications over amateur radio spectrum.

This document explains why the protocol was written, what is required, and gives examples from ORI's reference design to show how it can be implemented. 

---

## 1. Introduction

### 1.1 Protocol Goals

**Primary Objectives:**
- Deliver high-fidelity voice quality surpassing existing amateur digital voice modes. OPV has a minimum of 16 kbps Opus vs 3.2 kbps Codec 2 vs 3.4 kbps AMBE. See https://en.wikipedia.org/wiki/Codec_2 for a description of Codec 2 and https://en.wikipedia.org/wiki/Multi-Band_Excitation for a description of AMBE. 
- Seamlessly integrate multiple data types (voice, text, files, control) in a single protocol. No more switching to a clunky second packet mode for data. 
- Provide robust error correction and interference resilience using modern digital communications techniques. 
- Enable remote operation.
- Maintain compatibility with standard Internet protocols where beneficial.

**Design Philosophy:**
- **Voice Always Wins**: Voice transmission has absolute priority over all other data types.
- **Modern Codec Quality**: Leverage Opus codec for superior audio fidelity (16 kbps baseline).
- **Unified Protocol**: Single protocol handles all current and future communication types without mode switching through priority queues and User Datagram Protocol (UDP) port number assignments. 
- **Open Source**: Fully documented, patent-free implementation available to all. 
- **40ms Frame Timing**: Reference implementation is synchronized to 40ms audio callback timing from hardware.

### 1.2 Protocol Stack Overview

The Opulent Voice Protocol defines a complete digital voice and data communication system:

```
┌─────────────────────────────────────────┐
│           Application Layer             │
│     (Voice, Control, Text, Data)        │
├─────────────────────────────────────────┤
│         Opulent Voice Protocol          │
│   (COBS, Station ID, Authentication)    │
├─────────────────────────────────────────┤
│           Transport Layer               │
│         (COBS/IP/UDP/RTP Headers)       │
├─────────────────────────────────────────┤
│           Physical Layer                │
│        (Randomization, FEC,             |
|    Interleaving, Modulation, RF)        │
└─────────────────────────────────────────┘
```

**Protocol Responsibilities:**
- **COBS Framing**: Consistent Overhead Byte Stuffing (COBS) is used for data boundary detection. Opus voice packets are consistent in size and occupy exactly one OPV frame. However, text, control, and data payloads are variable length. Some can be quite long. COBS framing keeps track of the boundaries of all data types. It does not matter whether the data takes less than an OPV frame, exactly one OPV frame, or multiple OPV frames. COBS keeps track of boundaries so that the edges of our sent data are not lost during networking or transmission functions.  
- **Priority Management**: Voice-first queuing and transmission ensures that the operator hears voice without delay.
- **Encapsulation**: Integration with standard Internet protocols provides immense opportunity and flexibility for integration into existing radio and networking products and services. 
- **Authentication**: Station identification and access control comply with regulatory and policy situations ranging from uncontrolled access to highly restricted access. Authentication can be done on a per-frame basis, when triggered or requested, or not at all. 

**Implementation Freedom:**
The protocol can be implemented in various ways. It can be implemented as separate modules, integrated systems, or distributed across different hardware platforms. All implementations must use OPV headers, COBS encoding, IP headers, UDP headers, and RTP (for Opus payloads) for dataframe interoperability. For modem interoperability, randomization, the forward error correction, interleaving, and synchronization word must be included. For transmission interoperability, the preamble, dummy frames, and end of transmission signals must be included. The reference implementations of Interlocutor and Locutus are given throughout this document as an example. 

---

## 2. Frame Structure

### 2.1 Opulent Voice Protocol Frame Format

The Opulent Voice Protocol uses fixed-size and fixed-timing frames for all data types. It is 134 bytes long and 40 mS in duration.

```
┌─────────────────────────────────────────┐
│          OPV Header (12 bytes)          │
├─────────────────────────────────────────┤
│                 Payload                 |
|            (122-byte payload)           │
└─────────────────────────────────────────┘
```

**Frame Requirements:**
- **Header Size**: 12 bytes.
- **Timing**: Frames are 40 mS in duration.
- **Priority**: Voice frames have transmission priority over control frames, which have priority over text frames, which have priority over data frames.
- **Encapsulation**: Standard Internet protocols (COBS/IP/UDP/RTP) are used within the Opulent Voice payload.

**OPV Header Structure:**

```
├─────────────────────────────────────────────────────────────────┤
│                  Station Identifier (6 bytes)                   │
├─────────────────────────────────────────────────────────────────┤
│                    Token (3 bytes)                              │
├─────────────────────────────────────────────────────────────────┤
│                   Reserved (3 bytes)                            │
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
- **Authentication Ready:** The protocol supports cryptographic verification if needed. 
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
- **Codec:** Opus compression
- **Bitrate:** 16 kbps (higher bitrates anticipated in future versions)
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
│           Opus Data                       │
│        (40ms encoded audio)               │
└───────────────────────────────────────────┘
```

#### Implementation Example: Interlocutor

Uses RTP headers for streaming management with Opus payload. Structure: RTP Header (12 bytes) + Opus data (80 bytes) = 92 bytes total. RTP provides sequence numbering, timestamps at 48 kHz sample rate, and the SSRC field takes a hash of the station identification value. The complete voice payload is then encapsulated in UDP/IP headers before COBS encoding into the OPV frame.

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

**Payload Format:**
```
┌───────────────────────────────────────────┐
│           UTF-8 Encoded Text              │
│           (Variable Length)               │
└───────────────────────────────────────────┘
```

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
- **Addressing:** Support for point-to-point and and conference connection scenarios with an IP address and port in the IP header.
- **Port Management:** UDP Destination ports in the UDP header are used to indicate the data types. The Opulent Voice header does not have a data type. 
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
- Text: Fixed size queue, oldest messages dropped if implementation's queue size is exceeded.
- Data: Flow control, transmission pauses when buffer full

Authentication and authorization failures need immediate user attention, while dropped chat messages are more of a usability issue than a system integrity issue.

---

## 6. Physical Layer Interface

### 6.1 COBS Framing

Consistent Overhead Byte Stuffing (COBS) provides frame boundaries for our data. Data may be smaller than the fixed-length payload of a single frame, or it may be much larger, requiring many frames to transmit. We need to know where our data begins and ends, and COBS provides that knowledge. 

**COBS Benefits:**
- Guaranteed frame delimiters (0x00 bytes)
- Minimal overhead (typically <1%)
- Self-synchronizing frame recovery
- Compatible with byte-oriented interfaces

**Implementation:**
1. Apply COBS encoding to OPV frame
2. Append 0x00 delimiter
3. Transmit encoded frame + delimiter
4. Receiver uses 0x00 bytes to find frame boundaries

### 6.2 Supported Physical Layers

**Primary Target: MSK Modem**
- Minimum Shift Keying modulation
- Libre SDR implementation
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
   System to Station: Authentication challenge
   Station to System: Signed response + certificate
   System: Verify certificate chain and signature
4. Authentication result communicated to all participants
```

### 7.2 Authorization Framework

**Protocol Options:**
Opulent Voice authentication and authorization can provide support for different privilege levels. Critical traffic can bypass normal restrictions with an emergency override. Policy flexibility can be provided through configurable access control. Opulent Voice can maintain basic functionality when control systems go offline. 

**Access Control Concepts:**
- **Deny Lists:** Stations temporarily or permanently restricted
- **Allow Lists:** Stations with enhanced privileges
- **Tiered Access:** Different capabilities (text-only, voice, full bandwidth)
- **Emergency Access:** Unrestricted access for emergency communications

### 7.3 Security Considerations

**Threat Model:**
Unauthorized use overwhelming system capacity and jammers. Interference, identity spoofing, and denial of service. The recommended design principal is that security should not impede emergency communications. 

#### Implementation Example: Interlocutor

Supports ARRL Logbook of the World (LoTW) certificate authentication. Station callsign embedded in every frame header using Base-40 encoding. Implements challenge-response authentication using ASCII control messages ("AUTH_REQUEST", "AUTH_RESPONSE"). Default policy allows initial access without authentication (emergency consideration) with on-demand verification available.

---

## 8. Physical Layer Requirements

### 8.1 Frame Structure Overview

| Parameter | Value | Notes |
|-------|-----------|----------|
| Input Frame Size | 134 bytes (1072 bits) | From application layer |
| Encoded Frame Size | 268 bytes (2144 bits) | After FEC |
| Frame Period |40 ms | Synchronized to audio callback |
| Symbol Rate | 27,100 symbols/second | MSK modulation |

---

### 8.2 Synchronization Word

**Value:** in hex, `0x02B8DB` (24 bits), and in binary `0000 0010 1011 1000 1101 1011`

**Properties:**
- Peak-to-Sidelobe Ratio (PSLR): 8:1
- Balanced 0/1 count for DC neutrality
- Selected via exhaustive search for optimal autocorrelation
- Transmitted MSB-first

**Correlation:**
- Soft correlation used for detection
- Hunting threshold: ~70-80% of peak correlation
- Locked threshold: ~40-50% of peak (flywheel mode)

---

## 8.3 Processing Order (Transmit)

```
Input Data Frame (134 bytes)
        │
┌───────────────────┐
│   RANDOMIZE       │  XOR with CCSDS LFSR
└───────────────────┘
        │
┌───────────────────┐
│   FEC ENCODE      │  K=7 Convolutional (rate 1/2)
│ 134 to 268 bytes  │  
└───────────────────┘
        │
┌───────────────────┐
│   INTERLEAVE      │  67×32 bit matrix
│ (burst protect)   │  
└───────────────────┘
        │
┌───────────────────┐
│   SYNC WORD       │  Prepend 0x02B8DB
│   INSERTION       │  
└───────────────────┘
        │
   MSK Modulation
```

---

## 8.4 CCSDS LFSR Randomizer

**Purpose:** Randomize data before FEC to eliminate spectral spurs from repetitive patterns, and increase the number of transitions, which is important in minimum shift key modulation. 

**Standard:** CCSDS (Consultative Committee for Space Data Systems)

**Polynomial:** x^8 + x^7 + x^5 + x^3 + 1

**Seed:** 0xFF (all ones), reset at the start of each frame

**Period:** 255 bits

**Application:**

Randomization sequence is applied to the 134-byte input frame BEFORE convolutional encoding. Each byte is XORed with 8 consecutive LFSR output bits. The LFSR is clocked 8 times per byte (once per bit). On receive, the same operation is applied AFTER Viterbi decoding to recover original data.

**Linear Feedback Shift Register Operation:**
```
For each clock cycle:
  output_bit = state[7]  (MSB is output)
  feedback = state[7] xor state[6] xor state[4] xor state[2]
  state = (state << 1) | feedback
```

**Bit Ordering:** The LFSR outputs MSB-first. For byte-level XOR, generate 8 output bits (clocking the LFSR each time), then XOR with the data byte.

---

## 8.5 Convolutional Encoder (FEC)

**Standard:** NASA/CCSDS (also used in 802.11)

**Parameters:**
| Parameter | Value |
|-----------|-------|
| Constraint Length | K = 7 (64-state trellis) |
| Code Rate | 1/2 (each input bit results in 2 output bits) |
| Input Bits | 1072 (134 bytes) |
| Output Bits | 2144 (268 bytes) |
| Coding Gain | ~7 dB (soft Viterbi) at BER=10^-5 |

**Generator Polynomials (NASA/Voyager Standard):**

| Polynomial | Octal | Binary | Description |
|------------|-------|--------|-------------|
| G1 | 171 | 1111001 | First output |
| G2 | 133 | 1011011 | Second output |

This is the well-known NASA convolutional code used in the Voyager missions and many other space and terrestrial communication systems. It is also used in IEEE 802.11.

**Output Order:** For each input bit, output G1 then G2.

**Termination:** No tail bits are added. The trellis is left unterminated in the reference implementation. Decoders should handle the unterminated trellis appropriately (e.g., traceback from best final state rather than assuming all-zeros final state, or go ahead and terminate the trellis).

---

## 8.6 Interleaver

**Type:** Block interleaver (row-column) at bit level

**Dimensions:** 67 rows × 32 columns = 2144 bits

**Write Order:** Row-major (fill rows sequentially)

**Read Order:** Column-major (read columns sequentially)

**Effect:** Consecutive input bits are separated by 67 bit positions in the output. This spreads burst errors across multiple constraint lengths of the convolutional code, enabling the Viterbi decoder to correct them.

**Address Mapping:**
For input bit position `p` (0 to 2143):
```
row = p ÷ 32
col = p mod 32
output_position = (col × 67) + row
```

**Example:** Input bits 0, 1, 2, 3... appear at output positions 0, 67, 134, 201...

---

## 8.7 Complete Transmit Frame

The sync word is prepended to each encoded frame before modulation.

```
┌──────────────┬─────────────────────────────────────┐
│  Sync Word   │        Encoded Payload              │
│   24 bits    │         2144 bits                   │
│   0x02B8DB   │   (randomized + FEC + interleaved)  │
└──────────────┴─────────────────────────────────────┘
     3 bytes              268 bytes
              Total: 271 bytes per frame
```

**Transmission Order:** Sync word is transmitted first (MSB-first), followed by the encoded payload.

---

## 8.8 Receive Processing Order

```
   MSK Demodulation
        │
┌───────────────────┐
│   SYNC DETECT     │  Soft correlation on 0x02B8DB
│                   │  
└───────────────────┘
        │
┌───────────────────┐
│   DEINTERLEAVE    │  Reverse 67×32 matrix
│                   │  
└───────────────────┘
        │
┌───────────────────┐
│   FEC DECODE      │  Soft Viterbi K=7
│   268→134 bytes   │  
└───────────────────┘
        │
┌───────────────────┐
│   DERANDOMIZE     │  XOR with CCSDS LFSR
│   (Post-FEC)      │  
└───────────────────┘
        │
Output Data (134 bytes)
```

---

## 8.9 Soft Decision Decoding

Soft-decision Viterbi decoding is strongly recommended for improved performance. The use of soft decisions provides approximately 2-3 dB coding gain over hard-decision decoding.

**Implementation Note:** The degree of soft quantization (number of bits per soft sample) is an implementation choice. More resolution may improve performance slightly but is not required for interoperability. The HDL reference implementation uses 3-bit quantization.

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
- **Data:** Variable bandwidth (background priority, yield to voice, text, and control)
- **RF:** Complex baseband at 27,100 symbols/second carries 2 bits per symbol. The result is 54,200 bps. 1.5x the bit rate, typical for unfiltered MSK, results in an 81.3 kHz RF bandwidth.

**Latency Tolerance:**
- **Voice:** <200 ms for good user experience
- **Text:** <2 seconds for responsive chat
- **Control:** <500 ms for system responsiveness
- **Data:** No specific latency requirements

### 9.3 Error Resilience

**Protocol Requirements:**
- **Forward Error Correction:** Sufficient coding for target bit error rate performance.
- **Burst Error Protection:** Interleaving required for fast fading channel resilience.

#### Implementation Example: Interlocutor + Dialogus + Locutus

Achieves target audio quality using 16 kbps OPUS encoding with 40ms frames. Network overhead approximately 25% (134-byte frames carrying 80-byte OPUS payload). Convolutional forward error correction provides robust error correction. Soft decoding of forward error correction and soft decoding for synchronization word search and verification delivers preformance goals. 

---

## 10. Reference Implementation

### 10.1 ORI Implementation Architecture

The Open Research Institute provides a complete reference implementation split across two main components:

**Interlocutor (Human-Radio Interface):**
- **Platform:** Raspberry Pi, Linux, MacOS Python implementation
- **Function:** User interface, audio processing, frame creation
- **Features:** Web GUI, CLI interface, priority queuing, hardware interrupt frame timing
- **Integration:** Creates 134-byte OPV frames for transmission to modem

https://github.com/OpenResearchInstitute/interlocutor

**Dialogus (Processor Side of Modem):**
- **Platform:** ARM Zynq PS implementation
- **Function:** Frame delivery from network interface to modem, modem configuration
- **Features:** Modem interface, communications channel statistics
- **Integration:** Delivers 134-byte OPV frames to and from modem

https://github.com/OpenResearchInstitute/Dialogus

**Locutus (Modem Layer):**
- **Platform:** Libre SDR FPGA implementation
- **Function:** Physical layer processing and RF transmission
- **Features:** MSK modulation, randomization, FEC, interleaving, synchronization
- **Integration:** Processes OPV frames from Interlocutor, delivered through Dialogus

https://github.com/OpenResearchInstitute/pluto_msk

### 10.2 Interlocutor Implementation Details

**Frame Processing Pipeline:**
1. Audio: PyAudio to OPUS to RTP to UDP to IP to COBS to OPV Frame
2. Text: UTF-8 to UDP to IP to COBS to OPV Frame (with fragmentation)
3. Control: ASCII to UDP to IP to COBS to OPV Frame
4. Data: binary data to UDP to IP to COBS to OPV Frame
   
All frames: 134 bytes total (12-byte header + 122-byte payload)

**Audio Callback Architecture:**

40ms PyAudio callback drives all timing. Voice transmission bypasses all queues. Voice transmission is immediately sent. Other message types processed when voice queue is empty. PTT-aware buffering for seamless operation.

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
  COBS data:  IP() + RTP(12) + OPUS(80) encoded
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

### Appendix D: Implementation Compliance Checklist

**Mandatory Protocol Features:**
- [ ] 12-byte OPV header format
- [ ] Base-40 station identifier encoding
- [ ] Voice priority over control, then text, then data
- [ ] COBS frame boundary detection
- [ ] IP/UDP encapsulation
- [ ] Forward error correction as specified
- [ ] OPUS codec support (16 kbps minimum)
- [ ] RTP headers for audio support
- [ ] UTF-8 text message support

**Recommended Features:**
- [ ] Soft decoding of forward error correction
- [ ] Correlation of synchronization word
- [ ] Authentication framework support
- [ ] LoTW certificate integration
- [ ] Basic control message handling for push to talk

**Optional Features:**
- [ ] Web-based configuration interface
- [ ] Multiple audio device support
- [ ] Network reconnection logic

---

**Document Status:** This specification defines the Opulent Voice Protocol for high-fidelity amateur radio digital communications. It serves as both documentation of the existing ORI implementation and a specification enabling development of compatible systems.

**Contributing:** This is an open-source protocol developed by the amateur radio community. Contributions, feedback, and alternative implementations are encouraged through the Open Research Institute community channels.

**License:** This specification is released under open-source terms compatible with amateur radio experimental use and commercial implementation. We use CERN 2.0 license for hardware and GPL 2.0 license for software.

---

*Opulent Voice Protocol Specification - Open Research Institute - 2026*
