#!/usr/bin/env python3
"""
GPIO PTT Audio, Terminal Chat, Control Messages, and Config Files
- Voice PTT with OPUS encoding (highest priority)
- Terminal-based keyboard chat interface
- Priority queue system for message handling
- Background thread for non-voice transmission
- Debug/verbose mode for development
- UDP ports indicate data types
- Operator and Audio Device Configuration files in YAML
- Atkinson Hyperlegible font
- Audio transcription

Text Input → ChatManagerAudioDriven → AudioDrivenFrameManager.queue_text_message() → Simple Queue()
Voice Input → audio_callback → AudioDrivenFrameManager.process_voice_and_transmit() → Direct transmission

Class Organization

1. Foundation & Configuration "What do we need?"

StreamFrame - Data container for the 40ms frame system

2. Chat & User Interface Layer "How do users interact with chat?"

TerminalChatInterface - Terminal-based user interaction
ChatManagerAudioDriven - Audio-synchronized chat management

3. Stream Management & Timing "How do we manage frame timing?"

ContinuousStreamManager - Controls when the 40ms stream runs
AudioDrivenFrameManager - The heart of frame transmission logic

4. Network & Protocol "How do we connect to compouters or modems?"

MessageReceiver - Handles incoming data parsing and reassembly

5. Hardware Integration & Main System "How does it all come together?"

GPIOZeroPTTHandler - The main radio system class that orchestrates everything

Method Organization Within Classes

1. Constructor Pattern

def __init__(self)          # Always first
def setup_*_methods(self)   # Configuration methods
def _validate_config(self)  # Private validation helpers

2. Core Operations (The Main Quest)

We put the most important method first.
They are Ordered by typical call sequence.
We group related operations together.

3. Interface Methods (Party Coordination)

Public methods other classes call.
Then, callback methods (when_, on_).
Finally, event handlers.

4. Utility & Testing (Skill Checks)

Validation methods.
Test methods.
Helper functions.

5. Status and Cleanup (Character Record Sheet)

def get_stats(self)     # Status inquiry
def print_stats(self)   # Status display
def stop(self)          # Graceful shutdown
def cleanup(self)       # Final cleanup

"""

import sys
import socket
import struct
import time
import threading
import argparse
import re
from datetime import datetime
import asyncio
from queue import PriorityQueue, Empty, Queue
#from queue import Empty, Queue
from enum import Enum
from typing import Union, Tuple, Optional, List, Dict
import select
import logging
import traceback
import random
import sounddevice
from dataclasses import dataclass

from config_manager import (
	OpulentVoiceConfig, 
	ConfigurationManager, 
	create_enhanced_argument_parser, 
	setup_configuration
)


from audio_device_manager import (
	AudioDeviceManager,
	AudioManagerMode,
	create_audio_manager_for_cli,
	create_audio_manager_for_interactive
)

from web_interface import initialize_web_interface, run_web_server

from enhanced_receiver import integrate_enhanced_receiver

from radio_protocol import (
	COBSEncoder,
	SimpleFrameReassembler,
	COBSFrameBoundaryManager,
	OpulentVoiceProtocolWithIP,
	StationIdentifier,
	encode_callsign,
	decode_callsign,
	MessageType,
	QueuedMessage,
	RTPHeader,
	RTPAudioFrameBuilder,
	UDPHeader,
	UDPAudioFrameBuilder,
	UDPTextFrameBuilder,
	UDPControlFrameBuilder,
	IPHeader,
	IPAudioFrameBuilder,
	IPTextFrameBuilder,
	IPControlFrameBuilder,
	SimpleFrameSplitter,
	SimpleFrameReassembler,
	FrameType,
	FramePriority,
	NetworkTransmitter,
	DebugConfig
)

from enhanced_receiver import integrate_enhanced_receiver

# global variable for GUI
web_interface_instance = None

# check for virtual environment
if not (hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)):
	print("You need to run this code in a virtual environment:")
	print("	 source /LED_test/bin/activate")
	sys.exit(1)

try: 
	import opuslib_next as opuslib
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
	print("Please install gpiozero.")
	raise


# ===================================================================
# 1. FOUNDATION & CONFIGURATION
# ===================================================================




# ===================================================================
# 2. CHAT & USER INTERFACE LAYER
# ===================================================================

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
				DebugConfig.user_print(f"	  {i}. {msg}")
	
	def display_received_message(self, from_station, message):
		"""Display received chat message"""
		DebugConfig.user_print(f"\n📨 [{from_station}]: {message}")
		self._show_prompt()


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


# ===================================================================
# 3. STREAM MANAGEMENT & TIMING
# ===================================================================

