#!/usr/bin/env python3
"""
FIXED Enhanced MessageReceiver with Web Interface Integration
Addresses missing imports and connection issues
"""

import asyncio
import threading
import time
import struct
import json
import socket  # 🔧 FIXED: Missing socket import
import pyaudio
from queue import Queue, Empty
from typing import Optional, Dict, List, Callable
from datetime import datetime

from radio_protocol import (
    SimpleFrameReassembler,
    COBSFrameBoundaryManager, 
    OpulentVoiceProtocolWithIP,
    StationIdentifier,
    DebugConfig
)



class WebSocketBridge:
    """Bridges MessageReceiver events to WebSocket interface"""
    
    def __init__(self):
        self.web_interface = None
        self.message_callbacks = []
        self.audio_callbacks = []
        self.control_callbacks = []
        self.outgoing_transmission_callbacks = []
        
    def set_web_interface(self, web_interface):
        """Connect to web interface instance"""
        self.web_interface = web_interface
        
    def add_message_callback(self, callback):
        """Add callback for received messages"""
        self.message_callbacks.append(callback)
        
    def add_audio_callback(self, callback):
        """Add callback for received audio"""
        self.audio_callbacks.append(callback)

    def add_control_callback(self, callback):
        """Add callback for received control messages"""
        self.control_callbacks.append(callback)
        
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

    async def notify_control_received(self, control_data):
        """Notify web interface of received control messages"""
        if self.web_interface:
            try:
                # Check if the web interface has the on_control_received method
                if hasattr(self.web_interface, 'on_control_received'):
                    await self.web_interface.on_control_received(control_data)
                else:
                    # Fallback to regular message handling
                    await self.web_interface.on_message_received(control_data)
            except Exception as e:
                print(f"Error notifying web interface of control: {e}")
                
        # Also notify other callbacks
        for callback in self.control_callbacks:
            try:
                callback(control_data)
            except Exception as e:
                print(f"Error in control callback: {e}")

    # New for UI bubbles for outgoing transmission
    def add_outgoing_transmission_callback(self, callback):
        """Add callback for outgoing transmission events"""
        self.outgoing_transmission_callbacks.append(callback)
    
    async def notify_outgoing_transmission_started(self, transmission_data):
        """Notify web interface of outgoing transmission start"""
        if self.web_interface:
            try:
                # Check if the web interface has outgoing transmission methods
                if hasattr(self.web_interface, 'on_outgoing_transmission_started'):
                    await self.web_interface.on_outgoing_transmission_started(transmission_data)
            except Exception as e:
                print(f"Error notifying web interface of outgoing transmission start: {e}")
                
        # Also notify other callbacks
        for callback in self.outgoing_transmission_callbacks:
            try:
                callback(transmission_data)
            except Exception as e:
                print(f"Error in outgoing transmission callback: {e}")
    
    async def notify_outgoing_transmission_ended(self, transmission_data):
        """Notify web interface of outgoing transmission end"""
        if self.web_interface:
            try:
                if hasattr(self.web_interface, 'on_outgoing_transmission_ended'):
                    await self.web_interface.on_outgoing_transmission_ended(transmission_data)
            except Exception as e:
                print(f"Error notifying web interface of outgoing transmission end: {e}")
                
        # Also notify other callbacks
        for callback in self.outgoing_transmission_callbacks:
            try:
                callback(transmission_data)
            except Exception as e:
                print(f"Error in outgoing transmission callback: {e}")

    async def notify_outgoing_audio_received(self, audio_data):
        """Notify web interface of outgoing audio (our own transmission)"""
        if self.web_interface:
            try:
                # Use the same audio notification but mark as outgoing
                await self.web_interface.on_audio_received(audio_data)
            except Exception as e:
                print(f"Error notifying web interface of outgoing audio: {e}")
                
        # Also notify other callbacks
        for callback in self.audio_callbacks:
            try:
                callback(audio_data)
            except Exception as e:
                print(f"Error in outgoing audio callback: {e}")






