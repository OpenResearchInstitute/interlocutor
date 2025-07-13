#!/usr/bin/env python3
"""
Complete Radio Protocol Classes
Contains all protocol classes moved from interlocutor.py - unmodified and complete
"""

import struct
import time
import random
import socket
import logging
from typing import List, Tuple, Union, Dict
from enum import Enum





# debug configuration
class DebugConfig:
        """Centralized debug configuration"""
        VERBOSE = False
        QUIET = False

        @classmethod
        def set_mode(cls, verbose=False, quiet=False):
                cls.VERBOSE = verbose
                cls.QUIET = quiet
                
                # Set up logging based on mode
                if verbose:
                        logging.basicConfig(level=logging.DEBUG, format='🐛 %(message)s')
                elif quiet:
                        logging.basicConfig(level=logging.WARNING, format='⚠️  %(message)s')
                else:
                        logging.basicConfig(level=logging.INFO, format='ℹ️  %(message)s')
        
        @classmethod
        def debug_print(cls, message, force=False):
                """Print message only in verbose mode or if forced"""
                if cls.VERBOSE or force:
                        print(message)
        
        @classmethod
        def user_print(cls, message):
                """Print user-facing messages (always shown unless quiet)"""
                if not cls.QUIET:
                        print(message)

        @classmethod
        def system_print(cls, message):
                """Print important system messages (always shown)"""
                print(message)
















def encode_callsign(callsign: str) -> int:
	"""
	Encodes a callsign into a 6-byte binary format using base-40 encoding.

	The callsign is any combination of uppercase letters, digits,
	hyphens, slashes, and periods. Each character is encoded base-40.

	:param callsign: The callsign to encode.
	:return: A 6-byte binary representation of the callsign.
	"""
	encoded = 0

	for c in callsign[::-1]:
		encoded *= 40
		if "A" <= c <= "Z":
			encoded += ord(c) - ord("A") + 1
		elif "0" <= c <= "9":
			encoded += ord(c) - ord("0") + 27
		elif c == "-":
			encoded += 37
		elif c == "/":
			encoded += 38
		elif c == ".":
			encoded += 39
		else:
			raise ValueError(f"Invalid character '{c}' in callsign.")

	if encoded > 0xFFFFFFFFFFFF:
		raise ValueError("Encoded callsign exceeds maximum length of 6 bytes.")

	return encoded


def decode_callsign(encoded: int) -> str:
	"""
	Decodes a 6-byte binary callsign back to string format.
	
	:param encoded: The encoded callsign as an integer.
	:return: The decoded callsign string.
	"""
	callsign_map = {
		1: "A", 2: "B", 3: "C", 4: "D", 5: "E", 6: "F", 7: "G", 8: "H", 9: "I", 10: "J",
		11: "K", 12: "L", 13: "M", 14: "N", 15: "O", 16: "P", 17: "Q", 18: "R", 19: "S", 20: "T",
		21: "U", 22: "V", 23: "W", 24: "X", 25: "Y", 26: "Z", 27: "0", 28: "1", 29: "2", 30: "3",
		31: "4", 32: "5", 33: "6", 34: "7", 35: "8", 36: "9", 37: "-", 38: "/", 39: ".",
	}

	decoded: str = ""
	while encoded > 0:
		remainder = encoded % 40
		if remainder in callsign_map:
			decoded = callsign_map[remainder] + decoded
		else:
			raise ValueError(f"Invalid encoded value: {remainder}")
		encoded //= 40
	return decoded[::-1]  # Reverse to get the correct order


class MessageType(Enum):
	"""Message types with priority ordering"""
	VOICE = (1, "VOICE")
	CONTROL = (2, "CONTROL") 
	TEXT = (3, "TEXT")
	DATA = (4, "DATA")
	
	def __init__(self, priority, name):
		self.priority = priority
		self.message_name = name


class StationIdentifier:
	"""Domain model for flexible station identification using base-40 encoding"""
	
	def __init__(self, callsign):
		"""Initialize with a flexible callsign (no SSID in base-40 encoding)"""
		self.callsign = self._validate_callsign(callsign)
		self.encoded_value = encode_callsign(self.callsign)
	
	def _validate_callsign(self, callsign):
		"""Validate callsign for base-40 encoding"""
		if not callsign:
			raise ValueError("Callsign cannot be empty")
		
		callsign_upper = callsign.upper().strip()
		
		# Check for valid base-40 characters
		valid_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-/.")
		invalid_chars = set(callsign_upper) - valid_chars
		
		if invalid_chars:
			raise ValueError(f"Invalid characters in callsign: {', '.join(invalid_chars)}")
		
		# Test encoding to ensure it fits in 6 bytes
		try:
			encoded = encode_callsign(callsign_upper)
			if encoded > 0xFFFFFFFFFFFF:
				raise ValueError("Callsign too long for 6-byte encoding")
		except ValueError as e:
			raise ValueError(f"Callsign encoding failed: {e}")
		
		return callsign_upper
	
	def to_bytes(self):
		"""Convert station ID to 6-byte representation for protocol"""
		# Convert the encoded integer to 6 bytes (big-endian)
		return self.encoded_value.to_bytes(6, byteorder='big')
	
	def __str__(self):
		return self.callsign
	
	@classmethod
	def from_bytes(cls, station_bytes):
		"""Create StationIdentifier from 6-byte representation"""
		if len(station_bytes) != 6:
			raise ValueError("Station ID must be exactly 6 bytes")
		
		# Convert bytes to integer (big-endian)
		encoded_value = int.from_bytes(station_bytes, byteorder='big')
		
		# Decode the callsign
		try:
			callsign = decode_callsign(encoded_value)
			return cls(callsign)
		except ValueError as e:
			raise ValueError(f"Failed to decode station ID: {e}")
	
	@classmethod
	def from_encoded(cls, encoded_value):
		"""Create StationIdentifier from already encoded integer"""
		callsign = decode_callsign(encoded_value)
		instance = cls.__new__(cls)  # Create without calling __init__
		instance.callsign = callsign
		instance.encoded_value = encoded_value
		return instance


