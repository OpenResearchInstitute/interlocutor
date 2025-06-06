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
- Add RTP Headers
"""

import sys
import socket
import struct
import time
import threading
import argparse
import re
from queue import PriorityQueue, Empty
from enum import Enum
import select
import logging
import random

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
		except:
			return station_id_bytes.hex().upper()










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



















class NetworkTransmitter:
	"""UDP Network Transmitter for Opulent Voice"""

	def __init__(self, target_ip="192.168.1.100", target_port=8080):
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






class GPIOZeroPTTHandler:
	def __init__(self, station_identifier, ptt_pin=23, led_pin=17, target_ip="192.168.2.1", target_port=8080):
		# Store station identifier
		self.station_id = station_identifier

		# Message queue system
		self.message_queue = MessagePriorityQueue()

		# Chat management system
		self.chat_manager = ChatManager(self.station_id)
		self.chat_manager.set_message_queue(self.message_queue)

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
		#self.protocol = OpulentVoiceProtocol(station_identifier) # first class, no RTP
		self.protocol = OpulentVoiceProtocolWithRTP(station_identifier)
		print(f"DEBUG: RTP builder type: {type(self.protocol.rtp_builder)}")
		print(f"DEBUG: RTP header type: {type(self.protocol.rtp_builder.rtp_header)}")

		self.transmitter = NetworkTransmitter(target_ip, target_port)

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
		self.tx_thread = None
		self.tx_running = False

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




	# new audio_callback with RTP
	def audio_callback(self, in_data, frame_count, time_info, status):
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


















# old audio callback method, for OPV without RTP at all
	def audio_callback_old(self, in_data, frame_count, time_info, status):
		"""Process audio input when PTT is active"""
		if self.ptt_active:
			# Validate frame first
			if not self.validate_audio_frame(in_data):
				self.audio_stats['invalid_frames'] += 1
				return (None, pyaudio.paContinue)

			try:
				# Encode to OPUS
				opus_packet = self.encoder.encode(in_data, self.samples_per_frame)
				self.audio_stats['frames_encoded'] += 1

				# Send via Opulent Voice Protocol (immediate transmission for voice)
				if self.send_voice_frame_immediate(opus_packet):
					self.audio_stats['frames_sent'] += 1

			except Exception as e:
				self.audio_stats['encoding_errors'] += 1
				DebugConfig.debug_print(f"✗ Encoding error: {e}")
				DebugConfig.debug_print(f"   Frame size: {len(in_data)} bytes")
				DebugConfig.debug_print(f"   Samples: {self.samples_per_frame}")

		return (None, pyaudio.paContinue)











	def send_voice_frame_immediate(self, opus_packet):
		"""Send voice frame immediately (bypass queue for real-time requirement)"""
		# Final PTT check before creating frame and sending
		if not self.ptt_active:
			return False
			
		# Create Opulent Voice frame
		ov_frame = self.protocol.create_audio_frame(opus_packet)
		
		# Send over network immediately
		success = self.transmitter.send_frame(ov_frame)

		if success:
			DebugConfig.debug_print(f"🎤 {self.station_id}: Voice: {len(opus_packet)}B")
		else:
			DebugConfig.debug_print(f"✗ Failed to send voice frame")

		return success

	def start_background_transmission(self):
		"""Start background thread for non-voice message transmission"""
		self.tx_running = True
		self.tx_thread = threading.Thread(target=self._transmission_loop, daemon=True)
		self.tx_thread.start()
		DebugConfig.debug_print("✓ Background transmission thread started")

	def _transmission_loop(self):
		"""Background transmission loop for queued messages"""
		while self.tx_running:
			try:
				# Don't transmit non-voice when PTT is active (voice has priority)
				if self.ptt_active:
					time.sleep(0.01)  # Short sleep during voice transmission
					continue
				
				# Get next message from queue
				message = self.message_queue.get_next_message(timeout=0.1)
				
				if message is None:
					continue  # No messages, continue loop
				
				# Send the message based on type
				success = self._send_queued_message(message)
				
				if success:
					self.message_queue.mark_sent()
					DebugConfig.debug_print(f"📤 Sent {message.msg_type.message_name}: {len(message.data)}B")
				else:
					self.message_queue.mark_dropped()
					DebugConfig.debug_print(f"✗ Failed to send {message.msg_type.message_name}")
				
				# Small delay between non-voice transmissions
				time.sleep(0.05)
				
			except Exception as e:
				DebugConfig.debug_print(f"Transmission loop error: {e}")
				time.sleep(0.1)

	def _send_queued_message(self, message: QueuedMessage):
		"""Send a queued message based on its type"""
		try:
			if message.msg_type == MessageType.TEXT:
				frame = self.protocol.create_text_frame(message.data)
			elif message.msg_type == MessageType.CONTROL:
				frame = self.protocol.create_control_frame(message.data)
			elif message.msg_type == MessageType.DATA:
				frame = self.protocol.create_data_frame(message.data)
			else:
				DebugConfig.debug_print(f"Unknown message type: {message.msg_type}")
				return False
			
			return self.transmitter.send_frame(frame)
			
		except Exception as e:
			DebugConfig.debug_print(f"Error sending {message.msg_type.message_name}: {e}")
			return False



	def ptt_pressed(self):
		"""PTT button pressed - NOTIFY RTP SYSTEM"""
		self.ptt_active = True
		self.chat_manager.set_ptt_state(True)
		self.led.on()

		# NEW: Notify protocol about talk spurt start, which Paul questions
		self.protocol.notify_ptt_pressed()
		self._is_first_voice_frame = True
		DebugConfig.user_print(f"\n🎤 {self.station_id}: PTT: Transmit Start")
		self.message_queue.add_message(MessageType.CONTROL, b"PTT_START")

	def ptt_released(self):
		"""PTT button released - NOTIFY RTP SYSTEM"""
		self.ptt_active = False
		self.chat_manager.set_ptt_state(False)
		self.led.off()

		# NEW: Notify protocol about talk spurt end, which Paul questions
		self.protocol.notify_ptt_released()
		DebugConfig.user_print(f"\n🔇 {self.station_id}: PTT: Transmit Stop")
		self.message_queue.add_message(MessageType.CONTROL, b"PTT_STOP")

		time.sleep(0.1)
		if DebugConfig.VERBOSE:
			self.print_stats()



	# This version is just OPV, without RTP
	def ptt_pressed_old(self):
		"""PTT button pressed"""
		self.ptt_active = True
		self.chat_manager.set_ptt_state(True)  # Notify chat manager
		self.led.on()
		DebugConfig.user_print(f"\n🎤 {self.station_id}: PTT: Transmit Start")
		
		# Send PTT start control message
		self.message_queue.add_message(MessageType.CONTROL, b"PTT_START")

	def ptt_released_old(self):
		"""PTT button released"""
		self.ptt_active = False
		self.chat_manager.set_ptt_state(False)  # Notify chat manager (triggers buffered message flush)
		self.led.off()
		DebugConfig.user_print(f"\n🔇 {self.station_id}: PTT: Transmit Stop")
		
		# Send PTT stop control message
		self.message_queue.add_message(MessageType.CONTROL, b"PTT_STOP")
		
		# Small delay to let buffered messages get processed
		time.sleep(0.1)
		
		if DebugConfig.VERBOSE:
			self.print_stats()









	def print_stats(self):
		"""Print transmission statistics"""
		audio_stats = self.audio_stats
		net_stats = self.transmitter.get_stats()
		queue_stats = self.message_queue.get_stats()

		print(f"\n📊 {self.station_id} Transmission Statistics:")
		print(f"   Voice frames encoded: {audio_stats['frames_encoded']}")
		print(f"   Voice frames sent: {audio_stats['frames_sent']}")
		print(f"   Invalid frames: {audio_stats['invalid_frames']}")
		print(f"   Total network packets: {net_stats['packets_sent']}")
		print(f"   Total bytes sent: {net_stats['bytes_sent']}")
		print(f"   Queue stats: {queue_stats['sent']} sent, {queue_stats['dropped']} dropped, {queue_stats['queue_size']} pending")
		print(f"   Encoding errors: {audio_stats['encoding_errors']}")
		print(f"   Network errors: {net_stats['errors']}")

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
				print(f"   📡 Frame structure: OV(13B) + RTP(12B) + OPUS(80B) = {len(test_frame)}B total")
				print(f"   📡 RTP SSRC: 0x{rtp_stats['ssrc']:08X}")
			else:
				print("   ✗ Test RTP audio frame failed")
		except ValueError as e:
			print(f"   ✗ Protocol validation error: {e}")
		except Exception as e:
			print(f"   ✗ Unexpected error in test_network: {e}")
			import traceback
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













	# old test_network function, OPV without RTP
	def test_network_old(self):
		"""Test network connectivity"""
		print("🌐 Testing network...")
		print(f"   Target: {self.transmitter.target_ip}:{self.transmitter.target_port}")

		test_message = f"OPULENT_VOICE_TEST_MESSAGE_TO_CONFIRM_AUDIO_PACKET_NETWORK_HHHHHHHH_TRANSMISSION"
		test_data = test_message.encode('utf-8')
		test_frame = self.protocol.create_audio_frame(test_data)

		if self.transmitter.send_frame(test_frame):
			print("   ✓ Test frame sent successfully")
		else:
			print("   ✗ Test frame failed")

	def test_chat(self):
		"""Test chat functionality"""
		print("💬 Testing chat system...")
		
		# Send a test chat message
		test_msg = f"Test message from {self.station_id}"
		self.message_queue.add_message(MessageType.TEXT, test_msg.encode('utf-8'))
		print(f"   ✓ Test chat message queued: {test_msg}")
		
		# Brief wait to see if it gets sent
		time.sleep(0.5)

	def start(self):
		"""Start the complete radio system"""
		if self.audio_input_stream:
			self.audio_input_stream.start_stream()
		
		# Start background transmission
		self.start_background_transmission()
		
		# Start chat interface
		self.chat_interface.start()
		
		print(f"\n🚀 {self.station_id} Radio system started")
		print(f"\n🚀 {self.station_id} Radio system started")
		print("📋 Configuration:")
		print(f"   Station: {self.station_id}")
		print(f"   Sample rate: {self.sample_rate} Hz")
		print(f"   Bitrate: {self.bitrate} bps CBR")
		print(f"   Frame size: {self.frame_duration_ms}ms ({self.samples_per_frame} samples)")
		print(f"   Frame rate: {1000/self.frame_duration_ms} fps")
		print(f"   Network target: {self.transmitter.target_ip}:{self.transmitter.target_port}")
		print(f"   Chat interface: Terminal-based")

	def stop(self):
		"""Stop the audio system"""
		self.tx_running = False
		if self.tx_thread:
			self.tx_thread.join(timeout=1.0)
		
		self.chat_interface.stop()
		
		if self.audio_input_stream:
			self.audio_input_stream.stop_stream()
			self.audio_input_stream.close()
		self.audio.terminate()
		print(f"🛑 {self.station_id} Audio system stopped")

	def cleanup(self):
		"""Clean shutdown"""
		self.stop()
		self.transmitter.close()
		self.led.off()
		print(f"Thank you for shopping at Omega Mart. {self.station_id} cleanup complete.")


class MessageReceiver:
	"""Handles receiving and parsing incoming messages"""
	
	def __init__(self, listen_port=8080, chat_interface=None):
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
		default=8080,
		help='Target port for transmission'
	)
	
	parser.add_argument(
		'-l', '--listen-port',
		type=int,
		default=8080,
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
