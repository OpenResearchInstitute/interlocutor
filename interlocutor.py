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
- Audio Device Configuration in YAML
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

import asyncio
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

# Keep your existing imports
from enhanced_receiver import integrate_enhanced_receiver
# The above classes were renamed _remove



# global variable for GUI
web_interface_instance = None


# check for virtual environment
if not (hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)):
	print("You need to run this code in a virtual environment:")
	print("	 source /LED_test/bin/activate")
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
	print("Please install gpiozero.")
	raise








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
				DebugConfig.user_print(f"	  {i}. {msg}")
	
	def display_received_message(self, from_station, message):
		"""Display received chat message"""
		DebugConfig.user_print(f"\n📨 [{from_station}]: {message}")
		self._show_prompt()

















@dataclass
class StreamFrame:
	"""Container for data going into 40ms frames"""
	frame_type: FrameType
	priority: FramePriority
	data: bytes
	timestamp: float
	is_continuation: bool = False
	sequence_id: int = 0













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
			
			# Update our instance variables to match selected params
			self.sample_rate = params['sample_rate']
			self.samples_per_frame = params['frames_per_buffer']
			self.bytes_per_frame = self.samples_per_frame * 2
			
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
			from enhanced_receiver import EnhancedMessageReceiver
		
			# Create enhanced receiver (UNCHANGED)
			self.enhanced_receiver = EnhancedMessageReceiver(
				listen_port=self.config.network.listen_port,
				chat_interface=self.chat_interface
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
				chat_interface=self.chat_interface
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




	# minimal audio_callback to see where audio overflow problem was
	# swap in for audio_callback to test things
	# results were: problem is not in our code
	def audio_callback_minimal(self, in_data, frame_count, time_info, status):
		if status:
			print(f"⚠ Audio status flags: {status}")
	
		# Do absolutely nothing else - just return
		return (None, pyaudio.paContinue)





	def audio_callback(self, in_data, frame_count, time_info, status):
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

		# 
		self.cobs_manager = COBSFrameBoundaryManager()

		# For parsing complete frames
		self.protocol = OpulentVoiceProtocolWithIP(StationIdentifier("TEMP"))

	# def _process_received_data(self, data, addr):
	# 	"""
	# 	Simple receiver processing - no fragmentation headers to worry about
	# 	"""
	# 	try:
	# 		# Step 1: Parse Opulent Voice header
	# 		if len(data) != 133:  # All frames must be exactly 133 bytes
	# 			DebugConfig.debug_print(f"⚠ Expected 133-byte frame, got {len(data)}B from {addr}")
	# 			return

	# 		ov_header = data[:12]
	# 		frame_payload = data[12:]  # Should be exactly 121 bytes

	# 		# Parse OV header
	# 		station_bytes, token, reserved = struct.unpack('>6s 3s 3s', ov_header)

	# 		DebugConfig.debug_print(f"📥 Received 133B frame from {addr}")

	# 		if token != OpulentVoiceProtocolWithIP.TOKEN:
	# 			DebugConfig.debug_print(f"⚠ Invalid token from {addr}")
	# 			return  # Invalid frame

	# 		# Step 2: Try to reassemble COBS frame
	# 		complete_cobs_frame = self.reassembler.add_frame_payload(frame_payload)

	# 		if complete_cobs_frame:
	# 			DebugConfig.debug_print(f"✅ Reassembled complete COBS frame: {len(complete_cobs_frame)}B")

	# 			# Step 3: COBS decode to get original IP frame
	# 			try:
	# 				ip_frame, _ = self.cobs_manager.decode_frame(complete_cobs_frame)
	# 				DebugConfig.debug_print(f"✅ COBS decoded to IP frame: {len(ip_frame)}B")

	# 				# Step 4: Process the complete IP frame
	# 				self._process_complete_ip_frame(ip_frame, station_bytes, addr)

	# 			except Exception as e:
	# 				DebugConfig.debug_print(f"✗ COBS decode error from {addr}: {e}")
	# 		else:
	# 			DebugConfig.debug_print(f"📝 Frame payload added to buffer...")

	# 	except Exception as e:
	# 		DebugConfig.debug_print(f"Error processing received data from {addr}: {e}")



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
			DebugConfig.debug_print(f"Error processing IP frame: {e}")







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
	
	# Store original PTT methods
	original_ptt_pressed = radio_system.ptt_pressed
	original_ptt_released = radio_system.ptt_released
	
	# Wrap PTT methods to notify web interface
	async def ptt_pressed_with_web():
		original_ptt_pressed()
		await web_interface.on_ptt_state_changed(True)
	
	async def ptt_released_with_web():
		original_ptt_released() 
		await web_interface.on_ptt_state_changed(False)
	
	# Replace methods (note: this is simplified - you may need async handling)
	radio_system.ptt_pressed = lambda: asyncio.create_task(ptt_pressed_with_web())
	radio_system.ptt_released = lambda: asyncio.create_task(ptt_released_with_web())
	
	# TODO: Add other callbacks as needed
	# - Message received callbacks
	# - Status change callbacks
	# - Audio message callbacks (Phase 2)













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

















# Usage




# Replace the entire main section in interlocutor.py (starting from "if __name__ == "__main__":") with this:

if __name__ == "__main__":
	print("-=" * 40)
	print("Opulent Voice Radio with Terminal Chat")
	print("-=" * 40)

	try:
		# Setup configuration system - NOW RETURNS CONFIG MANAGER TOO
		config, should_exit, config_manager = setup_configuration()
		
		if should_exit:
			sys.exit(0)

		# Set debug mode from configuration
		DebugConfig.set_mode(verbose=config.debug.verbose, quiet=config.debug.quiet)

		# Handle audio CLI commands FIRST (existing code unchanged)
		if '--list-audio' in sys.argv:
			from audio_device_manager import create_audio_manager_for_cli
			device_manager = create_audio_manager_for_cli()
			device_manager.list_audio_devices()
			device_manager.cleanup()
			sys.exit(0)
		
		if '--test-audio' in sys.argv:
			from audio_device_manager import create_audio_manager_for_cli
			device_manager = create_audio_manager_for_cli()
			device_manager.test_audio_devices()
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
			# WEB INTERFACE MODE - FIXED VERSION
			print("🌐 Starting in web interface mode ...")

			# Initialize radio system
			radio = GPIOZeroPTTHandler(
				station_identifier=station_id,
				config=config
			)

			# Setup web interface
			web_interface_instance = initialize_web_interface(radio, config, config_manager)
	
			# Setup enhanced reception (this creates and starts the receiver)
			# enhanced_receiver = setup_enhanced_reception(radio, web_interface_instance)
			enhanced_receiver = radio.setup_enhanced_receiver_with_audio()
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
	
			# Initialize full radio system
			radio = GPIOZeroPTTHandler(
				station_identifier=station_id,
				config=config
			)

			# ENHANCED: Setup enhanced reception for CLI mode
			enhanced_receiver = radio.setup_enhanced_receiver_for_cli()
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


# Also add this function near the top of the file (after the imports):

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



























