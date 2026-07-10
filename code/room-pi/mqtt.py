import paho.mqtt.client as mqtt
from log import log

client: mqtt.Client = None


def __on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        log("Connected successfully to the broker.")
    else:
        log(f"Failed to connect, return code {reason_code}")


def connect(host: str, port: int) -> mqtt.Client:
    global client

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = __on_connect
    client.connect(host, port, 60)
    client.loop_start()
    return client


def publish(topic: str, msg: str) -> bool:
    result = client.publish(topic, msg)
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        log(f"Published to topic '{topic}'")
        return True
    else:
        log(f"Failed to publish to topic '{topic}', error code: {result.rc}")
        return False
