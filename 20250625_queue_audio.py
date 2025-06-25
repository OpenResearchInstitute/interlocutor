#!/usr/bin/env python3
"""
GPIO PTT Audio, Terminal Chat, Control Messages, and Config Files
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
- Configuration Files in YAML
"""

import sys
import socket
import struct
import time
import threading
import argparse
import re
from queue import PriorityQueue, Empty, Queue
from enum import Enum
from typing import Union, Tuple, Optional, List, Dict
import select
import logging
import traceback
import random
from dataclasses import dataclass

from config_manager import (
    OpulentVoiceConfig, 
    ConfigurationManager, 
    create_enhanced_argument_parser, 
    setup_configuration
)


# check for virtual environment
if not (hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)):
	print("You need to run this code in a virtual environment:")
	print("     source /LED_test/bin/activate")
	sys.exit(1)

try: 
	import opuslib
	print("opuslib ready")
except ImportError:
	print("opuslib is missing: pip3 install opuslib")
	sys.exit()

try:
	import pyaudio
	print("pyaudio ready")
except ImportError:
	print("pyaudio is missing: sudo apt install python3-pyaudio")
	sys.exit(1)

try:
	from gpiozero import Button, LED
	print("gpiozero ready and standing by")
except ImportError:
	print("installing gpiozero...")
	import subprocess
	subprocess.run([sys.executable, '-m', 'pip', 'install', 'gpiozero'])
	from gpiozero import Button, LED


# Global debug configuration
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
			if delimiter_pos == -1:
				raise ValueError("No frame delimiter found")

			frame_data = encoded_data[:delimiter_pos + 1]
			decoded_frame = COBSEncoder.decode(frame_data)

			self.stats['frames_decoded'] += 1
			return decoded_frame, len(frame_data)

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


class MessagePriorityQueue:
	"""Thread-safe priority queue for managing different message types"""
	
	def __init__(self):
		self.queue = PriorityQueue()
		self._stats = {
			'queued': 0,
			'sent': 0,
			'dropped': 0,
			'voice_preempted': 0
		}
		self._lock = threading.Lock()
	
	def add_message(self, msg_type: MessageType, data: bytes):
		"""Add message to priority queue"""
		message = QueuedMessage(msg_type, data)
		self.queue.put(message)
		
		with self._lock:
			self._stats['queued'] += 1
			
		return message
	
	def get_next_message(self, timeout=None):
		"""Get next highest priority message"""
		try:
			return self.queue.get(timeout=timeout)
		except Empty:
			return None
	
	def clear_lower_priority(self, min_priority: int):
		"""Clear messages below specified priority (for voice preemption)"""
		# This is complex to implement efficiently with PriorityQueue
		# For now, we'll rely on voice having highest priority
		pass
	
	def get_stats(self):
		"""Get queue statistics"""
		with self._lock:
			stats = self._stats.copy()
			stats['queue_size'] = self.queue.qsize()
			return stats
	
	def mark_sent(self):
		"""Mark a message as successfully sent"""
		with self._lock:
			self._stats['sent'] += 1
	
	def mark_dropped(self):
		"""Mark a message as dropped"""
		with self._lock:
			self._stats['dropped'] += 1


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
		DebugConfig.debug_print(f"🔍 RTP frame: {len(rtp_frame)}B")

		# Step 2: Wrap RTP frame in UDP
		udp_frame = self.udp_audio_builder.create_udp_audio_frame(
			rtp_frame,
			source_ip=self.source_ip,
			dest_ip=self.dest_ip
		)
		DebugConfig.debug_print(f"🔍 UDP frame: {len(udp_frame)}B")

		# Step 3: Wrap UDP frame in IP
		ip_frame = self.ip_audio_builder.create_ip_audio_frame(udp_frame)
		DebugConfig.debug_print(f"🔍 IP frame: {len(ip_frame)}B")

		# Step 4: COBS encode the complete IP frame
		cobs_frame = self.cobs_manager.encode_frame(ip_frame)
		DebugConfig.debug_print(f"🔍 COBS frame: {len(cobs_frame)}B (should be ≤121)")

		# Step 5: Split the COBS frame into 126-byte chunks
		frame_payloads = self.frame_splitter.split_cobs_frame(cobs_frame)
		DebugConfig.debug_print(f"🔍 Split into {len(frame_payloads)} frames - SHOULD BE 1 FOR AUDIO!")

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





	def create_data_frame(self, data):
		"""
		Create Opulent Voice data frame (NO IP/UDP - will get TCP later)
		Frame: [OV Header][Data Payload]
		"""
		# Data frames don't get IP/UDP yet - they'll get TCP in the next phase
		ov_header = struct.pack(
			'>2s 6s B 3s B',
			self.STREAM_SYNCH_WORD,
			self.station_id_bytes,
			self.FRAME_TYPE_DATA,
			self.TOKEN,
			0
		)

		return ov_header + data





	def parse_audio_frame(self, frame_data):
		"""
		Parse Opulent Voice audio frame and extract IP + UDP + RTP + OPUS
		Expected: [OV Header][IP Header][UDP Header][RTP Header][OPUS Payload]
 		"""
		min_size = self.HEADER_SIZE + IPHeader.HEADER_SIZE + UDPHeader.HEADER_SIZE + 12
		if len(frame_data) < min_size:
			return None

		try:
			# Parse Opulent Voice header
			ov_header = struct.unpack('>2s 6s B 3s B', frame_data[:self.HEADER_SIZE])
			synch, station_bytes, frame_type, token, reserved = ov_header

			if synch != self.STREAM_SYNCH_WORD or frame_type != self.FRAME_TYPE_AUDIO:
				return None

			# Extract IP frame (everything after OV header)
			ip_frame = frame_data[self.HEADER_SIZE:]

			# Parse IP header
			ip_header_obj = IPHeader()
			ip_info = ip_header_obj.parse_header(ip_frame[:IPHeader.HEADER_SIZE])

			# Extract UDP frame (after IP header)
			udp_frame = ip_frame[IPHeader.HEADER_SIZE:]

			# Parse UDP header
			udp_header_obj = UDPHeader()
			udp_info = udp_header_obj.parse_header(udp_frame[:UDPHeader.HEADER_SIZE])

			# Extract RTP frame (after UDP header)
			rtp_frame = udp_frame[UDPHeader.HEADER_SIZE:]

			# Parse RTP header
			rtp_header_obj = RTPHeader()
			rtp_info = rtp_header_obj.parse_header(rtp_frame)

			# Extract OPUS payload
			opus_payload = rtp_frame[rtp_info['header_size']:]

			return {
				'ov_synch': synch,
				'ov_station_bytes': station_bytes,
				'ov_frame_type': frame_type,
				'ov_token': token,
				'ip_info': ip_info,
				'udp_info': udp_info,
				'rtp_info': rtp_info,
				'opus_payload': opus_payload,
				'total_size': len(frame_data)
			}

		except struct.error:
			return None

	def parse_text_frame(self, frame_data):
		"""
		Parse Opulent Voice text frame and extract IP + UDP + text
		Expected: [OV Header][IP Header][UDP Header][Text Payload]
		"""
		min_size = self.HEADER_SIZE + IPHeader.HEADER_SIZE + UDPHeader.HEADER_SIZE
		if len(frame_data) < min_size:
			return None

		try:
			# Parse Opulent Voice header
			ov_header = struct.unpack('>2s 6s B 3s B', frame_data[:self.HEADER_SIZE])
			synch, station_bytes, frame_type, token, reserved = ov_header

			if synch != self.STREAM_SYNCH_WORD or frame_type != self.FRAME_TYPE_TEXT:
				return None

			# Extract IP frame
			ip_frame = frame_data[self.HEADER_SIZE:]

			# Parse IP header
			ip_header_obj = IPHeader()
			ip_info = ip_header_obj.parse_header(ip_frame[:IPHeader.HEADER_SIZE])

			# Extract UDP frame
			udp_frame = ip_frame[IPHeader.HEADER_SIZE:]

			# Parse UDP header
			udp_header_obj = UDPHeader()
			udp_info = udp_header_obj.parse_header(udp_frame[:UDPHeader.HEADER_SIZE])

			# Extract text payload
			text_payload = udp_frame[UDPHeader.HEADER_SIZE:]

			return {
				'ov_synch': synch,
				'ov_station_bytes': station_bytes,
				'ov_frame_type': frame_type,
				'ov_token': token,
				'ip_info': ip_info,
				'udp_info': udp_info,
				'text_payload': text_payload,
				'total_size': len(frame_data)
			}

		except struct.error:
			return None

	def parse_control_frame(self, frame_data):
		"""
		Parse Opulent Voice control frame and extract IP + UDP + control data
		Expected: [OV Header][IP Header][UDP Header][Control Payload]
		"""
		min_size = self.HEADER_SIZE + IPHeader.HEADER_SIZE + UDPHeader.HEADER_SIZE
		if len(frame_data) < min_size:
			return None
		try:
			# Parse Opulent Voice header
			ov_header = struct.unpack('>2s 6s B 3s B', frame_data[:self.HEADER_SIZE])
			synch, station_bytes, frame_type, token, reserved = ov_header

			if synch != self.STREAM_SYNCH_WORD or frame_type != self.FRAME_TYPE_CONTROL:
				return None

			# Extract IP frame
			ip_frame = frame_data[self.HEADER_SIZE:]

			# Parse IP header
			ip_header_obj = IPHeader()
			ip_info = ip_header_obj.parse_header(ip_frame[:IPHeader.HEADER_SIZE])

			# Extract UDP frame
			udp_frame = ip_frame[IPHeader.HEADER_SIZE:]

			# Parse UDP header
			udp_header_obj = UDPHeader()
			udp_info = udp_header_obj.parse_header(udp_frame[:UDPHeader.HEADER_SIZE])

			# Extract control payload
			control_payload = udp_frame[UDPHeader.HEADER_SIZE:]

			return {
				'ov_synch': synch,
				'ov_station_bytes': station_bytes,
				'ov_frame_type': frame_type,
				'ov_token': token,
				'ip_info': ip_info,
				'udp_info': udp_info,
				'control_payload': control_payload,
				'total_size': len(frame_data)
			}

		except struct.error:
			return None

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
			DebugConfig.debug_print(f"✓ UDP socket created for {self.target_ip}:{self.target_port}")
		except Exception as e:
			DebugConfig.system_print(f"✗ Socket creation error: {e}")

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


