#!/usr/bin/env python3
"""
GPIO PTT Audio with Terminal Chat - Phase 1 Foundation
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
	"""

	MAX_BLOCK_SIZE = 254 # review this because this limit may just be optimized overhead limit

	@staticmethod
	def encode(data: bytes) -> bytes:
		"""Encode data using COBS algorithm"""
		if not data:
			return b'\x01\x00'

		encoded = bytearray()
		block_start = 0

		while block_start < len(data):
			zero_pos = data.find(0, block_start)

			if zero_pos == -1:
				block_len = len(data) - block_start
				if block_len >= COBSEncoder.MAX_BLOCK_SIZE:
					encoded.append(COBSEncoder.MAX_BLOCK_SIZE + 1)
					encoded.extend(data[block_start:block_start + COBSEncoder.MAX_BLOCK_SIZE])
					block_start += COBSEncoder.MAX_BLOCK_SIZE
				else:
					encoded.append(block_len + 1)
					encoded.extend(data[block_start:])
					break
			else:
				block_len = zero_pos - block_start
				encoded.append(block_len + 1)
				encoded.extend(data[block_start:zero_pos])
				block_start = zero_pos + 1

		encoded.append(0)
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










# Original Opulent Voice Protocol class, without RTP header stuffs
# Superseded by OpulentVoiceProtocolWithRDP
class OpulentVoiceProtocol:
	""" 
	Frame format: [Header][Payload]

	Synchronization: 2 bytes, unencoded

	Header: 12 bytes, coded
		Station ID: 6 bytes (callsign + SSID)
		Flags: 3 bytes
			Frame Type: 0x01 Audio, 0x02 Text, 0x03 Auth, 0x4 Data
			EOS: End of Stream Bit, 0 = This is not the last frame, 1 = this is the last frame
		Token: Claimed authorization token, 3 bytes (station generated n-bit PRNG token)
	"""

	STREAM_SYNCH_WORD = b'\xFF\x5D'  # FF5D 
	EOT_SYNCH_WORD = b'\x55\x5D'     # 555D
	FRAME_TYPE_AUDIO = 0x01
	FRAME_TYPE_TEXT = 0x02
	FRAME_TYPE_CONTROL = 0x03
	FRAME_TYPE_DATA = 0x04
	TOKEN = b'\xBB\xAA\xDD'          # temporary value for the token

	HEADER_SIZE = 13  # 2 (synch) + 6 (station) + 1 (type) + 3 (token) + 1 (reserved)

	def __init__(self, station_identifier):
		"""Initialize protocol with station identifier"""
		self.station_id = station_identifier
		self.station_id_bytes = station_identifier.to_bytes()
		DebugConfig.system_print(f"📻 Station ID: {self.station_id} (Base-40: 0x{self.station_id.encoded_value:012X})")

	def create_frame(self, frame_type: int, payload: bytes):
		"""Create Opulent Voice frame with specified type"""
		header = struct.pack(
			'>2s 6s B 3s B',  # Fixed format: synch + station_id + type + token + reserved
			self.STREAM_SYNCH_WORD,     # 2 bytes
			self.station_id_bytes,      # 6 bytes  
			frame_type,                 # 1 byte
			self.TOKEN,                 # 3 bytes
			0                           # 1 byte reserved
		)

		return header + payload

	def create_audio_frame(self, opus_packet):
		"""Create Opulent Voice audio frame"""
		return self.create_frame(self.FRAME_TYPE_AUDIO, opus_packet)

	def create_text_frame(self, text_data):
		"""Create Opulent Voice text frame"""
		if isinstance(text_data, str):
			text_data = text_data.encode('utf-8')
		return self.create_frame(self.FRAME_TYPE_TEXT, text_data)

	def create_control_frame(self, control_data):
		"""Create Opulent Voice control frame"""
		if isinstance(control_data, str):
			control_data = control_data.encode('utf-8')
		return self.create_frame(self.FRAME_TYPE_CONTROL, control_data)

	def create_data_frame(self, data):
		"""Create Opulent Voice data frame"""
		return self.create_frame(self.FRAME_TYPE_DATA, data)

	def parse_frame(self, frame_data):
		"""Parse received Opulent Voice frame"""
		if len(frame_data) < self.HEADER_SIZE:
			return None

		try:
			stream_synch, station_id_bytes, frame_type, token, reserved = struct.unpack(
				'>2s 6s B 3s B', frame_data[:self.HEADER_SIZE]
			)

			if stream_synch != self.STREAM_SYNCH_WORD:
				return None

			payload = frame_data[self.HEADER_SIZE:self.HEADER_SIZE + payload_len]

			# Parse station identifier
			try:
				station_id = StationIdentifier.from_bytes(station_id_bytes)
			except ValueError:
				station_id = None

			return {
				'synch': stream_synch,
				'station_id_bytes': station_id_bytes,
				'station_id': station_id,
				'type': frame_type,
				'token': token,
				'reserved': reserved,
				'payload': payload
			}

		except struct.error:
			return None

	def station_id_to_string(self, station_id_bytes):
		"""Convert 6-byte station ID to readable string"""
		try:
			station_id = StationIdentifier.from_bytes(station_id_bytes)
			return str(station_id)
		except Exception as e:
			return station_id_bytes.hex().upper()









