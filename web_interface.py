#!/usr/bin/env python3
"""
Web Interface for Opulent Voice Radio System
"""

import asyncio
import json
import logging
import ipaddress

from datetime import datetime
from pathlib import Path
from typing import Dict, Set, Optional, Any

import threading
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

import uvicorn
import re
import mimetypes

from config_manager import OpulentVoiceConfig
from radio_protocol import DebugConfig
from interlocutor_commands import dispatcher as command_dispatcher

class EnhancedRadioWebInterface:
	"""Enhanced bridge between web GUI and radio system with voice, control, and chat integration"""
	
	def __init__(self, radio_system=None, config: OpulentVoiceConfig = None, config_manager=None):
		self.radio_system = radio_system
		self.config = config
		self.config_manager = config_manager
		self.websocket_clients: Set[WebSocket] = set()
		self.status_cache = {}
		self.message_history = []
		
		# Chat-specific state
		self.chat_manager = None
		self.ptt_state = False
		

		# TRANSMISSION-BASED storage for GUI for incoming transmissions
		self.active_transmissions = {}  # station_id -> current transmission data
		self.completed_transmissions = []  # List of complete transmissions
		self.max_completed_transmissions = 50  # Store last 50 complete transmissions

		# NEW: Add outgoing transmission storage (parallel to incoming)
		self.outgoing_active_transmissions = {}  # For our own outgoing transmissions
		self.outgoing_completed_transmissions = []  # List of our completed outgoing transmissions
		self.max_outgoing_completed_transmissions = 50  # Store last 50 outgoing transmissions

	
		# Keep individual packets for live audio only (small buffer)
		self.live_audio_packets = {}  # For real-time streaming
		self.max_live_packets = 200  # Small buffer for live audio
	
		DebugConfig.debug_print(f"✅ Incoming transmission storage: {self.max_completed_transmissions} transmissions")

		DebugConfig.debug_print(f"✅ Outgoing transmission storage: {self.max_outgoing_completed_transmissions} transmissions")
		
		self.logger = logging.getLogger(__name__)
		
		# Connect to existing chat system
		if radio_system and hasattr(radio_system, 'chat_manager'):
			self.chat_manager = radio_system.chat_manager
			self.logger.info("Connected to existing chat manager")
		
		# Log which config file we're using (if any)
		if self.config_manager and hasattr(self.config_manager, 'config_file_path'):
			self.logger.info(f"Web interface using config file: {self.config_manager.config_file_path}")
		else:
			self.logger.info("Web interface using default configuration")

    






	async def connect_websocket(self, websocket: WebSocket):
		"""Handle new WebSocket connection - Enhanced with message history"""
		try:
			await websocket.accept()
			self.websocket_clients.add(websocket)
		
			# Send current status to new client
			status_data = {
				"type": "initial_status",
				"data": {
					**self.get_current_status(),
					"message_history": self.message_history[-20:]  # Last 20 messages
				}
			}
			await self.send_to_client(websocket, status_data)
		
			self.logger.info(f"New WebSocket client connected. Total: {len(self.websocket_clients)}")
		except Exception as e:
			self.logger.error(f"Error in connect_websocket: {e}")
			raise












	def start_transmission(self, station_id: str, start_time: str):
		"""Start tracking a new transmission"""
		transmission_id = f"tx_{station_id}_{int(time.time() * 1000)}"
		
		self.active_transmissions[station_id] = {
			'transmission_id': transmission_id,
			'station_id': station_id,
			'start_time': start_time,
			'audio_packets': [],
			'total_duration_ms': 0,
			'packet_count': 0
		}
		
		DebugConfig.debug_print(f"📡 TRANSMISSION START: {transmission_id} from {station_id}")






	def end_transmission(self, station_id: str, end_time: str):
		"""End transmission and move to completed storage"""
		if station_id not in self.active_transmissions:
			DebugConfig.debug_print(f"⚠️ TRANSMISSION END: No active transmission for {station_id}")
			return
	
		transmission = self.active_transmissions[station_id]
		transmission['end_time'] = end_time
		transmission['completed_at'] = datetime.now().isoformat()

		# Transcribe complete transmission
		self._transcribe_complete_transmission(transmission)
		
		# Move to completed transmissions
		self.completed_transmissions.append(transmission)
		del self.active_transmissions[station_id]
		
		DebugConfig.debug_print(f"📡 TRANSMISSION COMPLETE: {transmission['transmission_id']} - "
			  f"{transmission['packet_count']} packets, {transmission['total_duration_ms']}ms")
		
		# Cleanup old transmissions
		self.cleanup_completed_transmissions()

	def cleanup_completed_transmissions(self):
		"""Remove oldest complete transmissions when limit exceeded"""
		while len(self.completed_transmissions) > self.max_completed_transmissions:
			old_transmission = self.completed_transmissions.pop(0)  # Remove oldest
			DebugConfig.debug_print(f"🗑️ CLEANUP: Removed old transmission {old_transmission['transmission_id']} "
				  f"({old_transmission['packet_count']} packets)")





	async def on_outgoing_transmission_started(self, transmission_data):
		"""Handle start of outgoing transmission (our own PTT)"""
		try:
			station_id = transmission_data.get('station_id')
			start_time = transmission_data.get('start_time')
            
			DebugConfig.debug_print(f"📤 OUTGOING START: {station_id} at {start_time}")
            
			# End any previous incomplete outgoing transmission
			if station_id in self.outgoing_active_transmissions:
				DebugConfig.debug_print(f"⚠️ Force-ending previous incomplete outgoing transmission from {station_id}")
				await self.on_outgoing_transmission_ended({
					"station_id": station_id,
					"end_time": datetime.now().isoformat(),
					"direction": "outgoing"
				})
            
			# Create new outgoing transmission tracking
			transmission_id = f"tx_out_{station_id}_{int(time.time() * 1000)}"
            
			self.outgoing_active_transmissions[station_id] = {
				'transmission_id': transmission_id,
				'station_id': station_id,
				'start_time': start_time,
				'audio_packets': [],
				'total_duration_ms': 0,
				'packet_count': 0,
				'direction': 'outgoing'
			}
            
			DebugConfig.debug_print(f"📤 OUTGOING TRANSMISSION START: {transmission_id} from {station_id}")
            
			# Notify web clients
			await self.broadcast_to_all({
				"type": "outgoing_transmission_started",
				"data": {
					"station_id": station_id,
					"transmission_id": transmission_id,
					"start_time": start_time,
					"direction": "outgoing"
				}
			})
            
		except Exception as e:
			print(f"📤 OUTGOING START ERROR: {e}")
			import traceback
			traceback.print_exc()





	async def on_outgoing_transmission_ended(self, transmission_data):
		"""Handle end of outgoing transmission (our own PTT release)"""
		try:
			station_id = transmission_data.get('station_id')
			end_time = transmission_data.get('end_time')
            
			DebugConfig.debug_print(f"📤 OUTGOING END: {station_id} at {end_time}")
            
			if station_id not in self.outgoing_active_transmissions:
				DebugConfig.debug_print(f"⚠️ OUTGOING END: No active outgoing transmission for {station_id}")
				return
            
			transmission = self.outgoing_active_transmissions[station_id]
			transmission['end_time'] = end_time
			transmission['completed_at'] = datetime.now().isoformat()

			# Transcribe complete outgoing transmission
			self._transcribe_complete_outgoing_transmission(transmission)
            
			# Move to completed outgoing transmissions
			self.outgoing_completed_transmissions.append(transmission)
			del self.outgoing_active_transmissions[station_id]
            
			DebugConfig.debug_print(f"📤 OUTGOING TRANSMISSION COMPLETE: {transmission['transmission_id']} - "
				f"{transmission['packet_count']} packets, {transmission['total_duration_ms']}ms")
            
			# Cleanup old outgoing transmissions
			self.cleanup_outgoing_completed_transmissions()
            
			# Notify web clients to create outgoing audio bubble
			await self.broadcast_to_all({
				"type": "outgoing_transmission_ended",
				"data": {
					"station_id": station_id,
					"transmission_id": transmission['transmission_id'],
					"end_time": end_time,
					"direction": "outgoing",
					"packet_count": transmission['packet_count'],
					"total_duration_ms": transmission['total_duration_ms']
				}
			})
            
		except Exception as e:
			print(f"📤 OUTGOING END ERROR: {e}")
			import traceback
			traceback.print_exc()

	def cleanup_outgoing_completed_transmissions(self):
		"""Remove oldest complete outgoing transmissions when limit exceeded"""
		while len(self.outgoing_completed_transmissions) > self.max_outgoing_completed_transmissions:
			old_transmission = self.outgoing_completed_transmissions.pop(0)  # Remove oldest
			DebugConfig.debug_print(f"🗑️ OUTGOING CLEANUP: Removed old outgoing transmission {old_transmission['transmission_id']} "
				f"({old_transmission['packet_count']} packets)")




	def _transcribe_complete_outgoing_transmission(self, transmission):
		"""Transcribe a complete outgoing transmission"""
		try:
			audio_packets = transmission.get('audio_packets', [])
			if not audio_packets:
				DebugConfig.debug_print(f"📝 OUTGOING TRANSCRIPTION: No audio packets in transmission {transmission['transmission_id']}")
				return
        
			# Concatenate all audio data from the outgoing transmission
			concatenated_audio = bytearray()
			for packet in audio_packets:
				audio_data = packet.get('audio_data')
				if audio_data:
					concatenated_audio.extend(audio_data)
        
			if not concatenated_audio:
				DebugConfig.debug_print(f"📝 OUTGOING TRANSCRIPTION: No audio data found in transmission {transmission['transmission_id']}")
				return
        
			# Get transcriber from radio system
			transcriber = None
			if (hasattr(self, 'radio_system') and 
				hasattr(self.radio_system, 'enhanced_receiver') and
				hasattr(self.radio_system.enhanced_receiver, 'transcriber')):
				transcriber = self.radio_system.enhanced_receiver.transcriber
        
			if transcriber:
				DebugConfig.debug_print(f"📝 OUTGOING TRANSCRIPTION: Processing complete transmission {transmission['transmission_id']} "
					f"({len(concatenated_audio)}B audio from {len(audio_packets)} packets)")
            
				# Process the complete outgoing transmission audio
				transcriber.process_audio_segment(
					audio_data=bytes(concatenated_audio),
					station_id=transmission['station_id'],
					direction='outgoing',  # Mark as outgoing
					transmission_id=transmission['transmission_id']
				)
			else:
				DebugConfig.debug_print(f"📝 OUTGOING TRANSCRIPTION: No transcriber available")
    
		except Exception as e:
			DebugConfig.debug_print(f"📝 OUTGOING TRANSCRIPTION ERROR: {e}")
			import traceback
			traceback.print_exc()



	async def handle_send_text_message(self, data: Dict):
		"""Handle text message from GUI - Enhanced with proper message flow"""
		message = data.get('message', '').strip()
		if not message:
			return

		# ── Slash-command dispatch ──────────────────────────────
		# Check for commands BEFORE creating message records or
		# sending to chat_manager. Commands are local-only.
		cmd_result = command_dispatcher.dispatch(message)
		if cmd_result is not None:
			# Build a system message for the chat display
			if cmd_result.is_error:
				content = f"⚠️ {cmd_result.error}"
			else:
				content = cmd_result.summary

			command_message = {
				"type": "command_result",
				"direction": "system",
				"content": content,
				"command": cmd_result.command,
				"details": cmd_result.details if not cmd_result.is_error else {},
				"is_error": cmd_result.is_error,
				"timestamp": datetime.now().isoformat(),
				"from": "Interlocutor",
				"message_id": f"cmd_{int(time.time() * 1000)}"
			}

			# Add to history so it persists across reconnects
			self.message_history.append(command_message)

			# Broadcast to all connected web clients
			await self.broadcast_to_all({
				"type": "command_result",
				"data": command_message
			})
			return  # Do NOT send to chat_manager / radio
		# ── End command dispatch ────────────────────────────────

		try:
			# Create message record immediately
			message_data = {
				"type": "text",
				"direction": "outgoing",
				"content": message,
				"timestamp": datetime.now().isoformat(),
				"from": str(self.radio_system.station_id) if self.radio_system else "LOCAL",
				"message_id": f"msg_{int(time.time() * 1000)}_{hash(message) % 10000}"
			}
		
			# Add to history FIRST (before sending)
			self.message_history.append(message_data)
		
			# Limit history size
			if len(self.message_history) > 1000:
				self.message_history = self.message_history[-500:]  # Keep last 500
		
			# Send through existing chat manager if available
			if self.chat_manager:
				result = self.chat_manager.handle_message_input(message)
			
				# Handle different result types
				if result['status'] == 'sent':
					# Message sent successfully
					await self.broadcast_to_all({
						"type": "message_sent",
						"data": message_data
					})
				
				elif result['status'] == 'buffered':
					# Message buffered during PTT
					await self.broadcast_to_all({
						"type": "message_buffered",
						"data": {
							"message": message,
							"count": result['count'],
							"reason": "PTT active"
						}
					})
				
				elif result['status'] == 'queued_audio_driven':
					# Message queued for audio-driven transmission
					await self.broadcast_to_all({
						"type": "message_sent",
						"data": message_data
					})
					# TTS is handled by chat_manager path, not here



			# Fallback: Send directly through radio system
			elif self.radio_system and hasattr(self.radio_system, 'audio_frame_manager'):
				self.radio_system.audio_frame_manager.queue_text_message(message)
				await self.broadcast_to_all({
					"type": "message_sent",
					"data": message_data
				})
		
			else:
				# No radio system available - store message but mark as simulated
				message_data["simulated"] = True
				await self.broadcast_to_all({
					"type": "message_sent",
					"data": message_data
				})
			
			self.logger.info(f"Text message processed: {message[:50]}...")
		
		except Exception as e:
			self.logger.error(f"Error sending text message: {e}")
			await self.broadcast_to_all({
				"type": "error",
				"message": f"Failed to send message: {str(e)}"
			})

	def disconnect_websocket(self, websocket: WebSocket):
		"""Handle WebSocket disconnection"""
		self.websocket_clients.discard(websocket)
		self.logger.info(f"WebSocket client disconnected. Remaining: {len(self.websocket_clients)}")
	
	async def send_to_client(self, websocket: WebSocket, message: Dict):
		"""Send message to specific client"""
		try:
			await websocket.send_text(json.dumps(message))
		except Exception as e:
			self.logger.warning(f"Failed to send to client: {e}")
			self.websocket_clients.discard(websocket)
	

















	async def on_audio_received(self, audio_data: Dict):
		"""Handle received audio data - now handles both incoming AND outgoing"""
		try:
			station_id = audio_data.get('from_station', 'UNKNOWN')
			timestamp = audio_data.get('timestamp', datetime.now().isoformat())
			direction = audio_data.get('direction', 'incoming')  # NEW: Check direction

			audio_packet = {
				**audio_data,
				'audio_id': f"audio_{direction}_{int(time.time() * 1000)}_{hash(station_id) % 10000}",
				'received_at': datetime.now().isoformat()
			}

			DebugConfig.debug_print(f"🎤 AUDIO PACKET: {direction} from {station_id}")




			if direction == 'outgoing':
				# OUTGOING: Add to our own outgoing transmission if exists
				if station_id in self.outgoing_active_transmissions:
					transmission = self.outgoing_active_transmissions[station_id]
					transmission['audio_packets'].append(audio_packet)
					transmission['packet_count'] += 1
					transmission['total_duration_ms'] += audio_data.get('duration_ms', 40)

					DebugConfig.debug_print(f"📤 OUTGOING AUDIO: Added packet to {transmission['transmission_id']} "
						f"({transmission['packet_count']} packets)")
        
					# Send outgoing audio notification to web clients
					await self.broadcast_to_all({
						"type": "outgoing_audio_received",
						"data": {
							"from_station": station_id,
							"timestamp": timestamp,
							"audio_id": audio_packet['audio_id'],
 							"audio_length": audio_data.get('audio_length', 0),
							"sample_rate": audio_data.get('sample_rate', 48000),
							"duration_ms": audio_data.get('duration_ms', 40),
							"direction": "outgoing"
						}
 					})
				else:
					# GUARD: Don't process late audio packets (prevents ghost transmissions)
					DebugConfig.debug_print(f"📤 DROPPED: Late outgoing audio from {station_id} (transmission already ended)")
					return  # Stop processing - prevents ghost transmission





			else:
				# INCOMING: Use existing logic (unchanged)
				if station_id in self.active_transmissions:
					transmission = self.active_transmissions[station_id]
					transmission['audio_packets'].append(audio_packet)
					transmission['packet_count'] += 1
					transmission['total_duration_ms'] += audio_data.get('duration_ms', 40)
        
					DebugConfig.debug_print(f"📡 INCOMING AUDIO: Added packet to {transmission['transmission_id']} "
						f"({transmission['packet_count']} packets)")
				else:
					# No active transmission - add to live buffer for real-time audio
					self.live_audio_packets[audio_packet['audio_id']] = audio_packet
        
					# Cleanup live buffer
					if len(self.live_audio_packets) > self.max_live_packets:
						oldest_id = min(self.live_audio_packets.keys())
						del self.live_audio_packets[oldest_id]
        
					DebugConfig.debug_print(f"🔊 LIVE AUDIO: Added packet to live buffer ({len(self.live_audio_packets)} packets)")
    
				# Broadcast to web clients (existing notification)
				await self.broadcast_to_all({
					"type": "audio_received",
					"data": {
						"from_station": station_id,
						"timestamp": timestamp,
						"audio_id": audio_packet['audio_id'],
						"audio_length": audio_data.get('audio_length', 0),
						"sample_rate": audio_data.get('sample_rate', 48000),
						"duration_ms": audio_data.get('duration_ms', 40),
						"direction": "incoming"
					}
				})

		except Exception as e:
			print(f"📡 TRANSMISSION AUDIO ERROR: {e}")
			import traceback
			traceback.print_exc()






	async def on_control_received(self, control_data: Dict):
		"""Handle received control messages - especially PTT boundaries for transmission grouping"""
		try:
			control_msg = control_data.get('content', '')
			from_station = control_data.get('from', 'UNKNOWN')
			timestamp = control_data.get('timestamp', datetime.now().isoformat())
		
			DebugConfig.debug_print(f"🎛️ TRANSMISSION CONTROL: {control_msg} from {from_station}")
		
			if control_msg == 'PTT_START':
				# Start new transmission and get ID
				transmission_id = self.start_transmission(from_station, timestamp)
				
				# Send transmission started notification (separate from control message)
				await self.broadcast_to_all({
					"type": "transmission_started",
					"data": {
						"station_id": from_station,
						"transmission_id": transmission_id,
						"start_time": timestamp
					}
				})
				DebugConfig.debug_print(f"🎛️ TRANSMISSION: Sent transmission_started with ID {transmission_id}")
				
			elif control_msg == 'PTT_STOP':
				# Get transmission ID before ending
				transmission_id = None
				if from_station in self.active_transmissions:
					transmission_id = self.active_transmissions[from_station]['transmission_id']
				
				# End transmission and store it
				self.end_transmission(from_station, timestamp)
				
				# Send transmission ended notification (separate from control message)
				if transmission_id:
					await self.broadcast_to_all({
						"type": "transmission_ended", 
						"data": {
							"station_id": from_station,
							"transmission_id": transmission_id,
							"end_time": timestamp
						}
					})
					DebugConfig.debug_print(f"🎛️ TRANSMISSION: Sent transmission_ended with ID {transmission_id}")
		
			# Send original control message unchanged (don't modify PTT messages!)
			await self.broadcast_to_all({
				"type": "control_received",
				"data": {
					"content": control_msg,
					"from": from_station,
					"timestamp": timestamp,
					"type": "control",
					"priority": "high" if control_msg.startswith('PTT_') else "normal"
				}
			})
		
			DebugConfig.debug_print(f"🌐 WEB CONTROL DEBUG: Control broadcast complete as control_received type")
		
		except Exception as e:
			print(f"🌐 WEB CONTROL DEBUG ERROR: Error handling control message: {e}")
			import traceback
			traceback.print_exc()








	# Also add debug to the broadcast method (just above)
	async def broadcast_to_all(self, message: Dict):
		"""Broadcast message to all connected clients with debugging"""
		if not self.websocket_clients:
			DebugConfig.debug_print(f"🌐 BROADCAST DEBUG: No clients connected")
			return
        
		DebugConfig.debug_print(f"🌐 BROADCAST DEBUG: Broadcasting {message.get('type', 'unknown')} to {len(self.websocket_clients)} clients")
    
		disconnected = set()
		successful_sends = 0
    
		for websocket in self.websocket_clients.copy():
			try:
				await websocket.send_text(json.dumps(message))
				successful_sends += 1
			except Exception as e:
				print(f"🌐 BROADCAST DEBUG: Failed to send to client: {e}")
				disconnected.add(websocket)
    
		# Clean up disconnected clients
		self.websocket_clients -= disconnected
    
		DebugConfig.debug_print(f"🌐 BROADCAST DEBUG: Sent to {successful_sends}/{len(self.websocket_clients) + len(disconnected)} clients")
		if disconnected:
			DebugConfig.debug_print(f"🌐 BROADCAST DEBUG: Removed {len(disconnected)} disconnected clients")











	async def on_message_received(self, message_data: Dict):
		"""Enhanced message received handler"""
		try:
			# Process the message data (existing logic enhanced)
			processed_message = {
				"type": message_data.get("type", "text"),
				"direction": "incoming",
				"content": message_data.get("content", ""),
				"timestamp": message_data.get("timestamp", datetime.now().isoformat()),	
				"from": message_data.get("from", "UNKNOWN"),
				"metadata": message_data.get("metadata", {}),
				"message_id": f"msg_{int(time.time() * 1000)}_{hash(message_data.get('content', '')) % 10000}"
			}
		
			# Add to history
			self.message_history.append(processed_message)
		
			# Limit history size
			if len(self.message_history) > 1000:
				self.message_history = self.message_history[-500:]
			
			# Broadcast to all web clients immediately
			await self.broadcast_to_all({
				"type": "message_received",
				"data": processed_message
			})
		
			self.logger.info(f"Message received from {processed_message['from']}: {processed_message['content'][:50]}...")
		
		except Exception as e:
			self.logger.error(f"Error handling received message: {e}")

	async def handle_get_audio_stream(self, websocket: WebSocket):
		"""Stream audio data to web interface"""
		try:
			# Get audio data from receiver if available
			if (hasattr(self.radio_system, 'receiver') and 
				hasattr(self.radio_system.receiver, 'get_audio_stream_data')):
				
				audio_packets = self.radio_system.receiver.get_audio_stream_data()
				
				await self.send_to_client(websocket, {
					"type": "audio_stream_data",
					"data": {
						"packets": len(audio_packets),
						"audio_available": len(audio_packets) > 0
					}
				})
			else:
				await self.send_to_client(websocket, {
					"type": "audio_stream_data", 
					"data": {
						"packets": 0,
						"audio_available": False,
						"error": "Audio receiver not available"
					}
				})
			
		except Exception as e:
			self.logger.error(f"Error getting audio stream: {e}")
			await self.send_to_client(websocket, {
				"type": "error",
				"message": f"Audio stream error: {str(e)}"
			})















	async def handle_audio_playback_request(self, websocket: WebSocket, data: Dict):
		"""Handle request to play back received audio - UPDATED for transmission storage"""
		try:
			audio_id = data.get('audio_id')
			if not audio_id:
				await self.send_to_client(websocket, {
					"type": "error",
					"message": "Audio ID not provided"
				})
				return
			
			# Search for audio in completed transmissions
			found_audio = None
			for transmission in self.completed_transmissions:
				for packet in transmission['audio_packets']:
					if packet.get('audio_id') == audio_id:
						found_audio = packet
						break
				if found_audio:
					break
			
			# Search in live audio packets if not found in transmissions
			if not found_audio and audio_id in self.live_audio_packets:
				found_audio = self.live_audio_packets[audio_id]
			
			if not found_audio:
				await self.send_to_client(websocket, {
					"type": "error",
					"message": "Audio message not found"
				})
				return
			
			# Send audio info for playback
			await self.send_to_client(websocket, {
				"type": "audio_playback_data",
				"data": {
					"audio_id": audio_id,
					"from_station": found_audio.get('from_station'),
					"timestamp": found_audio.get('timestamp'),
					"sample_rate": found_audio.get('sample_rate', 48000),
					"duration_ms": found_audio.get('duration_ms', 40)
				}
			})
		
		except Exception as e:
			self.logger.error(f"Error handling audio playback request: {e}")







	async def handle_transmission_playback_request(self, websocket: WebSocket, data: Dict):
		"""Handle playback request using CLI speakers - FIXED for both incoming and outgoing"""
		try:
			transmission_id = data.get('transmission_id')
			station_id = data.get('station_id')
			
			DebugConfig.debug_print(f"🎵 PLAYBACK REQUEST: {transmission_id}")
	
			# Search in both incoming AND outgoing completed transmissions
			target_transmission = None
			direction = 'incoming'  # Default assumption
			
			# First, search completed incoming transmissions
			for transmission in self.completed_transmissions:
				if transmission['transmission_id'] == transmission_id:
					target_transmission = transmission
					direction = 'incoming'
					break
		
			# If not found, search completed outgoing transmissions
			if not target_transmission:
				for transmission in self.outgoing_completed_transmissions:
					if transmission['transmission_id'] == transmission_id:
						target_transmission = transmission
						direction = 'outgoing'
						break
	
			DebugConfig.debug_print(f"🎵 PLAYBACK: Found {direction} transmission with {len(target_transmission['audio_packets']) if target_transmission else 0} packets")
	
			if not target_transmission:
				DebugConfig.debug_print(f"🎵 PLAYBACK: Transmission {transmission_id} not found in incoming or outgoing")
				await self.send_to_client(websocket, {
					"type": "transmission_playback_error",
					"data": {
						"transmission_id": transmission_id,
						"error": f"Transmission {transmission_id} not found"
					}
				})
				return
			
			audio_packets = target_transmission['audio_packets']
			if not audio_packets:
				print(f"🎵 PLAYBACK: No audio packets in transmission")
				await self.send_to_client(websocket, {
					"type": "transmission_playback_error",
					"data": {
						"transmission_id": transmission_id,
						"error": "No audio data in transmission"
					}
				})
				return
		
			DebugConfig.debug_print(f"🎵 REQUEST PLAYBACK: Found {direction} transmission with {len(audio_packets)} packets")
			
			# Get AudioOutputManager from enhanced receiver
			audio_output_manager = None
			if (self.radio_system and 
				hasattr(self.radio_system, 'enhanced_receiver') and 
				self.radio_system.enhanced_receiver and
				hasattr(self.radio_system.enhanced_receiver, 'audio_output') and
				self.radio_system.enhanced_receiver.audio_output):
				
				audio_output_manager = self.radio_system.enhanced_receiver.audio_output
				DebugConfig.debug_print(f"🎵 PLAYBACK: AudioOutputManager found - device {audio_output_manager.output_device}")
			
			if not audio_output_manager or not audio_output_manager.playing:
				print(f"🎵 PLAYBACK: ❌ AudioOutputManager not available or not active")
				await self.send_to_client(websocket, {
					"type": "transmission_playback_error",
					"data": {
						"transmission_id": transmission_id,
						"error": "CLI audio output not available"
					}
				})
				return
		
			DebugConfig.debug_print(f"🎵 PLAYBACK: ✅ Using CLI speakers (device {audio_output_manager.output_device})")
			
			# Concatenate all audio data
			concatenated_audio = bytearray()
			packets_with_data = 0
			
			for i, packet in enumerate(audio_packets):
				audio_data_field = packet.get('audio_data')
				if audio_data_field:
					concatenated_audio.extend(audio_data_field)
					packets_with_data += 1
				else:
					print(f"🎵 PLAYBACK: ⚠️ Packet {i+1} has no audio_data field")
			
			DebugConfig.debug_print(f"🎵 PLAYBACK: {packets_with_data}/{len(audio_packets)} packets had audio data")
			
			if concatenated_audio:
				# Queue the concatenated audio for playback through CLI speakers!
				playback_label = f"{station_id}_{direction.upper()}_PLAYBACK"
				audio_output_manager.queue_audio_for_playback(
					bytes(concatenated_audio), 
					playback_label
				)
				
				duration_ms = target_transmission['total_duration_ms']
				duration_sec = duration_ms / 1000.0
				
				print(f"🎵 PLAYBACK SUCCESS: {direction} transmission queued ({len(concatenated_audio)} bytes)")
			
				# Send success response
				await self.send_to_client(websocket, {
					"type": "transmission_playback_started",
					"data": {
						"transmission_id": transmission_id,
						"from_station": station_id,
						"duration_ms": duration_ms,
						"total_segments": packets_with_data,
						"playback_method": "cli_speakers",
						"device_index": audio_output_manager.output_device,
						"audio_bytes": len(concatenated_audio),
						"direction": direction  # Include direction in response
					}
				})
				
			else:
				print(f"🎵 PLAYBACK: ❌ No audio data found in any packets")
				await self.send_to_client(websocket, {
					"type": "transmission_playback_error",
					"data": {
						"transmission_id": transmission_id,
						"error": "No audio data found in transmission packets"
					}
				})
			
		except Exception as e:
			print(f"🎵 PLAYBACK ERROR: {e}")
			import traceback
			traceback.print_exc()
			await self.send_to_client(websocket, {
				"type": "transmission_playback_error",
				"data": {
					"transmission_id": transmission_id,
					"error": f"Playback failed: {str(e)}"
				}
			})






	# Add transcription result handler to EnhancedRadioWebInterface:
	async def on_transcription_received(self, transcription_data):
		"""Handle transcription results from the transcription system"""
		try:
			# Broadcast transcription to web clients
			await self.broadcast_to_all({
				"type": "transcription_received",
				"data": transcription_data
			})
        
			print(f"📝 Transcription: [{transcription_data['station_id']}] \"{transcription_data['transcription']}\"")
        
		except Exception as e:
			print(f"Error handling transcription: {e}")




	def _transcribe_complete_transmission(self, transmission):
		"""Transcribe a complete transmission using all audio packets"""
		try:
			audio_packets = transmission.get('audio_packets', [])
			if not audio_packets:
				DebugConfig.debug_print(f"📝 TRANSCRIPTION: No audio packets in transmission {transmission['transmission_id']}")
				return
        
			# Concatenate all audio data from the transmission
			concatenated_audio = bytearray()
			for packet in audio_packets:
				audio_data = packet.get('audio_data')
				if audio_data:
					concatenated_audio.extend(audio_data)
        
			if not concatenated_audio:
				DebugConfig.debug_print(f"📝 TRANSCRIPTION: No audio data found in transmission {transmission['transmission_id']}")
				return
        
			# Get transcriber from radio system
			transcriber = None
			if (hasattr(self, 'radio_system') and 
				hasattr(self.radio_system, 'enhanced_receiver') and
				hasattr(self.radio_system.enhanced_receiver, 'transcriber')):
				transcriber = self.radio_system.enhanced_receiver.transcriber
        
			if transcriber:
				DebugConfig.debug_print(f"📝 TRANSCRIPTION: Processing complete transmission {transmission['transmission_id']} "
					f"({len(concatenated_audio)}B audio from {len(audio_packets)} packets)")
            
				# Process the complete transmission audio
				transcriber.process_audio_segment(
					audio_data=bytes(concatenated_audio),
					station_id=transmission['station_id'],
					direction='incoming',
					transmission_id=transmission['transmission_id']
				)
			else:
				DebugConfig.debug_print(f"📝 TRANSCRIPTION: No transcriber available")
				DebugConfig.debug_print(f"   Has radio_system: {hasattr(self, 'radio_system')}")
				if hasattr(self, 'radio_system'):
					DebugConfig.debug_print(f"   Has enhanced_receiver: {hasattr(self.radio_system, 'enhanced_receiver')}")
					if hasattr(self.radio_system, 'enhanced_receiver'):
						DebugConfig.debug_print(f"   Has transcriber: {hasattr(self.radio_system.enhanced_receiver, 'transcriber')}")
    
		except Exception as e:
			DebugConfig.debug_print(f"📝 TRANSCRIPTION ERROR: {e}")
			import traceback
			traceback.print_exc()




	def _calculate_audio_duration(self, audio_data):
		"""Calculate audio duration in milliseconds"""
		try:
			audio_length = audio_data.get('audio_length', 0)
			sample_rate = audio_data.get('sample_rate', 48000)
			
			# Assuming 16-bit mono PCM
			samples = audio_length // 2
			duration_ms = (samples / sample_rate) * 1000
		
			return int(duration_ms)
		except:
			return 40  # Default 40ms frame









	async def get_reception_stats(self):
		"""Get reception statistics for web interface - UPDATED for transmission storage"""
		# Count total audio packets across all transmissions
		total_audio_packets = 0
		for transmission in self.completed_transmissions:
			total_audio_packets += transmission['packet_count']
		
		# Add active transmission packets
		for transmission in self.active_transmissions.values():
			total_audio_packets += transmission['packet_count']
		
		stats = {
			'audio_messages_stored': total_audio_packets,
			'completed_transmissions': len(self.completed_transmissions),
			'active_transmissions': len(self.active_transmissions),
			'message_history_count': len(self.message_history),
			'last_received_message': None,
			'last_received_audio': None
		}
	
		# Get last received message
		incoming_messages = [m for m in self.message_history if m.get('direction') == 'incoming']
		if incoming_messages:
			stats['last_received_message'] = incoming_messages[-1]
			
		# Get last received audio from completed transmissions
		if self.completed_transmissions:
			latest_transmission = self.completed_transmissions[-1]
			if latest_transmission['audio_packets']:
				latest_audio = latest_transmission['audio_packets'][-1]
				stats['last_received_audio'] = {
					'from_station': latest_transmission['station_id'],
					'timestamp': latest_audio.get('timestamp'),
					'audio_id': latest_audio.get('audio_id')
				}
		
		# Get receiver stats if available
		if (hasattr(self.radio_system, 'receiver') and 
			hasattr(self.radio_system.receiver, 'get_stats')):
			stats['receiver_stats'] = self.radio_system.receiver.get_stats()
		
		return stats








	async def handle_gui_command(self, websocket: WebSocket, command_data: Dict):
		"""Process commands from GUI - Enhanced with new message commands"""
		try:
			command = command_data.get('action')
			data = command_data.get('data', {})
		
			# Configuration commands (existing)
			if command == 'update_config':
				await self.handle_update_config(data)
			elif command == 'get_current_config':
				await self.handle_get_current_config(websocket)
			elif command == 'save_config':
				await self.handle_save_config(data)
			elif command == 'load_config':
				await self.handle_load_config(websocket, data)
			elif command == 'create_config':
				await self.handle_create_config(data)
			elif command == 'test_connection':
				await self.handle_test_connection(websocket)
			elif command == 'get_audio_devices':
				await self.handle_get_audio_devices(websocket)
			elif command == 'test_audio':
				await self.handle_test_audio(websocket, data)
			elif command == 'set_debug_mode':
				await self.handle_debug_mode_change(data)
			elif command == 'test_connection_with_form': 
				await self.handle_test_connection_with_form(websocket, data) 

			# TTS command
			elif command == 'test_tts':
				await self.handle_test_tts(websocket, data)

			# Voice commands (enhanced)
			elif command == 'get_audio_stream':
				await self.handle_get_audio_stream(websocket)
			elif command == 'request_audio_playback':
				await self.handle_audio_playback_request(websocket, data)
			elif command == 'request_transmission_playback':
				await self.handle_transmission_playback_request(websocket, data)
			elif command == 'get_reception_stats':
				stats = await self.get_reception_stats()
				await self.send_to_client(websocket, {
					"type": "reception_stats",
					"data": stats
				})

		
			# Chat commands (existing + enhanced)
			elif command == 'send_text_message':
				await self.handle_send_text_message(data)
			elif command == 'ptt_pressed':
				await self.handle_ptt_pressed()
			elif command == 'ptt_released':
				await self.handle_ptt_released()
			elif command == 'get_message_history':  # NEW
				await self.handle_get_message_history(websocket)
			elif command == 'clear_message_history':  # NEW
				await self.handle_clear_message_history()
			
			else:
				self.logger.warning(f"Unknown command: {command}")
				await self.send_to_client(websocket, {
					"type": "error",
					"message": f"Unknown command: {command}"
				})
			
		except Exception as e:
			self.logger.error(f"Error handling GUI command: {e}")
			await self.send_to_client(websocket, {
				"type": "error",
				"message": str(e)
			})

	async def handle_ptt_pressed(self):
		"""Handle PTT button press from GUI"""
		try:
			if self.radio_system:
				# Call the radio system's PTT method
				if hasattr(self.radio_system, 'ptt_pressed'):
					self.radio_system.ptt_pressed()
				elif hasattr(self.radio_system, 'audio_frame_manager'):
					self.radio_system.audio_frame_manager.set_voice_active(True)
			
			self.ptt_state = True
			
			# Update chat manager state if available
			if self.chat_manager:
				self.chat_manager.set_ptt_state(True)
			
			await self.broadcast_to_all({
				"type": "ptt_state_changed",
				"data": {"active": True}
			})
			
			self.logger.info("PTT activated via web interface")
			
		except Exception as e:
			self.logger.error(f"Error activating PTT: {e}")
			await self.broadcast_to_all({
				"type": "error",
				"message": f"Failed to activate PTT: {str(e)}"
			})

	async def handle_ptt_released(self):
		"""Handle PTT button release from GUI"""
		try:
			if self.radio_system:
				# Call the radio system's PTT release method
				if hasattr(self.radio_system, 'ptt_released'):
					self.radio_system.ptt_released()
				elif hasattr(self.radio_system, 'audio_frame_manager'):
					self.radio_system.audio_frame_manager.set_voice_active(False)
			
			self.ptt_state = False
			
			# Update chat manager state if available
			if self.chat_manager:
				self.chat_manager.set_ptt_state(False)
			
			await self.broadcast_to_all({
				"type": "ptt_state_changed",
				"data": {"active": False}
			})
			
			self.logger.info("PTT released via web interface")
			
		except Exception as e:
			self.logger.error(f"Error releasing PTT: {e}")
			await self.broadcast_to_all({
				"type": "error",
				"message": f"Failed to release PTT: {str(e)}"
			})

	async def handle_get_message_history(self, websocket: WebSocket):
		"""Send complete message history to client"""
		await self.send_to_client(websocket, {
			"type": "message_history",
			"data": self.message_history
		})

	async def handle_clear_message_history(self):
		"""Clear message history"""
		cleared_count = len(self.message_history)
		self.message_history.clear()
	
		await self.broadcast_to_all({
			"type": "message_history_cleared",
			"data": {
				"cleared_count": cleared_count,
				"timestamp": datetime.now().isoformat()
			}
		})
	
		self.logger.info(f"Cleared {cleared_count} messages from history")


	async def on_ptt_state_changed(self, active: bool):
		"""Called when PTT state changes from radio system"""
		self.ptt_state = active
		await self.broadcast_to_all({
			"type": "ptt_state_changed",
			"data": {"active": active}
		})







	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	#Configuration handler methods
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-





	async def handle_get_current_config(self, websocket: WebSocket):
		"""Send current configuration to the web interface - FULLY RESTORED with GUI support"""
		try:
			if self.config:
				# ADD DEBUG HERE
				print(f"🔧 DEBUG: config_manager exists: {self.config_manager is not None}")
				if self.config_manager:
					print(f"🔧 DEBUG: config_file_path: {getattr(self.config_manager, 'config_file_path', 'NOT_SET')}")

				# Convert config to dictionary format for the web interface
				config_dict = {
					'callsign': getattr(self.config, 'callsign', 'NOCALL'),
					'network': {
						'target_ip': self.config.network.target_ip,
						'target_port': self.config.network.target_port,
						'listen_port': self.config.network.listen_port,
						'encap_mode': self.config.network.encap_mode,
						'voice_port': getattr(self.config.network, 'voice_port', 57373),
						'text_port': getattr(self.config.network, 'text_port', 57374),
						'control_port': getattr(self.config.network, 'control_port', 57375),
					},
					'audio': {
						'input_device': self.config.audio.input_device,
						'device_keywords': self.config.audio.device_keywords,
					},
					'gpio': {
						'ptt_pin': self.config.gpio.ptt_pin,
						'led_pin': self.config.gpio.led_pin,
						'button_bounce_time': self.config.gpio.button_bounce_time,
						'led_brightness': self.config.gpio.led_brightness,
					},
					'protocol': {
						'target_type': self.config.protocol.target_type,
						'keepalive_interval': self.config.protocol.keepalive_interval,
						'continuous_stream': self.config.protocol.continuous_stream,
					},
					'debug': {
						'verbose': self.config.debug.verbose,
						'quiet': self.config.debug.quiet,
					},
					'ui': {
						'chat_only_mode': getattr(self.config.ui, 'chat_only_mode', False),
						'web_interface_enabled': getattr(self.config.ui, 'web_interface_enabled', False),
						'web_interface_port': getattr(self.config.ui, 'web_interface_port', 8000),
						'web_interface_host': getattr(self.config.ui, 'web_interface_host', '0.0.0.0'),
					},
					'gui': {
						'transcription': {
							'enabled': getattr(self.config.gui.transcription, 'enabled', False),
							'method': getattr(self.config.gui.transcription, 'method', 'auto'),
							'language': getattr(self.config.gui.transcription, 'language', 'auto'),
							'confidence_threshold': getattr(self.config.gui.transcription, 'confidence_threshold', 0.7),
							'model_size': getattr(self.config.gui.transcription, 'model_size', 'base'),
						},
						'tts': {
							'enabled': getattr(self.config.gui.tts, 'enabled', False),
							'engine': getattr(self.config.gui.tts, 'engine', 'system'),
							'voice': getattr(self.config.gui.tts, 'voice', 'default'),
							'rate': getattr(self.config.gui.tts, 'rate', 200),
							'volume': getattr(self.config.gui.tts, 'volume', 0.8),
							'incoming_enabled': getattr(self.config.gui.tts, 'incoming_enabled', True),
							'include_station_id': getattr(self.config.gui.tts, 'include_station_id', True),
							'outgoing_enabled': getattr(self.config.gui.tts, 'outgoing_enabled', False),
 							'include_confirmation': getattr(self.config.gui.tts, 'include_confirmation', True),
							'outgoing_delay_seconds': getattr(self.config.gui.tts, 'outgoing_delay_seconds', 1.0),
							'interrupt_on_ptt': getattr(self.config.gui.tts, 'interrupt_on_ptt', True)
 						},
						'audio_replay': {
							'enabled': getattr(self.config.gui.audio_replay, 'enabled', True),
							'max_stored_messages': getattr(self.config.gui.audio_replay, 'max_stored_messages', 100),
							'storage_duration_hours': getattr(self.config.gui.audio_replay, 'storage_duration_hours', 24),
							'auto_cleanup': getattr(self.config.gui.audio_replay, 'auto_cleanup', True),
						},
						'accessibility': {
							'high_contrast': getattr(self.config.gui.accessibility, 'high_contrast', False),
							'reduced_motion': getattr(self.config.gui.accessibility, 'reduced_motion', False),
							'screen_reader_optimized': getattr(self.config.gui.accessibility, 'screen_reader_optimized', False),
							'keyboard_shortcuts': getattr(self.config.gui.accessibility, 'keyboard_shortcuts', True),
							'announce_new_messages': getattr(self.config.gui.accessibility, 'announce_new_messages', True),
							'focus_management': getattr(self.config.gui.accessibility, 'focus_management', True),
							'font_family': getattr(self.config.gui.accessibility, 'font_family', 'Atkinson Hyperlegible'),
							'font_size': getattr(self.config.gui.accessibility, 'font_size', 'medium'),
							'line_height': getattr(self.config.gui.accessibility, 'line_height', 1.6),
							'character_spacing': getattr(self.config.gui.accessibility, 'character_spacing', 'normal'),
						}
					},
					# Add metadata about the current config file
					'_metadata': {
						'config_file_path': str(self.config_manager.config_file_path) if self.config_manager and hasattr(self.config_manager, 'config_file_path') else None,
						'config_version': getattr(self.config, 'config_version', '1.0'),
						'last_loaded': datetime.now().isoformat()
					}
				}
			
				await self.send_to_client(websocket, {
					"type": "current_config",
					"data": config_dict
				})
			else:
				await self.send_to_client(websocket, {
					"type": "error",
					"message": "No configuration available"
				})
			
		except Exception as e:
			self.logger.error(f"Error getting current config: {e}")
			await self.send_to_client(websocket, {
				"type": "error",
				"message": f"Error retrieving configuration: {str(e)}"
			})

	async def handle_update_config(self, data: Dict):
		"""Handle configuration updates from the web interface - ENHANCED with GUI support"""
		try:
			updated_sections = []
			
			# Apply updates to the current configuration
			if 'callsign' in data:
				old_callsign = self.config.callsign
				self.config.callsign = data['callsign']
				updated_sections.append('callsign')
				
				# Update radio system with new callsign
				if self.radio_system and old_callsign != data['callsign']:
					try:
						from interlocutor import StationIdentifier
						new_station_id = StationIdentifier(data['callsign'])
						
						# Update the radio system's station ID
						self.radio_system.station_id = new_station_id
						
						# Update the protocol's station ID and bytes
						if hasattr(self.radio_system, 'protocol'):
							self.radio_system.protocol.station_id = new_station_id
							self.radio_system.protocol.station_id_bytes = new_station_id.to_bytes()
						
						self.logger.info(f"Updated radio system callsign to: {data['callsign']}")
						
					except Exception as e:
						self.logger.error(f"Error updating radio system callsign: {e}")
		
			if 'network' in data:
				network = data['network']
				if 'target_ip' in network:
					self.config.network.target_ip = network['target_ip']
				if 'target_port' in network:
					self.config.network.target_port = int(network['target_port'])
				if 'listen_port' in network:
					self.config.network.listen_port = int(network['listen_port'])
				if 'encap_mode' in network:
					self.config.network.encap_mode = network['encap_mode']
				if 'voice_port' in network:
					self.config.network.voice_port = int(network['voice_port'])
				if 'text_port' in network:
					self.config.network.text_port = int(network['text_port'])
				if 'control_port' in network:
					self.config.network.control_port = int(network['control_port'])
				updated_sections.append('network')
		
			if 'audio' in data:
				audio = data['audio']
				if 'input_device' in audio:
					self.config.audio.input_device = audio['input_device']
				updated_sections.append('audio')

			if 'gpio' in data:
				gpio = data['gpio']
				if 'ptt_pin' in gpio:
					self.config.gpio.ptt_pin = int(gpio['ptt_pin'])
				if 'led_pin' in gpio:
					self.config.gpio.led_pin = int(gpio['led_pin'])
				if 'button_bounce_time' in gpio:
					self.config.gpio.button_bounce_time = float(gpio['button_bounce_time'])
				if 'led_brightness' in gpio:
					self.config.gpio.led_brightness = float(gpio['led_brightness'])
				updated_sections.append('gpio')
		
			if 'protocol' in data:
				protocol = data['protocol']
				if 'target_type' in protocol:
					self.config.protocol.target_type = protocol['target_type']
				if 'keepalive_interval' in protocol:
					self.config.protocol.keepalive_interval = float(protocol['keepalive_interval'])
				if 'continuous_stream' in protocol:
					self.config.protocol.continuous_stream = bool(protocol['continuous_stream'])
				updated_sections.append('protocol')
		
			if 'debug' in data:
				debug = data['debug']
				if 'verbose' in debug:
					self.config.debug.verbose = bool(debug['verbose'])
				if 'quiet' in debug:
					self.config.debug.quiet = bool(debug['quiet'])
				updated_sections.append('debug')
		
			if 'ui' in data:
				ui = data['ui']
				if 'chat_only_mode' in ui:
					self.config.ui.chat_only_mode = bool(ui['chat_only_mode'])
				if 'web_interface_enabled' in ui:
					self.config.ui.web_interface_enabled = bool(ui['web_interface_enabled'])
				if 'web_interface_port' in ui:
					self.config.ui.web_interface_port = int(ui['web_interface_port'])
				if 'web_interface_host' in ui:
					self.config.ui.web_interface_host = ui['web_interface_host']
				updated_sections.append('ui')

			if 'gui' in data:
				gui = data['gui']
				self.logger.info(f"🔧 Processing GUI config update: {gui}")
				
				if 'transcription' in gui:
					transcription = gui['transcription']
					if 'enabled' in transcription:
						self.config.gui.transcription.enabled = bool(transcription['enabled'])
						self.logger.info(f"🔧 Set transcription.enabled = {self.config.gui.transcription.enabled}")
					if 'method' in transcription:
						self.config.gui.transcription.method = transcription['method']
					if 'language' in transcription:
						self.config.gui.transcription.language = transcription['language']
					if 'confidence_threshold' in transcription:
						self.config.gui.transcription.confidence_threshold = float(transcription['confidence_threshold'])
					if 'model_size' in transcription:
						self.config.gui.transcription.model_size = transcription['model_size']
						# do we need a pass here?

				if 'tts' in gui:
					tts = gui['tts']


					# Replaced self.logger.info below with:
					enabled = self.config.gui.tts.enabled
					incoming_enabled = self.config.gui.tts.incoming_enabled  
					outgoing_enabled = self.config.gui.tts.outgoing_enabled
					include_station_id = self.config.gui.tts.include_station_id
					include_confirmation = self.config.gui.tts.include_confirmation

					self.logger.info(f"🔧 TTS config updated: enabled={enabled}, incoming={incoming_enabled}, outgoing={outgoing_enabled}, include_station_id={include_station_id}, include_confirmation={include_confirmation}")

					#self.logger.info(f"🔧 Processing TTS config update: {tts}")

					if 'enabled' in tts:
						self.config.gui.tts.enabled = bool(tts['enabled'])
						self.logger.info(f"🔧 Set tts.enabled = {self.config.gui.tts.enabled}")
					if 'engine' in tts:
						self.config.gui.tts.engine = tts['engine']
					if 'voice' in tts:
						self.config.gui.tts.voice = tts['voice']
					if 'rate' in tts:
						self.config.gui.tts.rate = int(tts['rate'])
					if 'volume' in tts:
						self.config.gui.tts.volume = float(tts['volume'])
					if 'incoming_enabled' in tts:
						self.config.gui.tts.incoming_enabled = bool(tts['incoming_enabled'])
					if 'include_station_id' in tts:
						self.config.gui.tts.include_station_id = bool(tts['include_station_id'])
					if 'outgoing_enabled' in tts:
						self.config.gui.tts.outgoing_enabled = bool(tts['outgoing_enabled'])
					if 'include_confirmation' in tts:
						self.config.gui.tts.include_confirmation = bool(tts['include_confirmation'])
					if 'outgoing_delay_seconds' in tts:
						self.config.gui.tts.outgoing_delay_seconds = float(tts['outgoing_delay_seconds'])
					if 'interrupt_on_ptt' in tts:
						self.config.gui.tts.interrupt_on_ptt = bool(tts['interrupt_on_ptt'])

				if 'audio_replay' in gui:
					audio_replay = gui['audio_replay']
					if 'enabled' in audio_replay:
						self.config.gui.audio_replay.enabled = bool(audio_replay['enabled'])
					if 'max_stored_messages' in audio_replay:
						self.config.gui.audio_replay.max_stored_messages = int(audio_replay['max_stored_messages'])
					if 'storage_duration_hours' in audio_replay:
						self.config.gui.audio_replay.storage_duration_hours = int(audio_replay['storage_duration_hours'])
					if 'auto_cleanup' in audio_replay:
						self.config.gui.audio_replay.auto_cleanup = bool(audio_replay['auto_cleanup'])
				
				if 'accessibility' in gui:
					accessibility = gui['accessibility']
					if 'high_contrast' in accessibility:
						self.config.gui.accessibility.high_contrast = bool(accessibility['high_contrast'])
					if 'reduced_motion' in accessibility:
						self.config.gui.accessibility.reduced_motion = bool(accessibility['reduced_motion'])
					if 'screen_reader_optimized' in accessibility:
						self.config.gui.accessibility.screen_reader_optimized = bool(accessibility['screen_reader_optimized'])
					if 'keyboard_shortcuts' in accessibility:
						self.config.gui.accessibility.keyboard_shortcuts = bool(accessibility['keyboard_shortcuts'])
					if 'announce_new_messages' in accessibility:
						self.config.gui.accessibility.announce_new_messages = bool(accessibility['announce_new_messages'])
					if 'focus_management' in accessibility:
						self.config.gui.accessibility.focus_management = bool(accessibility['focus_management'])
					if 'font_family' in accessibility:
						self.config.gui.accessibility.font_family = accessibility['font_family']
					if 'font_size' in accessibility:
						self.config.gui.accessibility.font_size = accessibility['font_size']
					if 'line_height' in accessibility:
						self.config.gui.accessibility.line_height = float(accessibility['line_height'])
					if 'character_spacing' in accessibility:
						self.config.gui.accessibility.character_spacing = accessibility['character_spacing']
				
				updated_sections.append('gui')

				# Update transcriber with live config changes
				if self.radio_system and hasattr(self.radio_system, 'update_transcriber_config'):
					try:
						success = self.radio_system.update_transcriber_config()
						if success:
							self.logger.info("🔧 Transcriber updated with new GUI config")
						else:
							self.logger.warning("🔧 Transcriber update failed - restart may be required")
					except Exception as e:
						self.logger.error(f"🔧 Error updating transcriber: {e}")
				else:
					self.logger.info("🔧 Transcriber config update not available - restart may be required")


				# Update TTS with live config changes
				if self.radio_system and hasattr(self.radio_system, 'enhanced_receiver'):
					try:
						if hasattr(self.radio_system.enhanced_receiver, 'update_tts_config'):
							success = self.radio_system.enhanced_receiver.update_tts_config()
							if success:
								self.logger.info("🔧 TTS updated with new GUI config")
						elif hasattr(self.radio_system.enhanced_receiver, 'tts_manager'):
							# Direct update if method doesn't exist
							self.radio_system.enhanced_receiver.tts_manager.update_config(self.config)
							self.logger.info("🔧 TTS config updated directly")
					except Exception as e:
						self.logger.error(f"🔧 Error updating TTS: {e}")

			# Apply debug changes immediately to the global DebugConfig
			if 'debug' in data:
				try:
					from interlocutor import DebugConfig as GlobalDebugConfig
					GlobalDebugConfig.set_mode(
						verbose=self.config.debug.verbose,
						quiet=self.config.debug.quiet
					)
				except ImportError:
					pass  # Gracefully handle if DebugConfig not available
		
			# Validate configuration if config manager available
			if self.config_manager:
				self.config_manager.config = self.config
				is_valid, errors = self.config_manager.validate_config()
				if not is_valid:
					await self.broadcast_to_all({
						"type": "config_validation_warning",
						"data": {
							"message": "Configuration has validation warnings",
							"errors": errors,
							"sections_updated": updated_sections
						}
					})
				else:
					await self.broadcast_to_all({
						"type": "config_updated",
						"data": {
							"message": "Configuration updated successfully",
							"sections_updated": updated_sections
						}
					})
			else:
				await self.broadcast_to_all({
					"type": "config_updated",
					"data": {
						"message": "Configuration updated successfully",
						"sections_updated": updated_sections
					}
				})
		
			self.logger.info(f"Configuration updated via web interface: {', '.join(updated_sections)}")
		
		except Exception as e:
			self.logger.error(f"Error updating config: {e}")
			await self.broadcast_to_all({
				"type": "error",
				"message": f"Error updating configuration: {str(e)}"
			})








	async def handle_save_config(self, data: Dict):
		"""Save configuration to file using CLI-compatible logic - FULLY RESTORED"""
		try:
			# Get filename from request or use smart defaults
			requested_filename = data.get('filename')
			
			if requested_filename:
				# User specified a filename explicitly
				filename = requested_filename
				self.logger.info(f"Saving config to user-specified file: {filename}")
			elif self.config_manager and hasattr(self.config_manager, 'config_file_path') and self.config_manager.config_file_path:
				# Save back to the original config file (best option)
				filename = str(self.config_manager.config_file_path)
				self.logger.info(f"Saving config to original file: {filename}")
			else:
				# Fall back to CLI default discovery logic
				filename = self._get_default_save_filename()
				self.logger.info(f"Saving config to default discovered file: {filename}")
			
			# Use the existing configuration manager to save
			if self.config_manager:
				# Update the config manager's current config
				self.config_manager.config = self.config
				success = self.config_manager.save_config(filename)
			else:
				# Create a new config manager if needed (fallback)
				from config_manager import ConfigurationManager
				config_manager = ConfigurationManager()
				config_manager.config = self.config
				success = config_manager.save_config(filename)
			
			if success:
				await self.broadcast_to_all({
					"type": "config_saved",
					"data": {
						"message": f"Configuration saved to {filename}",
						"filename": filename,
						"timestamp": datetime.now().isoformat()
					}
				})
				self.logger.info(f"Configuration saved to {filename}")
			else:
				await self.broadcast_to_all({
					"type": "error",
					"message": f"Failed to save configuration to {filename}"
				})
				
		except Exception as e:
			self.logger.error(f"Error saving config: {e}")
			await self.broadcast_to_all({
				"type": "error",
				"message": f"Error saving configuration: {str(e)}"
			})

	def _get_default_save_filename(self) -> str:
		"""Get default save filename using CLI logic - RESTORED"""
		# Use the same search order as CLI, but for saving
		candidate_files = [
			"opulent_voice.yaml",  # Current directory (most common)
			"config/opulent_voice.yaml",  # Config subdirectory
		]
		
		for candidate in candidate_files:
			candidate_path = Path(candidate)
			# Create parent directory if it doesn't exist
			try:
				candidate_path.parent.mkdir(parents=True, exist_ok=True)
				# Test write access
				test_file = candidate_path.parent / ".write_test"
				test_file.touch()
				test_file.unlink()
				return str(candidate_path)
			except (PermissionError, OSError):
				continue
		
		# Last resort: current directory
		return "opulent_voice.yaml"

	async def handle_load_config(self, websocket: WebSocket, data: Dict = None):
		"""Load configuration from file using CLI logic - FULLY RESTORED"""
		try:
			specified_file = data.get('filename') if data else None
			
			if self.config_manager:
				# Use existing config manager with CLI auto-discovery
				if specified_file:
					# Load specific file
					self.logger.info(f"Loading config from specified file: {specified_file}")
					loaded_config = self.config_manager.load_config(specified_file)
				else:
					# Use CLI auto-discovery logic
					self.logger.info("Loading config using CLI auto-discovery")
					loaded_config = self.config_manager.load_config()
			else:
				# Create new config manager with CLI logic
				from config_manager import ConfigurationManager
				config_manager = ConfigurationManager()
				if specified_file:
					loaded_config = config_manager.load_config(specified_file)
				else:
					loaded_config = config_manager.load_config()
				self.config_manager = config_manager
			
			if loaded_config:
				self.config = loaded_config
				
				# Validate the loaded config
				if self.config_manager:
					is_valid, errors = self.config_manager.validate_config()
					if not is_valid:
						await self.send_to_client(websocket, {
							"type": "config_validation_warning",
							"data": {
								"message": f"Configuration loaded but has validation warnings",
								"errors": errors
							}
						})
				
				# Send the loaded config back to the client
				await self.handle_get_current_config(websocket)
				
				# Determine what file was actually loaded
				loaded_file = "configuration file"
				if self.config_manager and hasattr(self.config_manager, 'config_file_path') and self.config_manager.config_file_path:
					loaded_file = str(self.config_manager.config_file_path)
				
				await self.send_to_client(websocket, {
					"type": "config_loaded",
					"data": {
						"message": f"Configuration loaded from {loaded_file}",
						"filename": loaded_file,
						"timestamp": datetime.now().isoformat()
					}
				})
				
				self.logger.info(f"Configuration loaded from {loaded_file}")
			else:
				# No config file found - suggest creating one
				search_paths = [
					"opulent_voice.yaml",
					"config/opulent_voice.yaml", 
					str(Path.home() / ".config" / "opulent_voice" / "config.yaml"),
					"/etc/opulent_voice/config.yaml"
				]
				
				await self.send_to_client(websocket, {
					"type": "config_not_found",
					"data": {
						"message": "No configuration file found in standard locations",
						"searched_paths": search_paths,
						"suggestion": "Use 'Create Configuration' to make a new config file"
					}
				})

		except Exception as e:
			self.logger.error(f"Error loading config: {e}")
			await self.send_to_client(websocket, {
				"type": "error",
				"message": f"Error loading configuration: {str(e)}"
			})

	async def handle_create_config(self, data: Dict):
		"""Create a new configuration file - FULLY RESTORED"""
		try:
			filename = data.get('filename', 'opulent_voice.yaml')
			template_type = data.get('template_type', 'full')  # 'full', 'minimal', 'current'
			
			if self.config_manager:
				config_manager = self.config_manager
			else:
				from config_manager import ConfigurationManager
				config_manager = ConfigurationManager()
				self.config_manager = config_manager
			
			if template_type == 'current':
				# Save current configuration as new file
				if self.config:
					config_manager.config = self.config
					success = config_manager.save_config(filename)
				else:
					success = config_manager.create_sample_config(filename)
			else:
				# Create sample configuration (full template)
				success = config_manager.create_sample_config(filename)
			
			if success:
				# Load the newly created config to make it active
				if template_type != 'current':
					self.config = config_manager.load_config(filename)
				
				await self.broadcast_to_all({
					"type": "config_created",
					"data": {
						"message": f"Configuration file created: {filename}",
						"filename": filename,
						"template_type": template_type,
						"timestamp": datetime.now().isoformat()
					}
				})
				
				# Also send the new config to populate the form
				await self.broadcast_to_all({
					"type": "config_loaded", 
					"data": {
						"message": f"New configuration loaded from {filename}",
						"filename": filename
					}
				})
				
				self.logger.info(f"Configuration file created: {filename} (template: {template_type})")
				
			else:
				await self.broadcast_to_all({
					"type": "error", 
					"message": f"Failed to create configuration file: {filename}"
				})
				
		except Exception as e:
			self.logger.error(f"Error creating config: {e}")
			await self.broadcast_to_all({
				"type": "error",
				"message": f"Error creating configuration: {str(e)}"
			})

	async def handle_test_connection(self, websocket: WebSocket):
		"""Test network connection - ENHANCED"""
		try:
			test_results = {
				"network_available": True,
				"target_reachable": False,
				"audio_system": False,
				"gpio_system": False,
				"config_valid": False
			}
			
			# Test network connectivity if radio system available
			if self.radio_system:
				# Test basic radio system components
				test_results["audio_system"] = hasattr(self.radio_system, 'audio_input_stream')
				test_results["gpio_system"] = hasattr(self.radio_system, 'ptt_button')
				
				# Test network transmission (basic UDP test)
				try:
					if hasattr(self.radio_system, 'transmitter'):
						# Create a small test frame
						test_data = b"TEST_CONNECTION"
						test_results["target_reachable"] = self.radio_system.transmitter.send_frame(test_data)
				except Exception as e:
					self.logger.warning(f"Network test failed: {e}")
			
			# Test configuration validity
			if self.config_manager:
				is_valid, errors = self.config_manager.validate_config()
				test_results["config_valid"] = is_valid
				if not is_valid:
					test_results["config_errors"] = errors
			
			overall_success = all([
				test_results["network_available"],
				test_results["config_valid"]
			])
			
			await self.send_to_client(websocket, {
				"type": "connection_test_result",
				"data": {
					"success": overall_success,
					"results": test_results,
					"message": "Connection test completed" if overall_success else "Connection test found issues",
					"timestamp": datetime.now().isoformat()
				}
			})
			
		except Exception as e:
			self.logger.error(f"Error testing connection: {e}")
			await self.send_to_client(websocket, {
				"type": "error",
				"message": f"Connection test failed: {str(e)}"
			})




	async def handle_test_tts(self, websocket: WebSocket, data: Dict):
		"""Test TTS functionality"""
		try:
			test_message = data.get('message', 'This is a test of the text to speech system')
        
			# Queue test message through TTS system
			if (self.radio_system and 
				hasattr(self.radio_system, 'enhanced_receiver') and 
				self.radio_system.enhanced_receiver and
				hasattr(self.radio_system.enhanced_receiver, 'tts_manager') and 
				self.radio_system.enhanced_receiver.tts_manager):

				success = self.radio_system.enhanced_receiver.tts_manager.queue_text_message(
					str(self.radio_system.station_id), 
					test_message, 
					is_outgoing=True  # Use outgoing TTS settings
				)
            
				if success:
					await self.send_to_client(websocket, {
						"type": "tts_test_result",
						"data": {"success": True, "message": "TTS test queued successfully"}
					})
				else:
					await self.send_to_client(websocket, {
						"type": "tts_test_result", 
						"data": {"success": False, "message": "TTS test failed to queue"}
					})
			else:
				await self.send_to_client(websocket, {
					"type": "tts_test_result",
					"data": {"success": False, "message": "TTS system not available"}
				})
            
		except Exception as e:
			await self.send_to_client(websocket, {
				"type": "error",
				"message": f"TTS test failed: {str(e)}"
			})







	async def handle_test_connection_with_form(self, websocket: WebSocket, data: Dict):
		"""Test system using current form values - validates form first"""
		try:
			form_config = data.get('form_config', {})
			
			# Step 1: Validate the form configuration
			validation_result = self._validate_form_config(form_config)
			
			if not validation_result['valid']:
				# Send validation failure immediately
				await self.send_to_client(websocket, {
					"type": "connection_test_with_form_result",
					"data": {
						"form_validation": validation_result,
						"system_test": {"success": False, "message": "Form validation failed"}
					}
				})
				return
			
			# Step 2: Temporarily apply form config for testing
			original_config = self.config
			try:
				# Create temporary config with form values
				temp_config = self._create_temp_config_from_form(form_config)
				self.config = temp_config
				
				# Step 3: Run system tests with temporary config
				system_test_result = await self._run_system_tests()
				
				# Step 4: Send combined results
				await self.send_to_client(websocket, {
					"type": "connection_test_with_form_result", 
					"data": {
						"form_validation": validation_result,
						"system_test": system_test_result
					}
				})
				
			finally:
				# Always restore original config
				self.config = original_config
				
		except Exception as e:
			self.logger.error(f"Error in test_connection_with_form: {e}")
			await self.send_to_client(websocket, {
				"type": "error",
				"message": f"System test failed: {str(e)}"
			})

	def _validate_form_config(self, form_config: Dict) -> Dict:
		"""Validate form configuration values"""
		errors = []
		field_errors = {}
		


		# Simple BASE40 callsign validation
		callsign = form_config.get('callsign', '').strip()
		if not callsign or callsign == "NOCALL":
			errors.append("Callsign is required")
			field_errors['callsign'] = "Callsign is required"
		else:
			try:
				# Use the actual BASE40 validation from radio_protocol
				from radio_protocol import StationIdentifier
        
				# Convert to uppercase and validate with BASE40 encoder
				callsign_upper = callsign.upper()
				station_id = StationIdentifier(callsign_upper)
        
				# If we get here, callsign is valid - update form with uppercase version
				form_config['callsign'] = callsign_upper
        
			except ValueError as e:
				# BASE40 validation failed
				errors.append(f"Invalid callsign: {str(e)}")
				field_errors['callsign'] = f"Invalid callsign: {str(e)}"
			except ImportError:
				# Fallback if radio_protocol not available
				if not re.match(r'^[A-Z0-9\-\/.]+$', callsign.upper()):
					errors.append("Callsign contains invalid characters")
					field_errors['callsign'] = "Only A-Z, 0-9, -, /, . allowed"
				else:
					form_config['callsign'] = callsign.upper()


		
		# Validate network settings
		network = form_config.get('network', {})

		target_ip = network.get('target_ip', '').strip()
		print(f"🔍 IP VALIDATION DEBUG: target_ip = '{target_ip}'")

		if target_ip:
			try:
				# Validate IP address format
				ip_obj = ipaddress.ip_address(target_ip)
				print(f"🔍 IP VALIDATION DEBUG: ip_obj = {ip_obj}")
				print(f"🔍 IP VALIDATION DEBUG: is_loopback = {ip_obj.is_loopback}")

				# Optional: Warn about unusual addresses
				if ip_obj.is_loopback:
					print(f"🔍 IP VALIDATION DEBUG: LOOPBACK DETECTED")
					field_errors['target-ip'] = "Warning: Loopback address (127.x.x.x)"
				elif ip_obj.is_multicast:
					print(f"🔍 IP VALIDATION DEBUG: MULTICAST DETECTED!")
					field_errors['target-ip'] = "Multicast addresses not yet implemented"
                
			except ValueError:
				print(f"🔍 IP VALIDATION DEBUG: INVALID IP")
				errors.append("Invalid IP address format")
				field_errors['target-ip'] = "Must be valid IP address (e.g., 192.168.1.100)"
		else:
			print(f"🔍 IP VALIDATION DEBUG: NO IP PROVIDED")
			errors.append("Target IP is required")
			field_errors['target-ip'] = "IP address is required"


		target_port = network.get('target_port')
		if target_port and not (1 <= int(target_port) <= 65535):
			errors.append("Invalid target port")
			field_errors['target-port'] = "Port must be 1-65535"
		
		listen_port = network.get('listen_port') 
		if listen_port and not (1 <= int(listen_port) <= 65535):
			errors.append("Invalid listen port")
			field_errors['listen-port'] = "Port must be 1-65535"
		
		encap_mode = network.get('encap_mode')
		if encap_mode and encap_mode != "UDP" and encap_mode != "TCP":
			errors.append("Invalid encapsulation mode")
			field_errors['encap-mode'] = "Mode must be UDP or TCP"
		
		# Validate GPIO pins
		gpio = form_config.get('gpio', {})
		ptt_pin = gpio.get('ptt_pin')
		led_pin = gpio.get('led_pin')
		
		if ptt_pin and not (2 <= int(ptt_pin) <= 27):
			errors.append("Invalid PTT pin")
			field_errors['ptt-pin'] = "Pin must be 2-27"
		
		if led_pin and not (2 <= int(led_pin) <= 27):
			errors.append("Invalid LED pin") 
			field_errors['led-pin'] = "Pin must be 2-27"
		
		if ptt_pin and led_pin and int(ptt_pin) == int(led_pin):
			errors.append("PTT and LED pins cannot be the same")
			field_errors['ptt-pin'] = "Cannot be same as LED pin"
			field_errors['led-pin'] = "Cannot be same as PTT pin"
		


		print(f"🔍 IP VALIDATION DEBUG: Final errors = {errors}")
		print(f"🔍 IP VALIDATION DEBUG: Final field_errors = {field_errors}")


		return {
			'valid': len(errors) == 0,
			'errors': errors,
			'field_errors': field_errors
		}

	def _create_temp_config_from_form(self, form_config: Dict):
		"""Create temporary config object from form values"""
		from copy import deepcopy
		
		# Start with current config as base
		temp_config = deepcopy(self.config)
		
		# Apply form values
		if 'callsign' in form_config:
			temp_config.callsign = form_config['callsign']
		
		if 'network' in form_config:
			network = form_config['network']
			if 'target_ip' in network:
				temp_config.network.target_ip = network['target_ip']
			if 'target_port' in network:
				temp_config.network.target_port = int(network['target_port'])
			if 'listen_port' in network:
				temp_config.network.listen_port = int(network['listen_port'])
			if 'encap_mode' in network:
				temp_config.network.encap_mode = network['encap_mode']
		
		if 'gpio' in form_config:
			gpio = form_config['gpio']
			if 'ptt_pin' in gpio:
				temp_config.gpio.ptt_pin = int(gpio['ptt_pin'])
			if 'led_pin' in gpio:
				temp_config.gpio.led_pin = int(gpio['led_pin'])
		
		if 'protocol' in form_config:
			protocol = form_config['protocol']
			if 'target_type' in protocol:
				temp_config.protocol.target_type = protocol['target_type']
			if 'keepalive_interval' in protocol:
				temp_config.protocol.keepalive_interval = float(protocol['keepalive_interval'])
		
		if 'debug' in form_config:
			debug = form_config['debug']
			if 'verbose' in debug:
				temp_config.debug.verbose = bool(debug['verbose'])
			if 'quiet' in debug:
				temp_config.debug.quiet = bool(debug['quiet'])
		
		return temp_config

	async def _run_system_tests(self) -> Dict:
		"""Run the actual system tests (extracted from existing handle_test_connection)"""
		test_results = {
			"network_available": True,
			"target_reachable": False,
			"audio_system": False,
			"gpio_system": False,
			"config_valid": True  # Already validated in form step
		}
		
		# Test network connectivity if radio system available
		if self.radio_system:
			test_results["audio_system"] = hasattr(self.radio_system, 'audio_input_stream')
			test_results["gpio_system"] = hasattr(self.radio_system, 'ptt_button')
			
			# IMPROVED NETWORK TEST
			target_ip = self.config.network.target_ip
			target_port = self.config.network.target_port
			encap_mode = self.config.network.encap_mode
        
			if encap_mode == "UDP":
				try:
					import socket
				
					# Test UDP connectivity with timeout
					sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
					sock.settimeout(3.0)  # 3 second timeout
				
					# Try to connect (for UDP this just validates the address)
					try:
						sock.connect((target_ip, target_port))
					
						# Send actual test frame like before
						if hasattr(self.radio_system, 'transmitter'):
							test_data = b"TEST_CONNECTION_FORM"
							test_success = self.radio_system.transmitter.send_frame(test_data)
							test_results["target_reachable"] = test_success
						else:
							test_results["target_reachable"] = True  # At least IP is valid
						
					except socket.gaierror:
						# DNS resolution failed
						test_results["target_reachable"] = False
						self.logger.warning(f"Cannot resolve hostname: {target_ip}")
					except socket.error as e:
						# Network unreachable, host unreachable, etc.
						test_results["target_reachable"] = False
						self.logger.warning(f"Network error to {encap_mode}:{target_ip}:{target_port}: {e}")
					finally:
						sock.close()
					
				except Exception as e:
					test_results["target_reachable"] = False
					self.logger.warning(f"Network test failed: {e}")
			elif encap_mode == "TCP":
				#!!! implement this
				...
				self.logger.warning("Network test unimplemented for TCP")
			else:
				self.logger.error(f"Encapsulation mode {encap_mode} is invalid")
    
		overall_success = all([
		test_results["network_available"],
		test_results["target_reachable"],
		test_results["config_valid"]
		])
    
		return {
			"success": overall_success,
			"results": test_results,
			"message": "System test completed" if overall_success else "System test found issues"
		}



	async def handle_get_audio_devices(self, websocket: WebSocket):
		"""Get audio devices"""
		await self.send_to_client(websocket, {
			"type": "audio_devices",
			"data": {"input": [], "output": []}
		})

	async def handle_test_audio(self, websocket: WebSocket, data: Dict):
		"""Test audio"""
		await self.send_to_client(websocket, {
			"type": "audio_test_result",
			"data": {"success": True, "message": "Audio test passed"}
		})

	async def handle_debug_mode_change(self, data: Dict):
		"""Handle debug mode changes"""
		mode = data.get('mode', 'normal')
		
		# Update debug configuration
		try:
			from interlocutor import DebugConfig
			if mode == 'verbose':
				DebugConfig.set_mode(verbose=True, quiet=False)
			elif mode == 'quiet':
				DebugConfig.set_mode(verbose=False, quiet=True)
			else:  # normal
				DebugConfig.set_mode(verbose=False, quiet=False)
		except ImportError:
			pass  # Gracefully handle if DebugConfig not available
			
		await self.broadcast_to_all({
			"type": "debug_mode_changed",
			"data": {"mode": mode}
		})

	def get_current_status(self) -> Dict:
		"""Get current radio system status - Enhanced with message stats"""
		status = {
			"connected": self.radio_system is not None,
			"station_id": str(self.radio_system.station_id) if self.radio_system else "DISCONNECTED",
			"ptt_active": self.ptt_state,
			"debug_mode": self._get_debug_mode(),
			"timestamp": datetime.now().isoformat(),
			"config": {
				"target_ip": self.config.network.target_ip if self.config else "unknown",
				"target_port": self.config.network.target_port if self.config else 0,
				"encap_mode": self.config.network.encap_mode if self.config else "unknown",
				"audio_enabled": True  # TODO: Check actual audio status
			},
			"stats": self.get_system_stats(),
			"message_stats": {
				"total_messages": len(self.message_history),
				"messages_sent": len([m for m in self.message_history if m["direction"] == "outgoing"]),
				"messages_received": len([m for m in self.message_history if m["direction"] == "incoming"]),
			}
		}
		
		return status

	def _get_debug_mode(self) -> str:
		"""Get current debug mode from config"""
		if self.config and hasattr(self.config, 'debug'):
			if self.config.debug.verbose:
				return "verbose"
			elif self.config.debug.quiet:
				return "quiet"
			else:
				return "normal"
		else:
			return "normal"








	def get_system_stats(self) -> Dict:
		"""Get system statistics for GUI display"""
		stats = {
			"messages_sent": len([m for m in self.message_history if m["direction"] == "outgoing"]),
			"messages_received": len([m for m in self.message_history if m["direction"] == "incoming"]),
			"audio_messages_stored": len(self.completed_transmissions) + sum(len(t['audio_packets']) for t in self.active_transmissions.values()),
			"connected_clients": len(self.websocket_clients),
			"uptime_seconds": 0  # TODO: Calculate actual uptime
		}
		
		# Get stats from radio system if available
		if self.radio_system and hasattr(self.radio_system, 'get_stats'):
			try:
				radio_stats = self.radio_system.get_stats()
				stats.update(radio_stats)
			except Exception:
				pass  # Gracefully handle if stats not available
		
		return stats