class ChatManager:
	"""Manages chat state and buffering - works for terminal and future HTML"""
	
	def __init__(self, station_id):
		self.station_id = station_id
		self.ptt_active = False
		self.pending_messages = []
		self.message_queue = None  # Will be set by radio system
		
	def set_message_queue(self, queue):
		"""Set the message queue for sending"""
		self.message_queue = queue
	
	def set_ptt_state(self, active):
		"""Called when PTT state changes"""
		was_active = self.ptt_active
		self.ptt_active = active
		
		# If PTT just released, flush any buffered messages
		if was_active and not active:
			self.flush_buffered_messages()
	
	def handle_message_input(self, message_text):
		"""Handle new message input - returns status for UI feedback"""
		if not message_text.strip():
			return {'status': 'empty', 'action': 'none'}
		
		if self.ptt_active:
			# Buffer the message during PTT
			self.pending_messages.append(message_text.strip())
			return {
				'status': 'buffered', 
				'action': 'show_buffered',
				'message': message_text.strip(),
				'count': len(self.pending_messages)
			}
		else:
			# Send immediately when PTT not active
			self.send_message_immediately(message_text.strip())
			return {
				'status': 'sent',
				'action': 'show_sent', 
				'message': message_text.strip()
			}
	
	def send_message_immediately(self, message_text):
		"""Send message immediately"""
		if self.message_queue:
			self.message_queue.add_message(MessageType.TEXT, message_text.encode('utf-8'))
	
	def flush_buffered_messages(self):
		"""Send all buffered messages after PTT release"""
		if not self.pending_messages:
			return []
		
		sent_messages = []
		for message in self.pending_messages:
			self.send_message_immediately(message)
			sent_messages.append(message)
		
		# Show summary of what was sent
		if len(sent_messages) == 1:
			DebugConfig.user_print(f"💬 Sent buffered message: {sent_messages[0]}")
		else:
			DebugConfig.user_print(f"💬 Sent {len(sent_messages)} buffered messages:")
			for i, msg in enumerate(sent_messages, 1):
				DebugConfig.user_print(f"   {i}. {msg}")
		
		self.pending_messages.clear()
		return sent_messages
	
	def get_pending_count(self):
		"""Get number of pending messages"""
		return len(self.pending_messages)
	
	def clear_pending(self):
		"""Clear pending messages (for cancel operation)"""
		cleared = len(self.pending_messages)
		self.pending_messages.clear()
		return cleared


