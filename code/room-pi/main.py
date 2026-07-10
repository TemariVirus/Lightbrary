from signal import pause
from time import time

import mqtt
import sensors

# TODO
MQTT_HOST = "192.168.1.4"
MQTT_PORT = 1883
ROOM_ID = 1
MQTT_TOPIC = f"rooms/{ROOM_ID}/status"

PIR_PIN = 20
TOUCH_PIN = 21

if __name__ == "__main__":
    mqtt_client = mqtt.connect(MQTT_HOST, MQTT_PORT)

    pir = sensors.init_motion(PIR_PIN)
    touch_sensor = sensors.init_touch(TOUCH_PIN)

    print("Sensor is ready. Waiting for motion events...")

    mqtt.publish(MQTT_TOPIC, f"testing {time()}")

    pause()