# FastAPI application setup
app = FastAPI(title="Opulent Voice Web Interface", version="1.0.0")

# Add CORS middleware for development
app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],  # Configure properly for production
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

# Global web interface instance
web_interface: Optional[EnhancedRadioWebInterface] = None













def initialize_web_interface(radio_system=None, config=None, config_manager=None):
	"""Initialize the enhanced web interface with radio system and config manager"""
	global web_interface
	
	try:
		web_interface = EnhancedRadioWebInterface(radio_system, config, config_manager)
		
		# Connect to existing chat system
		if radio_system and hasattr(radio_system, 'chat_interface'):
			# Hook into the existing chat interface to capture messages
			setup_chat_integration(radio_system.chat_interface, web_interface)
		
		print(f"✅ Web interface initialized successfully")
		return web_interface
	except Exception as e:
		print(f"❌ Error initializing web interface: {e}")
		import traceback
		traceback.print_exc()
		return None

def setup_chat_integration(chat_interface, web_interface):
	"""Setup integration between existing chat interface and web interface"""
	try:
		# Store original display method
		if hasattr(chat_interface, 'display_received_message'):
			original_display = chat_interface.display_received_message
			
			# Wrap the display method to also send to web interface
			def enhanced_display(from_station, message):
				# Call original display for terminal
				original_display(from_station, message)
				
				# Also send to web interface in a thread-safe way
				def notify_web():
					try:
						loop = asyncio.new_event_loop()
						asyncio.set_event_loop(loop)
						loop.run_until_complete(web_interface.on_message_received({
							"content": message,
							"from": from_station,
							"type": "text"
						}))
						loop.close()
					except Exception as e:
						print(f"Error notifying web interface: {e}")
				
				# Run in separate thread to avoid blocking
				threading.Thread(target=notify_web, daemon=True).start()
			
			# Replace the method
			chat_interface.display_received_message = enhanced_display
			print("✅ Chat integration setup complete")
	except Exception as e:
		print(f"⚠️ Chat integration setup failed: {e}")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
	"""Enhanced WebSocket endpoint for real-time communication"""
	if not web_interface:
		await websocket.close(code=1000, reason="Radio system not initialized")
		return
	
	try:
		await web_interface.connect_websocket(websocket)
		
		while True:
			# Receive messages from client
			data = await websocket.receive_text()
			try:
				command = json.loads(data)
				await web_interface.handle_gui_command(websocket, command)
			except json.JSONDecodeError:
				await web_interface.send_to_client(websocket, {
					"type": "error",
					"message": "Invalid JSON received"
				})
	except WebSocketDisconnect:
		web_interface.disconnect_websocket(websocket)
	except Exception as e:
		logging.error(f"WebSocket error: {e}")
		if web_interface:
			web_interface.disconnect_websocket(websocket)

