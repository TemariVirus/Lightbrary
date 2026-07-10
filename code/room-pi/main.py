#!/usr/bin/python3

from signal import pause
from time import time

import mqtt
import sensors

# TODO
MQTT_HOST = "localhost"
MQTT_PORT = 1883
ROOM_ID = 1
MQTT_TOPIC = f"rooms/{ROOM_ID}/status"

PIR_PIN = 2
# TODO
TOUCH_PIN = 20


if __name__ == "__main__":
    mqtt_client = mqtt.connect(MQTT_HOST, MQTT_PORT)

    pir = sensors.init_motion(PIR_PIN)

    print("Sensor is ready. Waiting for motion events...")

    mqtt.pub(mqtt_client, MQTT_TOPIC, f"testing {time()}")

    pause()