class TerminalChatInterface:
	"""Non-blocking terminal interface with PTT-aware buffering"""
	
	def __init__(self, station_id, chat_manager):
		self.station_id = station_id
		self.chat_manager = chat_manager
		self.running = False
		self.input_thread = None
		
	def start(self):
		"""Start the chat interface in a separate thread"""
		self.running = True
		self.input_thread = threading.Thread(target=self._input_loop, daemon=True)
		self.input_thread.start()
		
		print("\n" + "="*60)
		print("💬 CHAT INTERFACE READY")
		print("Type messages and press Enter to send")
		print("📝 Messages typed during PTT will be buffered and sent after release")
		print("🎤 Voice PTT takes priority - chat waits respectfully")
		print("⌨️  Type 'quit' to exit, 'status' for chat stats")
		print("="*60)
		self._show_prompt()
	
	def stop(self):
		"""Stop the chat interface"""
		self.running = False
		if self.input_thread:
			self.input_thread.join(timeout=1.0)
	
	def _show_prompt(self):
		"""Show the chat prompt with status"""
		pending_count = self.chat_manager.get_pending_count()
		if pending_count > 0:
			prompt = f"[{self.station_id}] Chat ({pending_count} buffered)> "
		elif self.chat_manager.ptt_active:
			prompt = f"[{self.station_id}] Chat (PTT ACTIVE)> "
		else:
			prompt = f"[{self.station_id}] Chat> "
		
		print(prompt, end='', flush=True)
	
	def _input_loop(self):
		"""Input loop with smart buffering"""
		while self.running:
			try:
				# Use select for non-blocking input on Unix systems
				if select.select([sys.stdin], [], [], 0.1)[0]:
					message = sys.stdin.readline().strip()
					
					if message.lower() == 'quit':
						print("\nExiting chat interface...")
						self.running = False
						break
					
					if message.lower() == 'status':
						self._show_status()
						self._show_prompt()
						continue
					
					if message.lower() == 'clear':
						cleared = self.chat_manager.clear_pending()
						if cleared > 0:
							print(f"🗑️  Cleared {cleared} buffered messages")
						else:
							print("🗑️  No buffered messages to clear")
						self._show_prompt()
						continue
					
					if message:
						# Handle the message through chat manager
						result = self.chat_manager.handle_message_input(message)
						self._display_result(result)
					
					# Show prompt again
					self._show_prompt()
				
				time.sleep(0.1)  # Small delay to prevent busy waiting
				
			except Exception as e:
				print(f"Chat input error: {e}")
				break
	
	def _display_result(self, result):
		"""Display result of message input"""
		if result['status'] == 'sent':
			DebugConfig.user_print(f"💬 Sent: {result['message']}")
		elif result['status'] == 'buffered':
			if self.chat_manager.ptt_active:
				DebugConfig.user_print(f"📝 Buffered during PTT: {result['message']} (total: {result['count']})")
			else:
				DebugConfig.user_print(f"📝 Buffered: {result['message']}")
	
	def _show_status(self):
		"""Show chat status"""
		pending = self.chat_manager.get_pending_count()
		ptt_status = "ACTIVE" if self.chat_manager.ptt_active else "INACTIVE"
		
		DebugConfig.user_print(f"\n📊 Chat Status:")
		DebugConfig.user_print(f"   PTT: {ptt_status}")
		DebugConfig.user_print(f"   Buffered messages: {pending}")
		if pending > 0:
			DebugConfig.user_print(f"   📝 Pending messages:")
			for i, msg in enumerate(self.chat_manager.pending_messages, 1):
				DebugConfig.user_print(f"      {i}. {msg}")
	
	def display_received_message(self, from_station, message):
		"""Display received chat message"""
		DebugConfig.user_print(f"\n📨 [{from_station}]: {message}")
		self._show_prompt()


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


		#DebugConfig.debug_print(f"UDP DEBUG: calc_checksum={calculate_checksum}, src_ip={source_ip}, dst_ip={dest_ip}")
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
			DebugConfig.system_print(f"✗ Struct error when trying to pack UDP Header.")
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
		#DebugConfig.debug_print(f"UDP CHECKSUM DEBUG: source_ip={source_ip}, dest_ip={dest_ip}")
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
			# Connect to a remote address to determine local IP
			# below method requires us to have Internet access!!!
			with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
				s.connect(("8.8.8.8", 80))
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
		Not a derecho!
		"""
		# Calculate total length (IP header + payload)
		total_length = self.HEADER_SIZE + len(payload_data)

		if total_length > 65535:
			raise ValueError(f"IP packet way too large: {total_length} bytes")

		# Increment packet ID for each packet
		# sometimes we need help finding ourselves
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
		#checksum = 111 # "wrong checksum" test for receiver

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
			raise RunTimeError(
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

@dataclass
class StreamFrame:
	"""Container for data going into 40ms frames"""
	frame_type: FrameType
	priority: FramePriority
	data: bytes
	timestamp: float
	is_continuation: bool = False
	sequence_id: int = 0






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
		
		DebugConfig.debug_print(f"📦 Split {len(cobs_encoded_data)}B COBS frame into {len(frames)} frames of 126B each")
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
	
	def add_frame_payload(self, frame_payload: bytes) -> Optional[bytes]:
		"""
		Add a 121-byte frame payload and return complete COBS frame if ready
		
		frame_payload: 121-byte payload from Opulent Voice frame (header removed)
		Returns: Complete COBS-encoded frame if delimiter found, None otherwise
		"""
		if len(frame_payload) != 121:
			DebugConfig.debug_print(f"⚠ Expected 121-byte payload, got {len(frame_payload)}B")
			return None
		
		self.stats['frames_received'] += 1
		
		# Add payload to buffer
		self.buffer.extend(frame_payload)
		self.stats['bytes_buffered'] = len(self.buffer)
		
		# Look for COBS delimiter (0x00)
		delimiter_pos = self.buffer.find(0)
		
		if delimiter_pos != -1:
			# Found complete COBS frame
			complete_cobs_frame = bytes(self.buffer[:delimiter_pos + 1])
			
			# Remove processed data from buffer
			self.buffer = self.buffer[delimiter_pos + 1:]
			self.stats['messages_completed'] += 1
			self.stats['bytes_buffered'] = len(self.buffer)
			
			DebugConfig.debug_print(f"✅ Reassembled complete COBS frame: {len(complete_cobs_frame)}B")
			return complete_cobs_frame
		
		# No complete frame yet
		DebugConfig.debug_print(f"📝 Buffering frame payload, total buffered: {len(self.buffer)}B")
		return None
	
	def get_stats(self):
		"""Get reassembly statistics"""
		return self.stats.copy()








class ContinuousStreamManager:
	#Manages the continuous 40ms frame stream

	def __init__(self, idle_timeout_seconds: float = 5.0):
		self.stream_active = False
		self.idle_timeout = idle_timeout_seconds
		self.last_activity_time = 0
		self.stream_start_time = 0

		# Activity tracking
		self.activity_stats = {
			'stream_starts': 0,
			'stream_stops': 0,
			'total_stream_time': 0,
			'voice_starts': 0,
			'non_voice_starts': 0
		}

	def activity_detected(self, activity_type: str = "unknown"):
		"""Called whenever there's any activity that should maintain the stream"""
		current_time = time.time()

		# Start stream if not already running
		if not self.stream_active:
			self.start_stream(triggered_by=activity_type)

		# Update activity timestamp
		self.last_activity_time = current_time

		# Track what starts the stream
		if activity_type == "voice":
			self.activity_stats['voice_starts'] += 1
		else:
			self.activity_stats['non_voice_starts'] += 1



	def start_stream(self, triggered_by: str = "unknown"):
		"""Start the continuous 40ms frame stream"""
		if self.stream_active:
			return  # Already running

		self.stream_active = True
		self.stream_start_time = time.time()
		self.last_activity_time = self.stream_start_time
		self.activity_stats['stream_starts'] += 1

		# ADD: Debug what's starting the stream
		#DebugConfig.debug_print(f"🚀 40ms stream STARTED (triggered by: {triggered_by})")
		#DebugConfig.debug_print("DEBUG: Stream started by:")
		#traceback.print_stack()









	def start_stream_old(self, triggered_by: str = "unknown"):
		"""Start the continuous 40ms frame stream"""
		if self.stream_active:
			return  # Already running

		self.stream_active = True
		self.stream_start_time = time.time()
		self.last_activity_time = self.stream_start_time
		self.activity_stats['stream_starts'] += 1

		print(f"🚀 40ms stream STARTED (triggered by: {triggered_by})")

	def should_stop_stream(self) -> bool:
		"""Check if stream should stop due to inactivity"""
		if not self.stream_active:
			return False

		time_since_activity = time.time() - self.last_activity_time
		return time_since_activity >= self.idle_timeout

	def stop_stream(self):
		"""Stop the continuous 40ms frame stream"""
		if not self.stream_active:
			return

		stream_duration = time.time() - self.stream_start_time
		self.activity_stats['total_stream_time'] += stream_duration
		self.activity_stats['stream_stops'] += 1
		self.stream_active = False

		print(f"🛑 40ms stream STOPPED (ran for {stream_duration:.1f}s)")
    
	def get_stream_status(self) -> Dict:
		"""Get current stream status"""
		current_time = time.time()
		status = {
			'stream_active': self.stream_active,
			'time_since_activity': current_time - self.last_activity_time if self.stream_active else 0,
			'current_stream_duration': current_time - self.stream_start_time if self.stream_active else 0,
			'stats': self.activity_stats.copy()
		}
		return status