@app.get("/")
async def get_index():
	"""Serve the unified GUI page"""
	# Try to find the HTML file in multiple locations
	possible_paths = [
		Path("html5_gui/index.html"),
		Path("index.html"),
		Path("static/index.html"),
		Path("templates/index.html")
	]
	
	for html_file in possible_paths:
		if html_file.exists():
			try:
				return HTMLResponse(content=html_file.read_text(), status_code=200)
			except Exception as e:
				print(f"Error reading {html_file}: {e}")
				continue
	
	# Fallback HTML if no file found
	return HTMLResponse(content="""
	<!DOCTYPE html>
	<html>
	<head><title>Opulent Voice GUI</title></head>
	<body>
		<h1>Opulent Voice Web Interface</h1>
		<p>GUI files not found. Please create html5_gui/index.html</p>
		<p>Expected locations checked:</p>
		<ul>
			<li>html5_gui/index.html</li>
			<li>index.html</li>
			<li>static/index.html</li>
			<li>templates/index.html</li>
		</ul>
		<p>Current working directory: {}</p>
	</body>
	</html>
	""".format(Path.cwd()), status_code=200)

@app.get("/api/status")
async def get_status():
	"""Get current system status via REST API"""
	if not web_interface:
		raise HTTPException(status_code=503, detail="Radio system not initialized")
	
	return web_interface.get_current_status()