class COBSEncoder:
	"""
	COBS encoder for Opulent Voice Protocol

	Think of this as a Frame Boundary Manager - it ensures we can always
	find where one frame ends and the next begins, even with arbitrary data.

	MAX_BLOCK_SIZE is how far ahead the COBS encoder looks to find the next
	0x00 value. If it's larger than the max_payload_per_frame in the fragmenter
	then we have the least amount of extra overhead from smaller COBS fragments
	than the text and control message fragmenter is creating, in order to
	fit text and control messages into 40ms frames. 
	"""

	MAX_BLOCK_SIZE = 254

	@staticmethod
	def encode(data: bytes) -> bytes:
		"""Encode data using COBS algorithm"""
		if not data:
			return b'\x01\x00'

		encoded = bytearray()
		pos = 0

		while pos < len(data):
			# Find next zero byte (or end of data)
			zero_pos = data.find(0, pos)
			if zero_pos == -1:
				zero_pos = len(data)  # No zero found, use end of data

			block_len = zero_pos - pos

			# Handle blocks larger than MAX_BLOCK_SIZE
			while block_len >= COBSEncoder.MAX_BLOCK_SIZE:
				encoded.append(COBSEncoder.MAX_BLOCK_SIZE + 1)  # 255
				encoded.extend(data[pos:pos + COBSEncoder.MAX_BLOCK_SIZE])
				pos += COBSEncoder.MAX_BLOCK_SIZE
				block_len = zero_pos - pos

			# Handle the remaining block (< MAX_BLOCK_SIZE)
			if block_len > 0:
				encoded.append(block_len + 1)
				encoded.extend(data[pos:zero_pos])
			else:
				encoded.append(1)  # Zero-length block

			pos = zero_pos + 1

			# If we've reached the end, break
			if zero_pos >= len(data):
				break

		encoded.append(0)  # COBS terminating delimiter
		return bytes(encoded)

	@staticmethod  
	def decode(encoded_data: bytes) -> bytes:
		"""Decode COBS-encoded data"""
		if not encoded_data or encoded_data[-1] != 0:
			raise ValueError("COBS data must end with zero byte")

		data = encoded_data[:-1]
		decoded = bytearray()
		pos = 0

		while pos < len(data):
			if pos >= len(data):
				break

			code = data[pos]
			pos += 1

			if code == 0:
				raise ValueError("Unexpected zero byte in COBS data")

			block_len = code - 1
            
			if pos + block_len > len(data):
				raise ValueError("COBS block extends beyond data")
                
			decoded.extend(data[pos:pos + block_len])
			pos += block_len
            
			if code <= COBSEncoder.MAX_BLOCK_SIZE and pos < len(data):
				decoded.append(0)
        
		return bytes(decoded)


class COBSFrameBoundaryManager:
	"""
	Domain model for managing frame boundaries in Opulent Voice Protocol
	"""

	def __init__(self):
		self.stats = {
			'frames_encoded': 0,
			'frames_decoded': 0, 
			'encoding_errors': 0,
			'decoding_errors': 0,
			'total_overhead_bytes': 0
		}

	def encode_frame(self, ip_frame_data: bytes) -> bytes:
		"""Encode IP frame with COBS for boundary management"""
		try:
			# Apply COBS encoding
			encoded_frame = COBSEncoder.encode(ip_frame_data)

			# Update statistics
			self.stats['frames_encoded'] += 1
			overhead = len(encoded_frame) - len(ip_frame_data)
			self.stats['total_overhead_bytes'] += overhead

			return encoded_frame

		except Exception as e:
			self.stats['encoding_errors'] += 1
			raise ValueError(f"COBS encoding failed: {e}")

	def decode_frame(self, encoded_data: bytes) -> Tuple[bytes, int]:
		"""Decode COBS frame and return original IP data"""
		try:
			delimiter_pos = encoded_data.find(0)
			if delimiter_pos != -1:
				raise ValueError("Frame delimiter found within COBS-encoded frame")

			encoded_data.extend(b'\x00')  # Include the delimiter for decoding
			decoded_frame = COBSEncoder.decode(encoded_data)

			self.stats['frames_decoded'] += 1
			return decoded_frame, len(encoded_data)

		except Exception as e:
			self.stats['decoding_errors'] += 1
			raise ValueError(f"COBS decoding failed: {e}")

	def get_stats(self) -> dict:
		"""Get encoding statistics"""
		stats = self.stats.copy()
		if stats['frames_encoded'] > 0:
			stats['avg_overhead_per_frame'] = stats['total_overhead_bytes'] / stats['frames_encoded']
		else:
			stats['avg_overhead_per_frame'] = 0
		return stats


class SimpleFrameSplitter:
	"""
	Simple COBS frame splitter - no fragmentation headers, just splits COBS data
	Maintains 138-byte Opulent Voice frames for specification compliance
	"""
	
	def __init__(self, opulent_voice_frame_size: int = 133):
		"""
		opulent_voice_frame_size: Total size of each Opulent Voice frame (including 12-byte header)
		"""
		self.opulent_voice_frame_size = opulent_voice_frame_size
		self.payload_size = opulent_voice_frame_size - 12  # 121 bytes available for COBS data
		self.stats = {
			'single_frame_messages': 0,
			'multi_frame_messages': 0,
			'total_frames_created': 0
		}

	def split_cobs_frame(self, cobs_encoded_data: bytes) -> List[bytes]:
		"""
		Split a COBS-encoded frame into 121-byte chunks (no fragmentation headers)
		
		cobs_encoded_data: Complete COBS frame (with delimiter)
		Returns: List of 121-byte payloads (without Opulent Voice headers)
		"""
		if len(cobs_encoded_data) <= self.payload_size:
			# Single frame - pad to exactly 121 bytes for specification compliance
			padded_data = cobs_encoded_data + b'\x00' * (self.payload_size - len(cobs_encoded_data))
			self.stats['single_frame_messages'] += 1
			self.stats['total_frames_created'] += 1
			return [padded_data]
		
		# Multi-frame - split into 121-byte chunks
		self.stats['multi_frame_messages'] += 1
		frames = []
		
		for i in range(0, len(cobs_encoded_data), self.payload_size):
			chunk = cobs_encoded_data[i:i + self.payload_size]
			
			# Pad last chunk to exactly 121 bytes if needed
			if len(chunk) < self.payload_size:
				chunk = chunk + b'\x00' * (self.payload_size - len(chunk))
			
			frames.append(chunk)
			self.stats['total_frames_created'] += 1
		
		print(f"📦 Split {len(cobs_encoded_data)}B COBS frame into {len(frames)} frames of 126B each")
		return frames

	def get_stats(self):
		"""Get frame splitting statistics"""
		return self.stats.copy()


class SimpleFrameReassembler:
	"""
	Simple frame reassembler - concatenates 121-byte payloads until COBS delimiter found
	No fragmentation headers to worry about
	"""
	
	def __init__(self):
		self.buffer = bytearray()
		self.stats = {
			'frames_received': 0,
			'messages_completed': 0,
			'bytes_buffered': 0
		}
	
	def add_frame_payload(self, frame_payload: bytes) -> List[bytes]:
		"""
		Add a 121-byte frame payload and return complete COBS frame if ready
		
		frame_payload: 121-byte payload from Opulent Voice frame (header removed)
		Returns: List of completed COBS-encoded frames
		"""
		# We will build a list of zero or more reassembled COBS frames
		reassembled_frames = []

		if len(frame_payload) != 121:
			print(f"⚠ Expected 121-byte payload, got {len(frame_payload)}B")
			return reassembled_frames
				
		# Add payload to buffer
		self.buffer.extend(frame_payload)
		self.stats['frames_received'] += 1		

		while len(self.buffer) > 0:
			# Look for COBS delimiter (0x00)
			delimiter_pos = self.buffer.find(0)
			if delimiter_pos != -1:
				if delimiter_pos == 0:
					# Delimiter at start, skip it
					self.buffer = self.buffer[1:]
					continue
				# Found a non-empty complete COBS frame, add it to the list
				reassembled_frames.append(self.buffer[:delimiter_pos])	# don't include the delimiter
				self.stats['messages_completed'] += 1
				# Remove processed data from buffer
				self.buffer = self.buffer[delimiter_pos + 1:]	# don't include the delimiter

		self.stats['bytes_buffered'] = len(self.buffer)
		
		if len(reassembled_frames) == 0:
			print("📝 No complete COBS frames yet, buffering payload")
		else:
			print(f"✅ Reassembled {len(reassembled_frames)} complete COBS frames")
			for frame in reassembled_frames:
				print(f"✅ Reassembled complete COBS frame: {len(frame)}B")
		
		return reassembled_frames
	
	def get_stats(self):
		"""Get reassembly statistics"""
		return self.stats.copy()