class AudioDrivenFrameManager:
	'''Handles all frame logic within audio callback timing'''
	def __init__(self, station_identifier, protocol, network_transmitter, config):
		self.station_id = station_identifier
		self.protocol = protocol
		self.network_transmitter = network_transmitter
		self.config = config
		
		# Frame queues (keep existing structure)
		self.control_queue = Queue()
		self.text_queue = Queue()
		
		# Voice state (simplified - no buffer needed)
		self.voice_active = False
		self.pending_voice_frame = None
		
		# Non-voice transmission throttling
		self.frames_since_nonvoice = 0
		self.nonvoice_send_interval = 1  # Send non-voice every N frames when no voice
		
		# Keepalive management - ALWAYS initialize ALL attributes
		self.target_type = config.protocol.target_type
		self.last_keepalive_time = 0  # Always initialize this
		self.keepalive_interval = config.protocol.keepalive_interval  # Always initialize this
		
		if self.target_type == "computer":
			self.send_keepalives = True
			DebugConfig.debug_print(f"📡 Target: Computer - keepalives enabled every {self.keepalive_interval}s")
		else:
			self.send_keepalives = False
			DebugConfig.debug_print(f"📻 Target: Modem - keepalives disabled, modem handles hang-time")
		
		# Statistics (compatible with existing stats)
		self.stats = {
			'total_frames_sent': 0,
			'voice_frames_sent': 0,
			'control_frames_sent': 0,
			'text_frames_sent': 0,
			'keepalive_frames_sent': 0,
			'skipped_frames': 0,
			'last_frame_type': None,
			'target_type': self.target_type
		}




	def get_transmission_stats(self):
		"""Get stats (updated for simple frame splitting)"""
		return {
			'scheduler_stats': self.stats,
			'queue_status': {
				'voice_active': self.voice_active,
				'control_queue': self.control_queue.qsize(),
				'text_queue': self.text_queue.qsize(),
				'frames_since_nonvoice': self.frames_since_nonvoice
			},
			'frame_info': {
				'frame_size': 133,
				'header_size': 12,
				'payload_size': 121
			},
			'running': self.voice_active or not (self.control_queue.empty() and self.text_queue.empty())
		}





	def process_voice_and_transmit(self, opus_packet, current_time):
		"""
		PAUL'S APPROACH: Process voice - may generate multiple frames per opus packet
		"""
		try:
			# NEW: Create potentially multiple OV frames (Paul's approach)
			ov_frames = self.protocol.create_audio_frames(opus_packet, 
										is_start_of_transmission=False)

			frames_sent = 0
			for frame in ov_frames:
				success = self.network_transmitter.send_frame(frame)
				if success:
					frames_sent += 1
					self.stats['voice_frames_sent'] += 1
					self.stats['total_frames_sent'] += 1

			if frames_sent > 0:
				self.stats['last_frame_type'] = 'VOICE'
				self.frames_since_nonvoice += 1
				
				if len(ov_frames) > 1:
					DebugConfig.debug_print(f"📡 {current_time:.3f}: VOICE {frames_sent}/{len(ov_frames)} frames")
				else:
					DebugConfig.debug_print(f"📡 {current_time:.3f}: VOICE ({len(ov_frames[0])}B)")

			return frames_sent > 0

		except Exception as e:
			DebugConfig.debug_print(f"✗ Voice frame transmission error: {e}")
			return False





	# Debugging version to find the keepalive issue:

	def process_nonvoice_and_transmit(self, current_time):
		"""
		Process non-voice frames with target-specific behavior
		"""
		frames_sent_this_cycle = 0
		
		# Priority 1: Control messages (always send immediately)
		try:
			ov_frame = self.control_queue.get_nowait()
			success = self.network_transmitter.send_frame(ov_frame)
			if success:
				frames_sent_this_cycle += 1
				self.stats['control_frames_sent'] += 1
				self.stats['total_frames_sent'] += 1
				self.stats['last_frame_type'] = 'CONTROL'
				self.frames_since_nonvoice = 0
				DebugConfig.debug_print(f"📡 {current_time:.3f}: CONTROL ({len(ov_frame)}B)")
				return True
				
		except Empty:
			pass
		except Exception as e:
			DebugConfig.debug_print(f"✗ Control frame error: {e}")
	
		# Priority 2: Text messages (send every 40ms now - no throttling)
		try:
			ov_frame = self.text_queue.get_nowait()
			success = self.network_transmitter.send_frame(ov_frame)
			if success:
				frames_sent_this_cycle += 1
				self.stats['text_frames_sent'] += 1
				self.stats['total_frames_sent'] += 1
				self.stats['last_frame_type'] = 'TEXT'
				self.frames_since_nonvoice = 0
				DebugConfig.debug_print(f"📡 {current_time:.3f}: TEXT ({len(ov_frame)}B)")
				return True
			
		except Empty:
			pass
		except Exception as e:
			DebugConfig.debug_print(f"✗ Text frame error: {e}")
	
		# DEBUG: Show keepalive decision process (commented out because it's a lot of reporting)
		time_since_keepalive = current_time - self.last_keepalive_time
		#DebugConfig.debug_print(f"🔍 Keepalive check: send_keepalives={self.send_keepalives}, voice_active={self.voice_active}, time_since={time_since_keepalive:.1f}s, interval={self.keepalive_interval}s")
	
		# Priority 3: Keepalive (ONLY for computer targets AND when enabled)
		if self.send_keepalives and not self.voice_active:
			if time_since_keepalive >= self.keepalive_interval:
				try:
					keepalive_data = f"KEEPALIVE:{int(current_time)}"
					ov_frames = self.protocol.create_control_frames(keepalive_data)
	
					if ov_frames:
						success = self.network_transmitter.send_frame(ov_frames[0])
						if success:
							self.stats['keepalive_frames_sent'] += 1
							self.stats['total_frames_sent'] += 1
							self.stats['last_frame_type'] = 'KEEPALIVE'
							self.last_keepalive_time = current_time
							self.frames_since_nonvoice = 0
							DebugConfig.debug_print(f"📡 {current_time:.3f}: KEEPALIVE ({len(ov_frames[0])}B) [computer target]")
							return True
	
				except Exception as e:
					DebugConfig.debug_print(f"✗ Keepalive frame error: {e}")
		else:
			# For modem targets: explicitly show that we're NOT sending keepalives
			if time_since_keepalive >= self.keepalive_interval:
				self.last_keepalive_time = current_time  # Update timer but don't send
				DebugConfig.debug_print(f"📻 {current_time:.3f}: Keepalive SKIPPED (target_type={self.target_type}, send_keepalives={self.send_keepalives})")
	
		# Nothing sent this cycle
		self.stats['skipped_frames'] += 1
		self.frames_since_nonvoice += 1
		return False
	



	# Interface methods (compatible with existing code)
	def set_voice_active(self, active):
		"""Called when PTT pressed/released"""
		self.voice_active = active
		if not active:
			self.pending_voice_frame = None


	def queue_text_message(self, text_data):
		"""
		PAUL'S APPROACH: Queue text message - creates complete OV frames
		"""
		if isinstance(text_data, str):
			text_data = text_data.encode('utf-8')

		try:
			# NEW: Create potentially multiple OV frames (Paul's approach)
			ov_frames = self.protocol.create_text_frames(text_data)

			# Queue all frames
			for frame in ov_frames:
				self.text_queue.put(frame)

			if len(ov_frames) > 1:
				DebugConfig.debug_print(f"📝 Text message created {len(ov_frames)} frames: {text_data.decode()[:50]}...")
			else:
				DebugConfig.debug_print(f"📝 Text message queued: {text_data.decode()[:50]}...")

		except Exception as e:
			DebugConfig.debug_print(f"✗ Error queuing text message: {e}")


	def queue_control_message(self, control_data):
		"""
		PAUL'S APPROACH: Queue control message - creates complete OV frames
		"""
		if isinstance(control_data, str):
			control_data = control_data.encode('utf-8')

		try:
			# NEW: Create potentially multiple OV frames (Paul's approach)
			ov_frames = self.protocol.create_control_frames(control_data)

			# Queue all frames
			for frame in ov_frames:
				self.control_queue.put(frame)

			if len(ov_frames) > 1:
				DebugConfig.debug_print(f"📋 Control message created {len(ov_frames)} frames")
			else:
				DebugConfig.debug_print(f"📋 Control message queued")

		except Exception as e:
			DebugConfig.debug_print(f"✗ Error queuing control message: {e}")










class ChatManagerAudioDriven:
	"""
	Modified chat manager for audio-driven system
	"""
	
	def __init__(self, station_id, audio_frame_manager):
		self.station_id = station_id
		self.audio_frame_manager = audio_frame_manager  # Instead of frame_transmitter
		self.ptt_active = False
		self.pending_messages = []
	
	def handle_message_input(self, message_text):
		"""Handle message input (same interface as before)"""
		if not message_text.strip():
			return {'status': 'empty', 'action': 'none'}
		
		if self.ptt_active:
			# Buffer during PTT
			self.pending_messages.append(message_text.strip())
			return {
				'status': 'buffered',
				'action': 'show_buffered', 
				'message': message_text.strip(),
				'count': len(self.pending_messages)
			}
		else:
			# Queue immediately for audio-driven transmission
			self.queue_message_for_transmission(message_text.strip())
			return {
				'status': 'queued_audio_driven',
				'action': 'show_queued',
				'message': message_text.strip()
			}
	
	def queue_message_for_transmission(self, message_text):
		"""Queue message for audio-driven transmission"""
		self.audio_frame_manager.queue_text_message(message_text)
	
	def set_ptt_state(self, active):
		"""Called when PTT state changes"""
		was_active = self.ptt_active
		self.ptt_active = active
		
		# If PTT just released, flush buffered messages
		if was_active and not active:
			self.flush_buffered_messages()
	
	def flush_buffered_messages(self):
		"""Send all buffered messages to audio-driven system after PTT release"""
		if not self.pending_messages:
			return []
		
		sent_messages = []
		for message in self.pending_messages:
			self.queue_message_for_transmission(message)
			sent_messages.append(message)
		
		# Show summary
		if len(sent_messages) == 1:
			print(f"💬 Queued buffered message for audio-driven transmission: {sent_messages[0]}")
		else:
			print(f"💬 Queued {len(sent_messages)} buffered messages for audio-driven transmission")
		
		self.pending_messages.clear()
		return sent_messages
	
	def get_pending_count(self):
		"""Get number of pending messages"""
		return len(self.pending_messages)
	
	def clear_pending(self):
		"""Clear pending messages"""
		cleared = len(self.pending_messages)
		self.pending_messages.clear()
		return cleared