class AudioDrivenFrameManager:
	'''Handles all frame logic within audio callback timing'''
	def __init__(self, station_identifier, protocol, network_transmitter, config):
		self.station_id = station_identifier
		self.protocol = protocol
		self.network_transmitter = network_transmitter
		self.config = config
		
		# Frame queues
		self.control_queue = Queue()
		self.text_queue = Queue()
		
		# Voice state (no buffer needed)
		self.voice_active = False
		self.pending_voice_frame = None
		
		# Non-voice transmission throttling
		self.frames_since_nonvoice = 0
		self.nonvoice_send_interval = 1  # Send non-voice every N frames when no voice !!!
		
		# Keepalive management - ALWAYS initialize ALL attributes !!!
		self.target_type = config.protocol.target_type
		self.last_keepalive_time = 0  # Always initialize this
		self.keepalive_interval = config.protocol.keepalive_interval  # Always initialize this
		
		if self.target_type == "computer":
			self.send_keepalives = True
			DebugConfig.debug_print(f"📡 Target: Computer - keepalives enabled every {self.keepalive_interval}s")
		else:
			self.send_keepalives = False
			DebugConfig.debug_print(f"📻 Target: Modem - keepalives disabled, modem handles hang-time")
		
		# Statistics
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

	def process_voice_and_transmit(self, opus_packet, current_time):
		"""
		PAUL'S APPROACH: Process voice - may generate multiple frames per opus packet
		"""
		try:
			# NEW: Create potentially multiple OV frames (Paul's approach)
			ov_frames = self.protocol.create_audio_frames(opus_packet, is_start_of_transmission=False)

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


# ===================================================================
# 4. NETWORK & PROTOCOL
# ===================================================================

class MessageReceiver:
	"""Handles receiving and parsing incoming messages"""
	def __init__(self, listen_port=57372, chat_interface=None):
		self.listen_port = listen_port
		self.chat_interface = chat_interface
		self.socket = None
		self.running = False
		self.receive_thread = None

		# Simple frame reassembler (no fragmentation headers)
		self.reassembler = SimpleFrameReassembler()
		self.cobs_manager = COBSFrameBoundaryManager()

		# For parsing complete frames
		self.protocol = OpulentVoiceProtocolWithIP(StationIdentifier("TEMP"))

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

			# Step 2: Try to reassemble COBS frames
			cobs_frames = self.reassembler.add_frame_payload(fragment_payload)

			# Step 3: Process all the reassembled COBS frames
			for frame in cobs_frames:
				DebugConfig.debug_print(f"📥 Received COBS frame from {addr}: {len(frame)}B")

				# Step 4: COBS decode to get original IP frame
				try:
					ip_frame, _ = self.cobs_manager.decode_frame(frame)
				except Exception as e:
					DebugConfig.debug_print(f"✗ COBS decode error from {addr}: {e}")
					continue

				self._process_complete_ip_frame(ip_frame, station_bytes, addr)

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
			print(f"Error processing IP frame: {e}")


# ===================================================================
# 5. HARDWARE INTEGRATION & MAIN SYSTEM
# ===================================================================

class GPIOZeroPTTHandler:
	def __init__(self, station_identifier, config: OpulentVoiceConfig):
		# cleanup flag
		self._cleanup_done = False

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
		self.transmitter = NetworkTransmitter(NetworkTransmitter.ENCAP_MODE_UDP, config.network.target_ip, config.network.target_port)

		# Audio-driven frame manager with config
		self.audio_frame_manager = AudioDrivenFrameManager(
			station_identifier,
			self.protocol,
			self.transmitter,
			config  # Pass the config object
		)

		# Audio-driven chat manager (evolved from the heroically retired ChatManager)
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

		# Add transcription support for outgoing audio
		self.transcriber = None
		if hasattr(self, 'enhanced_receiver') and self.enhanced_receiver:
			# Use the same transcriber as the receiver
			self.transcriber = self.enhanced_receiver.transcriber

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

	def setup_audio(self, force_device_selection=False):
		"""Setup audio input and output with optional device selection"""
		# create device manager with our config
		device_manager = AudioDeviceManager(
			mode=AudioManagerMode.INTERACTIVE,
			config_file="audio_config.yaml", 
			radio_config=self.config
		)

		try:
			# Device selection based on force flag or first-time setup
			input_device, output_device = device_manager.setup_audio_devices(
				force_selection=force_device_selection
			)
			
			# get audio parameters from device manager
			params = device_manager.audio_params

			# VERIFICATION: Ensure protocol requirements are met
			if params['sample_rate'] != 48000:
				DebugConfig.debug_print(f"⚠️ WARNING: Sample rate {params['sample_rate']} != 48000 (protocol requirement)")
				params['sample_rate'] = 48000

			if params['frame_duration_ms'] != 40:
				DebugConfig.debug_print(f"⚠️ WARNING: Frame duration {params['frame_duration_ms']} != 40ms (protocol requirement)")
				params['frame_duration_ms'] = 40
				params['frames_per_buffer'] = 1920  # Recalculate

			# CRITICAL: Enforce protocol requirements regardless of config
			# These are protocol requirements and cannot be changed by users
			protocol_sample_rate = 48000  # Protocol requirement
			protocol_frame_duration_ms = 40  # Protocol requirement
			protocol_frames_per_buffer = int(protocol_sample_rate * protocol_frame_duration_ms / 1000)

			# Override any config values with protocol requirements
			params['sample_rate'] = protocol_sample_rate
			params['frame_duration_ms'] = protocol_frame_duration_ms
			params['frames_per_buffer'] = protocol_frames_per_buffer

			# Update our instance variables to match protocol requirements
			self.sample_rate = protocol_sample_rate
			self.samples_per_frame = protocol_frames_per_buffer
			self.bytes_per_frame = self.samples_per_frame * 2


