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

            print(f"📥 RX DEBUG 2: Valid OV header, payload {len(fragment_payload)} bytes")

            # Step 2: Try to reassemble COBS frames
            cobs_frames = self.reassembler.add_frame_payload(fragment_payload)
            print(f"📥 RX DEBUG 3: Got {len(cobs_frames)} complete COBS frames")

            # Step 3: Process each complete COBS frame
            for i, frame in enumerate(cobs_frames):
                print(f"📥 RX DEBUG 4: Processing COBS frame {i+1}, size {len(frame)} bytes")

                try:
                    # CRITICAL: Pass the frame WITHOUT adding terminator here
                    # The decode_frame method will handle terminator addition
                    ip_frame, _ = self.cobs_manager.decode_frame(frame)
                
                    print(f"📥 RX DEBUG 5: SUCCESS - IP frame {len(ip_frame)} bytes")
                    self._process_complete_ip_frame_async_debug(ip_frame, station_bytes, addr)

                except Exception as e:
                    self.stats['decode_errors'] += 1
                    print(f"📥 RX DEBUG 5: COBS decode ERROR: {e}")

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

            # DEBUG!!!
            print(f"🔍 UDP dest port: {udp_dest_port}, payload length: {len(udp_payload)}")


                
        except Exception as e:
            print(f"Error processing IP frame: {e}")








    # hi
    def _process_complete_ip_frame_async_debug(self, ip_frame, station_bytes, addr):
        """Process complete IP frame with async web notifications - DEBUG VERSION"""
        try:
            print(f"🌐 ASYNC IP DEBUG 1: IP frame processing")
            print(f"   IP frame total size: {len(ip_frame)} bytes")
        
            # Get station identifier
            try:
                from_station = StationIdentifier.from_bytes(station_bytes)
                from_station_str = str(from_station)
            except:
                from_station_str = f"UNKNOWN-{station_bytes.hex()[:8]}"

            print(f"🌐 ASYNC IP DEBUG 1: From station: {from_station_str}")

            # Parse IP header to get protocol info
            if len(ip_frame) < 20:
                print(f"🌐 ASYNC IP DEBUG 1: IP frame too small for IP header")
                return

            # Quick IP header parse to get UDP payload
            ip_header_length = (ip_frame[0] & 0x0F) * 4
            print(f"🌐 ASYNC IP DEBUG 2: IP header analysis")
            print(f"   IP header length: {ip_header_length} bytes (expected: 20)")
            print(f"   IP payload starts at offset: {ip_header_length}")
        
            if len(ip_frame) < ip_header_length + 8:  # Need at least UDP header
                print(f"🌐 ASYNC IP DEBUG 2: Not enough data for UDP header")
                return

            # Extract UDP frame and payload
            udp_frame = ip_frame[ip_header_length:]
            udp_payload = ip_frame[ip_header_length + 8:]  # Skip IP + UDP headers
        
            print(f"🌐 ASYNC IP DEBUG 3: UDP frame analysis")
            print(f"   UDP frame size: {len(udp_frame)} bytes")
            print(f"   UDP payload size: {len(udp_payload)} bytes")
            print(f"   Expected for audio: RTP(12) + OPUS(80) = 92 bytes")

            # Parse UDP header to determine port/type
            if len(udp_frame) >= 8:
                udp_header = udp_frame[:8]
                src_port, dst_port, udp_length, udp_checksum = struct.unpack('!HHHH', udp_header)
            
                print(f"🌐 ASYNC IP DEBUG 3: UDP header details")
                print(f"   Source port: {src_port}")
                print(f"   Dest port: {dst_port}")
                print(f"   UDP length: {udp_length} bytes (header + payload)")
                print(f"   UDP checksum: 0x{udp_checksum:04X}")
                print(f"   Calculated payload: {udp_length - 8} bytes")
                print(f"   Actual payload extracted: {len(udp_payload)} bytes")
            
                # Check if the lengths match
                if udp_length - 8 != len(udp_payload):
                    print(f"🌐 ASYNC IP DEBUG 3: ⚠️  UDP length mismatch!")
                    print(f"   UDP header says payload: {udp_length - 8} bytes")
                    print(f"   Actual payload: {len(udp_payload)} bytes")
                else:
                    print(f"🌐 ASYNC IP DEBUG 3: ✅ UDP length matches payload")

            current_time = datetime.now().isoformat()

            # Route based on UDP port
            if dst_port == 57373:  # Voice
                print(f"🌐 ASYNC IP DEBUG 4: Audio packet detected")
                print(f"   UDP payload (RTP+OPUS): {len(udp_payload)} bytes")
                print(f"   Expected: RTP(12) + OPUS(80) = 92 bytes")
                if len(udp_payload) != 92:
                    print(f"   ⚠️  MISSING: {92 - len(udp_payload)} bytes")
                else:
                    print(f"   ✅ Correct size")
            
                self._handle_audio_packet(udp_payload, from_station_str, current_time)
             
            elif dst_port == 57374:  # Text  
                print(f"🌐 ASYNC IP DEBUG 4: Text packet detected")
                self._handle_text_packet(udp_payload, from_station_str, current_time)
            
            elif dst_port == 57375:  # Control
                print(f"🌐 ASYNC IP DEBUG 4: Control packet detected")
                self._handle_control_packet(udp_payload, from_station_str, current_time)
            else:
                print(f"🌐 ASYNC IP DEBUG 4: Unknown port {dst_port}")

            print(f"🌐 ASYNC IP DEBUG 5: Processing complete")
            print("-" * 50)

        except Exception as e:
            print(f"🌐 ASYNC IP DEBUG ERROR: {e}")
            import traceback
            traceback.print_exc()























    def _handle_audio_packet(self, udp_payload, from_station, timestamp):
        """Handle received audio packet with comprehensive debugging"""
        self.stats['audio_packets'] += 1
    
        # DEBUG 1: Basic packet info
        print(f"🎤 DEBUG 1: Audio packet received")
        print(f"   From: {from_station}")
        print(f"   UDP payload size: {len(udp_payload)} bytes")
        print(f"   Expected: ≥12 bytes (RTP header)")
    
        try:
            # DEBUG 2: RTP header extraction
            if len(udp_payload) >= 12:  # RTP header size
                rtp_payload = udp_payload[12:]  # Skip RTP header
                print(f"🎤 DEBUG 2: RTP processing")
                print(f"   RTP header: {udp_payload[:12].hex()}")
                print(f"   RTP payload size: {len(rtp_payload)} bytes")
                print(f"   Expected OPUS: ~80 bytes")
            
                # DEBUG 3: RTP header parsing (optional detailed check)
                if len(udp_payload) >= 12:
                    rtp_header = udp_payload[:12]
                    version = (rtp_header[0] >> 6) & 0x3
                    marker = (rtp_header[1] >> 7) & 0x1
                    payload_type = rtp_header[1] & 0x7F
                    sequence = int.from_bytes(rtp_header[2:4], 'big')
                    timestamp_rtp = int.from_bytes(rtp_header[4:8], 'big')
                    ssrc = int.from_bytes(rtp_header[8:12], 'big')
                
                    print(f"🎤 DEBUG 3: RTP Header Details")
                    print(f"   Version: {version} (should be 2)")
                    print(f"   Marker: {marker}")
                    print(f"   Payload Type: {payload_type} (should be 96 for OPUS)")
                    print(f"   Sequence: {sequence}")
                    print(f"   RTP Timestamp: {timestamp_rtp}")
                    print(f"   SSRC: 0x{ssrc:08X}")
            
                # DEBUG 4: OPUS decoding attempt
                if len(rtp_payload) > 0:
                    print(f"🎤 DEBUG 4: OPUS decoding attempt")
                    print(f"   OPUS data endview: ...{rtp_payload[-4:].hex()}")
                    #print(f"   OPUS data preview: {rtp_payload[:16].hex()}...")
                
                    # Check if decoder is available
                    if hasattr(self, 'audio_decoder') and self.audio_decoder.decoder_available:
                        print(f"   OPUS decoder: Available")
                        audio_pcm = self.audio_decoder.decode_opus(rtp_payload)
                    
                        print(f"🎤 DEBUG 5: OPUS decode result")
                        if audio_pcm:
                            print(f"   PCM data produced: {len(audio_pcm)} bytes")
                            print(f"   Sample rate: 48000 Hz")
                            print(f"   Duration: {len(audio_pcm) / 2 / 48000 * 1000:.1f} ms (assuming 16-bit)")
                            print(f"   PCM preview: {audio_pcm[:16].hex()}...")
                        
                            # DEBUG 6: Queue for web streaming
                            try:
                                audio_data = {
                                    'audio_data': audio_pcm,
                                    'from_station': from_station,
                                    'timestamp': timestamp,
                                    'sample_rate': 48000,
                                    'duration_ms': int((len(audio_pcm) / 2) / 48000 * 1000)
                                }
                                self.audio_queue.put_nowait(audio_data)
                                print(f"🎤 DEBUG 6: Audio queued for web streaming")
                                print(f"   Queue size: {self.audio_queue.qsize()}")
                            except Exception as e:
                                print(f"🎤 DEBUG 6: Queue failed: {e}")
                            
                            # DEBUG 7: Web interface notification
                            web_notification_data = {
                                'from_station': from_station,
                                'timestamp': timestamp,
                                'audio_length': len(audio_pcm),
                                'sample_rate': 48000,
                                'duration_ms': int((len(audio_pcm) / 2) / 48000 * 1000)
                            }
                            print(f"🎤 DEBUG 7: Sending web notification")
                            print(f"   Notification data: {web_notification_data}")
                        
                            self._notify_web_async('audio_received', web_notification_data)
                            print(f"🎤 DEBUG 7: Web notification sent")
                        
                        else:
                            print(f"   PCM data: None (decode failed)")
                            print(f"   This suggests OPUS decoding issue")
                    else:
                        print(f"   OPUS decoder: NOT AVAILABLE")
                        print(f"   Decoder object: {getattr(self, 'audio_decoder', 'Missing')}")
                        if hasattr(self, 'audio_decoder'):
                            print(f"   Decoder available flag: {getattr(self.audio_decoder, 'decoder_available', 'Missing')}")
                else:
                    print(f"🎤 DEBUG 4: No RTP payload to decode")
            else:
                print(f"🎤 DEBUG 2: Packet too small for RTP header")
            
            # DEBUG 8: Summary
            print(f"🎤 DEBUG 8: Processing complete")
            print(f"   Audio packets processed: {self.stats['audio_packets']}")
            print(f"   Web notifications sent: {self.stats.get('web_notifications', 0)}")
            print("-" * 50)
            
        except Exception as e:
            print(f"🎤 DEBUG ERROR: Exception in audio processing: {e}")
            import traceback
            traceback.print_exc()
            print("-" * 50)










            
    def _handle_audio_packet_temp_replace_with_above(self, udp_payload, from_station, timestamp):
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
                        'sample_rate': 48000,
                        'duration_ms': int((len(audio_pcm) / 2) / 48000 * 1000)  # 16-bit samples
                    })
                    
                DebugConfig.debug_print(f"🎤 [{from_station}] Audio: {len(rtp_payload)}B OPUS → {len(audio_pcm) if audio_pcm else 0}B PCM")
                
        except Exception as e:
            print(f"Error processing audio: {e}")
            














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


#	# Diplay in CLI if chat interface available at all times
#            if self.chat_interface:
#                if hasattr(self.chat_interface, 'display_received_message'):
#                    self.chat_interface.display_received_message(from_station, message_text)
#                else:
#                    # Fallback display
#                    print(f"\n📨 [{from_station}]: {message_text}")
 




                   
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
        """Handle received control packet"""
        self.stats['control_packets'] += 1
        
        try:
            control_msg = udp_payload.decode('utf-8')
            
            # Only show non-keepalive control messages
            if not control_msg.startswith('KEEPALIVE'):
                DebugConfig.debug_print(f"📋 [{from_station}] Control: {control_msg}")
                
                # Notify web interface for important control messages
                self._notify_web_async('control_received', {
                    'type': 'control',
                    'content': control_msg,
                    'from': from_station,
                    'timestamp': timestamp
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
                else:
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