class RTPHeader:
	"""
	RTP Header implmentation for Opulent Voice Protocol
	"""
	VERSION = 2
	PT_OPUS = 96 # in the range 96 to 127
	HEADER_SIZE = 12

	# Opulent Voice Protocol Constants
	OPULENT_VOICE_FRAME_DURATION_MS = 40
	OPULENT_VOICE_SAMPLE_RATE = 48000
	OPULENT_VOICE_OPUS_PAYLOAD_SIZE = 80
	OPULENT_VOICE_SAMPLES_PER_FRAME = 1920

	def __init__(self, payload_type=PT_OPUS, ssrc=None): # Synchronization Source (SSRC)
							     # Identifies source of a stream of RTP packets
							     # Value is randomly chosen and unique within session.
							     # Contributing source (CSRC) is a source of a stream of
							     # RTP packets that has contributed to the combined
							     # stream produced by an RTP mixer
							     # Marker bit is set at the beginning of a "talkspurt"
		self.version = self.VERSION
		self.padding = 0
		self.extension = 0
		self.csrc_count = 0
		self.marker = 0
		self.payload_type = payload_type
		self.sequence_number = random.randint(0, 65535)
		self.ssrc = ssrc or self._generate_ssrc()
		self.timestamp_base = int(time.time() * self.OPULENT_VOICE_SAMPLE_RATE) % (2**32)
		self.samples_per_frame = self.OPULENT_VOICE_SAMPLES_PER_FRAME

	def _generate_ssrc(self):
		return random.randint(1, 2**32 - 1)

	def create_header(self, is_first_packet=False, custom_timestamp=None):
		marker = 1 if is_first_packet else 0

		if custom_timestamp is not None:
			timestamp = custom_timestamp
		else:
			timestamp = (self.timestamp_base + (self.sequence_number * self.samples_per_frame)) % (2**32)
		
		first_word = (
			(self.version << 30) |
			(self.padding << 29) |
			(self.extension << 28) |
			(self.csrc_count << 24) |
			(marker << 23) |
			(self.payload_type << 16) |
			self.sequence_number
			)
		
		header = struct.pack('!I I I',
			first_word,
			timestamp,
			self.ssrc)

		self.sequence_number = (self.sequence_number + 1) % 65535
		return header

	def parse_header(self, header_bytes):
		if len(header_bytes) < self.HEADER_SIZE:
			raise ValueError(f"RTP Header too short: {len(header_bytes)} bytes")

		first_word, timestamp, ssrc = struct.unpack('!I I I', header_bytes[:12])

		version = (first_word >> 30) & 0x3
		padding = (first_word >> 29) & 0x1
		extension = (first_word >> 28) & 0x1
		csrc_count = (first_word >>24) & 0xF
		marker = (first_word >> 23) & 0x1
		payload_type = (first_word >> 16) & 0x7F
		sequence_number = first_word & 0xFFFF

		return {
			'version': version,
			'padding': padding,
			'extension': extension,
			'csrc_count': csrc_count,
			'marker': marker,
			'payload_type': payload_type,
			'sequence_number': sequence_number,
			'timestamp': timestamp,
			'ssrc': ssrc,
			'header_size': self.HEADER_SIZE + (csrc_count * 4)
			}

	def get_stats(self):
		return {
			'ssrc': self.ssrc,
			'current_sequence': self.sequence_number,
			'payload_type': self.payload_type,
			'samples_per_frame': self.samples_per_frame
			}


class RTPAudioFrameBuilder:
	"""
	Combines RTP headers with Opus payloads for Opulent Voice transmission.
	"""
	def __init__(self, station_identifier, payload_type=RTPHeader.PT_OPUS):
		self.station_id = station_identifier

		ssrc = hash(str(station_identifier)) % (2**32)
		if ssrc == 0:
			ssrc = 1

		self.rtp_header = RTPHeader(payload_type = payload_type, ssrc = ssrc)
		self.is_talk_spurt_start = True
		self.expected_opus_size = RTPHeader.OPULENT_VOICE_OPUS_PAYLOAD_SIZE

	def create_rtp_audio_frame(self, opus_packet, is_start_of_transmission = False):
		# Validate that we have 80 bytes
		if len(opus_packet) != self.expected_opus_size:
			raise ValueError(
				f"Opulent Voice Protocol violation: OPUS packet must be "
				f"{self.expected_opus_size} bytes, but we got {len(opus_packet)} bytes."
				)
		marker = is_start_of_transmission or self.is_talk_spurt_start
		self.is_talk_spurt_start = False

		rtp_header = self.rtp_header.create_header(is_first_packet = marker)
		rtp_frame = rtp_header + opus_packet

		expected_total = RTPHeader.HEADER_SIZE + self.expected_opus_size
		if len(rtp_frame) != expected_total:
			raise RuntimeError(
				f"RTP frame size error: expected {expected_total} bytes, "
				f"created {len(rtp_frame)} bytes"
				)
		return rtp_frame

	def validate_opus_packet(self, opus_packet):
		return len(opus_packet) == self.expected_opus_size

	def start_new_talk_spurt(self):
		self.is_talk_spurt_start = True

	def end_talk_spurt(self):
		pass

	def get_rtp_stats(self):
		stats = self.rtp_header.get_stats()
		stats.update({
			'frame_duration_ms': RTPHeader.OPULENT_VOICE_FRAME_DURATION_MS,
			'opus_payload_size': self.expected_opus_size,
			'expected_frame_rate': 1000 / RTPHeader.OPULENT_VOICE_FRAME_DURATION_MS,
			'total_rtp_frame_size': RTPHeader.HEADER_SIZE + self.expected_opus_size
		})
		return stats


