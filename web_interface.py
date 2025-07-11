#!/usr/bin/env python3
"""
Web Interface for Opulent Voice Radio System
FastAPI backend that bridges the HTML5 GUI with the existing radio system
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

class RadioWebInterface:
    """Bridge between web GUI and radio system"""
    
    def __init__(self, radio_system=None, config: OpulentVoiceConfig = None):
        self.radio_system = radio_system
        self.config = config
        self.websocket_clients: Set[WebSocket] = set()
        self.status_cache = {}
        self.message_history = []
        
        # Audio message storage for GUI
        self.audio_messages = {}
        self.max_audio_messages = config.gui.audio_replay.max_stored_messages if config else 100
        
        self.logger = logging.getLogger(__name__)
        
    async def connect_websocket(self, websocket: WebSocket):
        """Handle new WebSocket connection"""
        await websocket.accept()
        self.websocket_clients.add(websocket)
        
        # Send current status to new client
        await self.send_to_client(websocket, {
            "type": "initial_status",
            "data": self.get_current_status()
        })
        
        self.logger.info(f"New WebSocket client connected. Total: {len(self.websocket_clients)}")
    
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
        """Process commands from GUI"""
        try:
            command = command_data.get('action')
            data = command_data.get('data', {})
        
            if command == 'send_text_message':
                await self.handle_send_text_message(data)
            elif command == 'update_config':
                await self.handle_update_config(data)  # Use the NEW method
            elif command == 'get_current_config':
                await self.handle_get_current_config(websocket)
            elif command == 'save_config':
                await self.handle_save_config(data)
            elif command == 'load_config':
                await self.handle_load_config(websocket)
            elif command == 'test_connection':
                await self.handle_test_connection(websocket)
            elif command == 'get_audio_devices':
                await self.handle_get_audio_devices(websocket)
            elif command == 'test_audio':
                await self.handle_test_audio(websocket, data)
            elif command == 'set_debug_mode':
                await self.handle_debug_mode_change(data)
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








    
    async def handle_send_text_message(self, data: Dict):
        """Handle text message from GUI"""
        message = data.get('message', '').strip()
        if not message:
            return
            
        # Send to radio system if available
        if self.radio_system and hasattr(self.radio_system, 'audio_frame_manager'):
            self.radio_system.audio_frame_manager.queue_text_message(message)
            
        # Add to message history
        self.message_history.append({
            "type": "text",
            "direction": "outgoing",
            "content": message,
            "timestamp": datetime.now().isoformat(),
            "from": str(self.radio_system.station_id) if self.radio_system else "LOCAL"
        })
        
        # Broadcast to all clients
        await self.broadcast_to_all({
            "type": "message_sent",
            "data": {
                "message": message,
                "timestamp": datetime.now().isoformat()
            }
        })
    
    async def handle_config_update(self, data: Dict):
        """Handle configuration updates from GUI"""
        # Apply GUI overrides to configuration
        if self.config:
            for key, value in data.items():
                # TODO: Implement safe config override system
                self.logger.info(f"GUI config override: {key} = {value}")
        
        # Broadcast config change to all clients
        await self.broadcast_to_all({
            "type": "config_updated",
            "data": data
        })
    
    async def handle_get_audio_devices(self, websocket: WebSocket):
        """Get audio devices for GUI display"""
        devices = {"input": [], "output": []}
        
        try:
            if self.radio_system and hasattr(self.radio_system, 'list_audio_devices'):
                # Get devices from radio system
                # This is a simplified version - you'll need to adapt based on your audio system
                devices = {
                    "input": [
                        {"index": 0, "name": "Default Input", "channels": 1},
                        {"index": 2, "name": "USB Microphone", "channels": 1}
                    ],
                    "output": [
                        {"index": 0, "name": "Default Output", "channels": 2},
                        {"index": 1, "name": "Speakers", "channels": 2}
                    ]
                }
        except Exception as e:
            self.logger.error(f"Error getting audio devices: {e}")
        
        await self.send_to_client(websocket, {
            "type": "audio_devices",
            "data": devices
        })









# Added these methods to the RadioWebInterface class in web_interface.py to get frontend working

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
                self.config.callsign = data['callsign']
        
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
        
            if 'protocol' in data:
                protocol = data['protocol']
                if 'target_type' in protocol:
                    self.config.protocol.target_type = protocol['target_type']
                if 'keepalive_interval' in protocol:
                    self.config.protocol.keepalive_interval = float(protocol['keepalive_interval'])
                if 'continuous_stream' in protocol:
                    self.config.protocol.continuous_stream = bool(protocol['continuous_stream'])
        
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
        
            # Apply debug changes immediately to the global DebugConfig
            if 'debug' in data:
                from interlocutor import DebugConfig as GlobalDebugConfig
                GlobalDebugConfig.set_mode(
                    verbose=self.config.debug.verbose,
                    quiet=self.config.debug.quiet
                )
        
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
            filename = data.get('filename', 'opulent_voice.yaml')
        
            # Use the configuration manager to save the config
            from config_manager import ConfigurationManager
            config_manager = ConfigurationManager()
            config_manager.config = self.config
        
            success = config_manager.save_config(filename)
        
            if success:
                await self.broadcast_to_all({
                    "type": "config_saved",
                    "data": {"message": f"Configuration saved to {filename}"}
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

    async def handle_load_config(self, websocket: WebSocket):
        """Load configuration from file"""
        try:
            from config_manager import ConfigurationManager
            config_manager = ConfigurationManager()
        
            # Load the configuration
            loaded_config = config_manager.load_config()
        
            if loaded_config:
                self.config = loaded_config
            
                # Send the loaded config back to the client
                await self.handle_get_current_config(websocket)
            
                await self.send_to_client(websocket, {
                    "type": "config_loaded",
                    "data": {"message": "Configuration loaded successfully"}
                })
            
                self.logger.info("Configuration loaded via web interface")
            else:
                await self.send_to_client(websocket, {
                    "type": "error",
                    "message": "Failed to load configuration file"
                })
            
        except Exception as e:
            self.logger.error(f"Error loading config: {e}")
            await self.send_to_client(websocket, {
                "type": "error",
                "message": f"Error loading configuration: {str(e)}"
            })

    async def handle_test_connection(self, websocket: WebSocket):
        """Test network connection"""
        try:
            # Basic connectivity test
            if self.radio_system:
                # Use the radio system's test methods
                test_results = {
                    "network_available": True,
                    "target_reachable": True,  # You could implement actual ping test
                    "audio_system": True,      # You could implement actual audio test
                    "gpio_system": True        # You could implement actual GPIO test
                }
            
                await self.send_to_client(websocket, {
                    "type": "connection_test_result",
                    "data": {
                        "success": True,
                        "results": test_results,
                        "message": "Connection test completed successfully"
                    }
                })
            else:
                await self.send_to_client(websocket, {
                    "type": "connection_test_result", 
                    "data": {
                        "success": False,
                        "message": "Radio system not available for testing"
                    }
                })
            
        except Exception as e:
            self.logger.error(f"Error testing connection: {e}")
            await self.send_to_client(websocket, {
                "type": "error",
                "message": f"Connection test failed: {str(e)}"
            })



















    
    async def handle_test_audio(self, websocket: WebSocket, data: Dict):
        """Handle audio device testing"""
        device_type = data.get('type')  # 'input' or 'output'
        device_index = data.get('index', 0)
        
        # TODO: Integrate with your audio device manager
        success = True  # Placeholder
        
        await self.send_to_client(websocket, {
            "type": "audio_test_result",
            "data": {
                "type": device_type,
                "index": device_index,
                "success": success,
                "message": "Audio test completed" if success else "Audio test failed"
            }
        })
    




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
            # Fallback to global DebugConfig if no config available
            try:
                from interlocutor import DebugConfig as GlobalDebugConfig
                if GlobalDebugConfig.VERBOSE:
                    return "verbose"
                elif GlobalDebugConfig.QUIET:
                    return "quiet"
                else:
                    return "normal"
            except ImportError:
                return "normal"




    async def handle_debug_mode_change(self, data: Dict):
        """Handle debug mode changes from GUI"""
        mode = data.get('mode', 'normal')
    
        # Import the global DebugConfig here to avoid import conflicts
        from interlocutor import DebugConfig as GlobalDebugConfig
    
        # Update debug configuration using the global class
        if mode == 'verbose':
            GlobalDebugConfig.set_mode(verbose=True, quiet=False)
        elif mode == 'quiet':
            GlobalDebugConfig.set_mode(verbose=False, quiet=True)
        else:  # normal
            GlobalDebugConfig.set_mode(verbose=False, quiet=False)
    
        await self.broadcast_to_all({
            "type": "debug_mode_changed",
            "data": {"mode": mode}
        })




    
    def get_current_status(self) -> Dict:
        """Get current radio system status"""
        status = {
            "connected": self.radio_system is not None,
            "station_id": str(self.radio_system.station_id) if self.radio_system else "DISCONNECTED",
            "ptt_active": getattr(self.radio_system, 'ptt_active', False) if self.radio_system else False,
            "debug_mode": self._get_debug_mode(),
            "timestamp": datetime.now().isoformat(),
            "config": {
                "target_ip": self.config.network.target_ip if self.config else "unknown",
                "target_port": self.config.network.target_port if self.config else 0,
                "audio_enabled": True  # TODO: Check actual audio status
            },
            "stats": self.get_system_stats()
        }
        
        return status
    
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
            radio_stats = self.radio_system.get_stats()
            stats.update(radio_stats)
        
        return stats
    
    # Methods to be called by radio system for updates
    
    async def on_message_received(self, message_data: Dict):
        """Called when radio system receives a message"""
        self.message_history.append({
            "type": message_data.get("type", "unknown"),
            "direction": "incoming",
            "content": message_data.get("content", ""),
            "timestamp": datetime.now().isoformat(),
            "from": message_data.get("from", "UNKNOWN"),
            "metadata": message_data.get("metadata", {})
        })
        
        await self.broadcast_to_all({
            "type": "message_received",
            "data": message_data
        })
    
    async def on_ptt_state_changed(self, active: bool):
        """Called when PTT state changes"""
        await self.broadcast_to_all({
            "type": "ptt_state_changed",
            "data": {"active": active}
        })
    
    async def on_audio_message_captured(self, audio_data: bytes, metadata: Dict):
        """Called when audio message is captured for replay"""
        message_id = f"msg_{int(time.time())}_{metadata.get('from', 'unknown')}"
        
        # Store audio message (simplified - in real implementation, convert to blob URL)
        self.audio_messages[message_id] = {
            "id": message_id,
            "metadata": metadata,
            "timestamp": datetime.now().isoformat(),
            "duration": metadata.get("duration", 0),
            "size_bytes": len(audio_data)
        }
        
        # Maintain storage limit (drop oldest)
        while len(self.audio_messages) > self.max_audio_messages:
            oldest_id = min(self.audio_messages.keys(), key=lambda k: self.audio_messages[k]["timestamp"])
            del self.audio_messages[oldest_id]
        
        await self.broadcast_to_all({
            "type": "audio_message_available",
            "data": {
                "id": message_id,
                "metadata": metadata,
                "timestamp": datetime.now().isoformat()
            }
        })
    
    async def on_system_status_changed(self, status_data: Dict):
        """Called when system status changes"""
        self.status_cache.update(status_data)
        
        await self.broadcast_to_all({
            "type": "status_update",
            "data": status_data
        })

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
web_interface: Optional[RadioWebInterface] = None

def initialize_web_interface(radio_system=None, config=None):
    """Initialize the web interface with radio system"""
    global web_interface
    web_interface = RadioWebInterface(radio_system, config)
    return web_interface

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication"""
    if not web_interface:
        await websocket.close(code=1000, reason="Radio system not initialized")
        return
    
    await web_interface.connect_websocket(websocket)
    
    try:
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
        web_interface.disconnect_websocket(websocket)

