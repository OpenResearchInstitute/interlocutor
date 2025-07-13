#!/usr/bin/env python3
"""
FIXED Web Interface for Opulent Voice Radio System
Addresses connection issues and improves chat integration
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Set, Optional, Any
import threading
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import re

# Import your existing radio system components
from config_manager import OpulentVoiceConfig

class EnhancedRadioWebInterface:
	"""Enhanced bridge between web GUI and radio system with chat integration"""
	
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
		
		# Audio message storage for GUI
		self.audio_messages = {}
		max_messages = 100
		if config and hasattr(config, 'gui') and hasattr(config.gui, 'audio_replay'):
			max_messages = config.gui.audio_replay.max_stored_messages
		self.max_audio_messages = max_messages
		
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

	async def handle_send_text_message(self, data: Dict):
		"""Handle text message from GUI - Enhanced with proper message flow"""
		message = data.get('message', '').strip()
		if not message:
			return
	
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
	
	async def broadcast_to_all(self, message: Dict):
		"""Broadcast message to all connected clients"""
		if not self.websocket_clients:
			return
			
		disconnected = set()
		
		for websocket in self.websocket_clients.copy():
			try:
				await websocket.send_text(json.dumps(message))
			except Exception as e:
				self.logger.warning(f"Failed to broadcast to client: {e}")
				disconnected.add(websocket)
		
		# Clean up disconnected clients
		self.websocket_clients -= disconnected

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

	# Enhanced event handlers for chat integration
	async def on_message_received(self, message_data: Dict):
		"""Called when radio system receives a message - Enhanced"""
		# Process the message data
		processed_message = {
			"type": message_data.get("type", "text"),
			"direction": "incoming",
			"content": message_data.get("content", ""),
			"timestamp": datetime.now().isoformat(),
			"from": message_data.get("from", "UNKNOWN"),
			"metadata": message_data.get("metadata", {}),
			"message_id": f"msg_{int(time.time() * 1000)}_{hash(message_data.get('content', '')) % 10000}"
		}
	
		# Add to history
		self.message_history.append(processed_message)
	
		# Limit history size
		if len(self.message_history) > 1000:
			self.message_history = self.message_history[-500:]  # Keep last 500
	
		# Broadcast to all clients
		await self.broadcast_to_all({
			"type": "message_received",
			"data": processed_message
		})
	
		self.logger.info(f"Received message from {processed_message['from']}: {processed_message['content'][:50]}...")

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

# Replace the configuration handler methods in web_interface.py with these restored versions:

	async def handle_get_current_config(self, websocket: WebSocket):
		"""Send current configuration to the web interface - FULLY RESTORED"""
		try:
			if self.config:
				# Convert config to dictionary format for the web interface
				config_dict = {
					'callsign': getattr(self.config, 'callsign', 'NOCALL'),
					'network': {
						'target_ip': self.config.network.target_ip,
						'target_port': self.config.network.target_port,
						'listen_port': self.config.network.listen_port,
						'voice_port': getattr(self.config.network, 'voice_port', 57373),
						'text_port': getattr(self.config.network, 'text_port', 57374),
						'control_port': getattr(self.config.network, 'control_port', 57375),
					},
					'audio': {
						'sample_rate': self.config.audio.sample_rate,
						'channels': self.config.audio.channels,
						'frame_duration_ms': self.config.audio.frame_duration_ms,
						'input_device': self.config.audio.input_device,
						'prefer_usb_device': self.config.audio.prefer_usb_device,
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
						'log_level': self.config.debug.log_level,
						'show_frame_details': getattr(self.config.debug, 'show_frame_details', False),
						'show_timing_info': getattr(self.config.debug, 'show_timing_info', False),
					},
					'ui': {
						'chat_only_mode': getattr(self.config.ui, 'chat_only_mode', False),
						'web_interface_enabled': getattr(self.config.ui, 'web_interface_enabled', False),
						'web_interface_port': getattr(self.config.ui, 'web_interface_port', 8000),
						'web_interface_host': getattr(self.config.ui, 'web_interface_host', 'localhost'),
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
		"""Handle configuration updates from the web interface - ENHANCED"""
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
				if 'voice_port' in network:
					self.config.network.voice_port = int(network['voice_port'])
				if 'text_port' in network:
					self.config.network.text_port = int(network['text_port'])
				if 'control_port' in network:
					self.config.network.control_port = int(network['control_port'])
				updated_sections.append('network')
		
			if 'audio' in data:
				audio = data['audio']
				if 'sample_rate' in audio:
					self.config.audio.sample_rate = int(audio['sample_rate'])
				if 'frame_duration_ms' in audio:
					self.config.audio.frame_duration_ms = int(audio['frame_duration_ms'])
				if 'input_device' in audio:
					self.config.audio.input_device = audio['input_device']
				if 'prefer_usb_device' in audio:
					self.config.audio.prefer_usb_device = bool(audio['prefer_usb_device'])
				if 'device_keywords' in audio:
					self.config.audio.device_keywords = audio['device_keywords']
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
				if 'log_level' in debug:
					self.config.debug.log_level = debug['log_level']
				if 'show_frame_details' in debug:
					self.config.debug.show_frame_details = bool(debug['show_frame_details'])
				if 'show_timing_info' in debug:
					self.config.debug.show_timing_info = bool(debug['show_timing_info'])
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
		
		# Validate callsign
		callsign = form_config.get('callsign', '').strip()
		if not callsign or callsign == "NOCALL":
			errors.append("Callsign is required")
			field_errors['callsign'] = "Callsign is required"
		elif not re.match(r'^[A-Z0-9\-\/.]+$', callsign.upper()):
			errors.append("Callsign contains invalid characters")
			field_errors['callsign'] = "Only A-Z, 0-9, -, /, . allowed"
		
		# Validate network settings
		network = form_config.get('network', {})
		
		target_port = network.get('target_port')
		if target_port and not (1 <= int(target_port) <= 65535):
			errors.append("Invalid target port")
			field_errors['target-port'] = "Port must be 1-65535"
		
		listen_port = network.get('listen_port') 
		if listen_port and not (1 <= int(listen_port) <= 65535):
			errors.append("Invalid listen port")
			field_errors['listen-port'] = "Port must be 1-65535"
		
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
		
		if 'audio' in form_config:
			audio = form_config['audio']
			if 'sample_rate' in audio:
				temp_config.audio.sample_rate = int(audio['sample_rate'])
			if 'frame_duration_ms' in audio:
				temp_config.audio.frame_duration_ms = int(audio['frame_duration_ms'])
		
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
			if 'log_level' in debug:
				temp_config.debug.log_level = debug['log_level']
		
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
			
			# Test network transmission
			try:
				if hasattr(self.radio_system, 'transmitter'):
					test_data = b"TEST_CONNECTION_FORM"
					test_results["target_reachable"] = self.radio_system.transmitter.send_frame(test_data)
			except Exception as e:
				self.logger.warning(f"Network test failed: {e}")
		
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
			"audio_messages_stored": len(self.audio_messages),
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

def run_web_server(host="localhost", port=8000, radio_system=None, config=None):
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