class UDPHeader:
	"""
	UDP Header implementation following RFC 768

	UDP Header Format (8 bytes):
	0      7 8     15 16    23 24    31
	+--------+--------+--------+--------+
	|     Source      |   Destination   |
	|      Port       |      Port       |
	+--------+--------+--------+--------+
	|                 |                 |
	|     Length      |    Checksum     |
	+--------+--------+--------+--------+
	"""
	
	HEADER_SIZE = 8

	def __init__(self, source_port=None, dest_port=57372):
		"""
		Initialize UDP header builder

		source_port: Source port (auto-assigned if None)
		dest_port: Destination port
		"""
		self.source_port = source_port or self._get_ephemeral_port()
		self.dest_port = dest_port

	def _get_ephemeral_port(self):
		"""Get an ephemeral port number (49152-65535 range)"""
		return random.randint(49152, 65535)

	def create_header(self, payload_data, calculate_checksum=True, source_ip=None, dest_ip=None):
		"""
		Create UDP header for given payload

		payload_data: The data to be wrapped in UDP
		calculate_checksum: Whether to calculate checksum (can be disabled for speed)
		source_ip: Source IP address
		dest_ip: Destination IP address
		return: 8-byte UDP header
		"""

		# UDP length includes header + payload
		udp_length = self.HEADER_SIZE + len(payload_data)

		if udp_length > 65535:
			raise ValueError(f"UDP packet way too big: {udp_length} bytes")

		# Calculate checksum if requested
		if calculate_checksum and source_ip and dest_ip:
			checksum = self._calculate_checksum(payload_data, udp_length, source_ip, dest_ip)
		elif calculate_checksum:
			checksum = self._simple_checksum(payload_data, udp_length) #fallback
		else:
			checksum = 0  # Checksum optional in IPv4

		try:
			# Pack UDP header
			header = struct.pack('!HHHH',
				self.source_port,
				self.dest_port,
				udp_length,
				checksum)
			return header

		except:
			print(f"✗ Struct error when trying to pack UDP Header.")
			return None

	def _calculate_checksum(self, payload_data, udp_length, source_ip, dest_ip):
		"""
		Calculate UDP checksum with proper pseudo-header (RFC 768)

		payload_data: UDP payload
		udp_length: UDP header + payload length
		source_ip: Source IP address (string format)
		dest_ip: Destination IP address (string format)
		return: 16-bit checksum
		"""
		# Convert IP addresses to network byte order integers using socket.inet_aton
		try:
			source_addr = struct.unpack("!I", socket.inet_aton(source_ip))[0]
			dest_addr = struct.unpack("!I", socket.inet_aton(dest_ip))[0]
		except socket.error:
			# Fallback to simple checksum if IP conversion fails
			return self._simple_checksum(payload_data, udp_length)

		# Create proper 12-byte UDP pseudo-header per RFC 768
		# Format: Source IP (4) + Dest IP (4) + Zero (1) + Protocol (1) + UDP Length (2)
		pseudo_header = struct.pack('!IIBBH',
			source_addr,	# Source IP (4 bytes)
			dest_addr,	# Dest IP (4 bytes)
			0,		# Zero byte (1 byte)
			17,		# Protocol = UDP (1 byte) 
			udp_length	# UDP Length (2 bytes)
		)

		# Create UDP header with zero checksum for calculation
		udp_header = struct.pack('!HHHH',
			self.source_port,
			self.dest_port,
			udp_length,
			0  # Zero checksum for calculation
		)

		# Combine pseudo-header + UDP header + payload
		checksum_data = pseudo_header + udp_header + payload_data

		# Pad to even length if necessary
		if len(checksum_data) % 2:
			checksum_data += b'\x00'

		# Calculate 16-bit ones complement checksum
		checksum = 0
		for i in range(0, len(checksum_data), 2):
			word = (checksum_data[i] << 8) + checksum_data[i + 1]
			checksum += word
			
			# Handle carries immediately to prevent overflow
			while checksum > 0xFFFF:
				checksum = (checksum & 0xFFFF) + (checksum >> 16)

		# Take one's complement
		checksum = (~checksum) & 0xFFFF

		# UDP checksum of 0 is invalid, use 0xFFFF instead
		if checksum == 0:
			checksum = 0xFFFF

		return checksum

	def _simple_checksum(self, payload_data, udp_length):
		"""
		Simplified checksum when no IP addresses are available
		Note: This is not RFC-compliant but better than nothing
		"""
		# Create simplified pseudo UDP packet for checksum calculation
		pseudo_header = struct.pack('!HHHH',
			self.source_port,
			self.dest_port,
			udp_length,
			0  # Checksum field zero for calculation
		)

		# Combine header and payload for checksum
		checksum_data = pseudo_header + payload_data

		# Pad to even length
		if len(checksum_data) % 2:
			checksum_data += b'\x00'

		# Calculate 16-bit checksum
		checksum = 0
		for i in range(0, len(checksum_data), 2):
			word = (checksum_data[i] << 8) + checksum_data[i + 1]
			checksum += word
			while checksum > 0xFFFF:
				checksum = (checksum & 0xFFFF) + (checksum >> 16)

		# Take one's complement
		checksum = (~checksum) & 0xFFFF

		# UDP checksum of 0 is invalid, use 0xFFFF instead
		if checksum == 0:
			checksum = 0xFFFF

		return checksum

	def parse_header(self, header_bytes):
		"""
		Parse UDP header from bytes

		header_bytes: 8-byte UDP header
		return: Dictionary with header fields
		"""
		if len(header_bytes) < self.HEADER_SIZE:
			raise ValueError(f"UDP header too short: {len(header_bytes)} bytes")

		source_port, dest_port, length, checksum = struct.unpack('!HHHH', header_bytes)

		return {
			'source_port': source_port,
			'dest_port': dest_port,
			'length': length,
			'checksum': checksum,
			'payload_length': length - self.HEADER_SIZE
		}

	def validate_packet(self, udp_header_bytes, payload_data):
		"""
		Validate UDP packet integrity

		udp_header_bytes: 8-byte UDP header
		payload_data: UDP payload
		return: True if valid, False otherwise
		"""
		try:
			header_info = self.parse_header(udp_header_bytes)

			# Check length consistency
			expected_payload_length = header_info['payload_length']
			if len(payload_data) != expected_payload_length:
				return False

			# Could add checksum validation here if needed
			return True

		except (struct.error, ValueError):
			return False


