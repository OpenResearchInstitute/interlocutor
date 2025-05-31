#!/usr/bin/env python3
"""
GPIO PTT Audio - FIXED VERSION
GPIO 17 set to light up when PTT
GPIO 23 detects PTT
Audio from microphone sent over network to e.g. Pluto

Fixed issues:
- Duplicate setup calls in __init__
- NetworkTransmitter stats bug
- Added audio validation
- Better error handling for OPUS
"""

import sys
import socket
import struct
import time
import threading

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
	STATION_ID = b'\x01\x23\x45\x01\x23\x45'  # 6 bytes as bytes, not int
	FRAME_TYPE_AUDIO = 0x01
	FRAME_TYPE_TEXT = 0x02
	FRAME_TYPE_CONTROL = 0x03
	FRAME_TYPE_DATA = 0x04

	HEADER_SIZE = 14  # 2 (synch) + 6 (station) + 1 (type) + 2 (seq) + 2 (len) + 1 (reserved)

	def __init__(self):
		self.sequence_counter = 0

	def create_audio_frame(self, opus_packet):
		"""Create Opulent Voice audio frame"""
		self.sequence_counter = (self.sequence_counter + 1) % 65536

		header = struct.pack(
			'>2s 6s B H H B',  # Fixed format: synch + station_id + type + seq + len + reserved
			self.STREAM_SYNCH_WORD,     # 2 bytes
			self.STATION_ID,            # 6 bytes  
			self.FRAME_TYPE_AUDIO,      # 1 byte
			self.sequence_counter,      # 2 bytes
			len(opus_packet),           # 2 bytes
			0                           # 1 byte reserved
		)

		return header + opus_packet

	def create_control_frame(self, control_data):
		"""Create Opulent Voice control frame"""
		self.sequence_counter = (self.sequence_counter + 1) % 65536

		header = struct.pack(
			'>2s 6s B H H B',
			self.STREAM_SYNCH_WORD,
			self.STATION_ID,
			self.FRAME_TYPE_CONTROL,
			self.sequence_counter,
			len(control_data),
			0
		)

		return header + control_data

	def parse_frame(self, frame_data):
		"""Parse received Opulent Voice frame"""
		if len(frame_data) < self.HEADER_SIZE:
			return None

		try:
			stream_synch, station_id, frame_type, sequence, payload_len, reserved = struct.unpack(
				'>2s 6s B H H B', frame_data[:self.HEADER_SIZE]
			)

			if stream_synch != self.STREAM_SYNCH_WORD:
				return None

			payload = frame_data[self.HEADER_SIZE:self.HEADER_SIZE + payload_len]

			return {
				'synch': stream_synch,
				'station_id': station_id,  # Now returns 6 bytes
				'type': frame_type,
				'sequence': sequence,
				'payload': payload
			}

		except struct.error:
			return None

	def station_id_to_string(self, station_id_bytes):
		"""Convert 6-byte station ID to readable string"""
		try:
			# Could be callsign encoding, for now just hex
			return station_id_bytes.hex().upper()
		except:
			return "UNKNOWN"



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
			self.stats['bytes_sent'] += bytes_sent  # ✓ FIXED: was += 1
			return True

		except Exception as e:
			self.stats['errors'] += 1  # ✓ FIXED: was 'errors!'
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