class GPIOZeroPTTHandler:
	def __init__(self, station_identifier, config: OpulentVoiceConfig):
		# Store configuration
		self.config = config

		# Store station identifier  
		self.station_id = station_identifier

		# GPIO setup with gpiozero using config values
		self.ptt_button = Button(
				config.gpio.ptt_pin,
				pull_up=True,
				bounce_time=config.gpio.button_bounce_time
		)
		self.led = LED(config.gpio.led_pin)
		self.ptt_active = False

		# Audio configuration from config
		self.sample_rate = config.audio.sample_rate
		self.bitrate = config.audio.bitrate
		self.channels = config.audio.channels
		self.frame_duration_ms = config.audio.frame_duration_ms
		self.samples_per_frame = int(self.sample_rate * self.frame_duration_ms / 1000)
		self.bytes_per_frame = self.samples_per_frame * 2

		DebugConfig.debug_print(f"🎵 Audio config: {self.sample_rate}Hz, {self.frame_duration_ms}ms frames")
		DebugConfig.debug_print(f"   Samples per frame: {self.samples_per_frame}")
		DebugConfig.debug_print(f"   Bytes per frame: {self.bytes_per_frame}")

		# OPUS setup with validation
		try:
			self.encoder = opuslib.Encoder(
				fs=self.sample_rate,
				channels=self.channels,
				application=opuslib.APPLICATION_VOIP
			)
			# Set the bitrate
			self.encoder.bitrate = self.bitrate
			# Set CBR mode
			self.encoder.vbr = 0
			DebugConfig.debug_print(f"✓ OPUS encoder ready: {self.bitrate}bps CBR")
		except Exception as e:
			DebugConfig.system_print(f"✗ OPUS encoder error: {e}")
			raise

		# Network setup using config
		self.protocol = OpulentVoiceProtocolWithIP(station_identifier, dest_ip=config.network.target_ip)
		self.transmitter = NetworkTransmitter(config.network.target_ip, config.network.target_port)

		# Audio-driven frame manager with config
		self.audio_frame_manager = AudioDrivenFrameManager(
			station_identifier,
			self.protocol,
			self.transmitter,
			config  # Pass the config object
		)

		# Modified chat manager (uses audio-driven manager)
		self.chat_manager = ChatManagerAudioDriven(self.station_id, self.audio_frame_manager)

		# Rest of existing initialization...
		self.audio = pyaudio.PyAudio()
		self.audio_input_stream = None

		# Statistics
		self.audio_stats = {
			'frames_encoded': 0,
			'frames_sent': 0,
			'encoding_errors': 0,
			'invalid_frames': 0
		}

		# Chat interface - now uses ChatManager
		self.chat_interface = TerminalChatInterface(self.station_id, self.chat_manager)

		self.setup_gpio_callbacks()
		self.setup_audio()



	def setup_gpio_callbacks(self):
		"""Setup PTT button callbacks"""
		self.ptt_button.when_pressed = self.ptt_pressed
		self.ptt_button.when_released = self.ptt_released
		DebugConfig.debug_print(f"✓ GPIO setup: PTT=GPIO{self.ptt_button.pin}, LED=GPIO{self.led.pin}")


	def list_audio_devices(self):
		"""List all available audio devices"""
		DebugConfig.debug_print("🎤 Available audio devices:")
		for i in range(self.audio.get_device_count()):
			info = self.audio.get_device_info_by_index(i)
			if info['maxInputChannels'] > 0:  # Has input capability
				DebugConfig.debug_print(f"   Device {i}: {info['name']} (inputs: {info['maxInputChannels']}, rate: {info['defaultSampleRate']})")

	def setup_audio(self):
		"""Setup audio input"""
		# Check device info first
		device_info = self.audio.get_default_input_device_info()
		DebugConfig.debug_print(device_info)
		DebugConfig.debug_print(f"Default input device: {device_info['name']}")
		DebugConfig.debug_print(f"Max input channels: {device_info['maxInputChannels']}")
		DebugConfig.debug_print(f"Default sample rate: {device_info['defaultSampleRate']}")


		# Test specific rates - unsure if this code really works, got weird results.
		for rate in [44100.0, 48000.0, 96000.0]:
			try:
				if self.audio.is_format_supported(
					rate,
					input_device=None,
					input_channels=1,
					input_format=pyaudio.paInt16
				):
					DebugConfig.debug_print(f"✓ Supported sample rate: {rate} Hz")
			except ValueError:
				DebugConfig.debug_print(f"✗ Unsupported sample rate: {rate} Hz")



		# List devices
		self.list_audio_devices()

		# Look for your USB headset - needs improvement
		usb_device_index = None
		for i in range(self.audio.get_device_count()):
			info = self.audio.get_device_info_by_index(i)
			if "Samson" in info['name'] or "C01U" in info['name']:
				usb_device_index = i
				DebugConfig.debug_print(f"🎧 Found USB device: {info['name']} at index {i}")
				DebugConfig.debug_print(f"   Sample rate: {info['defaultSampleRate']}")
				DebugConfig.debug_print(f"   Max input channels: {info['maxInputChannels']}")
				break


		# Check if your USB device supports 48kHz
		if usb_device_index is not None:
			try:
				supported = self.audio.is_format_supported(
					48000,
					input_device=usb_device_index,
					input_channels=1,
					input_format=pyaudio.paInt16
				)
				DebugConfig.debug_print(f"48kHz supported on USB device: {supported}")
			except:
				DebugConfig.debug_print("Error checking format support")



		# Check channel support
		device_info = self.audio.get_device_info_by_index(usb_device_index)
		max_channels = int(device_info['maxInputChannels'])
		channels_to_use = min(self.channels, max_channels)

		DebugConfig.debug_print(f"Using {channels_to_use} channel(s) (requested {self.channels}, max available {max_channels})")
    



		try:
			self.audio_input_stream = self.audio.open(
				format=pyaudio.paInt16,
				channels=self.channels,
				rate=self.sample_rate,
				input=True,
				input_device_index=usb_device_index,  # Use specific device
				frames_per_buffer=self.samples_per_frame, #1920 samples per frame
				stream_callback=self.audio_callback
			)
			DebugConfig.debug_print("✓ Audio input stream ready with USB device")
			DebugConfig.debug_print(f"Requested sample rate: {self.sample_rate} Hz")
			DebugConfig.debug_print(f"Buffer latency: {self.audio_input_stream.get_input_latency():.3f}s")
		except Exception as e:
			DebugConfig.debug_print(f"✗ Audio setup error: {e}")




	def validate_audio_frame(self, audio_data):
		"""Validate audio data before encoding"""
		if len(audio_data) != self.bytes_per_frame:
			DebugConfig.debug_print(f"⚠ Invalid frame size: {len(audio_data)} (expected {self.bytes_per_frame})")
			return False

		# Check for all-zero frames (might indicate audio issues)
		if audio_data == b'\x00' * len(audio_data):
			DebugConfig.debug_print("⚠ All-zero audio frame detected")
			return False

		return True


	def validate_opus_packet(self, opus_packet):
		"""Validate OPUS packet meets Opulent Voice Protocol requirements"""
		expected_size = 80  # Opulent Voice Protocol constraint
		if len(opus_packet) != expected_size:
			DebugConfig.debug_print(
				f"⚠ OPUS packet size violation: expected {expected_size}B, "
				f"got {len(opus_packet)}B"
			)
			return False
		return True




	# minimal audio_callback to see where the problem is
	def audio_callback(self, in_data, frame_count, time_info, status):
		if status:
			print(f"⚠ Audio status flags: {status}")
    
		# Do absolutely nothing else - just return
		return (None, pyaudio.paContinue)







	def audio_callback_actual(self, in_data, frame_count, time_info, status):
		"""
		MODIFIED audio callback that drives all transmission
		This replaces the existing audio_callback method
		"""
		if status:
			print(f"⚠ Audio status flags: {status}")

		current_time = time.time()

		# Debug: print contents
		#is_all_zeros = all(b == 0 for b in in_data)
		#DebugConfig.debug_print(f"🎤 Callback: {len(in_data)}B, frame_count={frame_count}, all_zeros={is_all_zeros}")

		# Debug: Track callback intervals
		#if hasattr(self, 'last_callback_time'):
		#	interval_ms = (current_time - self.last_callback_time) * 1000
		#	if interval_ms < 35 or interval_ms > 45:  # Outside normal range
		#		DebugConfig.debug_print(f"🕒 Audio callback: {interval_ms:.1f}ms")
		#self.last_callback_time = current_time




		# PART 1: Process incoming audio (existing logic)
		if self.ptt_active:
			if not self.validate_audio_frame(in_data):
				self.audio_stats['invalid_frames'] += 1
				return (None, pyaudio.paContinue)

			try:
				# Encode audio (existing logic)
				opus_packet = self.encoder.encode(in_data, self.samples_per_frame)
				#Debug!!!
				DebugConfig.debug_print(f"🔍 Real OPUS data: {opus_packet.hex()}")
				self.audio_stats['frames_encoded'] += 1

				# Validate packet (existing logic)
				if not self.validate_opus_packet(opus_packet):
					self.audio_stats['invalid_frames'] += 1
					DebugConfig.debug_print(f"⚠ Dropping invalid OPUS packet")
					return (None, pyaudio.paContinue)

				# NEW: Send voice frame immediately using audio timing
				if self.audio_frame_manager.process_voice_and_transmit(opus_packet, current_time):
					self.audio_stats['frames_sent'] += 1

			except ValueError as e:
				self.audio_stats['encoding_errors'] += 1
				DebugConfig.debug_print(f"✗ Protocol violation: {e}")
			except Exception as e:
				self.audio_stats['encoding_errors'] += 1
				DebugConfig.debug_print(f"✗ Encoding error: {e}")

		else:
			# PART 2: No voice - use this 40ms slot for other traffic
			self.audio_frame_manager.process_nonvoice_and_transmit(current_time)

		return (None, pyaudio.paContinue)










	def ptt_pressed(self):
		"""PTT button pressed - no more timer management needed"""
		# Send PTT_START control message
		self.audio_frame_manager.queue_control_message(b"PTT_START")

		# Enable voice (audio callback will handle transmission)
		self.ptt_active = True
		self.chat_manager.set_ptt_state(True)
		self.audio_frame_manager.set_voice_active(True)

		self.protocol.notify_ptt_pressed()
		self._is_first_voice_frame = True
		DebugConfig.user_print(f"\n🎤 {self.station_id}: PTT pressed - audio-driven transmission")

		# LED on
		self.led.on()

	def ptt_released(self):
		"""PTT button released - no more timer management needed"""
		self.ptt_active = False
		self.chat_manager.set_ptt_state(False)
		self.audio_frame_manager.set_voice_active(False)

		# Send PTT_STOP control message  
		self.audio_frame_manager.queue_control_message(b"PTT_STOP")
		self.protocol.notify_ptt_released()
		DebugConfig.user_print(f"\n🔇 {self.station_id}: PTT released - audio-driven continues")

		time.sleep(0.1)
		if DebugConfig.VERBOSE:
			self.print_stats()

		# LED off
		self.led.off()






	def print_stats(self):
		"""Print transmission statistics"""
		audio_stats = self.audio_stats
		net_stats = self.transmitter.get_stats()

		# CHANGE: Get stats from frame transmitter instead of message queue
		stream_stats = self.audio_frame_manager.get_transmission_stats()

		print(f"\n📊 {self.station_id} Transmission Statistics:")
		print(f"   Voice frames encoded: {audio_stats['frames_encoded']}")
		print(f"   Voice frames sent: {audio_stats['frames_sent']}")
		print(f"   Invalid frames: {audio_stats['invalid_frames']}")
		print(f"   Total network packets: {net_stats['packets_sent']}")
		print(f"   Total bytes sent: {net_stats['bytes_sent']}")
		print(f"   Stream stats: {stream_stats['scheduler_stats']}")
		print(f"   Queue status: {stream_stats['queue_status']}")
		print(f"   Stream active: {stream_stats['running']}")
		print(f"   Encoding errors: {audio_stats['encoding_errors']}")
		print(f"   Network errors: {net_stats['errors']}")

		# Protocol stats (if available)
		if hasattr(self.protocol, 'get_protocol_stats'):
			protocol_stats = self.protocol.get_protocol_stats()
			print(f"   COBS frames encoded: {protocol_stats['cobs']['frames_encoded']}")
			print(f"   COBS overhead: {protocol_stats['cobs']['avg_overhead_per_frame']:.1f}B/frame")

		# Audio success rate
		if audio_stats['frames_encoded'] > 0:
			voice_success_rate = (audio_stats['frames_sent'] / audio_stats['frames_encoded']) * 100
			print(f"   Voice success rate: {voice_success_rate:.1f}%")



	def test_gpio(self):
		"""Test GPIO functionality"""
		print("🧪 Testing GPIOS...")
		self.led.off()
		for i in range(3):
			self.led.on()
			print(f"   LED ON ({i+1})")
			time.sleep(0.3)
			self.led.off()
			print(f"   LED OFF ({i+1})")
			time.sleep(0.3)
		print("   ✓ LED test complete")
		print(f"   PTT status: {'PRESSED' if self.ptt_button.is_pressed else 'NOT PRESSED'}")






	def test_network(self):
		"""Test network connectivity - VALIDATES 80-BYTE OPUS CONSTRAINT"""
		print("🌐 Testing network...")
		print(f"   Target: {self.transmitter.target_ip}:{self.transmitter.target_port}")

		# Create something that looks like 80 bytes of Opus data
		# Random data is worst case situation for COBS, and will result
		# in two bytes of overhead. This will trigger a rare audio split. 
		test_opus_payload = bytes(random.randint(0, 255) for _ in range(80))
		print(f"   📏 Test OPUS payload: {len(test_opus_payload)}B (protocol-compliant)")

		try:
			# Test the RTP audio frame creation
			test_frames = self.protocol.create_audio_frames(test_opus_payload, is_start_of_transmission=True)
			test_frame = test_frames[0]  # Take first frame for test - should be the only frame for audio.

			if self.transmitter.send_frame(test_frame):
				print("   ✓ Test RTP audio frame sent successfully")
				DebugConfig.debug_print("     Special note: random test data is maximum COBS overhead.")
				DebugConfig.debug_print("     Did you see the audio frame split?")
				rtp_stats = self.protocol.rtp_builder.get_rtp_stats()
				DebugConfig.debug_print(f"   📡 Frame structure: OV(12B) + COBS(1B) + IP(20B) + UDP(8B) + RTP(12B) + OPUS(80B) = {len(test_frame)}B total")
				DebugConfig.debug_print(f"   📡 RTP SSRC: 0x{rtp_stats['ssrc']:08X}")
			else:
				print("   ✗ Test RTP audio frame failed")
		except ValueError as e:
			print(f"   ✗ Protocol validation error: {e}")
		except Exception as e:
			print(f"   ✗ Unexpected error in test_network: {e}")
			traceback.print_exc()



		test_text = "Test text message using Paul's COBS-first approach"
		try:
			text_frames = self.protocol.create_text_frames(test_text)
			print(f"   📦 Created {len(text_frames)} text frames")

			for i, frame in enumerate(text_frames):
				if self.transmitter.send_frame(frame):
					print(f"   ✓ Text frame {i+1}/{len(text_frames)} sent: {len(frame)}B")
				else:
					print(f"   ✗ Text frame {i+1}/{len(text_frames)} failed")

		except Exception as e:
			print(f"   ✗ Text frame error: {e}")




		# Test regular text frame (no RTP)
			test_text = "Test text message (no RTP)"
			try:
				text_frames = self.protocol.create_text_frames(test_text)
				print(f"   📦 Created {len(text_frames)} text frames (no RTP)")

				frames_sent = 0
				for i, frame in enumerate(text_frames):
					if self.transmitter.send_frame(frame):
						frames_sent += 1
						print(f"   ✓ Text frame {i+1}/{len(text_frames)} sent: {len(frame)}B (no RTP)")
					else:
						print(f"   ✗ Text frame {i+1}/{len(text_frames)} failed (no RTP)")

				if frames_sent > 0:
					print(f"   ✓ {frames_sent}/{len(text_frames)} text frames sent successfully (no RTP)")
				else:
					print("   ✗ All text frames failed (no RTP)")
			
			except Exception as e:
				print(f"   ✗ Text frame error: {e}")
				traceback.print_exc()






	def test_chat(self):
		"""Test chat functionality with continuous stream"""
		print("💬 Testing continuous stream chat system...")
	
		# Send a test chat message (should start stream)
		test_msg = f"Test message from {self.station_id}"
		self.audio_frame_manager.queue_text_message(test_msg)
		print(f"   ✓ Test chat message queued: {test_msg}")
	
		# Send a control message
		self.audio_frame_manager.queue_control_message(b"TEST_CONTROL")
		print(f"   ✓ Test control message queued")
	
		# Brief wait to see if stream starts
		time.sleep(1.0)
	
		# Check stream status
		stats = self.audio_frame_manager.get_transmission_stats()
		print(f"   Stream running: {stats['running']}")
		print(f"   Queue status: {stats['queue_status']}")








	def start(self):
		"""Start the continuous stream system"""
		if self.audio_input_stream:
			self.audio_input_stream.start_stream()

		# Start chat interface
		self.chat_interface.start()

		print(f"\n🚀 {self.station_id} Continuous stream system ready")
		print("📋 Configuration:")
		print(f"   Station: {self.station_id}")
		print(f"   Sample rate: {self.sample_rate} Hz")
		print(f"   Bitrate: {self.bitrate} bps CBR")
		print(f"   Frame size: {self.frame_duration_ms}ms ({self.samples_per_frame} samples)")
		print(f"   Frame rate: {1000/self.frame_duration_ms} fps")
		print(f"   Network target: {self.transmitter.target_ip}:{self.transmitter.target_port}")
		print(f"   Stream starts automatically when there's activity")


	def stop(self):
		"""Stop the continuous stream system"""
		self.chat_interface.stop()

		if self.audio_input_stream:
			self.audio_input_stream.stop_stream()
			self.audio_input_stream.close()
		self.audio.terminate()
		print(f"🛑 {self.station_id} Continuous stream system stopped")



	def cleanup(self):
		"""Clean shutdown"""
		self.stop()
		self.transmitter.close()
		self.led.off()
		print(f"Thank you for shopping at Omega Mart. {self.station_id} cleanup complete.")