class UDPAudioFrameBuilder:
	"""
	Creates UDP frames for RTP audio data (Voice)
	Frame structure: [UDP Header][RTP Header][OPUS Payload]
	"""
	def __init__(self, source_port=None, dest_port=57373):
		"""
		Initialize UDP frame builder for audio (RTP) data
		source_port: Source port for UDP
		dest_port: Destination port for UDP
		"""
		self.udp_header = UDPHeader(source_port, dest_port)

	def create_udp_audio_frame(self, rtp_frame_data, source_ip=None, dest_ip=None):
		"""
		Create UDP frame containing RTP audio data

		rtp_frame_data: Complete RTP frame (RTP header + OPUS payload)
		return: UDP header + RTP frame
		"""
		# Validate RTP frame size (should be 12 + 80 = 92 bytes for Opulent Voice)
		expected_rtp_size = 12 + 80  # RTP header + OPUS payload
		if len(rtp_frame_data) != expected_rtp_size:
			raise ValueError(
				f"RTP frame size error: expected {expected_rtp_size} bytes, "
				f"got {len(rtp_frame_data)} bytes"
			)

		# Create UDP header for this RTP frame
		udp_header = self.udp_header.create_header(
			rtp_frame_data,
			calculate_checksum = True,
			source_ip = source_ip,
			dest_ip = dest_ip
		)

		# Combine UDP header + RTP frame
		udp_frame = udp_header + rtp_frame_data

		# Validate total size
		expected_total = UDPHeader.HEADER_SIZE + expected_rtp_size  # 8 + 92 = 100 bytes
		if len(udp_frame) != expected_total:
			raise RuntimeError(
				f"UDP audio frame size error: expected {expected_total} bytes, "
				f"created {len(udp_frame)} bytes"
			)

		return udp_frame

	def get_udp_stats(self):
		"""Get UDP frame statistics"""
		return {
			'source_port': self.udp_header.source_port,
			'dest_port': self.udp_header.dest_port,
			'header_size': UDPHeader.HEADER_SIZE,
			'expected_audio_frame_size': UDPHeader.HEADER_SIZE + 12 + 80  # UDP + RTP + OPUS
		}


class UDPTextFrameBuilder:
	"""
	Creates UDP frames for keyboard chat data (No RTP)
	Frame structure: [UDP Header][Text Payload]
	"""

	def __init__(self, source_port=None, dest_port=57374):
		"""
		Initialize UDP frame builder for text data

		source_port: Source port for UDP
		dest_port: Destination port for UDP
		"""
		self.udp_header = UDPHeader(source_port, dest_port)

	def create_udp_text_frame(self, text_data, source_ip=None, dest_ip=None):
		"""
		Create UDP frame containing text data

		text_data: Text payload (bytes)
		return: UDP header + text payload
		"""
		if isinstance(text_data, str):
			text_data = text_data.encode('utf-8')

		# Create UDP header for this text data
		udp_header = self.udp_header.create_header(
			text_data,
			calculate_checksum = True,
			source_ip = source_ip,
			dest_ip = dest_ip
		)

		# Combine UDP header + text data
		udp_frame = udp_header + text_data

		return udp_frame

	def get_udp_stats(self):
		"""Get UDP frame statistics"""
		return {
			'source_port': self.udp_header.source_port,
			'dest_port': self.udp_header.dest_port,
			'header_size': UDPHeader.HEADER_SIZE
		}


class UDPControlFrameBuilder:
	"""
	Creates UDP frames for control data (No RTP)
	Frame structure: [UDP Header][Control Payload]
	"""

	def __init__(self, source_port=None, dest_port=57375):
		"""
		Initialize UDP frame builder for control data

		source_port: Source port for UDP
		dest_port: Destination port for UDP
		"""
		self.udp_header = UDPHeader(source_port, dest_port)

	def create_udp_control_frame(self, control_data, source_ip=None, dest_ip=None):
		"""
		Create UDP frame containing control data

		control_data: Control payload (bytes)
		return: UDP header + control payload
		"""
		if isinstance(control_data, str):
			control_data = control_data.encode('utf-8')

		# Create UDP header for this control data
		udp_header = self.udp_header.create_header(
			control_data,
			calculate_checksum = True,
			source_ip = source_ip,
			dest_ip = dest_ip
		)

		# Combine UDP header + control data
		udp_frame = udp_header + control_data

		return udp_frame

	def get_udp_stats(self):
		"""Get UDP frame statistics"""
		return {
			'source_port': self.udp_header.source_port,
			'dest_port': self.udp_header.dest_port,
			'header_size': UDPHeader.HEADER_SIZE
		}