class GPIOZeroPTTHandler:
	def __init__(self, ptt_pin=23, led_pin=17, target_ip="192.168.2.1", target_port=8080):
		# GPIO setup with gpiozero
		self.ptt_button = Button(ptt_pin, pull_up=True, bounce_time=0.05)
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

		# Network setup
		self.protocol = OpulentVoiceProtocol()
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

		# ✓ FIXED: Only call setup methods once
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

				# Send via Opulent Voice Protocol
				if self.send_opulent_voice_frame(opus_packet):
					self.audio_stats['frames_sent'] += 1

				print(f"📡 Audio: {len(in_data)}B → OPUS: {len(opus_packet)}B")

			except Exception as e:
				self.audio_stats['encoding_errors'] += 1
				print(f"✗ Encoding error: {e}")
				print(f"   Frame size: {len(in_data)} bytes")
				print(f"   Samples: {self.samples_per_frame}")

		return (None, pyaudio.paContinue)

	def ptt_pressed(self):
		"""PTT button pressed"""
		self.ptt_active = True
		self.led.on()
		print("🎤 PTT: Transmit Start")
		self.send_control_frame("PTT_START")

	def ptt_released(self):
		"""PTT button released"""
		self.ptt_active = False
		self.led.off()
		print("🔇 PTT: Transmit Stop")
		self.send_control_frame("PTT_STOP")
		self.print_stats()

	def send_opulent_voice_frame(self, opus_packet):
		"""Send OPUS data via Opulent Voice Protocol"""
		# Create Opulent Voice frame
		ov_frame = self.protocol.create_audio_frame(opus_packet)

		# Send over network
		success = self.transmitter.send_frame(ov_frame)

		if not success:
			print(f"✗ Failed to send (OPUS: {len(opus_packet)}B, OV: {len(ov_frame)}B)")

		return success




	def send_control_frame(self, message):
		"""Send control message"""
		try:
			# Create control frame using the protocol's method
			control_data = message.encode('utf-8')
			control_frame = self.protocol.create_control_frame(control_data)
			
			self.transmitter.send_frame(control_frame)
			print(f"📋 Control: {message}")
	
		except Exception as e:
			print(f"✗ Control frame error: {e}")



	def print_stats(self):
		"""Print transmission statistics"""
		audio_stats = self.audio_stats
		net_stats = self.transmitter.get_stats()

		print("\n📊 Transmission Statistics:")
		print(f"   Audio frames encoded: {audio_stats['frames_encoded']}")
		print(f"   Frames sent to network: {audio_stats['frames_sent']}")
		print(f"   Invalid frames: {audio_stats['invalid_frames']}")
		print(f"   Network packets sent: {net_stats['packets_sent']}")
		print(f"   Total bytes sent: {net_stats['bytes_sent']}")
		print(f"   Encoding errors: {audio_stats['encoding_errors']}")
		print(f"   Network errors: {net_stats['errors']}")

		if audio_stats['frames_encoded'] > 0:
			success_rate = (audio_stats['frames_sent'] / audio_stats['frames_encoded']) * 100
			print(f"   Success rate: {success_rate:.1f}%")

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

		test_message = "OPULENT_VOICE_TEST"
		test_data = test_message.encode('utf-8')
		test_frame = self.protocol.create_audio_frame(test_data)

		if self.transmitter.send_frame(test_frame):
			print("   ✓ Test frame sent successfully")
		else:
			print("   ✗ Test frame failed")

	def start(self):
		"""Start the audio system"""
		if self.audio_input_stream:
			self.audio_input_stream.start_stream()
		print("🚀 Radio system started")
		print("📋 Configuration:")
		print(f"   Sample rate: {self.sample_rate} Hz")
		print(f"   Bitrate: {self.bitrate} bps CBR")
		print(f"   Frame size: {self.frame_duration_ms}ms ({self.samples_per_frame} samples)")
		print(f"   Frame rate: {1000/self.frame_duration_ms} fps")
		print(f"   Network target: {self.transmitter.target_ip}:{self.transmitter.target_port}")

	def stop(self):
		"""Stop the audio system"""
		if self.audio_input_stream:
			self.audio_input_stream.stop_stream()
			self.audio_input_stream.close()
		self.audio.terminate()
		print("🛑 Audio system stopped")

	def cleanup(self):
		"""Clean shutdown"""
		self.stop()
		self.transmitter.close()
		self.led.off()
		print("Thank you for shopping at Omega Mart. Cleanup complete.")

# Usage
if __name__ == "__main__":
	print("-=" * 30)
	print("Opulent Voice Radio with Network Transmission")
	print("-=" * 30)

	# Configuration
	TARGET_IP = "192.168.2.152"  # Your receiver's IP
	TARGET_PORT = 8080

	print(f"📡 Target: {TARGET_IP}:{TARGET_PORT}")
	print("💡 Change TARGET_IP to your receiver computer's IP address")
	print()

	try:
		radio = GPIOZeroPTTHandler(
			ptt_pin=23, 
			led_pin=17,
			target_ip=TARGET_IP,
			target_port=TARGET_PORT
		)

		radio.test_gpio()
		radio.test_network()
		radio.start()

		print("\n✅ System Ready. Press PTT to transmit. Ctrl+C to exit.")

		while True:
			time.sleep(0.1)

	except KeyboardInterrupt:
		print("\nThank you for using Opulent Voice. Shutting down...")
	except Exception as e:
		print(f"✗ Error: {e}")
	finally:
		radio.cleanup()