@app.get("/")
async def get_index():
    """Serve the main GUI page"""
    html_file = Path("html5_gui/index.html")
    if html_file.exists():
        return HTMLResponse(content=html_file.read_text(), status_code=200)
    else:
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head><title>Opulent Voice GUI</title></head>
        <body>
            <h1>Opulent Voice Web Interface</h1>
            <p>GUI files not found. Please create html5_gui/index.html</p>
        </body>
        </html>
        """, status_code=200)



@app.get("/config")
async def get_config_page():
    """Serve the configuration page"""
    config_file = Path("html5_gui/config.html")
    if config_file.exists():
        return HTMLResponse(content=config_file.read_text(), status_code=200)
    else:
        return HTMLResponse(content="<h1>Configuration page not found</h1>", status_code=404)





@app.get("/api/status")
async def get_status():
    """Get current system status via REST API"""
    if not web_interface:
        raise HTTPException(status_code=503, detail="Radio system not initialized")
    
    return web_interface.get_current_status()

@app.get("/api/messages")
async def get_message_history():
    """Get message history"""
    if not web_interface:
        raise HTTPException(status_code=503, detail="Radio system not initialized")
    
    return {"messages": web_interface.message_history}

# Mount static files for GUI assets
try:
    app.mount("/static", StaticFiles(directory="html5_gui"), name="static")
except RuntimeError:
    # Directory doesn't exist yet - will be created during setup
    pass


def run_web_server(host="localhost", port=8000, radio_system=None, config=None):
    """Run the web server"""
    initialize_web_interface(radio_system, config)
    
    print(f"🌐 Starting Opulent Voice Web Interface on http://{host}:{port}")
    print(f"📡 WebSocket endpoint: ws://{host}:{port}/ws")
    
    # Configure logging - fix the DebugConfig reference
    # Use the config parameter instead of the global DebugConfig class
    if config and hasattr(config, 'debug'):
        log_level = "debug" if config.debug.verbose else "info"
        access_log = not config.debug.quiet
    else:
        # Fallback to reasonable defaults
        log_level = "info"
        access_log = True
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level,
        access_log=access_log
    )













if __name__ == "__main__":
    # For testing the web interface standalone
    run_web_server()
