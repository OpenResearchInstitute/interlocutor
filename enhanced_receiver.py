#!/usr/bin/env python3
"""
Enhanced MessageReceiver with Web Interface Integration
Bridges UDP packet reception to WebSocket for real-time web updates
"""

import asyncio
import threading
import time
import struct
import json
from queue import Queue, Empty
from typing import Optional, Dict, List, Callable
from datetime import datetime


from radio_protocol import (
    SimpleFrameReassembler,
    COBSFrameBoundaryManager, 
    OpulentVoiceProtocolWithIP,
    StationIdentifier
)


class WebSocketBridge:
	"""Bridges MessageReceiver events to WebSocket interface"""
	
	def __init__(self):
		self.web_interface = None
		self.message_callbacks = []
		self.audio_callbacks = []
		
	def set_web_interface(self, web_interface):
		"""Connect to web interface instance"""
		self.web_interface = web_interface
		
	def add_message_callback(self, callback):
		"""Add callback for received messages"""
		self.message_callbacks.append(callback)
		
	def add_audio_callback(self, callback):
		"""Add callback for received audio"""
		self.audio_callbacks.append(callback)
		
	async def notify_message_received(self, message_data):
		"""Notify web interface of received message"""
		if self.web_interface:
			try:
				await self.web_interface.on_message_received(message_data)
			except Exception as e:
				print(f"Error notifying web interface: {e}")
				
		# Also notify other callbacks
		for callback in self.message_callbacks:
			try:
				callback(message_data)
			except Exception as e:
				print(f"Error in message callback: {e}")
				
	async def notify_audio_received(self, audio_data):
		"""Notify web interface of received audio"""
		if self.web_interface:
			try:
				await self.web_interface.on_audio_received(audio_data)
			except Exception as e:
				print(f"Error notifying web interface of audio: {e}")
				
		# Also notify other callbacks
		for callback in self.audio_callbacks:
			try:
				callback(audio_data)
			except Exception as e:
				print(f"Error in audio callback: {e}")