class IPHeader:
	"""
	IPv4 Header implementation following RFC 791
	Diagram from RFC 791
	IPv4 Header Format (20 bytes minimum):
	 0                   1                   2                   3
	 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
	+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
	|Version|  IHL  |Type of Service|          Total Length         |
	+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
	|         Identification        |Flags|      Fragment Offset    |
	+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
	|  Time to Live |    Protocol   |         Header Checksum       |
	+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
	|                       Source Address                          |
	+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
	|                    Destination Address                        |
	+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
	"""

	HEADER_SIZE = 20  # Standard IPv4 header without options
	VERSION = 4       # IPv4
	PROTOCOL_UDP = 17 # UDP protocol number. TCP is 6.

	def __init__(self, source_ip=None, dest_ip="192.168.1.100"):
		"""
		Initialize IP header builder

		source_ip: Source IP address (auto-detected if None)
		dest_ip: Destination IP address
		"""
		self.version = self.VERSION
		self.ihl = 5  # Internet Header Length (5 * 4 = 20 bytes)
		self.tos = 0  # Type of Service (can be used for QoS)
		self.identification = self._generate_packet_id()
		self.flags = 2  # Don't Fragment (DF) bit set
		self.fragment_offset = 0
		self.ttl = 64  # Time to Live (standard value)
		self.protocol = self.PROTOCOL_UDP

		# IP addresses
		self.source_ip = source_ip or self._get_local_ip()
		self.dest_ip = dest_ip

		# Convert IP addresses to 32-bit integers, from RFC 791
		self.source_addr = self._ip_to_int(self.source_ip)
		self.dest_addr = self._ip_to_int(self.dest_ip)

	def _generate_packet_id(self):
		"""Generate a packet identification number"""
		return random.randint(1, 65535)

	def _get_local_ip(self):
		"""Auto-detect local IP address"""
		try:
			# Connect to our target address to determine our IP address
			with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
				s.connect((self.dest_ip, 80))
				return s.getsockname()[0]
		except:
			return "127.0.0.1"  # Fallback to localhost if all else fails

	def _ip_to_int(self, ip_str):
		"""Convert IP address string to 32-bit integer"""
		parts = [int(x) for x in ip_str.split('.')]
		return (parts[0] << 24) + (parts[1] << 16) + (parts[2] << 8) + parts[3]

	def _int_to_ip(self, ip_int):
		"""Convert 32-bit integer to IP address string"""
		return f"{(ip_int >> 24) & 0xFF}.{(ip_int >> 16) & 0xFF}.{(ip_int >> 8) & 0xFF}.{ip_int & 0xFF}"

	def create_header(self, payload_data):
		"""
		Create IP header for given payload

		payload_data: The UDP data to be wrapped in IP
 		return: 20-byte IP header
		"""
		# Calculate total length (IP header + payload)
		total_length = self.HEADER_SIZE + len(payload_data)

		if total_length > 65535:
			raise ValueError(f"IP packet way too large: {total_length} bytes")

		# Increment packet ID for each packet
		self.identification = (self.identification + 1) % 65536

		# Create header without checksum first, 
		# then use to calculate checksum, then create
		# final checksum. 
		version_ihl = (self.version << 4) | self.ihl
		flags_fragment = (self.flags << 13) | self.fragment_offset

		header_without_checksum = struct.pack('!BBHHHBBH4s4s',
			version_ihl,
			self.tos,
			total_length,
			self.identification,
			flags_fragment,
			self.ttl,
			self.protocol,
			0,  # Checksum placeholder
			self.source_addr.to_bytes(4, 'big'),
			self.dest_addr.to_bytes(4, 'big')
		)

		# Calculate header checksum
		checksum = self._calculate_checksum(header_without_checksum)

		# Create final header with checksum
		header = struct.pack('!BBHHHBBH4s4s',
			version_ihl,
			self.tos,
			total_length,
			self.identification,
			flags_fragment,
			self.ttl,
			self.protocol,
			checksum,
			self.source_addr.to_bytes(4, 'big'),
			self.dest_addr.to_bytes(4, 'big')
		)

		return header

	def _calculate_checksum(self, header_data):
		"""Calculate IP header checksum"""
		# Ensure even length
		if len(header_data) % 2:
			header_data += b'\x00'

		# Sum all 16-bit words
		checksum = 0
		for i in range(0, len(header_data), 2):
			word = (header_data[i] << 8) + header_data[i + 1]
			checksum += word
			checksum = (checksum & 0xFFFF) + (checksum >> 16)

		# One's complement
		return (~checksum) & 0xFFFF

	def parse_header(self, header_bytes):
		"""
		Parse IP header from bytes

 		header_bytes: 20-byte IP header
 		return: Dictionary with header fields
		"""
		if len(header_bytes) < self.HEADER_SIZE:
			raise ValueError(f"IP header too short: {len(header_bytes)} bytes")

		# Unpack the header
		unpacked = struct.unpack('!BBHHHBBH4s4s', header_bytes)

		version_ihl = unpacked[0]
		version = (version_ihl >> 4) & 0xF
		ihl = version_ihl & 0xF

		flags_fragment = unpacked[4]
		flags = (flags_fragment >> 13) & 0x7
		fragment_offset = flags_fragment & 0x1FFF

		source_addr = struct.unpack('!I', unpacked[8])[0]
		dest_addr = struct.unpack('!I', unpacked[9])[0]

		return {
			'version': version,
			'ihl': ihl,
			'tos': unpacked[1],
			'total_length': unpacked[2],
			'identification': unpacked[3],
			'flags': flags,
			'fragment_offset': fragment_offset,
			'ttl': unpacked[5],
			'protocol': unpacked[6],
			'checksum': unpacked[7],
			'source_ip': self._int_to_ip(source_addr),
			'dest_ip': self._int_to_ip(dest_addr),
			'header_size': ihl * 4,
			'payload_length': unpacked[2] - (ihl * 4)
		}

	def validate_packet(self, ip_header_bytes, payload_data):
		"""
		Validate IP packet integrity

	        ip_header_bytes: 20-byte IP header
	        payload_data: IP payload
	        return: True if valid, False otherwise
		"""
		try:
			header_info = self.parse_header(ip_header_bytes)

			# Check version
			if header_info['version'] != 4:
				return False

			# Check length consistency
			expected_payload_length = header_info['payload_length']
			if len(payload_data) != expected_payload_length:
				return False

			# Could add checksum validation here
			return True

		except (struct.error, ValueError):
			return False

	def set_tos_for_voice(self):
		"""Set Type of Service for voice traffic (low delay, high precedence)"""
		self.tos = 0xB8  # Precedence: 5 (Critical), Delay: Low, Throughput: Normal, Reliability: Normal

	def set_tos_for_data(self):
		"""Set Type of Service for data traffic (high throughput)"""
		self.tos = 0x08  # Precedence: 1 (Priority), Delay: Normal, Throughput: High, Reliability: Normal


class IPAudioFrameBuilder:
	"""
	Create IP frames for UDP+RTP audio data
	Frame structure: [IP Header][UDP Header][RTP Header][Opus Payload]
	"""
	def __init__(self, source_ip=None, dest_ip="192.168.1.100"):
		"""Initialize IP frame builder for our audio data

		source_ip: Source IP address
		dest_ip: Destination IP address
		"""
		self.ip_header = IPHeader(source_ip, dest_ip)
		# set our ToS for voice traffic
		self.ip_header.set_tos_for_voice

	def create_ip_audio_frame(self, udp_frame_data):
		"""
		Create IP frame containing UDP+RTP audio data

		udp_frame_data: Complete UDP frame (UDP header + RTP frame)
		return: IP Header + UDP frame
		"""

		# Validate UDP frame size (should be 8 + 92 = 100 bytes for Opulent Voice)
		expected_udp_size = 8 + 12 + 80 # UDP + RTP + Opus
		if len(udp_frame_data) != expected_udp_size:
			raise ValueError(
				f"UDP frame size error: expected {expected_udp_size} bytes, "
				f"got {len(udp_frame_data)} bytes"
			)

		# create IP header for this UDP frame
		ip_header = self.ip_header.create_header(udp_frame_data)

		# combine IP header + UDP frame
		ip_frame = ip_header + udp_frame_data

		# validate total size
		expected_total = IPHeader.HEADER_SIZE + expected_udp_size # 20 + 100 = 120 bytes
		if len(ip_frame) != expected_total:
			raise RuntimeError(
				f"IP audio frame size error: expected {expected_total} bytes, "
				f"created {len(ip_frame)} bytes"
			)

		return ip_frame

	def get_ip_stats(self):
		"""Get IP frame statistics"""
		return {
			'source_ip': self.ip_header.source_ip,
			'dest_ip': self.ip_header.dest_ip,
			'header_size': IPHeader.HEADER_SIZE,
			'tos': self.ip_header.tos,
			'expected_audio_frame_size': IPHeader.HEADER_SIZE + 8 + 12 + 80 # IP + UDP + RTP + Opus
		}


class IPTextFrameBuilder:
	"""
	Create IP frames for UDP+text data (Chat)
	Frame structure: [IP Header][UDP Header][Text payload]
	"""

	def __init__(self, source_ip=None, dest_ip="192.168.1.100"):
		"""
		Initialize IP frame builder for text data

		source_ip: Source IP address
		dest_ip: Destination IP address
		"""
		self.ip_header = IPHeader(source_ip, dest_ip)
		# use normal ToS for text traffic

	def create_ip_text_frame(self, udp_frame_data):
		"""
		Create IP frame containing UDP + text data

		udp_frame_data: Complete UDP frame (UDP header + text payload)
		return: IP header + UDP frame
		"""

		# Create IP header for this UDP frame
		ip_header = self.ip_header.create_header(udp_frame_data)

		# Combine IP header and UDP frame data
		ip_frame = ip_header + udp_frame_data

		return ip_frame

	def get_ip_stats(self):
		""" Get IP frame statistics"""
		return {
			'source_ip': self.ip_header.source_ip,
			'dest_ip': self.ip_header.dest_ip,
			'header_size': IPHeader.HEADER_SIZE,
			'tos': self.ip_header.tos
		}