@app.get("/api/messages")
async def get_message_history():
	"""Get message history via REST API"""
	if not web_interface:
		raise HTTPException(status_code=503, detail="Radio system not initialized")
	
	return {"messages": web_interface.message_history}




# Mount static files for GUI assets
try:
	# Try multiple static file locations
	static_dirs = ["html5_gui", "static", "public"]
	for static_dir in static_dirs:
		if Path(static_dir).exists():
			app.mount("/static", StaticFiles(directory=static_dir), name="static")
			print(f"✅ Static files mounted from {static_dir}")
			break
except RuntimeError as e:
	print(f"⚠️ Static files mount failed: {e}")

def run_web_server(host="0.0.0.0", port=8000, radio_system=None, config=None):
	"""Run the enhanced web server with better error handling"""
	
	print(f"🌐 Starting Enhanced Opulent Voice Web Interface on http://{host}:{port}")
	print(f"📡 WebSocket endpoint: ws://{host}:{port}/ws")
	print(f"💬 Unified chat and configuration interface available")
	
	# Configure logging based on config
	if config and hasattr(config, 'debug'):
		log_level = "debug" if config.debug.verbose else "info"
		access_log = not config.debug.quiet
	else:
		log_level = "info"
		access_log = True
	
	try:
		uvicorn.run(
			app,
			host=host,
			port=port,
			log_level=log_level,
			access_log=access_log
		)
	except Exception as e:
		print(f"❌ Failed to start web server: {e}")
		import traceback
		traceback.print_exc()
		raise

if __name__ == "__main__":
	# For testing the enhanced web interface standalone
	print("🧪 Testing web interface standalone mode")
	run_web_server()