class MessageReceiver:
	"""Handles receiving and parsing incoming messages"""
	def __init__(self, listen_port=57372, chat_interface=None):
		self.listen_port = listen_port
		self.chat_interface = chat_interface
		self.socket = None
		self.running = False
		self.receive_thread = None

		# NEW: Simple frame reassembler (no fragmentation headers)
		self.reassembler = SimpleFrameReassembler()
		self.cobs_manager = COBSFrameBoundaryManager()

		# For parsing complete frames
		self.protocol = OpulentVoiceProtocolWithIP(StationIdentifier("TEMP"))

	def _process_received_data(self, data, addr):
		"""
		Simple receiver processing - no fragmentation headers to worry about
		"""
		try:
			# Step 1: Parse Opulent Voice header
			if len(data) != 133:  # All frames must be exactly 133 bytes
				DebugConfig.debug_print(f"⚠ Expected 133-byte frame, got {len(data)}B from {addr}")
				return

			ov_header = data[:12]
			frame_payload = data[12:]  # Should be exactly 121 bytes

			# Parse OV header
			station_bytes, token, reserved = struct.unpack('>6s 3s 3s', ov_header)

			DebugConfig.debug_print(f"📥 Received 133B frame from {addr}")

			if token != OpulentVoiceProtocolWithIP.TOKEN:
				DebugConfig.debug_print(f"⚠ Invalid token from {addr}")
				return  # Invalid frame

			# Step 2: Try to reassemble COBS frame
			complete_cobs_frame = self.reassembler.add_frame_payload(frame_payload)

			if complete_cobs_frame:
				DebugConfig.debug_print(f"✅ Reassembled complete COBS frame: {len(complete_cobs_frame)}B")

				# Step 3: COBS decode to get original IP frame
				try:
					ip_frame, _ = self.cobs_manager.decode_frame(complete_cobs_frame)
					DebugConfig.debug_print(f"✅ COBS decoded to IP frame: {len(ip_frame)}B")

					# Step 4: Process the complete IP frame
					self._process_complete_ip_frame(ip_frame, station_bytes, addr)

				except Exception as e:
					DebugConfig.debug_print(f"✗ COBS decode error from {addr}: {e}")
			else:
				DebugConfig.debug_print(f"📝 Frame payload added to buffer...")

		except Exception as e:
			DebugConfig.debug_print(f"Error processing received data from {addr}: {e}")



	def start(self):
		"""Start the message receiver"""
		try:
			self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			self.socket.bind(('', self.listen_port))
			self.socket.settimeout(1.0)  # Allow periodic checking of running flag

			self.running = True
			self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
			self.receive_thread.start()

			print(f"👂 Message receiver listening on port {self.listen_port}")

		except Exception as e:
			print(f"✗ Failed to start receiver: {e}")

	def stop(self):
		"""Stop the message receiver"""
		self.running = False
		if self.receive_thread:
			self.receive_thread.join(timeout=2.0)
		if self.socket:
			self.socket.close()
		print("👂 Message receiver stopped")

	def _receive_loop(self):
		"""Main receive loop"""
		while self.running:
			try:
				data, addr = self.socket.recvfrom(4096)
				self._process_received_data(data, addr)

			except socket.timeout:
				continue  # Normal timeout, check running flag
			except Exception as e:
				if self.running:  # Only log errors if we're supposed to be running
					print(f"Receive error: {e}")





	def _process_received_data(self, data, addr):
		"""
		PAUL'S APPROACH: Much simpler receiver processing!
		"""
		try:
			# Step 1: Parse Opulent Voice header
			if len(data) < 12:
				return

			ov_header = data[:12]
			fragment_payload = data[12:]

			# Parse OV header
			station_bytes, token, reserved = struct.unpack('>6s 3s 3s', ov_header)

			if token != OpulentVoiceProtocolWithIP.TOKEN:
				return  # Invalid frame

			# Step 2: Try to reassemble COBS frame (Paul's key insight!)
			complete_cobs_frame = self.reassembler.add_fragment(fragment_payload)

			if complete_cobs_frame:
				# Step 3: COBS decode to get original IP frame
				try:
					ip_frame, _ = self.cobs_manager.decode_frame(complete_cobs_frame)

					# Step 4: Process the complete IP frame
					self._process_complete_ip_frame(ip_frame, station_bytes, addr)

				except Exception as e:
					DebugConfig.debug_print(f"✗ COBS decode error from {addr}: {e}")

			# Periodic cleanup of expired partial frames
			self.reassembler.cleanup_expired_frames()

		except Exception as e:
			DebugConfig.debug_print(f"Error processing received data from {addr}: {e}")


	def _process_complete_ip_frame(self, ip_frame, station_bytes, addr):
		"""
		Process a complete, decoded IP frame - much simpler now!
		"""
		try:
			# Get station identifier
			try:
				from_station = StationIdentifier.from_bytes(station_bytes)
			except:
				from_station = f"UNKNOWN-{station_bytes.hex()[:8]}"

			# Parse IP header to get protocol info
			if len(ip_frame) < 20:
				return

			# Quick IP header parse to get UDP payload
			ip_header_length = (ip_frame[0] & 0x0F) * 4
			if len(ip_frame) < ip_header_length + 8:  # Need at least UDP header
				return

			udp_payload = ip_frame[ip_header_length + 8:]  # Skip IP + UDP headers

			# Parse UDP header to determine port/type
			udp_dest_port = struct.unpack('!H', ip_frame[ip_header_length + 2:ip_header_length + 4])[0]

			# Route based on UDP port
			if udp_dest_port == 57373:  # Voice
				DebugConfig.debug_print(f"🎤 [{from_station}] Voice: {len(udp_payload)}B")
			elif udp_dest_port == 57374:  # Text  
				try:
					message = udp_payload.decode('utf-8')
					print(f"\n📨 [{from_station}]: {message}")
					if self.chat_interface:
						# Re-display chat prompt
						print(f"[{self.chat_interface.station_id}] Chat> ", end='', flush=True)
				except UnicodeDecodeError:
					print(f"📨 [{from_station}]: <Binary text data: {len(udp_payload)}B>")
			elif udp_dest_port == 57375:  # Control
				try:
					control_msg = udp_payload.decode('utf-8')
					if not control_msg.startswith('KEEPALIVE'):  # Don't spam with keepalives
						print(f"📋 [{from_station}] Control: {control_msg}")
				except UnicodeDecodeError:
					print(f"📋 [{from_station}] Control: <Binary data: {len(udp_payload)}B>")
			else:
				print(f"❓ [{from_station}] Unknown port {udp_dest_port}: {len(udp_payload)}B")

		except Exception as e:
			DebugConfig.debug_print(f"Error processing IP frame: {e}")