class IPControlFrameBuilder:
	"""
	Creates IP frames for UDP+control data
	Frame structure: [IP Header][UDP Header][Control Payload]
	"""
	def __init__(self, source_ip=None, dest_ip="192.168.1.100"):
		"""
		Initilize IP frame builder for control data

		source_ip: Source IP address
		dest_ip: Destination IP address
		"""
		self.ip_header = IPHeader(source_ip, dest_ip)
		# Set high priority ToS for control traffic
		self.ip_header.tos = 0xC0 # 6 Network Control?

	def create_ip_control_frame(self, udp_frame_data):
		"""
		create IP frame containing UDP+control data

		udp_frame_data: Complete UDP frame (UDP header + control payload)
		return: IP header + UDP frame
		"""

		# Create IP header for this UDP frame
		ip_header = self.ip_header.create_header(udp_frame_data)

		# Combine IP header + UDP frame
		ip_frame = ip_header + udp_frame_data

		return ip_frame

	def get_ip_stats(self):
		""" Get IP frame statistics"""
		return {
			'source_ip': self.ip_header.source_ip,
			'dest_ip': self.ip_header.dest_ip,
			'header_size': IPHeader.HEADER_SIZE,
			'tos': self.ip_header.tos
		}


class OpulentVoiceProtocolWithIP:
	"""
	Opulent Voice Protocol with IP support

	Frame structures:
	- Audio:   [OV Header][COBS([IP Header][UDP Header][RTP Header][OPUS Payload])]
	133		12	1	20		8	12	80
	- Text:    [OV Header][COBS([IP Header][UDP Header][Text Payload])]
	- Control: [OV Header][COBS([IP Header][UDP Header][Control Payload])]
	- Data:    [OV Header][Data Payload] This goes to network stack - not implemented fully yet
	"""

	# Header Constants
	TOKEN = b'\xBB\xAA\xDD'
	RESERVED = b'\x00\x00\x00'
	HEADER_SIZE = 12

	# Protocol ports (embedded in UDP headers, might want to move to config file)
	PROTOCOL_PORT_VOICE = 57373
	PROTOCOL_PORT_TEXT = 57374
	PROTOCOL_PORT_CONTROL = 57375

	def __init__(self, station_identifier, dest_ip="192.168.1.100"):
		"""Initialize protocol with IP support - Simple frame splitting approach"""
		self.station_id = station_identifier
		self.station_id_bytes = station_identifier.to_bytes()

		# Store destination IP
		self.dest_ip = dest_ip

		# Cache source IP once at startup
		self.source_ip = self._get_local_ip_once()

		# COBS manager for frame boundary detection
		self.cobs_manager = COBSFrameBoundaryManager()

		# Create RTP frame builder for audio
		self.rtp_builder = RTPAudioFrameBuilder(station_identifier)

		# Create UDP frame builders
		self.udp_audio_builder = UDPAudioFrameBuilder(dest_port=self.PROTOCOL_PORT_VOICE)
		self.udp_text_builder = UDPTextFrameBuilder(dest_port=self.PROTOCOL_PORT_TEXT)
		self.udp_control_builder = UDPControlFrameBuilder(dest_port=self.PROTOCOL_PORT_CONTROL)

		# Create IP frame builders
		self.ip_audio_builder = IPAudioFrameBuilder(source_ip=self.source_ip, dest_ip=dest_ip)
		self.ip_text_builder = IPTextFrameBuilder(source_ip=self.source_ip, dest_ip=dest_ip)
		self.ip_control_builder = IPControlFrameBuilder(source_ip=self.source_ip, dest_ip=dest_ip)

		# NEW: Simple frame splitter (specification compliant)
		self.frame_splitter = SimpleFrameSplitter(opulent_voice_frame_size=133)

		print(f"📻 Station ID: {self.station_id} (Base-40: 0x{self.station_id.encoded_value:012X})")
		print(f"🎵 RTP SSRC: 0x{self.rtp_builder.rtp_header.ssrc:08X}")
		print(f"📦 UDP Ports: Audio/Text/Control → {self.PROTOCOL_PORT_VOICE}/{self.PROTOCOL_PORT_TEXT}/{self.PROTOCOL_PORT_CONTROL}")
		print(f"🌐 IP Destination: {dest_ip}")
		print(f"🌐 IP Source: {self.source_ip}")
		print(f"📏 Frame Size: 133 bytes (12B header + 121B payload)")

	def _get_local_ip_once(self):
		"""Get local IP address once at startup"""
		try:
			with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
				s.connect((self.dest_ip, 80))
			return s.getsockname()[0]
		except:
			return "127.0.0.1"

	def create_audio_frames(self, opus_packet, is_start_of_transmission=False):
		"""
		Create complete IP frame, COBS encode, then split into 138-byte frames
		Returns: List of 138-byte Opulent Voice frames ready to send
		"""
		# Step 1: Create complete RTP frame (RTP header + OPUS payload)
		rtp_frame = self.rtp_builder.create_rtp_audio_frame(
			opus_packet,
			is_start_of_transmission
		)
		print(f"🔍 RTP frame: {len(rtp_frame)}B")

		# Step 2: Wrap RTP frame in UDP
		udp_frame = self.udp_audio_builder.create_udp_audio_frame(
			rtp_frame,
			source_ip=self.source_ip,
			dest_ip=self.dest_ip
		)
		print(f"🔍 UDP frame: {len(udp_frame)}B")

		# Step 3: Wrap UDP frame in IP
		ip_frame = self.ip_audio_builder.create_ip_audio_frame(udp_frame)
		print(f"🔍 IP frame: {len(ip_frame)}B")

		# Step 4: COBS encode the complete IP frame
		cobs_frame = self.cobs_manager.encode_frame(ip_frame)
		print(f"🔍 COBS frame: {len(cobs_frame)}B (should be ≤121)")

		# Step 5: Split the COBS frame into 126-byte chunks
		frame_payloads = self.frame_splitter.split_cobs_frame(cobs_frame)
		print(f"🔍 Split into {len(frame_payloads)} frames - SHOULD BE 1 FOR AUDIO!")

		# Step 6: Add Opulent Voice headers to each chunk (138 bytes total)
		ov_frames = []
		for payload in frame_payloads:
			ov_header = struct.pack(
				'>6s 3s 3s',
				self.station_id_bytes,
				self.TOKEN,
				self.RESERVED
			)
			ov_frames.append(ov_header + payload)

		return ov_frames

	def create_text_frames(self, text_data):
		"""
		Create complete IP frame, COBS encode, then split into 138-byte frames
		Returns: List of 138-byte Opulent Voice frames ready to send
		"""
		if isinstance(text_data, str):
			text_data = text_data.encode('utf-8')

		# Step 1: Wrap text in UDP
		udp_frame = self.udp_text_builder.create_udp_text_frame(
			text_data,
			source_ip=self.source_ip,
			dest_ip=self.dest_ip
		)

		# Step 2: Wrap UDP frame in IP
		ip_frame = self.ip_text_builder.create_ip_text_frame(udp_frame)

		# Step 3: COBS encode the complete IP frame
		cobs_frame = self.cobs_manager.encode_frame(ip_frame)

		# Step 4: Split the COBS frame into 126-byte chunks
		frame_payloads = self.frame_splitter.split_cobs_frame(cobs_frame)

		# Step 5: Add Opulent Voice headers to each chunk (138 bytes total)
		ov_frames = []
		for payload in frame_payloads:
			ov_header = struct.pack(
				'>6s 3s 3s',
				self.station_id_bytes,
				self.TOKEN,
				self.RESERVED
			)
			ov_frames.append(ov_header + payload)

		return ov_frames

	def create_control_frames(self, control_data):
		"""
		Create complete IP frame, COBS encode, then split into 138-byte frames
		Returns: List of 138-byte Opulent Voice frames ready to send
		"""
		if isinstance(control_data, str):
			control_data = control_data.encode('utf-8')

		# Step 1: Wrap control data in UDP
		udp_frame = self.udp_control_builder.create_udp_control_frame(
			control_data,
			source_ip=self.source_ip,
			dest_ip=self.dest_ip
		)

		# Step 2: Wrap UDP frame in IP
		ip_frame = self.ip_control_builder.create_ip_control_frame(udp_frame)

		# Step 3: COBS encode the complete IP frame
		cobs_frame = self.cobs_manager.encode_frame(ip_frame)

		# Step 4: Split the COBS frame into 126-byte chunks
		frame_payloads = self.frame_splitter.split_cobs_frame(cobs_frame)

		# Step 5: Add Opulent Voice headers to each chunk (138 bytes total)
		ov_frames = []
		for payload in frame_payloads:
			ov_header = struct.pack(
				'>6s 3s 3s',
				self.station_id_bytes,
				self.TOKEN,
				self.RESERVED
			)
			ov_frames.append(ov_header + payload)

		return ov_frames

	# Keep existing PTT notification methods
	def notify_ptt_pressed(self):
		"""Call when PTT is pressed"""
		self.rtp_builder.start_new_talk_spurt()

	def notify_ptt_released(self):
		"""Call when PTT is released"""
		self.rtp_builder.end_talk_spurt()

	def get_protocol_stats(self):
		"""Get comprehensive protocol statistics"""
		rtp_stats = self.rtp_builder.get_rtp_stats()
		udp_audio_stats = self.udp_audio_builder.get_udp_stats()
		udp_text_stats = self.udp_text_builder.get_udp_stats()
		udp_control_stats = self.udp_control_builder.get_udp_stats()
		ip_audio_stats = self.ip_audio_builder.get_ip_stats()
		ip_text_stats = self.ip_text_builder.get_ip_stats()
		ip_control_stats = self.ip_control_builder.get_ip_stats()
		
		# Updated stats
		cobs_stats = self.cobs_manager.get_stats()
		splitter_stats = self.frame_splitter.get_stats()

		return {
			'station_id': str(self.station_id),
			'rtp': rtp_stats,
			'udp_audio': udp_audio_stats,
			'udp_text': udp_text_stats,
			'udp_control': udp_control_stats,
			'ip_audio': ip_audio_stats,
			'ip_text': ip_text_stats,
			'ip_control': ip_control_stats,
			'cobs': cobs_stats,
			'frame_splitter': splitter_stats,
			'frame_sizes': {
				'opulent_voice_frame_size': 133,  # All frames are exactly 133 bytes
				'ov_header_size': 12,
				'payload_size': 121,
				'audio_calculation': '12 + IP(20) + UDP(8) + RTP(12) + OPUS(80) + COBS(~6) = 133B'
			}
		}


	def station_id_to_string(self, station_id_bytes):
		"""Convert 6-byte station ID to readable string"""
		try:
			station_id = StationIdentifier.from_bytes(station_id_bytes)
			return str(station_id)
		except:
			return station_id_bytes.hex().upper()







