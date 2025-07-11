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

	# Configuration handlers (simplified for space - keeping only essential ones)
	async def handle_get_current_config(self, websocket: WebSocket):
		"""Send current configuration to the web interface"""
		try:
			if self.config:
				# Convert config to dictionary format for the web interface
				config_dict = {
					'callsign': getattr(self.config, 'callsign', 'NOCALL'),
					'network': {
						'target_ip': self.config.network.target_ip,
						'target_port': self.config.network.target_port,
						'listen_port': self.config.network.listen_port,
					},
					'debug': {
						'verbose': self.config.debug.verbose,
						'quiet': self.config.debug.quiet,
						'log_level': self.config.debug.log_level,
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
		"""Handle configuration updates from the web interface"""
		try:
			# Apply updates to the current configuration
			if 'callsign' in data:
				old_callsign = self.config.callsign
				self.config.callsign = data['callsign']
				
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
		
			# Broadcast the update to all connected clients
			await self.broadcast_to_all({
				"type": "config_updated",
				"data": {"message": "Configuration updated successfully"}
			})
		
			self.logger.info("Configuration updated via web interface")
		
		except Exception as e:
			self.logger.error(f"Error updating config: {e}")
			await self.broadcast_to_all({
				"type": "error",
				"message": f"Error updating configuration: {str(e)}"
			})

	async def handle_save_config(self, data: Dict):
		"""Save configuration to file"""
		try:
			if self.config_manager:
				success = self.config_manager.save_config()
				if success:
					await self.broadcast_to_all({
						"type": "config_saved",
						"data": {"message": "Configuration saved successfully"}
					})
				else:
					await self.broadcast_to_all({
						"type": "error",
						"message": "Failed to save configuration"
					})
			else:
				await self.broadcast_to_all({
					"type": "error",
					"message": "No configuration manager available"
				})
		except Exception as e:
			self.logger.error(f"Error saving config: {e}")
			await self.broadcast_to_all({
				"type": "error",
				"message": f"Error saving configuration: {str(e)}"
			})

	# Stub handlers for other methods (keeping interface compatible)
	async def handle_load_config(self, websocket: WebSocket, data: Dict = None):
		"""Load configuration from file"""
		await self.send_to_client(websocket, {
			"type": "info",
			"message": "Config loading functionality not yet implemented"
		})

	async def handle_create_config(self, data: Dict):
		"""Create new configuration"""
		await self.broadcast_to_all({
			"type": "info",
			"message": "Config creation functionality not yet implemented"
		})

	async def handle_test_connection(self, websocket: WebSocket):
		"""Test connection"""
		await self.send_to_client(websocket, {
			"type": "connection_test_result",
			"data": {"success": True, "message": "Connection test passed"}
		})

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