class EnhancedMessageReceiver:
    """Enhanced MessageReceiver with web interface integration"""
    
    def __init__(self, listen_port=57372, chat_interface=None):
        self.listen_port = listen_port
        self.chat_interface = chat_interface
        self.socket = None
        self.running = False
        self.receive_thread = None
        self._stopped = False
        self._audio_stopped = False
        
        # Audio and message processing
        self.reassembler = SimpleFrameReassembler()
        self.cobs_manager = COBSFrameBoundaryManager()
        self.protocol = OpulentVoiceProtocolWithIP(StationIdentifier("TEMP"))
        
        # Web interface bridge
        self.web_bridge = WebSocketBridge()
        
        # Audio reception components
        self.audio_decoder = AudioDecoder()
        self.audio_queue = Queue(maxsize=100)  # Buffer for web streaming
        self.audio_output = None
        
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
        if self._stopped:
            return
            
        self._stopped = True
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











                    
    def _process_received_data_async_temp_replace_with_below(self, data, addr):
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
                    DebugConfig.debug_print(f"✗ COBS decode error: {e}")
                    
        except Exception as e:
            print(f"Error processing received data: {e}")










    # 3. In EnhancedMessageReceiver class, replace _process_received_data_async method:
    def _process_received_data_async(self, data, addr):
        """Process received data - FIXED FOR AUDIO RECEPTION and 134 byte frames"""
        try:
            # Step 1: Parse Opulent Voice header
            if len(data) != 134:  # CHANGED: 133 → 134
                print(f"⚠ Expected 134-byte frame, got {len(data)}B from {addr}")
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
            for i, frame in enumerate(cobs_frames):

                try:
                    # CRITICAL: Pass the frame WITHOUT adding terminator here
                    # The decode_frame method will handle terminator addition
                    ip_frame, _ = self.cobs_manager.decode_frame(frame)
                    self._process_complete_ip_frame_async_debug(ip_frame, station_bytes, addr)

                except Exception as e:
                    self.stats['decode_errors'] += 1

        except Exception as e:
            print(f"📥 RX DEBUG ERROR: {e}")
            import traceback
            traceback.print_exc()

















            
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








    def _process_complete_ip_frame_async_debug(self, ip_frame, station_bytes, addr):
        """Process complete IP frame with async web notifications - DEBUG VERSION"""
        try:
            # Get station identifier
            try:
                from_station = StationIdentifier.from_bytes(station_bytes)
                from_station_str = str(from_station)
            except:
                from_station_str = f"UNKNOWN-{station_bytes.hex()[:8]}"

            # Parse IP header to get protocol info
            if len(ip_frame) < 20:
                print(f"🌐 IP frame too small for IP header")
                return

            # Quick IP header parse to get UDP payload
            ip_header_length = (ip_frame[0] & 0x0F) * 4
        
            if len(ip_frame) < ip_header_length + 8:  # Need at least UDP header
                print(f"🌐 Not enough data for UDP header")
                return

            # Extract UDP frame and payload
            udp_frame = ip_frame[ip_header_length:]
            udp_payload = ip_frame[ip_header_length + 8:]  # Skip IP + UDP headers
        
            # Parse UDP header to determine port/type
            if len(udp_frame) >= 8:
                udp_header = udp_frame[:8]
                src_port, dst_port, udp_length, udp_checksum = struct.unpack('!HHHH', udp_header)
            
            # Check if the lengths match
            if udp_length - 8 != len(udp_payload):
                print(f"🌐 ⚠️  UDP length mismatch!")
                print(f"   UDP header says payload: {udp_length - 8} bytes")
                print(f"   Actual payload: {len(udp_payload)} bytes")

            current_time = datetime.now().isoformat()

            # Route based on UDP port
            if dst_port == 57373:  # Voice
                if len(udp_payload) != 92:
                    print(f"   ⚠️  MISSING: {92 - len(udp_payload)} bytes")
            
                self._handle_audio_packet(udp_payload, from_station_str, current_time)
             
            elif dst_port == 57374:  # Text  
                self._handle_text_packet(udp_payload, from_station_str, current_time)
            
            elif dst_port == 57375:  # Control
                self._handle_control_packet(udp_payload, from_station_str, current_time)
            else:
                print(f"🌐 Unknown port {dst_port}")

        except Exception as e:
            print(f"🌐 ASYNC IP DEBUG ERROR: {e}")
            import traceback
            traceback.print_exc()









    def stop_audio_output(self):
        """Stop audio output"""
        if self._audio_stopped:
            return
            
        self._audio_stopped = True
        
        if hasattr(self, 'audio_output') and self.audio_output:
            self.audio_output.stop_playback()
            DebugConfig.debug_print("🔊 Audio output stopped")





    def _handle_audio_packet(self, udp_payload, from_station, timestamp):
        """
        Handle received audio packet with:
            real-time playback
            web notifications
            debugging
        """
        self.stats['audio_packets'] += 1

        try:
            # Extract RTP header and Opus payload
            if len(udp_payload) >= 12:  # RTP header size
                rtp_payload = udp_payload[12:]  # Skip RTP header

                # Check if decoder is available and decode Opus audio
                if hasattr(self, 'audio_decoder') and self.audio_decoder.decoder_available:
                    audio_pcm = self.audio_decoder.decode_opus(rtp_payload)
                    if audio_pcm:
                        # REAL-TIME PLAYBACK THROUGH HEADPHONES
                        if self.audio_output and self.audio_output.playing:
                            self.audio_output.queue_audio_for_playback(audio_pcm, from_station)
                        else:
                            DebugConfig.debug_print(f"🎤 Audio output NOT available")
                            DebugConfig.debug_print(f"   Has audio_output: {hasattr(self, 'audio_output') and self.audio_output is not None}")
                            if hasattr(self, 'audio_output') and self.audio_output:
                                DebugConfig.debug_print(f"   Audio output playing: {self.audio_output.playing}")
                            else:
                                print(f"   Audio output is None")
                            print(f"🔊 Audio output not active - voice will be silent")

                        # Queue audio for web streaming
                        try:
                            audio_data = {
                                'audio_data': audio_pcm,
                                'from_station': from_station,
                                'timestamp': timestamp,
                                'sample_rate': 48000,
                                'duration_ms': int((len(audio_pcm) / 2) / 48000 * 1000)
                            }
                            self.audio_queue.put_nowait(audio_data)
                        except Exception as e:
                                print(f"🎤 Queue failed: {e}")
                                pass # web queue being full is not critical
                            
                        # Web interface notification
                        self._notify_web_async('audio_received', {
                                'from_station': from_station,
                                'timestamp': timestamp,
                                'audio_length': len(audio_pcm),
                                'sample_rate': 48000,
                                'duration_ms': int((len(audio_pcm) / 2) / 48000 * 1000),
                                'audio_data': audio_pcm  # ✅ CRITICAL: Include the actual PCM audio data
                        })
                        
                    else:
                        print(f"🎤 OPUS decode failed")
                else:
                    print(f"🎤 OPUS decoder NOT available")
                    print(f"   Has audio_decoder: {hasattr(self, 'audio_decoder')}")
                    if hasattr(self, 'audio_decoder'):
                        DebugConfig.debug_print(f"   Decoder available: {self.audio_decoder.decoder_available}")
            else:
                print(f"🎤 UDP payload too small for RTP header")
        except Exception as e:
            print(f"🎤 Audio processing error: {e}")
            import traceback
            traceback.print_exc()











    def _handle_text_packet(self, udp_payload, from_station, timestamp):
        """Handle received text packet"""
        self.stats['text_packets'] += 1
        
        try:
            message_text = udp_payload.decode('utf-8')
            


            # Display in CLI if chat interface available AND no web interface connected
            if self.chat_interface and not self.web_bridge.web_interface:
                if hasattr(self.chat_interface, 'display_received_message'):
                    self.chat_interface.display_received_message(from_station, message_text)
                else:
                    # Fallback display	
                    print(f"\n📨 [{from_station}]: {message_text}")


            # Notify web interface asynchronously
            self._notify_web_async('message_received', {
                'type': 'text',
                'content': message_text,
                'from': from_station,
                'timestamp': str(timestamp), # ensure that this is a string
                'direction': 'incoming'
            })
            
        except UnicodeDecodeError:
            print(f"📨 [{from_station}]: <Binary text data: {len(udp_payload)}B>")










    def _handle_control_packet(self, udp_payload, from_station, timestamp):
        """Handle received control packet with web interface notification"""
        self.stats['control_packets'] += 1
        
        try:
            control_msg = udp_payload.decode('utf-8')
            # Always process PTT Control Messages
            if control_msg.startswith('PTT_'):
                DebugConfig.debug_print(f"🎛️  PTT control message detected, sending control_received")
                DebugConfig.debug_print(f"📋 [{from_station}] PTT Control: {control_msg}")
            
                # Send to web interface immediately for transmission grouping
                self._notify_web_async('control_received', {
                    'type': 'control',
                    'content': control_msg,
                    'from': from_station,
                    'timestamp': timestamp,
                    'priority': 'high'
                })

                # Also send to web interface via the radio system if available
                if hasattr(self, 'web_interface') and self.web_interface:
                    def notify_web_control():
                        try:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            loop.run_until_complete(self.web_interface.on_control_received({
                                "content": control_msg,
                                "from": from_station,
                                "timestamp": timestamp,
                                "type": "control"
                            }))
                            loop.close()
                        except Exception as e:
                            print(f"Error notifying web interface of control: {e}")
                
                    threading.Thread(target=notify_web_control, daemon=True).start()
                
            elif not control_msg.startswith('KEEPALIVE'):
                # Show non-keepalive control messages
                DebugConfig.debug_print(f"📋 [{from_station}] Control: {control_msg}")

                # Notify web interface for important control messages
                self._notify_web_async('control_received', {
                    'type': 'control',
                    'content': control_msg,
                    'from': from_station,
                    'timestamp': timestamp,
                    'priority': 'normal'
                })
            
        except UnicodeDecodeError:
            DebugConfig.debug_print(f"📋 [{from_station}] Control: <Binary data: {len(udp_payload)}B>")







    def _notify_web_async(self, event_type, data):
        """Send async notification to web interface"""
        def notify():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
                if event_type == 'audio_received':
                    loop.run_until_complete(self.web_bridge.notify_audio_received(data))
                elif event_type == 'control_received':
                    # NEW: Handle control messages separately
                    loop.run_until_complete(self.web_bridge.notify_control_received(data))
                else:
                    # All other messages (text, etc.) go to message handler
                    loop.run_until_complete(self.web_bridge.notify_message_received(data))
                
                self.stats['web_notifications'] += 1
                loop.close()
            except Exception as e:
                DebugConfig.debug_print(f"Error in web notification: {e}")
            
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