def test_base40_encoding():
	"""Test the base-40 encoding/decoding functions"""
	print("🧪 Testing Base-40 Encoding/Decoding...")

	test_callsigns = [
		"W1ABC",      # Traditional US callsign
		"VE3XYZ",     # Canadian callsign
		"G0ABC",      # UK callsign
		"JA1ABC",     # Japanese callsign
		"TACTICAL1",  # Tactical callsign
		"TEST/P",     # Portable operation
		"NODE-1",     # Network node
		"RELAY.1",    # Relay station
	]

	for callsign in test_callsigns:
		try:
			encoded = encode_callsign(callsign)
			decoded = decode_callsign(encoded)
			status = "✓" if decoded == callsign else "✗"
			print(f"   {status} {callsign} → 0x{encoded:012X} → {decoded}")

			# Test StationIdentifier class
			station = StationIdentifier(callsign)
			station_bytes = station.to_bytes()
			recovered = StationIdentifier.from_bytes(station_bytes)

			if str(recovered) == callsign:
				print(f"      ✓ StationIdentifier round-trip successful")
			else:
				print(f"      ✗ StationIdentifier round-trip failed: {recovered}")

		except Exception as e:
			print(f"   ✗ {callsign} → Error: {e}")

	print("   🧪 Base-40 encoding tests complete\n")