# superseded by OpulentVoiceProtocolWithUDP
class OpulentVoiceProtocolWithRTP:
	"""
	Enhanced Opulent Voice Protocol with RTP support for audio frames
	"""
	# Keep all your existing constants
	STREAM_SYNCH_WORD = b'\xFF\x5D'
	FRAME_TYPE_AUDIO = 0x01
	FRAME_TYPE_TEXT = 0x02
	FRAME_TYPE_CONTROL = 0x03
	FRAME_TYPE_DATA = 0x04
	TOKEN = b'\xBB\xAA\xDD'
	HEADER_SIZE = 13

	def __init__(self, station_identifier):
		self.station_id = station_identifier
		self.station_id_bytes = station_identifier.to_bytes()
		# Create RTP frame builder for audio
		self.rtp_builder = RTPAudioFrameBuilder(station_identifier)

		print(f"📻 Station ID: {self.station_id} (Base-40: 0x{self.station_id.encoded_value:012X})")
		print(f"🎵 RTP SSRC: 0x{self.rtp_builder.rtp_header.ssrc:08X}")

	def create_audio_frame(self, opus_packet, is_start_of_transmission=False):
		"""
		Create Opulent Voice audio frame with RTP header
		"""
        	# Create RTP frame (RTP header + OPUS payload)
		rtp_frame = self.rtp_builder.create_rtp_audio_frame(
			opus_packet, 
			is_start_of_transmission
		)

		# Wrap RTP frame in Opulent Voice header
		ov_header = struct.pack(
			'>2s 6s B 3s B',
			self.STREAM_SYNCH_WORD,
			self.station_id_bytes,
			self.FRAME_TYPE_AUDIO,
			self.TOKEN,
			0
		)
		return ov_header + rtp_frame

	def parse_audio_frame(self, frame_data):
		"""
		Parse Opulent Voice audio frame and extract RTP + OPUS
		"""
		if len(frame_data) < self.HEADER_SIZE + RTPHeader.HEADER_SIZE:
			return None
		try:
			ov_header = struct.unpack('>2s 6s B 3s B', frame_data[:self.HEADER_SIZE])
			synch, station_bytes, frame_type, token, reserved = ov_header
			if synch != self.STREAM_SYNCH_WORD or frame_type != self.FRAME_TYPE_AUDIO:
				return None
			rtp_frame = frame_data[self.HEADER_SIZE:]
			rtp_header_obj = RTPHeader()
			rtp_info = rtp_header_obj.parse_header(rtp_frame)
			opus_payload = rtp_frame[rtp_info['header_size']:]
			return {
				'ov_synch': synch,
				'ov_station_bytes': station_bytes,
				'ov_frame_type': frame_type,
				'ov_token': token,
				'rtp_info': rtp_info,
				'opus_payload': opus_payload,
				'total_size': len(frame_data)
			}
		except struct.error:
			return None

	def notify_ptt_pressed(self):
		"""
		Call when PTT is pressed
		"""
		self.rtp_builder.start_new_talk_spurt()

	def notify_ptt_released(self):
		"""
		Call when PTT is released
		"""
		self.rtp_builder.end_talk_spurt()

	# Kept existing methods for non-audio frames unchanged
	def create_text_frame(self, text_data):
		if isinstance(text_data, str):
			text_data = text_data.encode('utf-8')
		return self._create_basic_frame(self.FRAME_TYPE_TEXT, text_data)

	def create_control_frame(self, control_data):
		if isinstance(control_data, str):
			control_data = control_data.encode('utf-8')
		return self._create_basic_frame(self.FRAME_TYPE_CONTROL, control_data)

	def create_data_frame(self, data):
		return self._create_basic_frame(self.FRAME_TYPE_DATA, data)

	def _create_basic_frame(self, frame_type, payload):
		header = struct.pack(
			'>2s 6s B 3s B',
			self.STREAM_SYNCH_WORD,
			self.station_id_bytes,
			frame_type,
			self.TOKEN,
			0
		)
		return header + payload

	def station_id_to_string(self, station_id_bytes):
		"""
		Convert 6-byte station ID to readable string
		"""
		try:
			station_id = StationIdentifier.from_bytes(station_id_bytes)
			return str(station_id)
		except:
			return station_id_bytes.hex().upper()