class EnhancedMessageReceiver:
	"""Enhanced MessageReceiver with web interface integration"""
	
	def __init__(self, listen_port=57372, chat_interface=None):
		self.listen_port = listen_port
		self.chat_interface = chat_interface
		self.socket = None
		self.running = False
		self.receive_thread = None
		
		# Audio and message processing
		self.reassembler = SimpleFrameReassembler()
		self.cobs_manager = COBSFrameBoundaryManager()
		self.protocol = OpulentVoiceProtocolWithIP(StationIdentifier("TEMP"))
		
		# Web interface bridge
		self.web_bridge = WebSocketBridge()
		
		# Audio reception components
		self.audio_decoder = AudioDecoder()
		self.audio_queue = Queue(maxsize=100)  # Buffer for web streaming
		
		# Statistics
		self.stats = {
			'total_packets': 0,
			'audio_packets': 0,
			'text_packets': 0,
			'control_packets': 0,
			'decode_errors': 0,
			'web_notifications': 0
		}
		
	def set_web_interface(self, web_interface):
		"""Connect to web interface for real-time updates"""
		self.web_bridge.set_web_interface(web_interface)
		print("✅ MessageReceiver connected to web interface")
		
	def start(self):
		"""Start the enhanced message receiver"""
		try:
			self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			self.socket.bind(('', self.listen_port))
			self.socket.settimeout(1.0)
			
			self.running = True
			self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
			self.receive_thread.start()
			
			print(f"👂 Enhanced receiver listening on port {self.listen_port}")
			print("🌐 Web interface notifications enabled")
			
		except Exception as e:
			print(f"✗ Failed to start enhanced receiver: {e}")
			
	def stop(self):
		"""Stop the enhanced message receiver"""
		self.running = False
		if self.receive_thread:
			self.receive_thread.join(timeout=2.0)
		if self.socket:
			self.socket.close()
		print("👂 Enhanced receiver stopped")
		
	def _receive_loop(self):
		"""Enhanced receive loop with web notifications"""
		while self.running:
			try:
				data, addr = self.socket.recvfrom(4096)
				self.stats['total_packets'] += 1
				
				# Process in separate thread to avoid blocking
				threading.Thread(
					target=self._process_received_data_async,
					args=(data, addr),
					daemon=True
				).start()
				
			except socket.timeout:
				continue
			except Exception as e:
				if self.running:
					print(f"Receive error: {e}")
					
	def _process_received_data_async(self, data, addr):
		"""Process received data with async web notifications"""
		try:
			# Step 1: Parse Opulent Voice header
			if len(data) < 12:
				return
				
			ov_header = data[:12]
			fragment_payload = data[12:]
			
			# Parse OV header
			station_bytes, token, reserved = struct.unpack('>6s 3s 3s', ov_header)
			
			if token != OpulentVoiceProtocolWithIP.TOKEN:
				return
				
			# Step 2: Try to reassemble COBS frames
			cobs_frames = self.reassembler.add_frame_payload(fragment_payload)
			
			# Step 3: Process each complete COBS frame
			for frame in cobs_frames:
				try:
					ip_frame, _ = self.cobs_manager.decode_frame(frame)
					self._process_complete_ip_frame_async(ip_frame, station_bytes, addr)
				except Exception as e:
					self.stats['decode_errors'] += 1
					print(f"✗ COBS decode error: {e}")
					
		except Exception as e:
			print(f"Error processing received data: {e}")
			
	def _process_complete_ip_frame_async(self, ip_frame, station_bytes, addr):
		"""Process complete IP frame with async web notifications"""
		try:
			# Get station identifier
			try:
				from_station = StationIdentifier.from_bytes(station_bytes)
				from_station_str = str(from_station)
			except:
				from_station_str = f"UNKNOWN-{station_bytes.hex()[:8]}"
				
			# Parse IP header to get UDP payload
			if len(ip_frame) < 20:
				return
				
			ip_header_length = (ip_frame[0] & 0x0F) * 4
			if len(ip_frame) < ip_header_length + 8:
				return
				
			udp_payload = ip_frame[ip_header_length + 8:]
			udp_dest_port = struct.unpack('!H', ip_frame[ip_header_length + 2:ip_header_length + 4])[0]
			
			current_time = datetime.now().isoformat()
			
			# Route based on UDP port and notify web interface
			if udp_dest_port == 57373:  # Voice
				self._handle_audio_packet(udp_payload, from_station_str, current_time)
				
			elif udp_dest_port == 57374:  # Text
				self._handle_text_packet(udp_payload, from_station_str, current_time)
				
			elif udp_dest_port == 57375:  # Control
				self._handle_control_packet(udp_payload, from_station_str, current_time)
				
		except Exception as e:
			print(f"Error processing IP frame: {e}")
			
	def _handle_audio_packet(self, udp_payload, from_station, timestamp):
		"""Handle received audio packet"""
		self.stats['audio_packets'] += 1
		
		try:
			# Extract RTP header and OPUS payload
			if len(udp_payload) >= 12:  # RTP header size
				rtp_payload = udp_payload[12:]  # Skip RTP header
				
				# Decode OPUS audio
				audio_pcm = self.audio_decoder.decode_opus(rtp_payload)
				
				if audio_pcm:
					# Queue for web streaming
					try:
						self.audio_queue.put_nowait({
							'audio_data': audio_pcm,
							'from_station': from_station,
							'timestamp': timestamp,
							'sample_rate': 48000
						})
					except:
						pass  # Queue full, drop oldest
						
					# Notify web interface asynchronously
					self._notify_web_async('audio_received', {
						'from_station': from_station,
						'timestamp': timestamp,
						'audio_length': len(audio_pcm),
						'sample_rate': 48000
					})
					
				print(f"🎤 [{from_station}] Audio: {len(rtp_payload)}B OPUS → {len(audio_pcm) if audio_pcm else 0}B PCM")
				
		except Exception as e:
			print(f"Error processing audio: {e}")
			
	def _handle_text_packet(self, udp_payload, from_station, timestamp):
		"""Handle received text packet"""
		self.stats['text_packets'] += 1
		
		try:
			message_text = udp_payload.decode('utf-8')
			
			# Display in CLI if chat interface available
			if self.chat_interface:
				print(f"\n📨 [{from_station}]: {message_text}")
				if hasattr(self.chat_interface, 'display_received_message'):
					self.chat_interface.display_received_message(from_station, message_text)
					
			# Notify web interface asynchronously
			self._notify_web_async('message_received', {
				'type': 'text',
				'content': message_text,
				'from': from_station,
				'timestamp': timestamp,
				'direction': 'incoming'
			})
			
		except UnicodeDecodeError:
			print(f"📨 [{from_station}]: <Binary text data: {len(udp_payload)}B>")
			
	def _handle_control_packet(self, udp_payload, from_station, timestamp):
		"""Handle received control packet"""
		self.stats['control_packets'] += 1
		
		try:
			control_msg = udp_payload.decode('utf-8')
			
			# Only show non-keepalive control messages
			if not control_msg.startswith('KEEPALIVE'):
				print(f"📋 [{from_station}] Control: {control_msg}")
				
				# Notify web interface for important control messages
				self._notify_web_async('control_received', {
					'type': 'control',
					'content': control_msg,
					'from': from_station,
					'timestamp': timestamp
				})
				
		except UnicodeDecodeError:
			print(f"📋 [{from_station}] Control: <Binary data: {len(udp_payload)}B>")
			
	def _notify_web_async(self, event_type, data):
		"""Send async notification to web interface"""
		def notify():
			try:
				loop = asyncio.new_event_loop()
				asyncio.set_event_loop(loop)
				
				if event_type == 'audio_received':
					loop.run_until_complete(self.web_bridge.notify_audio_received(data))
				else:
					loop.run_until_complete(self.web_bridge.notify_message_received(data))
					
				self.stats['web_notifications'] += 1
				loop.close()
			except Exception as e:
				print(f"Error in web notification: {e}")
				
		threading.Thread(target=notify, daemon=True).start()
		
	def get_audio_stream_data(self):
		"""Get queued audio data for web streaming"""
		audio_packets = []
		try:
			while not self.audio_queue.empty():
				audio_packets.append(self.audio_queue.get_nowait())
		except Empty:
			pass
		return audio_packets
		
	def get_stats(self):
		"""Get enhanced receiver statistics"""
		return self.stats.copy()