#			# Update our instance variables to match selected params
#			self.sample_rate = params['sample_rate']
#			self.samples_per_frame = params['frames_per_buffer']
#			self.bytes_per_frame = self.samples_per_frame * 2
			
			DebugConfig.debug_print(f"🎵 Audio config: {params['sample_rate']}Hz, {params['frame_duration_ms']}ms frames")
			DebugConfig.debug_print(f"   Samples per frame: {params['frames_per_buffer']}")
			DebugConfig.debug_print(f"   Selected input device: {input_device}")

			# set up input stream for the microphone
			try:
				self.audio_input_stream = self.audio.open(
					format=pyaudio.paInt16,
					channels=params['channels'],
					rate=params['sample_rate'], 
					input=True,
					input_device_index=input_device,
					frames_per_buffer=params['frames_per_buffer'],
					stream_callback=self.audio_callback
				)
				DebugConfig.debug_print("✓ Audio input stream ready with selected microphone")
			except Exception as e:
				DebugConfig.debug_print(f"✗ Audio input device setup error: {e}")
				raise

			# Store both devices and parameters for enhanced receiver
			self.selected_input_device = input_device	# For reference
			self.selected_output_device = output_device  # For received audio playback
			self.audio_params = params
			DebugConfig.debug_print("✅ Audio setup complete - input and output devices independently selected")

		finally:
			device_manager.cleanup()

	def setup_enhanced_receiver_with_audio(self):
		"""Setup enhanced receiver with audio output using independently selected output device"""
		try:
			from enhanced_receiver import 	EnhancedMessageReceiver
		
			# Create enhanced receiver (UNCHANGED)
			self.enhanced_receiver = EnhancedMessageReceiver(
				listen_port=self.config.network.listen_port,
				chat_interface=self.chat_interface,
				block_list=[self.station_id.to_bytes()],  # Block own frames only for now
			)
		
			# CORRECTED: Setup audio output with the independently selected OUTPUT device
			if hasattr(self, 'selected_output_device') and hasattr(self, 'audio_params'):
				print(f"🔊 Setting up received audio playback:")
				print(f"   Using output device: {self.selected_output_device}")
				print(f"   Audio parameters: {self.audio_params['sample_rate']}Hz, {self.audio_params['channels']} channel(s)")

				# Create audio output manager directly
				from enhanced_receiver import AudioOutputManager
				self.enhanced_receiver.audio_output = AudioOutputManager(self.audio_params)

				# Use your existing setup_with_device method
				if self.enhanced_receiver.audio_output.setup_with_device(self.selected_output_device):
					if self.enhanced_receiver.audio_output.start_playback():
						print(f"✅ Enhanced receiver: real-time audio output active")
					else:
						print(f"⚠️  Audio playback start failed")
				else:
					print(f"⚠️  Audio device setup failed")
			else:
				print("⚠️  No output device selected - voice reception will be web-only")

			# Start the receiver (UNCHANGED)
			self.enhanced_receiver.start()
			return self.enhanced_receiver
		
		except Exception as e:
			print(f"✗ Enhanced receiver setup failed: {e}")
			return None

	def setup_enhanced_receiver_for_cli(self):
		"""Setup enhanced receiver with audio output - CLI MODE ONLY (no web interface)"""
		try:
			from enhanced_receiver import EnhancedMessageReceiver
		
			# Create enhanced receiver (same as web interface mode)
			self.enhanced_receiver = EnhancedMessageReceiver(
				listen_port=self.config.network.listen_port,
				chat_interface=self.chat_interface,
				block_list=[self.station_id.to_bytes()],  # Block own frames only for now
			)
		
			# Setup audio output if we have device info (same as web interface mode)
			if hasattr(self, 'selected_output_device') and hasattr(self, 'audio_params'):
				print(f"🔊 Setting up received audio playback for CLI mode:")
				print(f"   Using output device: {self.selected_output_device}")
				print(f"   Audio parameters: {self.audio_params['sample_rate']}Hz, {self.audio_params['channels']} channel(s)")
				
				# Create audio output manager directly (same as web interface mode)
				from enhanced_receiver import AudioOutputManager
				self.enhanced_receiver.audio_output = AudioOutputManager(self.audio_params)
				
				# Use existing setup_with_device method (same as web interface mode)
				if self.enhanced_receiver.audio_output.setup_with_device(self.selected_output_device):
					if self.enhanced_receiver.audio_output.start_playback():
						print(f"✅ CLI mode: real-time audio output active")
					else:
						print(f"⚠️  CLI mode: Audio playback start failed")
				else:
					print(f"⚠️  CLI mode: Audio device setup failed")
			else:
				print("⚠️  CLI mode: No output device selected - voice reception disabled")
				print("   (Use --setup-audio to configure audio devices)")
		
			# Start the receiver (same as web interface mode)
			self.enhanced_receiver.start()
			
			# IMPORTANT: Do NOT set web interface - this is CLI mode only
			print("✅ Enhanced receiver ready for CLI mode (no web interface)")
			return self.enhanced_receiver
		
		except Exception as e:
			print(f"✗ CLI audio setup failed: {e}")
			import traceback
			traceback.print_exc()
			return None

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
		"""
		MODIFIED audio callback that drives all transmission
		"""
		if status:
			DebugConfig.debug_print(f"⚠ Audio status flags: {status}")

		current_time = time.time()

		# PART 1: Process incoming audio (existing logic)
		if self.ptt_active:
			if not self.validate_audio_frame(in_data):
				self.audio_stats['invalid_frames'] += 1
				return (None, pyaudio.paContinue)

			try:
				# Encode audio (existing logic)
				opus_packet = self.encoder.encode(in_data, self.samples_per_frame)
				self.audio_stats['frames_encoded'] += 1

				# Validate packet (existing logic)
				if not self.validate_opus_packet(opus_packet):
					self.audio_stats['invalid_frames'] += 1
					DebugConfig.debug_print(f"⚠ Dropping invalid OPUS packet")
					return (None, pyaudio.paContinue)

				# NEW: Capture outgoing audio for web interface (ONLY if web interface exists)
				if hasattr(self, 'enhanced_receiver') and hasattr(self.enhanced_receiver, 'web_bridge'):
					self._capture_outgoing_audio_for_web(opus_packet, current_time)

				# Send voice frame immediately using audio timing
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
		"""PTT button pressed - send control message IMMEDIATELY before voice"""

		# Send PTT_START control message IMMEDIATELY
		# Create and send the control frame directly, bypassing the queue
		try:
			control_frames = self.protocol.create_control_frames(b"PTT_START")
			for frame in control_frames:
				success = self.transmitter.send_frame(frame)
				if success:
					DebugConfig.user_print(f"📡 PTT_START control frame sent immediately")
				else:
					DebugConfig.debug_print(f"✗ Failed to send immediate PTT_START")
		except Exception as e:
			DebugConfig.debug_print(f"✗ Error sending PTT_START control frame immediately: {e}")
    
		# STEP 2: Brief delay to ensure control message is transmitted before voice
		time.sleep(0.050)  # 50ms delay - more than one frame period
    
		# STEP 3: Enable voice transmission (existing code)
		self.ptt_active = True
		self.chat_manager.set_ptt_state(True)
		self.audio_frame_manager.set_voice_active(True)

		self.protocol.notify_ptt_pressed()
		self._is_first_voice_frame = True

		DebugConfig.user_print(f"\n🎤 {self.station_id}: PTT was pressed")



		# DEBUG: Check if enhanced receiver is available
		DebugConfig.debug_print(f"🔍 DEBUG: hasattr enhanced_receiver: {hasattr(self, 'enhanced_receiver')}")
		if hasattr(self, 'enhanced_receiver'):
			DebugConfig.debug_print(f"🔍 DEBUG: enhanced_receiver exists: {self.enhanced_receiver is not None}")
			if self.enhanced_receiver:
				DebugConfig.debug_print(f"🔍 DEBUG: hasattr web_bridge: {hasattr(self.enhanced_receiver, 'web_bridge')}")
				if hasattr(self.enhanced_receiver, 'web_bridge'):
					DebugConfig.debug_print(f"🔍 DEBUG: web_bridge exists: {self.enhanced_receiver.web_bridge is not None}")





		# NEW: Start tracking our own outgoing transmission for web interface
		if hasattr(self, 'enhanced_receiver') and self.enhanced_receiver and hasattr(self.enhanced_receiver, 'web_bridge'):
			try:
				# Create outgoing transmission tracking
				def notify_outgoing_start():
					try:
						loop = asyncio.new_event_loop()
						asyncio.set_event_loop(loop)
						loop.run_until_complete(
							self.enhanced_receiver.web_bridge.notify_outgoing_transmission_started({
								"station_id": str(self.station_id),
								"start_time": datetime.now().isoformat(),
								"direction": "outgoing"
							})
						)
						loop.close()
					except Exception as e:
						DebugConfig.debug_print(f"Error notifying outgoing start: {e}")
            
				# Run in separate thread to avoid blocking audio
				threading.Thread(target=notify_outgoing_start, daemon=True).start()
				DebugConfig.debug_print(f"📤 Started tracking outgoing transmission")
			except Exception as e:
				DebugConfig.debug_print(f"Error starting outgoing transmission tracking: {e}")


		# LED on
		self.led.on()

	def ptt_released(self):
		"""PTT button released - send control message IMMEDIATELY after voice stops"""
    
		# STEP 1: Stop voice transmission immediately	
		self.ptt_active = False
		self.chat_manager.set_ptt_state(False)
		self.audio_frame_manager.set_voice_active(False)
		self.protocol.notify_ptt_released()

		DebugConfig.user_print(f"\n🔇 {self.station_id}: PTT was released")

		# NEW: End tracking our own outgoing transmission for web interface
		if hasattr(self, 'enhanced_receiver') and self.enhanced_receiver and hasattr(self.enhanced_receiver, 'web_bridge'):
			try:
				# Create outgoing transmission end tracking
				def notify_outgoing_end():
					try:
						loop = asyncio.new_event_loop()
						asyncio.set_event_loop(loop)
						loop.run_until_complete(
							self.enhanced_receiver.web_bridge.notify_outgoing_transmission_ended({
								"station_id": str(self.station_id),
								"end_time": datetime.now().isoformat(),
								"direction": "outgoing"
							})
						)
						loop.close()
					except Exception as e:
						DebugConfig.debug_print(f"Error notifying outgoing end: {e}")
            
				# Run in separate thread to avoid blocking audio
				threading.Thread(target=notify_outgoing_end, daemon=True).start()
				DebugConfig.debug_print(f"📤 Ended tracking outgoing transmission")
			except Exception as e:
				DebugConfig.debug_print(f"Error ending outgoing transmission tracking: {e}")

    
		# STEP 2: Brief delay to ensure last voice frame is sent
		time.sleep(0.050)  # 50ms delay
    
		# STEP 3: Send PTT_STOP control message IMMEDIATELY
		# Create and send the control frame directly, bypassing the queue
		try:
			control_frames = self.protocol.create_control_frames(b"PTT_STOP")
			for frame in control_frames:
				success = self.transmitter.send_frame(frame)
				if success:
					DebugConfig.user_print(f"📡 PTT_STOP control frame was sent immediately")
				else:
					DebugConfig.debug_print(f"✗ Failed to send immediate PTT_STOP")
		except Exception as e:
			DebugConfig.debug_print(f"✗ Error sending immediate PTT_STOP: {e}")


		# Show stats and LED off (existing code)
		time.sleep(0.1)
		if DebugConfig.VERBOSE:
			self.print_stats()

		# LED off
		self.led.off()









	def _capture_outgoing_audio_for_web(self, opus_packet, current_time):
		"""
		Capture outgoing audio for web interface replay (does not affect live audio)
		"""
		# Try to get audio data first
		audio_pcm = None
		
		try:
			# Only capture if web interface is connected
			if not (hasattr(self, 'enhanced_receiver') and
					hasattr(self.enhanced_receiver, 'web_bridge') and
					self.enhanced_receiver.web_bridge.web_interface):
				return
	
			# Decode OPUS to PCM for web interface storage
			if hasattr(self.enhanced_receiver, 'audio_decoder'):
				audio_pcm = self.enhanced_receiver.audio_decoder.decode_opus(opus_packet)
									
				if audio_pcm:
					# Create audio data packet (same format as incoming)
					audio_data = {
						'audio_data': audio_pcm,
						'from_station': str(self.station_id),
						'timestamp': datetime.now().isoformat(),
						'sample_rate': self.sample_rate,
						'duration_ms': self.frame_duration_ms,
						'direction': 'outgoing'
					}
	
					# Send to web interface asynchronously (doesn't block audio)
					def notify_web():
						try:
							loop = asyncio.new_event_loop()
							asyncio.set_event_loop(loop)
							loop.run_until_complete(
								self.enhanced_receiver.web_bridge.notify_audio_received(audio_data)
							)
							loop.close()
						except Exception as e:
							DebugConfig.debug_print(f"Web outgoing audio notification error: {e}")
	
					# Run in separate thread to avoid blocking audio callback
					threading.Thread(target=notify_web, daemon=True).start()
					DebugConfig.debug_print(f"📤 Captured outgoing audio: {len(opus_packet)}B OPUS → {len(audio_pcm)}B PCM")
				else:
					DebugConfig.debug_print(f"⚠️ OPUS decode failed for outgoing audio")
			else:   
				DebugConfig.debug_print(f"⚠️ No audio decoder available for outgoing capture")
	
		except Exception as e:
			# Never let web interface issues affect live audio
			DebugConfig.debug_print(f"Web interface capture error (non-fatal): {e}")










	def start(self):
		"""Start the continuous stream system"""
		if self.audio_input_stream:
			self.audio_input_stream.start_stream()

		# Start chat interface
		self.chat_interface.start()

		print(f"\n🚀 {self.station_id} Start Chat Interface")
		print("📋 Configuration:")
		print(f"   Station: {self.station_id}")
		print(f"   Sample rate: {self.sample_rate} Hz")
		print(f"   Bitrate: {self.bitrate} bps CBR")
		print(f"   Frame size: {self.frame_duration_ms}ms ({self.samples_per_frame} samples)")
		print(f"   Frame rate: {1000/self.frame_duration_ms} fps")
		print(f"   Network target: {self.transmitter.target_ip}:{self.transmitter.target_port}")
		print(f"   Stream starts automatically when there's activity")

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
				DebugConfig.debug_print("	 Special note: random test data is maximum COBS overhead.")
				DebugConfig.debug_print("	 Did you see the audio frame split?")
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

	def stop(self):
		"""Stop the continuous stream system"""
		self.chat_interface.stop()

		if self.audio_input_stream:
			self.audio_input_stream.stop_stream()
			self.audio_input_stream.close()
		self.audio.terminate()
		print(f"🛑 {self.station_id} Continuous stream system stopped")

	def cleanup(self):
		"""Clean shutdown - FIXED to prevent duplicate cleanup"""
		if self._cleanup_done:
			DebugConfig.debug_print("🔄 Cleanup already completed - skipping")
			return

		self._cleanup_done = True

		self.chat_interface.stop()
		if self.audio_input_stream:
			self.audio_input_stream.stop_stream()
			self.audio_input_stream.close()
		self.audio.terminate()

		if hasattr(self, 'enhanced_receiver') and self.enhanced_receiver:
			self.enhanced_receiver.stop_audio_output()
			self.enhanced_receiver.stop()

		self.transmitter.close()
		self.led.off()
		print(f"Thank you for shopping at Omega Mart. {self.station_id} cleanup complete.")


