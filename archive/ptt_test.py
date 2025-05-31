#!/usr/bin/env python3
"""
GPIO PTT Test
GPIO 17 set to light up when PTT
GPIO 23 detects PTT
"""

import RPi.GPIO as GPIO
import time
import sys
from threading import Thread

class PTTHandler:
	def __init__(self, ptt_pin=23, led_pin=17):
		self.ptt_pin = ptt_pin
		self.ptt_active = False
		self.led_pin = led_pin
		self.led_active = False
		self.setup_gpio()

	def setup_gpio(self):
		GPIO.setmode(GPIO.BCM)
		GPIO.setup(self.ptt_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
		GPIO.setup(self.led_pin, GPIO.OUT)
		GPIO.output(self.led_pin, GPIO.LOW)
		# Hardware interrupt
		GPIO.add_event_detect(
			self.ptt_pin,
			GPIO.BOTH,
			callback=self.ptt_interrupt,
			bouncetime = 50 #in milliseconds
		)

	def ptt_interrupt(self, channel):
		# Active low (pressed is low, grounded)
		new_state = not GPIO.input(self.ptt_pin)

		if new_state != self.ptt_active:
			self.ptt_active = new_state
			if self.ptt_active:
				self.start_transmission()
			else:
				self.stop_transmission()

	def start_transmission(self):
		print("PTT: Voice transmit start")
		GPIO.output(self.led_pin, GPIO.HIGH)
		#radio stuff here

	def stop_transmission(self):
		print("PTT: Voice transmit stop")
		GPIO.output(self.led_pin, GPIO.LOW)
		#radio stuff here

	def cleanup(self):
		GPIO.cleanup()

# here is the usage
if __name__ == "__main__":
	ptt = PTTHandler(23, 17)
	try:
		print("PTT input button on GPIO 23. Press CTRL+C to exit.")
		while True:
			pass #have to have if time.sleep() commented
			#time.sleep(0.1) #AI make sure we don't need this!
	except KeyboardInterrupt:
		print("\nDropping out of PTT monitor")
	finally:
		ptt.cleanup()