# Additional classes that may be needed by other modules

class QueuedMessage:
	"""Container for queued messages with priority and metadata"""
	def __init__(self, msg_type: MessageType, data: bytes, timestamp: float = None):
		self.msg_type = msg_type
		self.data = data
		self.timestamp = timestamp or time.time()
		self.attempts = 0
		self.max_attempts = 3
	
	def __lt__(self, other):
		# Primary sort by priority, secondary by timestamp (FIFO within priority)
		if self.msg_type.priority != other.msg_type.priority:
			return self.msg_type.priority < other.msg_type.priority
		return self.timestamp < other.timestamp


class FrameType(Enum):
	"""Types of 40ms frames"""
	VOICE = 1      # Audio/voice transmission
	CONTROL = 2    # Control messages (A5 auth, system commands)
	TEXT = 3       # Chat/text messages
	DATA = 4       # Data transfer (skip for now)
	KEEPALIVE = 5  # Background keepalive

class FramePriority(Enum):
	"""Frame priority levels - Voice > Control > Text > Data"""
	VOICE = 1      # Highest - interrupts everything
	CONTROL = 2    # High - A5 auth, system control
	TEXT = 3       # Normal - chat messages
	DATA = 4       # Lower - file transfers, bulk data
	KEEPALIVE = 5  # Lowest


# Network transmission class
class NetworkTransmitter:
	"""UDP Network Transmitter for Opulent Voice"""

	def __init__(self, target_ip="192.168.1.100", target_port=57372):
		self.target_ip = target_ip
		self.target_port = target_port
		self.socket = None
		self.stats = {
			'packets_sent': 0,
			'bytes_sent': 0,
			'errors': 0
		}
		self.setup_socket()

	def setup_socket(self):
		"""Create UDP socket"""
		try:
			self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			# Allow socket reuse
			self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
			print(f"✓ UDP socket created for {self.target_ip}:{self.target_port}")
		except Exception as e:
			print(f"✗ Socket creation error: {e}")

	def send_frame(self, frame_data):
		"""Send Opulent Voice frame via UDP"""
		if not self.socket:
			return False

		try:
			bytes_sent = self.socket.sendto(frame_data, (self.target_ip, self.target_port))
			self.stats['packets_sent'] += 1
			self.stats['bytes_sent'] += bytes_sent
			DebugConfig.debug_print(f"📤 Sent frame: {bytes_sent}B to {self.target_ip}:{self.target_port}")
			return True

		except Exception as e:
			self.stats['errors'] += 1
			DebugConfig.system_print(f"✗ Network send error: {e}")
			return False

	def get_stats(self):
		"""Get transmission statistics"""
		return self.stats.copy()

	def close(self):
		"""Close socket"""
		if self.socket:
			self.socket.close()
			self.socket = None