# ===================================================================
# UTILITY FUNCTIONS
# ===================================================================

def test_base40_encoding():
	"""Test the base-40 encoding/decoding functions"""
	print("🧪 Testing Base-40 Encoding/Decoding...")

	test_callsigns = [
		"W1ABC",	  # Traditional US callsign
		"VE3XYZ",	 # Canadian callsign
		"G0ABC",	  # UK callsign
		"JA1ABC",	 # Japanese callsign
		"TACTICAL1",  # Tactical callsign
		"TEST/P",	 # Portable operation
		"NODE-1",	 # Network node
		"RELAY.1",	# Relay station
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
				print(f"	  ✓ StationIdentifier round-trip successful")
			else:
				print(f"	  ✗ StationIdentifier round-trip failed: {recovered}")

		except Exception as e:
			print(f"   ✗ {callsign} → Error: {e}")

	print("   🧪 Base-40 encoding tests complete\n")

def parse_arguments():
	"""Enhanced argument parser that works with configuration system"""
	return create_enhanced_argument_parser()

def setup_web_interface_callbacks(radio_system, web_interface):
	"""Connect radio system callbacks to web interface for real-time updates"""
	
	# Store original chat display method if it exists
	if (hasattr(radio_system, 'chat_interface') and 
		hasattr(radio_system.chat_interface, 'display_received_message')):
		
		original_display = radio_system.chat_interface.display_received_message
		
		# Create async wrapper for message display
		def enhanced_display(from_station, message):
			# Call original display for terminal
			original_display(from_station, message)
			
			# Also send to web interface asynchronously
			if web_interface:
				# Create a task to handle the async call
				loop = None
				try:
					loop = asyncio.get_event_loop()
				except RuntimeError:
					# No event loop in current thread, create one
					pass
				
				if loop and loop.is_running():
					# Schedule the coroutine to run
					asyncio.create_task(web_interface.on_message_received({
						"content": message,
						"from": str(from_station),
						"type": "text"
					}))
				else:
					# Handle in a thread-safe way
					def run_async():
						asyncio.run(web_interface.on_message_received({
							"content": message,
							"from": str(from_station),
							"type": "text"
						}))
					
					# Run in a separate thread to avoid blocking
					threading.Thread(target=run_async, daemon=True).start()
		
		# Replace the method
		radio_system.chat_interface.display_received_message = enhanced_display
	
	# Store original PTT methods if they exist
	if hasattr(radio_system, 'ptt_pressed') and hasattr(radio_system, 'ptt_released'):
		original_ptt_pressed = radio_system.ptt_pressed
		original_ptt_released = radio_system.ptt_released
		
		# Create thread-safe PTT wrappers
		def ptt_pressed_with_web():
			original_ptt_pressed()
			# Notify web interface in thread-safe way
			if web_interface:
				def notify_web():
					asyncio.run(web_interface.on_ptt_state_changed(True))
				threading.Thread(target=notify_web, daemon=True).start()
		
		def ptt_released_with_web():
			original_ptt_released()
			# Notify web interface in thread-safe way
			if web_interface:
				def notify_web():
					asyncio.run(web_interface.on_ptt_state_changed(False))
				threading.Thread(target=notify_web, daemon=True).start()
		
		# Replace methods
		radio_system.ptt_pressed = ptt_pressed_with_web
		radio_system.ptt_released = ptt_released_with_web

def setup_enhanced_reception(radio_system, web_interface=None):
	"""Setup enhanced message reception with web interface integration"""
	
	print("🔄 Setting up enhanced reception with web interface integration...")
	
	# Replace the existing receiver with enhanced version
	enhanced_receiver = integrate_enhanced_receiver(radio_system, web_interface)
	
	# Connect web interface callbacks if provided
	if web_interface:
		setup_web_reception_callbacks(radio_system, web_interface, enhanced_receiver)
	
	print("✅ Enhanced reception setup complete")
	return enhanced_receiver

def setup_web_reception_callbacks(radio_system, web_interface, receiver):
	"""Setup callbacks between radio system and web interface for reception"""
	
	# Store original methods if they exist
	original_display = None
	if (hasattr(radio_system, 'chat_interface') and 
		hasattr(radio_system.chat_interface, 'display_received_message')):
		original_display = radio_system.chat_interface.display_received_message
	
	# Enhanced display method that also notifies web interface
	def enhanced_display_received_message(from_station, message):
		# Call original display for CLI
		if original_display:
			original_display(from_station, message)
		else:
			print(f"\n📨 [{from_station}]: {message}")
		
		# Notify web interface asynchronously
		def notify_web():
			try:
				loop = asyncio.new_event_loop()
				asyncio.set_event_loop(loop)
				loop.run_until_complete(web_interface.on_message_received({
					"content": message,
					"from": str(from_station),
					"type": "text",
					"timestamp": datetime.now().isoformat(),
					"direction": "incoming"
				}))
				loop.close()
			except Exception as e:
				print(f"Error notifying web interface: {e}")
		
		threading.Thread(target=notify_web, daemon=True).start()
	
	# Replace the display method if chat interface exists
	if hasattr(radio_system, 'chat_interface'):
		radio_system.chat_interface.display_received_message = enhanced_display_received_message
		print("✅ Chat interface enhanced for web notifications")
	
	print("✅ Web reception callbacks configured")


# ===================================================================
# MAIN PROGRAM
# ===================================================================

if __name__ == "__main__":
	print("-=" * 40)
	print("Opulent Voice Radio with Terminal Chat")
	print("-=" * 40)

	try:
		# Setup configuration system and return config manager
		config, should_exit, config_manager = setup_configuration()
		
		if should_exit:
			sys.exit(0)

		# Set debug mode from configuration
		DebugConfig.set_mode(verbose=config.debug.verbose, quiet=config.debug.quiet)

		# Handle audio CLI commands FIRST (existing code unchanged)
		if '--list-audio' in sys.argv:
			from audio_device_manager import create_audio_manager_for_cli
			device_manager = create_audio_manager_for_cli()
			device_manager.list_devices_cli_format()
			#device_manager.list_audio_devices()
			device_manager.cleanup()
			sys.exit(0)
		
		if '--test-audio' in sys.argv:
			from audio_device_manager import create_audio_manager_for_cli
			device_manager = create_audio_manager_for_cli()
			success = device_manager.test_audio_cli_format()
			#device_manager.test_audio_devices()
			device_manager.cleanup()
			sys.exit(0)
		
		if '--setup-audio' in sys.argv:
			from audio_device_manager import create_audio_manager_for_interactive
			device_manager = create_audio_manager_for_interactive()
			device_manager.setup_audio_devices(force_selection=True)
			device_manager.cleanup()
			sys.exit(0)

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

		# Check for web interface mode first
		if hasattr(config, 'ui') and hasattr(config.ui, 'web_interface_enabled') and config.ui.web_interface_enabled:
			# Web Interface Mode
			print("🌐 Starting in web interface mode ...")

			# Initialize radio system with config for transcription
			radio = GPIOZeroPTTHandler(
				station_identifier=station_id,
				config=config
			)

			# Setup web interface
			web_interface_instance = initialize_web_interface(radio, config, config_manager)
	
			# Setup enhanced reception (this creates and starts the receiver)
			# enhanced_receiver = setup_enhanced_reception(radio, web_interface_instance)
			enhanced_receiver = radio.setup_enhanced_receiver_with_audio()


			# IMPORTANT: Pass config to enhanced receiver for transcription
			if enhanced_receiver and hasattr(enhanced_receiver, '__init__'):
				# Update the enhanced receiver to include config
				enhanced_receiver.config = config
				enhanced_receiver._initialize_transcription()


			# CRITICAL DEBUG: Verify the receiver is accessible
			print(f"🔍 POST-SETUP RECEIVER DEBUG:")
			print(f"   enhanced_receiver variable: {enhanced_receiver is not None}")
			print(f"   radio.enhanced_receiver attribute: {hasattr(radio, 'enhanced_receiver')}")
			if hasattr(radio, 'enhanced_receiver'):
				print(f"   radio.enhanced_receiver value: {radio.enhanced_receiver is not None}")
				if radio.enhanced_receiver and hasattr(radio.enhanced_receiver, 'audio_output'):
					print(f"   radio.enhanced_receiver.audio_output: {radio.enhanced_receiver.audio_output is not None}")
					if radio.enhanced_receiver.audio_output:
						print(f"   AudioOutputManager details:")
						print(f"     - playing: {radio.enhanced_receiver.audio_output.playing}")
						print(f"     - device: {radio.enhanced_receiver.audio_output.output_device}")
						print(f"     - has queue method: {hasattr(radio.enhanced_receiver.audio_output, 'queue_audio_for_playback')}")

			# Double-check assignment
			if enhanced_receiver and not hasattr(radio, 'enhanced_receiver'):
				print(f"🔧 FIXING: Manually assigning enhanced_receiver to radio object")
				radio.enhanced_receiver = enhanced_receiver

			# Triple-check
			if hasattr(radio, 'enhanced_receiver') and radio.enhanced_receiver:
				print(f"✅ VERIFIED: Enhanced receiver is accessible via radio.enhanced_receiver")
			else:
				print(f"❌ PROBLEM: Enhanced receiver still not accessible")



			receiver = enhanced_receiver






			# Connect to web interface
			if web_interface_instance and enhanced_receiver:
				enhanced_receiver.set_web_interface(web_interface_instance)
				setup_web_reception_callbacks(radio, web_interface_instance, enhanced_receiver)

	
			# Connect receiver to radio's chat interface
			receiver.chat_interface = radio.chat_interface
	
			# Start radio system
			radio.start()

			print("🚀 Web interface starting on http://localhost:8000")
			print("🌐 Press Ctrl+C to stop the web interface")
			
			try:
				# FIXED: Get the correct host and port from config
				host = getattr(config.ui, 'web_interface_host', 'localhost')
				port = getattr(config.ui, 'web_interface_port', 8000)
				
				# Run web server (this blocks until Ctrl+C)
				run_web_server(
					host=host,
					port=port,
					radio_system=radio,
					config=config
				)
			except KeyboardInterrupt:
				print("\n🛑 Web interface shutting down...")
			finally:
				# Clean shutdown of web interface components
				if 'radio' in locals():
					radio.cleanup()
				print("🌐 Web interface stopped")
			
			# CRITICAL: Exit here - don't fall through to CLI mode
			sys.exit(0)
			
		elif config.ui.chat_only_mode:
			# Chat-only mode (existing code unchanged)
			print("💬 Chat-only mode (no GPIO/audio)")
			# Create a minimal chat-only system
			from terminal_chat import TerminalChatSystem
			chat_system = TerminalChatSystem(station_id, config)
			receiver.chat_interface = chat_system
			
			print(f"✅ {station_id} Chat System Ready!")
			print("💬 Type messages in terminal")
			print("⌨️  Press Ctrl+C to exit")
			
			try:
				chat_system.start()
				while True:
					time.sleep(0.1)
			except KeyboardInterrupt:
				print("\n🛑 Chat system shutting down...")
				chat_system.stop()

		else:
			# FULL CLI RADIO MODE
			print("📻 Starting full radio system with enhanced reception...")
	
			# Initialize full radio system with config
			radio = GPIOZeroPTTHandler(
				station_identifier=station_id,
				config=config
			)

			# ENHANCED: Setup enhanced reception for CLI mode with config
			enhanced_receiver = radio.setup_enhanced_receiver_for_cli()


			# Initialize transcription for CLI
			if enhanced_receiver:
				enhanced_receiver.config = config
				enhanced_receiver._initialize_transcription()

			receiver = enhanced_receiver
	
			# Connect receiver to chat interface
			if receiver:
				receiver.chat_interface = radio.chat_interface

			# Run tests and start
			radio.test_gpio()
			radio.test_network()
			radio.test_chat()
			radio.start()

			print(f"\n✅ {station_id} Enhanced System Ready!")
			print("🎤 Press PTT for voice transmission (highest priority)")
			print("💬 Type chat messages in terminal")
			print("🎧 Audio reception active for incoming voice")
			print("📊 Enhanced statistics shown after each PTT release")
			print("⌨️  Press Ctrl+C to exit")

			# CLI Main loop
			try:
				while True:
					time.sleep(0.1)
			except KeyboardInterrupt:
				print("\n🛑 Enhanced CLI radio system shutting down...")

	except KeyboardInterrupt:
		print("\nShutting down...")
	except Exception as e:
		print(f"✗ Error: {e}")
		import traceback
		traceback.print_exc()
		sys.exit(1)
	finally:
		# Cleanup (this runs regardless of which mode was used)
		if 'receiver' in locals():
			receiver.stop()
		if 'radio' in locals():
			radio.cleanup()
		elif 'chat_system' in locals():
			chat_system.stop()

		print("Thank you for using Opulent Voice!")

