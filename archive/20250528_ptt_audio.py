#!/usr/bin/env python3
"""
GPIO PTT Audio with Terminal Chat - Phase 1 Foundation
- Voice PTT with OPUS encoding (highest priority)
- Terminal-based keyboard chat interface  
- Priority queue system for message handling
- Background thread for non-voice transmission
- Point-to-point testing while maintaining voice quality
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


class OpulentVoiceProtocol:
	""" 
	Frame format: [Header][Payload]

	Synchronization: 2 bytes, unencoded

	Header: 12 bytes, coded
		Station ID: 6 bytes (callsign + SSID)
		Flags: 3 bytes
			Frame Type: 0x01 Audio, 0x02 Text, 0x03 Auth, 0x4 Data
			BERT: Bit Error Rate Test, 0 = normal payload, 1 = BERT mode active
			EOS: End of Stream Bit, 0 = This is not the last frame, 1 = this is the last frame
		Token: Claimed authorization token, 3 bytes (station generated n-bit PRNG token)
	"""

	STREAM_SYNCH_WORD = b'\xFF\x5D'  # FF5D 
	EOT_SYNCH_WORD = b'\x55\x5D'     # 555D
	FRAME_TYPE_AUDIO = 0x01
	FRAME_TYPE_TEXT = 0x02
	FRAME_TYPE_CONTROL = 0x03
	FRAME_TYPE_DATA = 0x04

	HEADER_SIZE = 14  # 2 (synch) + 6 (station) + 1 (type) + 2 (seq) + 2 (len) + 1 (reserved)

	def __init__(self, station_identifier):
		"""Initialize protocol with station identifier"""
		self.station_id = station_identifier
		self.station_id_bytes = station_identifier.to_bytes()
		self.sequence_counter = 0
		print(f"📻 Station ID: {self.station_id} (Base-40: 0x{self.station_id.encoded_value:012X})")

	def create_frame(self, frame_type: int, payload: bytes):
		"""Create Opulent Voice frame with specified type"""
		self.sequence_counter = (self.sequence_counter + 1) % 65536

		header = struct.pack(
			'>2s 6s B H H B',  # Fixed format: synch + station_id + type + seq + len + reserved
			self.STREAM_SYNCH_WORD,     # 2 bytes
			self.station_id_bytes,      # 6 bytes  
			frame_type,                 # 1 byte
			self.sequence_counter,      # 2 bytes
			len(payload),               # 2 bytes
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
			stream_synch, station_id_bytes, frame_type, sequence, payload_len, reserved = struct.unpack(
				'>2s 6s B H H B', frame_data[:self.HEADER_SIZE]
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
				'sequence': sequence,
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
			return True

		except Exception as e:
			self.stats['errors'] += 1
			print(f"✗ Network send error: {e}")
			return False

	def get_stats(self):
		"""Get transmission statistics"""
		return self.stats.copy()

	def close(self):
		"""Close socket"""
		if self.socket:
			self.socket.close()
			self.socket = None


class TerminalChatInterface:
	"""Non-blocking terminal interface for chat input"""
	
	def __init__(self, station_id, message_queue):
		self.station_id = station_id
		self.message_queue = message_queue
		self.running = False
		self.input_thread = None
		
	def start(self):
		"""Start the chat interface in a separate thread"""
		self.running = True
		self.input_thread = threading.Thread(target=self._input_loop, daemon=True)
		self.input_thread.start()
		
		print("\n" + "="*50)
		print("💬 CHAT INTERFACE READY")
		print("Type messages and press Enter to send")
		print("Voice PTT takes priority - chat will pause during transmission")
		print("Type 'quit' to exit")
		print("="*50)
		print(f"[{self.station_id}] Chat> ", end='', flush=True)
	
	def stop(self):
		"""Stop the chat interface"""
		self.running = False
		if self.input_thread:
			self.input_thread.join(timeout=1.0)
	
	def _input_loop(self):
		"""Input loop running in separate thread"""
		while self.running:
			try:
				# Use select for non-blocking input on Unix systems
				if select.select([sys.stdin], [], [], 0.1)[0]:
					message = sys.stdin.readline().strip()
					
					if message.lower() == 'quit':
						print("\nExiting chat interface...")
						self.running = False
						break
					
					if message:
						# Queue the text message
						self.message_queue.add_message(MessageType.TEXT, message.encode('utf-8'))
						print(f"💬 Queued: {message}")
					
					# Show prompt again
					print(f"[{self.station_id}] Chat> ", end='', flush=True)
				
				time.sleep(0.1)  # Small delay to prevent busy waiting
				
			except Exception as e:
				print(f"Chat input error: {e}")
				break
	
	def display_received_message(self, from_station, message):
		"""Display received chat message"""
		print(f"\n📨 [{from_station}]: {message}")
		print(f"[{self.station_id}] Chat> ", end='', flush=True)


class GPIOZeroPTTHandler:
	def __init__(self, station_identifier, ptt_pin=23, led_pin=17, target_ip="192.168.2.1", target_port=8080):
		# Store station identifier
		self.station_id = station_identifier
		
		# Message queue system
		self.message_queue = MessagePriorityQueue()
		
		# GPIO setup with gpiozero
		self.ptt_button = Button(ptt_pin, pull_up=True, bounce_time=0.02)
		self.led = LED(led_pin)
		self.ptt_active = False

		# Audio configuration
		self.sample_rate = 48000
		self.bitrate = 16000
		self.channels = 1
		self.frame_duration_ms = 40
		self.samples_per_frame = int(self.sample_rate * self.frame_duration_ms / 1000)
		self.bytes_per_frame = self.samples_per_frame * 2

		print(f"🎵 Audio config: {self.sample_rate}Hz, {self.frame_duration_ms}ms frames")
		print(f"   Samples per frame: {self.samples_per_frame}")
		print(f"   Bytes per frame: {self.bytes_per_frame}")

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
			print(f"✓ OPUS encoder ready: {self.bitrate}bps CBR")
		except Exception as e:
			print(f"✗ OPUS encoder error: {e}")
			raise

		# Network setup - pass station identifier to protocol
		self.protocol = OpulentVoiceProtocol(station_identifier)
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

		# Chat interface
		self.chat_interface = TerminalChatInterface(self.station_id, self.message_queue)

		self.setup_gpio_callbacks()
		self.setup_audio()

	def setup_gpio_callbacks(self):
		"""Setup PTT button callbacks"""
		self.ptt_button.when_pressed = self.ptt_pressed
		self.ptt_button.when_released = self.ptt_released
		print(f"✓ GPIO setup: PTT=GPIO{self.ptt_button.pin}, LED=GPIO{self.led.pin}")

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
			print("✓ Audio input stream ready")
		except Exception as e:
			print(f"✗ Audio setup error: {e}")

	def validate_audio_frame(self, audio_data):
		"""Validate audio data before encoding"""
		if len(audio_data) != self.bytes_per_frame:
			print(f"⚠ Invalid frame size: {len(audio_data)} (expected {self.bytes_per_frame})")
			return False
		
		# Check for all-zero frames (might indicate audio issues)
		if audio_data == b'\x00' * len(audio_data):
			print("⚠ All-zero audio frame detected")
			return False
		
		return True

	def audio_callback(self, in_data, frame_count, time_info, status):
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
				print(f"✗ Encoding error: {e}")
				print(f"   Frame size: {len(in_data)} bytes")
				print(f"   Samples: {self.samples_per_frame}")

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
			pass
			# Keep the following comment for debug
			#print(f"🎤 {self.station_id}: Voice: {len(opus_packet)}B")
		else:
			print(f"✗ Failed to send voice frame")

		return success

	def start_background_transmission(self):
		"""Start background thread for non-voice message transmission"""
		self.tx_running = True
		self.tx_thread = threading.Thread(target=self._transmission_loop, daemon=True)
		self.tx_thread.start()
		print("✓ Background transmission thread started")

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
					print(f"📤 Sent {message.msg_type.message_name}: {len(message.data)}B")
				else:
					self.message_queue.mark_dropped()
					print(f"✗ Failed to send {message.msg_type.message_name}")
				
				# Small delay between non-voice transmissions
				time.sleep(0.05)
				
			except Exception as e:
				print(f"Transmission loop error: {e}")
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
				print(f"Unknown message type: {message.msg_type}")
				return False
			
			return self.transmitter.send_frame(frame)
			
		except Exception as e:
			print(f"Error sending {message.msg_type.message_name}: {e}")
			return False

	def ptt_pressed(self):
		"""PTT button pressed"""
		self.ptt_active = True
		self.led.on()
		print(f"\n🎤 {self.station_id}: PTT: Transmit Start")
		
		# Send PTT start control message
		self.message_queue.add_message(MessageType.CONTROL, b"PTT_START")

	def ptt_released(self):
		"""PTT button released"""
		self.ptt_active = False
		self.led.off()
		print(f"\n🔇 {self.station_id}: PTT: Transmit Stop")
 
		# Send PTT stop control message
		self.message_queue.add_message(MessageType.CONTROL, b"PTT_STOP")
 
		# Small delay to let any pending chat messages get queued/processed
		time.sleep(0.1)

		# NOW print statistics (after chat has been processed)
		self.print_stats()



	"""
	# Original method
	def ptt_released(self):
		self.ptt_active = False
		self.led.off()
		print(f"\n🔇 {self.station_id}: PTT: Transmit Stop")
		
		# Send PTT stop control message
		self.message_queue.add_message(MessageType.CONTROL, b"PTT_STOP")
		self.print_stats()
		"""


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
		"""Test network connectivity"""
		print("🌐 Testing network...")
		print(f"   Target: {self.transmitter.target_ip}:{self.transmitter.target_port}")

		test_message = f"OPULENT_VOICE_TEST_{self.station_id}"
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
	
	return parser.parse_args()


# Usage
if __name__ == "__main__":
	print("-=" * 40)
	print("Opulent Voice Radio with Terminal Chat - Phase 1")
	print("-=" * 40)

	try:
		args = parse_arguments()
		
		# Test the base-40 encoding first
		test_base40_encoding()
		
		# Create station identifier from command line args
		station_id = StationIdentifier(args.callsign)
		
		print(f"📡 Station: {station_id}")
		print(f"📡 Target: {args.ip}:{args.port}")
		print(f"👂 Listen: Port {args.listen_port}")
		print("💡 Use --help for configuration options")
		print()

		# Create message receiver
		receiver = MessageReceiver(listen_port=args.listen_port)
		receiver.start()

		if args.chat_only:
			print("💬 Chat-only mode (no GPIO/audio)")
			
			# Simple chat-only implementation for testing
			message_queue = MessagePriorityQueue()
			chat_interface = TerminalChatInterface(station_id, message_queue)
			receiver.chat_interface = chat_interface
			
			# Create minimal transmitter for chat
			transmitter = NetworkTransmitter(args.ip, args.port)
			protocol = OpulentVoiceProtocol(station_id)
			
			chat_interface.start()
			
			print(f"\n✅ {station_id} Chat system ready. Type messages or 'quit' to exit.")
			
			# Simple transmission loop for chat-only mode
			try:
				while chat_interface.running:
					message = message_queue.get_next_message(timeout=0.1)
					if message and message.msg_type == MessageType.TEXT:
						frame = protocol.create_text_frame(message.data)
						if transmitter.send_frame(frame):
							print(f"💬 Sent: {message.data.decode('utf-8')}")
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
