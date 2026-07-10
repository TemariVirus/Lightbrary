import json
from time import time

import mqtt
from gpiozero import Button, MotionSensor
from log import log

ROOM_ID = 1
MQTT_TOPIC = f"rooms/{ROOM_ID}/status"

# TODO: combine motion and touch inputs
# TODO: create 30s timer


def on_motion():
    log("Motion detected! Event triggered.")
    mqtt.publish(MQTT_TOPIC, json.dumps({"status": "Occupied", "timestamp": time()}))


def on_no_motion():
    log("No motion. Event triggered.")
    mqtt.publish(MQTT_TOPIC, json.dumps({"status": "Available", "timestamp": time()}))


def on_touch():
    log("Touch detected! Event triggered.")
    mqtt.publish(MQTT_TOPIC, json.dumps({"status": "Occupied", "timestamp": time()}))


def on_no_touch():
    log("No touch. Event triggered.")
    mqtt.publish(MQTT_TOPIC, json.dumps({"status": "Available", "timestamp": time()}))


def init_motion(pin: int):
    pir = MotionSensor(pin)
    pir.when_motion = on_motion
    pir.when_no_motion = on_no_motion
    return pir


def init_touch(pin: int):
    touch = Button(pin, pull_up=None, active_state=True)
    touch.when_pressed = on_touch
    touch.when_released = on_no_touch
    return touch
