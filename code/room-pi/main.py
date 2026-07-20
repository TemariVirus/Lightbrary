import json
import sys
from datetime import datetime
from random import randint
from time import sleep

import paho.mqtt.client as mqtt
from gpiozero import Button, MotionSensor

MQTT_HOST = "192.168.1.253"
MQTT_PORT = 1883
ROOM_ID = 1
MQTT_TOPIC = f"rooms/{ROOM_ID}/status"

MQTT_INTERVAL = 2  # seconds
MQTT_RETRY_INTERVAL = 5  # seconds

PIR_PIN = 20
TOUCH_PIN = 21


def log(msg: str) -> None:
    t = datetime.now()
    print(f"[{t.isoformat()}] {msg}", end="\n")


def mqtt_on_connect(client, userdata, flags, reason_code, properties) -> None:
    if reason_code == 0:
        log("Connected successfully to the broker.")
    else:
        log(f"Failed to connect, return code {reason_code}")
        sys.exit(1)


def mqtt_connect(host: str, port: int) -> mqtt.Client:
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"lightbrary-room-{ROOM_ID}",
    )
    client.on_connect = mqtt_on_connect
    client.connect(host, port, 60)
    client.loop_start()
    return client


def init_motion(pin: int) -> MotionSensor:
    pir = MotionSensor(pin)
    return pir


def init_touch(pin: int) -> Button:
    touch = Button(pin, pull_up=None, active_state=True)
    return touch


if __name__ == "__main__":
    mqtt_client = mqtt_connect(MQTT_HOST, MQTT_PORT)
    log("Connected to MQTT broker.")

    pir_sensor = init_motion(PIR_PIN)
    touch_sensor = init_touch(TOUCH_PIN)
    log("Sensors initialised.")

    sleep(randint(1, MQTT_INTERVAL))
    while True:
        if pir_sensor.motion_detected or touch_sensor.is_pressed:
            status = "Occupied"
        else:
            status = "Available"
        timestamp = datetime.now().timestamp()

        result = mqtt_client.publish(
            MQTT_TOPIC,
            json.dumps({"status": status, "timestamp": int(timestamp)}),
            qos=1,
        )
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            log(f"Published status '{status}'")
            sleep(MQTT_INTERVAL)
        else:
            log(
                f"Failed to publish status '{status}', error code: {result.rc}. Retrying..."
            )
            sleep(MQTT_RETRY_INTERVAL)
