#!/usr/bin/env python3
"""
GPIO LED Test
GPIO 17 set to blink
This may become PTT indicator light
"""

import RPi.GPIO as GPIO
import time
import sys

#Configure the pin and the blink rate
LED_PIN = 17
BLINK_RATE = 0.5 #in seconds

def setup_gpio():
	print("Setting up your GPIO my liege.")
	# We are going to use BCM pin numbering
	# These are the GPIO numbers and not
	# the pin numbers
	GPIO.setmode(GPIO.BCM)
	
	# Configure GPIO 17 as an output
	GPIO.setup(LED_PIN, GPIO.LOW)
	print(f"GPIO {LED_PIN} configured as output.")

def blink_test():
	# Run our blinking LED test
	print(f"Starting blink test on GPIO {LED_PIN}")
	print("Press CTRL+C to stop.")

	try:
		blink_count = 0
		while True:
			# turn LED on
			GPIO.output(LED_PIN, GPIO.HIGH)
			print(f"Blink {blink_count + 1}: LED ON")
			time.sleep(BLINK_RATE)
			# turn LED off
			GPIO.output(LED_PIN, GPIO.LOW)
			print(f"Blink {blink_count + 1}: LED OFF")
			time.sleep(BLINK_RATE)
			blink_count += 1

	except KeyboardInterrupt:
		print(f"\nBlink test stopped after {blink_count} blinks")
	
def cleanup():
	# Clean up the GPIO resources to be good citizen
	print("Cleaning up GPIOs")
	GPIO.output(LED_PIN, GPIO.LOW) # ensure it's off before we do this
	GPIO.cleanup()
	print("GPIO cleanup should be complete")

def main():
	print("-=" * 25)
	print("Raspberry Pi GPIO LED_TEST")
	print("-=" * 25)
	print(f"Using GPI {LED_PIN}")

	try: 
		setup_gpio()
		blink_test()
	except Exception as e:
		print(f"Oops: {e}")
		return 1
	finally:
		cleanup()
	return 0

if __name__ == "__main__":
	sys.exit(main())