class AudioOutputManager:
    """Audio output manager focused on real-time playback"""
    
    def __init__(self, audio_params):
        # Use exact parameters from radio system
        self.sample_rate = audio_params['sample_rate']
        self.channels = audio_params['channels'] 
        self.buffer_size = audio_params['frames_per_buffer']
        self._stopped = False
        
        # Audio output setup with PyAudio initialization

        try:
            import pyaudio  # Make sure pyaudio is available
            self.audio = pyaudio.PyAudio()
            self.output_stream = None
            self.output_device = None
            DebugConfig.debug_print(f"✅ PyAudio initialized successfully")
        except ImportError as e:
            print(f"❌ PyAudio import failed: {e}")
            self.audio = None
            return
        except Exception as e:
            print(f"❌ PyAudio initialization failed: {e}")
            self.audio = None
            return

        # Simple playback queue
        self.playback_queue = Queue(maxsize=10)  # Small buffer for real-time
        self.playback_thread = None
        self.playing = False
        
        # Basic statistics
        self.stats = {
            'packets_queued': 0,
            'packets_played': 0,
            'total_samples_played': 0
        }
        
        print("🔊 Simplified AudioOutputManager ready")
    
    def setup_with_device(self, output_device_index):
        """Setup using pre-selected device index"""
        try:
            self.output_device = output_device_index
            print(f"🔊 Output device set: {output_device_index}")
            return True
        except Exception as e:
            print(f"✗ Output device setup failed: {e}")
            return False
    
    def start_playback(self):
        """Start audio output stream and playback thread"""
        if self.playing:
            return True
            
        try:
            # Create output stream
            self.output_stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.sample_rate,
                output=True,
                output_device_index=self.output_device,
                frames_per_buffer=self.buffer_size
            )
            
            # Start playback thread
            self.playing = True
            self.playback_thread = threading.Thread(target=self._playback_loop, daemon=True)
            self.playback_thread.start()
            
            DebugConfig.debug_print(f"🔊 Audio output started: {self.sample_rate}Hz, device {self.output_device}")
            DebugConfig.debug_print(f"   Output latency: {self.output_stream.get_output_latency():.3f}s")
            return True
            
        except Exception as e:
            print(f"✗ Failed to start audio output: {e}")
            self.playing = False
            return False
    
    def stop_playback(self):
        if self._stopped:
            return
            
        self._stopped = True
        self.playing = False
        
        if self.playback_thread:
            self.playback_thread.join(timeout=2.0)
            
        if self.output_stream:
            self.output_stream.stop_stream()
            self.output_stream.close()
            self.output_stream = None
            
        print("🔊 Audio playback loop stopped")
    
    def queue_audio_for_playback(self, pcm_data, from_station="UNKNOWN"):
        """Queue PCM audio data for playback"""
        try:
            audio_packet = {
                'pcm_data': pcm_data,
                'from_station': from_station,
                'timestamp': time.time(),
                'sample_count': len(pcm_data) // 2  # 16-bit samples
            }
            
            self.playback_queue.put_nowait(audio_packet)
            self.stats['packets_queued'] += 1
            
            DebugConfig.debug_print(f"🔊 Queued audio: {len(pcm_data)}B from {from_station} "
                  f"(queue: {self.playback_queue.qsize()})")
            
        except Exception as e:
            self.stats['buffer_overruns'] += 1
            print(f"🔊 Audio queue full, dropping packet from {from_station}")
    
    def _playback_loop(self):
        """Main playback loop - runs in separate thread"""
        print("🔊 Audio playback loop started")
        
        while self.playing:
            try:
                # Get audio packet from queue
                audio_packet = self.playback_queue.get(timeout=0.1)
                
                # Play the audio
                pcm_data = audio_packet['pcm_data']
                from_station = audio_packet['from_station']
                
                if self.output_stream and self.output_stream.is_active():
                    # Write PCM data to output stream
                    self.output_stream.write(pcm_data)
                    
                    # Update statistics
                    self.stats['packets_played'] += 1
                    self.stats['total_samples_played'] += audio_packet['sample_count']
                    
                    print(f"🔊 Playing audio from {from_station}: "
                          f"{len(pcm_data)}B ({audio_packet['sample_count']} samples)")
                
            except Empty:
                # No audio to play - normal timeout
                continue
            except Exception as e:
                print(f"🔊 Playback error: {e}")
                time.sleep(0.01)  # Brief pause on error
        
    
    def get_stats(self):
        """Get audio output statistics"""
        stats = self.stats.copy()
        stats['queue_size'] = self.playback_queue.qsize()
        stats['playing'] = self.playing
        stats['output_latency'] = (self.output_stream.get_output_latency() 
                                  if self.output_stream else 0)
        return stats
    
    def cleanup(self):
        """Cleanup audio resources"""
        self.stop_playback()
        if hasattr(self, 'audio'):
            self.audio.terminate()
        print("🔊 AudioOutputManager cleanup complete")



















class AudioDecoder:
    """OPUS audio decoder for web interface"""
    
    def __init__(self, sample_rate=48000, channels=1):
        self.sample_rate = sample_rate
        self.channels = channels
        
        try:
            import opuslib_next as opuslib
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
            print(f"-=-=-=-=-=-=-=-=-=OPUS decode error: {e}")
            #DebugConfig.debug_print(f"OPUS decode error: {e}")
            return None


# Integration functions for existing code
def integrate_enhanced_receiver(radio_system, web_interface=None):
    """Replace existing MessageReceiver with enhanced version"""
    
    # Stop existing receiver if running
    if hasattr(radio_system, 'receiver') and radio_system.receiver:
        radio_system.receiver.stop()
        
    # Create enhanced receiver with proper config
    config = radio_system.config if hasattr(radio_system, 'config') else None
    listen_port = config.network.listen_port if config else 57372
    
    enhanced_receiver = EnhancedMessageReceiver(
        listen_port=listen_port,
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
