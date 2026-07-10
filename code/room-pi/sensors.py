from gpiozero import MotionSensor

from .log import log


def on_motion():
    log("Motion detected! Event triggered.")


def on_no_motion():
    log("No motion. Event triggered.")


def init_motion(pin: int):
    pir = MotionSensor(pin)
    pir.when_motion = on_motion
    pir.when_no_motion = on_no_motion
    return pir