def parse_arguments():
	"""Enhanced argument parser that works with configuration system"""
	return create_enhanced_argument_parser()




def parse_arguments_old():
	"""Parse command line arguments"""
	parser = argparse.ArgumentParser(
		description='Opulent Voice Protocol PTT Radio Interface with Chat',
		formatter_class=argparse.ArgumentDefaultsHelpFormatter
	)

	parser.add_argument(
		'callsign',
		help='Station callsign (supports A-Z, 0-9, -, /, . characters)'
	)

	parser.add_argument(
		'-i', '--ip',
		default="192.168.2.152",
		help='Target IP address for transmission'
	)

	parser.add_argument(
		'-p', '--port',
		type=int,
		default=57372,
		help='Target port for transmission'
	)

	parser.add_argument(
		'-l', '--listen-port',
		type=int,
		default=57372,
		help='Local port for receiving messages'
	)

	parser.add_argument(
		'--ptt-pin',
		type=int,
		default=23,
		help='GPIO pin for PTT button input'
	)

	parser.add_argument(
		'--led-pin',
		type=int,
		default=17,
		help='GPIO pin for PTT LED output'
	)

	parser.add_argument(
		'--chat-only',
		action='store_true',
		help='Run in chat-only mode (no GPIO/audio)'
	)

	parser.add_argument(
		'-v', '--verbose',
		action='store_true',
		help='Enable verbose debug output'
	)

	parser.add_argument(
		'-q', '--quiet',
		action='store_true',
		help='Quiet mode - minimal output'
	)

	return parser.parse_args()


# Usage

# 5. REPLACE the entire main execution block at the bottom:
if __name__ == "__main__":
	print("-=" * 40)
	print("Opulent Voice Radio with Terminal Chat")
	print("-=" * 40)

	try:
		# Setup configuration system (replaces old argument parsing)
		config, should_exit = setup_configuration()
		
		if should_exit:
			sys.exit(0)

		# Set debug mode from configuration
		DebugConfig.set_mode(verbose=config.debug.verbose, quiet=config.debug.quiet)

		# Test the base-40 encoding first
		if config.debug.verbose:
			test_base40_encoding()

		# Create station identifier from configuration
		station_id = StationIdentifier(config.callsign)

		DebugConfig.system_print(f"📡 Station: {station_id}")
		DebugConfig.system_print(f"📡 Target: {config.network.target_ip}:{config.network.target_port}")
		DebugConfig.system_print(f"👂 Listen: Port {config.network.listen_port}")
		DebugConfig.system_print(f"🎯 Target Type: {config.protocol.target_type}")
		if config.debug.verbose:
			DebugConfig.debug_print("💡 Configuration loaded from file and CLI overrides")
		DebugConfig.system_print("")

		# Create message receiver using config
		receiver = MessageReceiver(listen_port=config.network.listen_port)
		receiver.start()

		if config.ui.chat_only_mode:
			print("💬 Chat-only mode (no GPIO/audio)")

			# Simple chat-only implementation for testing
			chat_manager = ChatManager(station_id)
			message_queue = MessagePriorityQueue()
			chat_manager.set_message_queue(message_queue)

			chat_interface = TerminalChatInterface(station_id, chat_manager)
			receiver.chat_interface = chat_interface

			# Create minimal transmitter for chat using config
			transmitter = NetworkTransmitter(config.network.target_ip, config.network.target_port)
			protocol = OpulentVoiceProtocolWithIP(station_id, dest_ip=config.network.target_ip)

			chat_interface.start()

			print(f"\n✅ {station_id} Chat system ready. Type messages or 'quit' to exit.")
			print("💡 Commands: 'status' (show chat status), 'clear' (clear buffered), 'quit' (exit)")

			# Simple transmission loop for chat-only mode
			try:
				while chat_interface.running:
					message = message_queue.get_next_message(timeout=0.1)
					if message and message.msg_type == MessageType.TEXT:
						frames = protocol.create_text_frames(message.data)
						for frame in frames:
							if transmitter.send_frame(frame):
								print(f"📤 Transmitted: {message.data.decode('utf-8')}")
						message_queue.mark_sent()
					time.sleep(0.1)
			except KeyboardInterrupt:
				pass

		else:
			# Full radio system with GPIO and audio using configuration
			radio = GPIOZeroPTTHandler(
				station_identifier=station_id,
				config=config  # Pass entire config object
			)

			# Connect receiver to chat interface
			receiver.chat_interface = radio.chat_interface

			radio.test_gpio()
			radio.test_network()
			radio.test_chat()
			radio.start()

			print(f"\n✅ {station_id} System Ready!")
			print("🎤 Press PTT for voice transmission (highest priority)")
			print("💬 Type chat messages in terminal")
			print("📊 Voice and chat statistics shown after each PTT release")
			print("⌨️  Press Ctrl+C to exit")

			# Main loop
			try:
				while True:
					time.sleep(0.1)
			except KeyboardInterrupt:
				pass

	except KeyboardInterrupt:
		print("\nShutting down...")
	except Exception as e:
		print(f"✗ Error: {e}")
		sys.exit(1)
	finally:
		# Cleanup
		if 'receiver' in locals():
			receiver.stop()
		if 'radio' in locals():
			radio.cleanup()
		elif 'chat_interface' in locals():
			chat_interface.stop()

		print("Thank you for using Opulent Voice!")