class AudioDecoder:
	"""OPUS audio decoder for web interface"""
	
	def __init__(self, sample_rate=48000, channels=1):
		self.sample_rate = sample_rate
		self.channels = channels
		
		try:
			import opuslib
			self.decoder = opuslib.Decoder(
				fs=sample_rate,
				channels=channels
			)
			self.decoder_available = True
			print("✅ OPUS decoder ready for web audio")
		except ImportError:
			print("⚠️  opuslib not available - audio reception disabled")
			self.decoder_available = False
			
	def decode_opus(self, opus_data):
		"""Decode OPUS packet to PCM audio"""
		if not self.decoder_available or not opus_data:
			return None
			
		try:
			# Decode OPUS to PCM
			pcm_data = self.decoder.decode(opus_data, frame_size=1920)  # 40ms at 48kHz
			return pcm_data
		except Exception as e:
			print(f"OPUS decode error: {e}")
			return None


# Integration functions for existing code
def integrate_enhanced_receiver(radio_system, web_interface=None):
	"""Replace existing MessageReceiver with enhanced version"""
	
	# Stop existing receiver if running
	if hasattr(radio_system, 'receiver') and radio_system.receiver:
		radio_system.receiver.stop()
		
	# Create enhanced receiver
	enhanced_receiver = EnhancedMessageReceiver(
		listen_port=radio_system.config.network.listen_port,
		chat_interface=getattr(radio_system, 'chat_interface', None)
	)
	
	# Connect to web interface if provided
	if web_interface:
		enhanced_receiver.set_web_interface(web_interface)
		
	# Replace receiver
	radio_system.receiver = enhanced_receiver
	enhanced_receiver.start()
	
	print("🔄 Upgraded to enhanced message receiver with web integration")
	return enhanced_receiver