# Superseded by OpulentVoiceProtocolWithIP
# Opulent Voice with RTP and UDP, for audio, chat, and control (data not done yet)
class OpulentVoiceProtocolWithUDP:
	"""
	Opulent Voice Protocol with UDP support

	Frame structures:
	- Audio: [OV Header][UDP Header][RTP Header][OPUS Payload]
	- Text:  [OV Header][UDP Header][Text Payload] 
	- Control: [OV Header][UDP Header][Control Payload]
	- Data: [OV Header][Data Payload] (no UDP - will get TCP/IP later)
	"""

	# Keep existing constants
	STREAM_SYNCH_WORD = b'\xFF\x5D'
	FRAME_TYPE_AUDIO = 0x01
	FRAME_TYPE_TEXT = 0x02
	FRAME_TYPE_CONTROL = 0x03
	FRAME_TYPE_DATA = 0x04
	TOKEN = b'\xBB\xAA\xDD'
	HEADER_SIZE = 13

	def __init__(self, station_identifier, udp_dest_port=57373):
		"""Initialize protocol with UDP support"""
		self.station_id = station_identifier
		self.station_id_bytes = station_identifier.to_bytes()

		# Create RTP frame builder for audio (unchanged)
		self.rtp_builder = RTPAudioFrameBuilder(station_identifier)

		# NEW: Create UDP frame builders for different message types
		self.udp_audio_builder = UDPAudioFrameBuilder(dest_port=udp_dest_port)
		self.udp_text_builder = UDPTextFrameBuilder(dest_port=udp_dest_port)
		self.udp_control_builder = UDPControlFrameBuilder(dest_port=udp_dest_port)

		print(f"📻 Station ID: {self.station_id} (Base-40: 0x{self.station_id.encoded_value:012X})")
		print(f"🎵 RTP SSRC: 0x{self.rtp_builder.rtp_header.ssrc:08X}")
		print(f"📦 UDP Ports: Audio/Text/Control → {udp_dest_port}")

	def create_audio_frame(self, opus_packet, is_start_of_transmission=False):
		"""
		Create Opulent Voice audio frame with UDP + RTP headers
		Frame: [OV Header][UDP Header][RTP Header][OPUS Payload]
		"""
		# Create RTP frame (RTP header + OPUS payload) - unchanged
		rtp_frame = self.rtp_builder.create_rtp_audio_frame(
			opus_packet, 
			is_start_of_transmission
		)

		# NEW: Wrap RTP frame in UDP
		udp_frame = self.udp_audio_builder.create_udp_audio_frame(
			rtp_frame,
			source_ip=source_ip,
			dest_ip=dest_ip
		)

		# Wrap UDP frame in Opulent Voice header
		ov_header = struct.pack(
			'>2s 6s B 3s B',
			self.STREAM_SYNCH_WORD,
			self.station_id_bytes,
			self.FRAME_TYPE_AUDIO,
			self.TOKEN,
			0
		)

		return ov_header + udp_frame

	def create_text_frame(self, text_data):
		"""
		Create Opulent Voice text frame with UDP header
		Frame: [OV Header][UDP Header][Text Payload]
		"""
		if isinstance(text_data, str):
			text_data = text_data.encode('utf-8')

		# NEW: Wrap text in UDP
		udp_frame = self.udp_text_builder.create_udp_text_frame(
			text_data,
			source_ip=source_ip,
			dest_ip=dest_ip
		)

		# Wrap UDP frame in Opulent Voice header
		ov_header = struct.pack(
			'>2s 6s B 3s B',
			self.STREAM_SYNCH_WORD,
			self.station_id_bytes,
			self.FRAME_TYPE_TEXT,
			self.TOKEN,
			0
		)

		return ov_header + udp_frame

	def create_control_frame(self, control_data):
		"""
		Create Opulent Voice control frame with UDP header
		Frame: [OV Header][UDP Header][Control Payload]
		"""
		if isinstance(control_data, str):
			control_data = control_data.encode('utf-8')

		# NEW: Wrap control data in UDP
		udp_frame = self.udp_control_builder.create_udp_control_frame(
			control_data,
			source_ip=source_ip,
			dest_ip=dest_ip
		)

		# Wrap UDP frame in Opulent Voice header
		ov_header = struct.pack(
			'>2s 6s B 3s B',
			self.STREAM_SYNCH_WORD,
			self.station_id_bytes,
			self.FRAME_TYPE_CONTROL,
			self.TOKEN,
			0
		)

		return ov_header + udp_frame

	def create_data_frame(self, data):
		"""
		Create Opulent Voice data frame (NO UDP - will get TCP later)
		Frame: [OV Header][Data Payload]
		"""
		# Data frames don't get UDP yet - they'll get TCP in the next phase
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
		Parse Opulent Voice audio frame and extract UDP + RTP + OPUS
		Expected: [OV Header][UDP Header][RTP Header][OPUS Payload]
		"""
		if len(frame_data) < self.HEADER_SIZE + UDPHeader.HEADER_SIZE + 12:  # OV + UDP + RTP minimum
			return None

		try:
			# Parse Opulent Voice header
			ov_header = struct.unpack('>2s 6s B 3s B', frame_data[:self.HEADER_SIZE])
			synch, station_bytes, frame_type, token, reserved = ov_header

			if synch != self.STREAM_SYNCH_WORD or frame_type != self.FRAME_TYPE_AUDIO:
				return None

			# Extract UDP frame (everything after OV header)
			udp_frame = frame_data[self.HEADER_SIZE:]

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
				'udp_info': udp_info,
				'rtp_info': rtp_info,
				'opus_payload': opus_payload,
				'total_size': len(frame_data)
			}

		except struct.error:
			return None

	def parse_text_frame(self, frame_data):
		"""
		Parse Opulent Voice text frame and extract UDP + text
		Expected: [OV Header][UDP Header][Text Payload]
		"""
		if len(frame_data) < self.HEADER_SIZE + UDPHeader.HEADER_SIZE:
			return None

		try:
			# Parse Opulent Voice header
			ov_header = struct.unpack('>2s 6s B 3s B', frame_data[:self.HEADER_SIZE])
			synch, station_bytes, frame_type, token, reserved = ov_header

			if synch != self.STREAM_SYNCH_WORD or frame_type != self.FRAME_TYPE_TEXT:
				return None

			# Extract UDP frame
			udp_frame = frame_data[self.HEADER_SIZE:]\

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
				'udp_info': udp_info,
				'text_payload': text_payload,
				'total_size': len(frame_data)
			}

		except struct.error:
			return None

	def parse_control_frame(self, frame_data):
		"""
		Parse Opulent Voice control frame and extract UDP + control data
		Expected: [OV Header][UDP Header][Control Payload]
		"""
		if len(frame_data) < self.HEADER_SIZE + UDPHeader.HEADER_SIZE:
			return None

		try:
			# Parse Opulent Voice header
			ov_header = struct.unpack('>2s 6s B 3s B', frame_data[:self.HEADER_SIZE])
			synch, station_bytes, frame_type, token, reserved = ov_header

			if synch != self.STREAM_SYNCH_WORD or frame_type != self.FRAME_TYPE_CONTROL:
				return None

			# Extract UDP frame
			udp_frame = frame_data[self.HEADER_SIZE:]

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

		return {
			'station_id': str(self.station_id),
			'rtp': rtp_stats,
			'udp_audio': udp_audio_stats,
			'udp_text': udp_text_stats,
			'udp_control': udp_control_stats,
			'frame_sizes': {
				'audio_total': 13 + 8 + 12 + 80,  # OV + UDP + RTP + OPUS = 113 bytes
				'text_variable': 13 + 8,           # OV + UDP + text (variable)
				'control_variable': 13 + 8,       # OV + UDP + control (variable)
				'data_variable': 13                # OV + data (variable, no UDP yet)
			}
		}

	def station_id_to_string(self, station_id_bytes):
		"""Convert 6-byte station ID to readable string"""
		try:
			station_id = StationIdentifier.from_bytes(station_id_bytes)
			return str(station_id)
		except:
			return station_id_bytes.hex().upper()






class OpulentVoiceProtocolWithIP:
	"""
	Enhanced Opulent Voice Protocol with IP support

	Frame structures:
	- Audio:   [OV Header][IP Header][UDP Header][RTP Header][OPUS Payload]
	- Text:    [OV Header][IP Header][UDP Header][Text Payload] 
	- Control: [OV Header][IP Header][UDP Header][Control Payload]
	- Data:    [OV Header][Data Payload] (no IP/UDP yet - will get TCP later)
	"""

	# Keep existing constants
	#STREAM_SYNCH_WORD = b'\xFF\x5D'
	#FRAME_TYPE_AUDIO = 0x01
	#FRAME_TYPE_TEXT = 0x02
	#FRAME_TYPE_CONTROL = 0x03
	#FRAME_TYPE_DATA = 0x04
	TOKEN = b'\xBB\xAA\xDD'
	RESERVED = b'\x00\x00\x00'

	HEADER_SIZE = 12

	# Protocol ports (embedded in UDP headers, might want to move to config file)
	PROTOCOL_PORT_VOICE = 57373
	PROTOCOL_PORT_TEXT = 57374
	PROTOCOL_PORT_CONTROL = 57375

	def __init__(self, station_identifier, dest_ip="192.168.1.100"):
		"""Initialize protocol with IP support"""
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

		print(f"📻 Station ID: {self.station_id} (Base-40: 0x{self.station_id.encoded_value:012X})")
		print(f"🎵 RTP SSRC: 0x{self.rtp_builder.rtp_header.ssrc:08X}")
		print(f"📦 UDP Ports: Audio/Text/Control → {self.PROTOCOL_PORT_VOICE}/{self.PROTOCOL_PORT_TEXT}/{self.PROTOCOL_PORT_CONTROL}")
		print(f"🌐 IP Destination: {dest_ip}")
		print(f"🌐 IP Source: {self.source_ip}")

	def _get_local_ip_once(self):
		"""Get local IP address once at startup"""
		try:
			with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
				s.connect((self.dest_ip, 80))
			return s.getsockname()[0]
		except:
			return "127.0.0.1"


	def create_audio_frame(self, opus_packet, is_start_of_transmission=False):
		"""
		Create Opulent Voice audio frame with IP + UDP + RTP headers
		Frame: [OV Header][IP Header][UDP Header][RTP Header][OPUS Payload]
		"""
		# Create RTP frame (RTP header + OPUS payload)
		rtp_frame = self.rtp_builder.create_rtp_audio_frame(
			opus_packet,
			is_start_of_transmission
		)

		# Wrap RTP frame in UDP
		udp_frame = self.udp_audio_builder.create_udp_audio_frame(
			rtp_frame,
                        source_ip=self.source_ip,    # Use cached IP
                        dest_ip=self.dest_ip         # Use cached IP
                )

		# Wrap UDP frame in IP
		ip_frame = self.ip_audio_builder.create_ip_audio_frame(udp_frame)

		# Apply COBS encoding to the complete IP frame
		cobs_encoded_frame = self.cobs_manager.encode_frame(ip_frame)

		# Wrap COBS frame in Opulent Voice header
		ov_header = struct.pack(
			'>6s 3s 3s',
			self.station_id_bytes,
			self.TOKEN,
			self.RESERVED
		)

		return ov_header + cobs_encoded_frame

	def create_text_frame(self, text_data):
		"""
		Create Opulent Voice text frame with COBS + IP + UDP + RTP
		Frame: [OV Header][COBS([IP Header][UDP Header][RTP Header][OPUS])][Zero Delimiter]
		"""
		if isinstance(text_data, str):
			text_data = text_data.encode('utf-8')

		# Wrap text in UDP
		udp_frame = self.udp_text_builder.create_udp_text_frame(
			text_data,
			source_ip=self.source_ip,    # Use cached IP
			dest_ip=self.dest_ip         # Use cached IP
		)

		# Wrap UDP frame in IP
		ip_frame = self.ip_text_builder.create_ip_text_frame(udp_frame)

		# Wrap IP frame in COBS
		cobs_encoded_frame = self.cobs_manager.encode_frame(ip_frame)

		# Wrap IP frame in Opulent Voice header
		ov_header = struct.pack(
			'>6s 3s 3s',
			self.station_id_bytes,
			self.TOKEN,
			self.RESERVED
		)

		return ov_header + cobs_encoded_frame


	def create_control_frame(self, control_data):
		"""
		Create Opulent Voice control frame with COBS + IP + UDP headers
		Frame: [OV Header][COBS([IP Header][UDP Header][Control])][Zero Delimiter]
		"""
		if isinstance(control_data, str):
			control_data = control_data.encode('utf-8')

		# Wrap control data in UDP
		udp_frame = self.udp_control_builder.create_udp_control_frame(
			control_data,
                        source_ip=self.source_ip,    # Use cached IP
                        dest_ip=self.dest_ip         # Use cached IP
                )


		# Wrap UDP frame in IP
		ip_frame = self.ip_control_builder.create_ip_control_frame(udp_frame)

		# Apply COBS encoding to the whole IP frame
		cobs_encoded_frame = self.cobs_manager.encode_frame(ip_frame)

        	# Wrap IP frame in Opulent Voice header
		ov_header = struct.pack(
			'>6s 3s 3s',
			self.station_id_bytes,
			self.TOKEN,
			self.RESERVED
		)

		return ov_header + cobs_encoded_frame

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

		return {
			'station_id': str(self.station_id),
			'rtp': rtp_stats,
			'udp_audio': udp_audio_stats,
			'udp_text': udp_text_stats,
			'udp_control': udp_control_stats,
			'ip_audio': ip_audio_stats,
			'ip_text': ip_text_stats,
			'ip_control': ip_control_stats,
			'frame_sizes': {
				'audio_total': 13 + 20 + 8 + 12 + 80,      # OV + IP + UDP + RTP + OPUS = 133 bytes
				'text_variable': 13 + 20 + 8,              # OV + IP + UDP + text (variable) = 41 + text
				'control_variable': 13 + 20 + 8,           # OV + IP + UDP + control (variable) = 41 + control
				'data_variable': 13                        # OV + data (variable, no IP/UDP yet)
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
#		checksum = 111 # "wrong checksum" test for receiver

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










# Copy these classes from the second artifact:

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

class MessageFragmenter:
	"""Breaks long messages into 40ms frame-sized chunks"""

	def __init__(self, max_payload_per_frame: int = 800):
		self.max_payload_per_frame = max_payload_per_frame
		self.next_sequence_id = 1

	def fragment_message(self, message_data: bytes, frame_type: FrameType, priority: FramePriority) -> List[StreamFrame]:
		"""Fragment a message into 40ms-frame-sized chunks"""
		if len(message_data) <= self.max_payload_per_frame:
			# Single frame message
			return [StreamFrame(
				frame_type=frame_type,
				priority=priority,
				data=message_data,
				timestamp=time.time(),
				is_continuation=False,
				sequence_id=0
			)]

		# Multi-frame message
		fragments = []
		sequence_id = self.next_sequence_id
		self.next_sequence_id += 1

		for i in range(0, len(message_data), self.max_payload_per_frame):
			chunk = message_data[i:i + self.max_payload_per_frame]

			# Add fragmentation header to chunk
			is_first = (i == 0)
			is_last = (i + len(chunk) >= len(message_data))

			# Create fragment header (4 bytes)
			fragment_header = struct.pack('>H B B',
				sequence_id,              # 2 bytes: sequence ID
				1 if is_first else 0,     # 1 byte: first flag
				1 if is_last else 0       # 1 byte: last flag
			)

			fragment_data = fragment_header + chunk

			fragments.append(StreamFrame(
				frame_type=frame_type,
				priority=priority,
				data=fragment_data,
				timestamp=time.time(),
				is_continuation=(not is_first),
				sequence_id=sequence_id
			))

		return fragments









class ContinuousStreamManager:
	"""Manages the continuous 40ms frame stream"""

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
	#	import traceback
	#	print(f"🚀 40ms stream STARTED (triggered by: {triggered_by})")
	#	print("DEBUG: Stream started by:")
	#	traceback.print_stack()









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





class Frame40msScheduler:
	"""Schedules what goes into each 40ms frame based on priority and availability"""
	
	def __init__(self, keepalive_interval: float = 2.0):
		# Priority queues - Voice > Control > Text
		self.voice_queue = Queue()      # Immediate priority (PTT audio)
		self.control_queue = Queue()    # High priority (A5 auth, system)
		self.text_queue = Queue()       # Normal priority (chat)
		
		# Stream management
		self.stream_manager = ContinuousStreamManager()
		
		# Keepalive for stream maintenance
		self.keepalive_interval = keepalive_interval
		self.last_keepalive_time = 0
		
		# Current state
		self.current_voice_frame = None
		self.voice_active = False
		
		# Statistics
		self.stats = {
			'total_frames_sent': 0,
			'voice_frames_sent': 0,
			'control_frames_sent': 0,
			'text_frames_sent': 0,
			'keepalive_frames_sent': 0,
			'voice_interruptions': 0,
			'last_frame_type': None
		}
	
	def set_voice_frame(self, opus_packet: bytes):
		"""Set the current voice frame (called from audio callback)"""
		self.current_voice_frame = opus_packet
		self.voice_active = True
		# Voice activity starts/maintains the stream
		self.stream_manager.activity_detected("voice")
	
	def clear_voice_frame(self):
		"""Clear voice frame (PTT released)"""
		self.current_voice_frame = None
		self.voice_active = False
		# Note: Stream continues running even after PTT release
	
	def queue_text_message(self, text_data: str):
		"""Queue a text message for 40ms frame transmission"""
		if isinstance(text_data, str):
			text_data = text_data.encode('utf-8')
		
		# Fragment the message
		fragmenter = MessageFragmenter()
		fragments = fragmenter.fragment_message(
			text_data, 
			FrameType.TEXT, 
			FramePriority.TEXT
		)
		
		# Queue all fragments
		for fragment in fragments:
			self.text_queue.put(fragment)
		
		# Text activity starts/maintains the stream
		self.stream_manager.activity_detected("text")
	
	def queue_control_message(self, control_data: bytes):
		"""Queue a control message for 40ms frame transmission"""
		# Fragment the message
		fragmenter = MessageFragmenter()
		fragments = fragmenter.fragment_message(
			control_data,
			FrameType.CONTROL,
			FramePriority.CONTROL
		)
		
		# Queue all fragments with high priority
		for fragment in fragments:
			self.control_queue.put(fragment)
		
		# Control activity starts/maintains the stream
		self.stream_manager.activity_detected("control")
	
	def get_next_frame_content(self) -> Optional[StreamFrame]:
		"""Determine what content goes in the next 40ms frame"""
		current_time = time.time()
		
		# Check if stream should stop due to inactivity
		if self.stream_manager.should_stop_stream():
			return None  # Signal to stop the stream
		
		# Highest priority: Voice (interrupts everything)
		if self.voice_active and self.current_voice_frame:
			opus_data = self.current_voice_frame
			self.current_voice_frame = None  # Consume the frame
			
			# Check if we're interrupting non-voice transmission
			if self.stats['last_frame_type'] and self.stats['last_frame_type'] != FrameType.VOICE:
				self.stats['voice_interruptions'] += 1
				print(f"🎤 Voice interrupting {self.stats['last_frame_type'].name} transmission")
			
			self.stats['voice_frames_sent'] += 1
			self.stats['last_frame_type'] = FrameType.VOICE
			return StreamFrame(
				frame_type=FrameType.VOICE,
				priority=FramePriority.VOICE,
				data=opus_data,
				timestamp=current_time
			)
		
		# Second priority: Control messages
		try:
			control_frame = self.control_queue.get_nowait()
			self.stats['control_frames_sent'] += 1
			self.stats['last_frame_type'] = FrameType.CONTROL
			return control_frame
		except Empty:
			pass
		
		# Third priority: Text messages
		try:
			text_frame = self.text_queue.get_nowait()
			self.stats['text_frames_sent'] += 1
			self.stats['last_frame_type'] = FrameType.TEXT
			return text_frame
		except Empty:
			pass
		
		# Keepalive to maintain stream when no content available
		time_since_keepalive = current_time - self.last_keepalive_time
		if time_since_keepalive >= self.keepalive_interval:
			keepalive_data = f"KEEPALIVE:{int(current_time)}".encode('utf-8')
			self.stats['keepalive_frames_sent'] += 1
			self.stats['last_frame_type'] = FrameType.KEEPALIVE
			self.last_keepalive_time = current_time
			
			# Keepalive maintains stream activity
			self.stream_manager.activity_detected("keepalive")
			
			return StreamFrame(
				frame_type=FrameType.KEEPALIVE,
				priority=FramePriority.KEEPALIVE,
				data=keepalive_data,
				timestamp=current_time
			)
		
		# No content available and no keepalive needed yet
		#return StreamFrame(
		#	frame_type=FrameType.KEEPALIVE,
		#	priority=FramePriority.KEEPALIVE,
		#	data=b"",  # Empty frame
		#	timestamp=current_time
		#)
		return None # don't return an empty frame - it just confuses us



	def get_queue_status(self) -> Dict[str, int]:
		"""Get current queue lengths and stream status"""
		return {
			'voice_active': self.voice_active,
			'control_queue': self.control_queue.qsize(),
			'text_queue': self.text_queue.qsize(),
			'stream_status': self.stream_manager.get_stream_status()
		}








class Frame40msTransmitter:
	"""Continuous 40ms Frame Stream Transmitter"""
	
	def __init__(self, station_identifier, protocol_with_cobs, network_transmitter):
		self.station_id = station_identifier
		self.protocol = protocol_with_cobs  # Your COBS-enabled protocol
		self.network_transmitter = network_transmitter
		self.scheduler = Frame40msScheduler()
		
		# Timing control
		self.frame_timer = None
		self.running = False
		self.frame_interval = 0.040  # 40ms
		
		print(f"📡 Continuous 40ms transmitter ready for {station_identifier}")
	
	def start_stream_if_needed(self):
		"""Start the 40ms stream if not already running"""
		if not self.running:
			self.running = True
			self._schedule_next_frame()
			print(f"🚀 40ms continuous stream STARTED for {self.station_id}")
	
	def stop_stream(self):
		"""Force stop the 40ms stream"""
		self.running = False
		if self.frame_timer:
			self.frame_timer.cancel()
		self.scheduler.stream_manager.stop_stream()
		print(f"🛑 40ms continuous stream STOPPED for {self.station_id}")
	
	def _schedule_next_frame(self):
		"""Schedule the next 40ms frame transmission"""
		if not self.running:
			return
		
		# Schedule next frame
		self.frame_timer = threading.Timer(self.frame_interval, self._transmit_frame)
		self.frame_timer.start()
	
	def _transmit_frame(self):
		"""Transmit one 40ms frame"""
		try:
			# Get next frame content from scheduler
			frame_content = self.scheduler.get_next_frame_content()
			
			# Check if stream should stop
			if frame_content is None:
				print("📡 Stream stopping due to inactivity")
				self.stop_stream()
				return
			
			# Skip empty frames
			if len(frame_content.data) == 0:
				print("📡 40ms slot: Empty frame (no content)")
				self._schedule_next_frame()
				return
			
			# Create frame using your existing methods
			if frame_content.frame_type == FrameType.VOICE:
				complete_frame = self.protocol.create_audio_frame(frame_content.data)
			elif frame_content.frame_type == FrameType.CONTROL:
				complete_frame = self.protocol.create_control_frame(frame_content.data)
			elif frame_content.frame_type == FrameType.TEXT:
				complete_frame = self.protocol.create_text_frame(frame_content.data)
			else:  # KEEPALIVE
				complete_frame = self.protocol.create_control_frame(frame_content.data)
			
			# Transmit the frame
			success = self.network_transmitter.send_frame(complete_frame)
			
			if success:
				self.scheduler.stats['total_frames_sent'] += 1
				print(f"📡 40ms frame: {frame_content.frame_type.name} ({len(complete_frame)}B)")
			else:
				print(f"✗ Failed to send 40ms frame: {frame_content.frame_type.name}")
				
		except Exception as e:
			print(f"✗ Frame transmission error: {e}")
		
		# Schedule next frame
		self._schedule_next_frame()
	
	# Interface methods for your existing code
	def queue_text_message(self, text_data: str):
		"""Queue text message and start stream if needed"""
		self.scheduler.queue_text_message(text_data)
		self.start_stream_if_needed()
		print(f"📝 Queued text message for continuous 40ms stream: {text_data[:50]}...")
	
	def queue_control_message(self, control_data: bytes):
		"""Queue control message and start stream if needed"""
		self.scheduler.queue_control_message(control_data)
		self.start_stream_if_needed()
		print(f"📋 Queued control message for continuous 40ms stream")
	
	def set_voice_active(self, active: bool, opus_packet: bytes = None):
		"""Set voice state and start stream if needed"""
		if active and opus_packet:
			self.scheduler.set_voice_frame(opus_packet)
			self.start_stream_if_needed()
		else:
			self.scheduler.clear_voice_frame()
	
	def get_transmission_stats(self) -> Dict:
		"""Get comprehensive transmission statistics"""
		return {
			'scheduler_stats': self.scheduler.stats,
			'queue_status': self.scheduler.get_queue_status(),
			'stream_status': self.scheduler.stream_manager.get_stream_status(),
			'frame_interval_ms': self.frame_interval * 1000,
			'running': self.running
		}





class ChatManager40ms:
	"""Modified ChatManager that works with 40ms frame streaming"""
	
	def __init__(self, station_id, frame_transmitter):
		self.station_id = station_id
		self.frame_transmitter = frame_transmitter
		self.ptt_active = False
		self.pending_messages = []
	
	def set_ptt_state(self, active: bool):
		"""Called when PTT state changes"""
		was_active = self.ptt_active
		self.ptt_active = active
		
		# If PTT just released, flush buffered messages to 40ms frame system
		if was_active and not active:
			self.flush_buffered_messages()
	
	def handle_message_input(self, message_text: str) -> Dict:
		"""Handle new message input - queue for 40ms transmission"""
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
			# Queue for 40ms transmission immediately
			self.queue_message_for_transmission(message_text.strip())
			return {
				'status': 'queued_40ms',
				'action': 'show_queued',
				'message': message_text.strip()
			}
	
	def queue_message_for_transmission(self, message_text: str):
		"""Queue message for 40ms frame transmission"""
		self.frame_transmitter.queue_text_message(message_text)
	
	def flush_buffered_messages(self):
		"""Send all buffered messages to 40ms frame system after PTT release"""
		if not self.pending_messages:
			return []
		
		sent_messages = []
		for message in self.pending_messages:
			self.queue_message_for_transmission(message)
			sent_messages.append(message)
		
		# Show summary
		if len(sent_messages) == 1:
			print(f"💬 Queued buffered message for 40ms transmission: {sent_messages[0]}")
		else:
			print(f"💬 Queued {len(sent_messages)} buffered messages for 40ms transmission")
		
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
	def __init__(self, station_identifier, ptt_pin=23, led_pin=17, target_ip="192.168.2.1", target_port=57372):
		# Store station identifier
		self.station_id = station_identifier

		# Message queue system
		#self.message_queue = MessagePriorityQueue()

		# Chat management system
		#self.chat_manager = ChatManager(self.station_id)
		#self.chat_manager.set_message_queue(self.message_queue)

		# GPIO setup with gpiozero
		self.ptt_button = Button(ptt_pin, pull_up=True, bounce_time=0.02)
		self.led = LED(led_pin) # will need more led names for indicator lights
		self.ptt_active = False

		# Audio configuration
		self.sample_rate = 48000
		self.bitrate = 16000
		self.channels = 1
		self.frame_duration_ms = 40
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

		# Network setup - pass station identifier to protocol
		self.protocol = OpulentVoiceProtocolWithIP(station_identifier, dest_ip=args.ip)
		self.transmitter = NetworkTransmitter(target_ip, target_port)

		# frame transmitter setup
		self.frame_transmitter = Frame40msTransmitter(
			station_identifier,
			self.protocol,
			self.transmitter
		)

		# 40ms-aware chat manager
		self.chat_manager = ChatManager40ms(self.station_id, self.frame_transmitter)

		# Audio setup
		self.audio = pyaudio.PyAudio()
		self.audio_input_stream = None

		# Statistics
		self.audio_stats = {
			'frames_encoded': 0,
			'frames_sent': 0,
			'encoding_errors': 0,
			'invalid_frames': 0
		}

		# Background transmission thread
		#self.tx_thread = None
		#self.tx_running = False

		# Chat interface - now uses ChatManager
		self.chat_interface = TerminalChatInterface(self.station_id, self.chat_manager)

		self.setup_gpio_callbacks()
		self.setup_audio()

	def setup_gpio_callbacks(self):
		"""Setup PTT button callbacks"""
		self.ptt_button.when_pressed = self.ptt_pressed
		self.ptt_button.when_released = self.ptt_released
		DebugConfig.debug_print(f"✓ GPIO setup: PTT=GPIO{self.ptt_button.pin}, LED=GPIO{self.led.pin}")

	def setup_audio(self):
		"""Setup audio input"""
		try:
			self.audio_input_stream = self.audio.open(
				format=pyaudio.paInt16,
				channels=self.channels,
				rate=self.sample_rate,
				input=True,
				frames_per_buffer=self.samples_per_frame,
				stream_callback=self.audio_callback
			)
			DebugConfig.debug_print("✓ Audio input stream ready")
		except Exception as e:
			DebugConfig.system_print(f"✗ Audio setup error: {e}")

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



	def audio_callback(self, in_data, frame_count, time_info, status):
		"""Process audio input - feeds into continuous 40ms stream"""
		if self.ptt_active:
			if not self.validate_audio_frame(in_data):
				self.audio_stats['invalid_frames'] += 1
				return (None, pyaudio.paContinue)

			try:
				opus_packet = self.encoder.encode(in_data, self.samples_per_frame)
				self.audio_stats['frames_encoded'] += 1

				# Validate Opulent Voice Protocol constraint
				if not self.validate_opus_packet(opus_packet):
					self.audio_stats['invalid_frames'] += 1
					DebugConfig.debug_print(f"⚠ Dropping invalid OPUS packet")
					return (None, pyaudio.paContinue)

				# CHANGE: Feed voice into continuous stream instead of immediate send
				self.frame_transmitter.set_voice_active(True, opus_packet)
				self.audio_stats['frames_sent'] += 1

			except ValueError as e:
				self.audio_stats['encoding_errors'] += 1
				DebugConfig.debug_print(f"✗ Protocol violation: {e}")
			except Exception as e:
				self.audio_stats['encoding_errors'] += 1
				DebugConfig.debug_print(f"✗ Encoding error: {e}")
		else:
			# CHANGE: Clear voice but don't stop stream
			self.frame_transmitter.set_voice_active(False)

		return (None, pyaudio.paContinue)



















	# old audio callback - before COBS and moving everything to 40ms
	def audio_callback_old(self, in_data, frame_count, time_info, status):
		"""Process audio input when PTT is active - NOW WITH RTP"""
		if self.ptt_active:
			if not self.validate_audio_frame(in_data):
				self.audio_stats['invalid_frames'] += 1
				return (None, pyaudio.paContinue)

			try:
				opus_packet = self.encoder.encode(in_data, self.samples_per_frame)
				self.audio_stats['frames_encoded'] += 1

				# NEW: Validate Opulent Voice Protocol constraint
				if not self.validate_opus_packet(opus_packet):
					self.audio_stats['invalid_frames'] += 1
					DebugConfig.debug_print(f"⚠ Dropping invalid OPUS packet")
					return (None, pyaudio.paContinue)
				if self.send_voice_frame_immediate(opus_packet):
					self.audio_stats['frames_sent'] += 1
			except ValueError as e:
				self.audio_stats['encoding_errors'] += 1
				DebugConfig.debug_print(f"✗ Protocol violation: {e}")
			except Exception as e:
				self.audio_stats['encoding_errors'] += 1
				DebugConfig.debug_print(f"✗ Encoding error: {e}")
		return (None, pyaudio.paContinue)






	def ptt_pressed(self):
		"""PTT button pressed - send control message first, then enable voice"""
		# Send PTT_START control message FIRST
		self.frame_transmitter.queue_control_message(b"PTT_START")

		# then enable voice
		"""PTT button pressed - voice joins continuous stream"""
		self.ptt_active = True
		self.chat_manager.set_ptt_state(True)

		self.protocol.notify_ptt_pressed()
		self._is_first_voice_frame = True
		DebugConfig.user_print(f"\n🎤 {self.station_id}: PTT pressed - voice joining stream")

		# turn led on
		self.led.on()


	def ptt_released(self):
		"""PTT button released - stream continues"""
		self.ptt_active = False
		self.chat_manager.set_ptt_state(False)

		# CHANGE: Send control message through continuous stream
		self.frame_transmitter.queue_control_message(b"PTT_STOP")
		self.protocol.notify_ptt_released()
		DebugConfig.user_print(f"\n🔇 {self.station_id}: PTT released - stream continues")

		time.sleep(0.1)
		if DebugConfig.VERBOSE:
			self.print_stats()

		# turn led off
		self.led.off()






	def print_stats(self):
		"""Print transmission statistics"""
		audio_stats = self.audio_stats
		net_stats = self.transmitter.get_stats()

		# CHANGE: Get stats from frame transmitter instead of message queue
		stream_stats = self.frame_transmitter.get_transmission_stats()

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
		print("🧪 Testing GPIO...")
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

		# Create EXACTLY 80-byte test payload (simple approach)
		test_message = "OPULENT_VOICE_80_BYTE_TEST_PAYLOAD_"
		# Pad to exactly 80 bytes
		test_opus_payload = (test_message * 10)[:80].encode('utf-8')
		# Ensure exactly 80 bytes
		if len(test_opus_payload) < 80:
			test_opus_payload += b'\x00' * (80 - len(test_opus_payload))
		test_opus_payload = test_opus_payload[:80]  # Truncate if over

		print(f"   📏 Test OPUS payload: {len(test_opus_payload)}B (protocol-compliant)")

		try:
			# Test the RTP audio frame creation
			test_frame = self.protocol.create_audio_frame(test_opus_payload, is_start_of_transmission=True)

			if self.transmitter.send_frame(test_frame):
				print("   ✓ Test RTP audio frame sent successfully")
				rtp_stats = self.protocol.rtp_builder.get_rtp_stats()
				print(f"   📡 Frame structure: OV(12B) + IP(20B) + UDP(8B) + RTP(12B) + OPUS(80B) = {len(test_frame)}B total")
				print(f"   📡 RTP SSRC: 0x{rtp_stats['ssrc']:08X}")
			else:
				print("   ✗ Test RTP audio frame failed")
		except ValueError as e:
			print(f"   ✗ Protocol validation error: {e}")
		except Exception as e:
			print(f"   ✗ Unexpected error in test_network: {e}")
			traceback.print_exc()

		# Test regular text frame (no RTP)
		test_text = "Test text message (no RTP)"
		try:
			text_frame = self.protocol.create_text_frame(test_text)
			if self.transmitter.send_frame(text_frame):
				print("   ✓ Test text frame sent successfully (no RTP)")
			else:
				print("   ✗ Test text frame failed")
		except Exception as e:
			print(f"   ✗ Text frame error: {e}")
			traceback.print_exc()




	def test_chat(self):
		"""Test chat functionality with continuous stream"""
		print("💬 Testing continuous stream chat system...")
	
		# Send a test chat message (should start stream)
		test_msg = f"Test message from {self.station_id}"
		self.frame_transmitter.queue_text_message(test_msg)
		print(f"   ✓ Test chat message queued: {test_msg}")
	
		# Send a control message
		self.frame_transmitter.queue_control_message(b"TEST_CONTROL")
		print(f"   ✓ Test control message queued")
	
		# Brief wait to see if stream starts
		time.sleep(1.0)
	
		# Check stream status
		stats = self.frame_transmitter.get_transmission_stats()
		print(f"   Stream running: {stats['running']}")
		print(f"   Queue status: {stats['queue_status']}")








	def start(self):
		"""Start the continuous stream system"""
		if self.audio_input_stream:
			self.audio_input_stream.start_stream()
	
		# REMOVE: Start background transmission (stream starts automatically)
		# self.start_background_transmission()  # Remove this line
	
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
		# CHANGE: Stop frame transmitter instead of old tx thread
		self.frame_transmitter.stop_stream()
	
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
	
	def __init__(self, listen_port=57373, chat_interface=None):
		self.listen_port = listen_port
		self.chat_interface = chat_interface
		self.socket = None
		self.running = False
		self.receive_thread = None
		self.protocol = OpulentVoiceProtocol(StationIdentifier("TEMP"))  # Temp for parsing
		
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
		"""Process received data and route based on frame type"""
		try:
			frame = self.protocol.parse_frame(data)
			if not frame:
				return
			
			from_station = str(frame['station_id']) if frame['station_id'] else "UNKNOWN"
			frame_type = frame['type']
			payload = frame['payload']
			
			if frame_type == self.protocol.FRAME_TYPE_TEXT:
				# Handle chat message
				try:
					message = payload.decode('utf-8')
					print(f"\n📨 [{from_station}]: {message}")
					if self.chat_interface:
						# Re-display chat prompt
						print(f"[LOCAL] Chat> ", end='', flush=True)
				except UnicodeDecodeError:
					print(f"📨 [{from_station}]: <Binary text data>")
			
			elif frame_type == self.protocol.FRAME_TYPE_CONTROL:
				# Handle control message
				try:
					control_msg = payload.decode('utf-8')
					print(f"📋 [{from_station}] Control: {control_msg}")
				except UnicodeDecodeError:
					print(f"📋 [{from_station}] Control: <Binary data>")
			
			elif frame_type == self.protocol.FRAME_TYPE_AUDIO:
				# Handle voice data (for future decode/playback)
				print(f"🎤 [{from_station}] Voice: {len(payload)}B")
			
			elif frame_type == self.protocol.FRAME_TYPE_DATA:
				# Handle data transfer
				print(f"📁 [{from_station}] Data: {len(payload)}B")
			
			else:
				print(f"❓ [{from_station}] Unknown frame type: {frame_type}")
				
		except Exception as e:
			print(f"Error processing received data: {e}")


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
if __name__ == "__main__":
	print("-=" * 40)
	print("Opulent Voice Radio with Terminal Chat - Phase 1")
	print("-=" * 40)

	try:
		args = parse_arguments()
		
		# Set debug mode based on arguments
		DebugConfig.set_mode(verbose=args.verbose, quiet=args.quiet)
		
		# Test the base-40 encoding first
		if DebugConfig.VERBOSE:
			test_base40_encoding()
		
		# Create station identifier from command line args
		station_id = StationIdentifier(args.callsign)
		
		DebugConfig.system_print(f"📡 Station: {station_id}")
		DebugConfig.system_print(f"📡 Target: {args.ip}:{args.port}")
		DebugConfig.system_print(f"👂 Listen: Port {args.listen_port}")
		if DebugConfig.VERBOSE:
			DebugConfig.debug_print("💡 Use --help for configuration options")
		DebugConfig.system_print("")  # Empty line

		# Create message receiver
		receiver = MessageReceiver(listen_port=args.listen_port)
		receiver.start()

		if args.chat_only:
			print("💬 Chat-only mode (no GPIO/audio)")
			
			# Simple chat-only implementation for testing
			chat_manager = ChatManager(station_id)
			message_queue = MessagePriorityQueue()
			chat_manager.set_message_queue(message_queue)
			
			chat_interface = TerminalChatInterface(station_id, chat_manager)
			receiver.chat_interface = chat_interface
			
			# Create minimal transmitter for chat
			transmitter = NetworkTransmitter(args.ip, args.port)
			protocol = OpulentVoiceProtocol(station_id)
			
			chat_interface.start()
			
			print(f"\n✅ {station_id} Chat system ready. Type messages or 'quit' to exit.")
			print("💡 Commands: 'status' (show chat status), 'clear' (clear buffered), 'quit' (exit)")
			
			# Simple transmission loop for chat-only mode
			try:
				while chat_interface.running:
					message = message_queue.get_next_message(timeout=0.1)
					if message and message.msg_type == MessageType.TEXT:
						frame = protocol.create_text_frame(message.data)
						if transmitter.send_frame(frame):
							print(f"📤 Transmitted: {message.data.decode('utf-8')}")
						message_queue.mark_sent()
					time.sleep(0.1)
			except KeyboardInterrupt:
				pass
			
		else:
			# Full radio system with GPIO and audio
			radio = GPIOZeroPTTHandler(
				station_identifier=station_id,
				ptt_pin=args.ptt_pin, 
				led_pin=args.led_pin,
				target_ip=args.ip,
				target_port=args.port
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
		
		print("Thank you for using Opulent Voice Phase 1!")
