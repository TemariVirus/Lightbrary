"""Lightbrary Server Pi: MQTT status collector and Flask dashboard."""

import csv
import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt
from flask import Flask, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("LIGHTBRARY_DATA_DIR", BASE_DIR / "data"))
MQTT_HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
OFFLINE_AFTER_SECONDS = 10
OFFLINE_CHECK_INTERVAL = 1  # Seconds
TOPIC_PATTERN = re.compile(r"^rooms/([^/]+)/status$")
VALID_STATUSES = {"Available", "Occupied"}
HTTP_PORT = int(os.environ.get("PORT", "80"))

app = Flask(__name__)
lock = threading.RLock()
# room -> {status, last_seen, changed_at}
rooms: dict[str, dict[str, Any]] = {}
# sorted in ascending order by time {room, time, status}
rows: list[dict[str, Any]] = []


def log_path() -> Path:
    return DATA_DIR / "status.csv"


def ensure_log_file(path: Path) -> None:
    """Create a new log with its header exactly once (exclusive creation)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with lock:
            # x is Python's exclusive-create flag: existing logs are never replaced.
            with path.open("x", newline="", encoding="utf-8") as file:
                csv.writer(file).writerow(["room", "time", "status"])
    except FileExistsError:
        pass


def get_row_index(timestamp: int) -> int:
    """Returns the index of the first row that has a timestamp larger than the
    provided timestamp, or `len(rows)` if no such row exists."""
    left = 0
    right = len(rows)
    while left < right:
        mid = (left + right) // 2
        if rows[mid]["time"] < timestamp:
            left = mid + 1
        else:
            right = mid
    while left < len(rows) and rows[left]["time"] == timestamp:
        left += 1
    return left


def append_change(room: str, timestamp: int, status: str) -> None:
    """Append, never rewrite, one status change to that day's CSV file."""
    path = log_path()
    ensure_log_file(path)
    with lock:
        index = get_row_index(timestamp)
        # Reject duplicates
        i = min(index, len(rows) - 1)
        while i >= 0 and rows[i]["time"] == timestamp:
            if rows[i]["room"] == room:
                return
            i -= 1

        rows.insert(index, {"room": room, "time": timestamp, "status": status})
        with path.open("a", newline="", encoding="utf-8") as file:
            csv.writer(file).writerow([room, timestamp, status])


def load_history() -> None:
    """Restore the most recent known status per room without editing old logs."""
    path = log_path()
    if not path.exists():
        return
    with lock:
        with path.open(newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                try:
                    timestamp = int(row["time"])
                except (KeyError, TypeError, ValueError):
                    logging.warning("Skipping malformed row in %s: %s", path, row)
                    continue
                room = row.get("room", "")
                status = row.get("status", "")
                rows.append({"room": room, "time": timestamp, "status": status})
                if room and timestamp >= rooms.get(room, {}).get("changed_at", -1):
                    rooms[room] = {
                        "status": status,
                        "last_seen": timestamp,
                        "changed_at": timestamp,
                    }
        rows.sort(key=lambda r: r["time"])


def record_status(room: str, status: str, timestamp: int) -> None:
    """Accept a device update and persist it only when the visible status changed."""
    with lock:
        previous = rooms.get(room)
        if previous is None or (
            previous["status"] != status and previous["last_seen"] <= timestamp
        ):
            append_change(room, timestamp, status)
            changed_at = timestamp
        else:
            changed_at = previous["changed_at"]
        rooms[room] = {
            "status": status,
            "last_seen": timestamp,
            "changed_at": changed_at,
        }


def refresh_offline_rooms() -> None:
    """Record an Offline transition after a device has been silent for too long."""
    now = int(time.time())
    with lock:
        for room, state in list(rooms.items()):
            if (
                state["status"] != "Offline"
                and now - state["last_seen"] > OFFLINE_AFTER_SECONDS
            ):
                append_change(
                    room, state["last_seen"] + OFFLINE_AFTER_SECONDS, "Offline"
                )
                rooms[room] = {
                    "status": "Offline",
                    "last_seen": state["last_seen"],
                    "changed_at": now,
                }


def check_offline_thread() -> None:
    while True:
        refresh_offline_rooms()
        time.sleep(1)


def room_snapshot() -> list[dict[str, Any]]:
    with lock:
        return [
            {"room": room, "status": state["status"]}
            for room, state in sorted(rooms.items())
        ]


def changes_since(timestamp: int) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    with lock:
        start = get_row_index(timestamp)
        assert start is not None
        while start > 0 and rows[start - 1]["time"] == timestamp:
            start -= 1
        for row in rows[start:]:
            changes.append(row.copy())
    return changes


@app.get("/")
def dashboard():
    return render_template(
        "dashboard.html", rooms=room_snapshot(), changes=changes_since(-1)
    )


@app.get("/api/status")
def api_status():
    """Return append-only changes after ?timestamp=Unix-seconds and current state."""
    raw_timestamp = request.args.get("timestamp", "0")
    try:
        timestamp = int(raw_timestamp)
    except ValueError:
        return jsonify({"error": "timestamp must be a Unix timestamp in seconds"}), 400
    return jsonify(
        {
            "changes": changes_since(timestamp),
            "rooms": room_snapshot(),
            "timestamp": int(time.time()),
        }
    )


def on_connect(
    client: mqtt.Client,
    userdata: Any,
    flags: Any,
    reason_code: Any,
    properties: Any = None,
) -> None:
    if reason_code == 0:
        client.subscribe("rooms/+/status")
        logging.info("Subscribed to room status updates")
    else:
        logging.error("MQTT connection failed: %s", reason_code)


def on_message(client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
    match = TOPIC_PATTERN.fullmatch(message.topic)
    if not match:
        logging.fatal("Invalid topic: %s", message.topic)
        return
    try:
        payload = json.loads(message.payload.decode("utf-8"))
        status = payload["status"]
        timestamp = payload["timestamp"]
        if (
            status not in VALID_STATUSES
            or isinstance(timestamp, bool)
            or not isinstance(timestamp, (int, float))
        ):
            raise ValueError("invalid status")
        record_status(match.group(1), status, int(time.time()))
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, ValueError) as error:
        logging.warning("Ignoring invalid MQTT message on %s: %s", message.topic, error)


def start_mqtt() -> mqtt.Client:
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2, client_id="lightbrary-dashboard"
    )
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()
    return client


# Run at import time so history is restored whether Flask is started via
# `python main.py`, gunicorn, or the debug reloader's child process.
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
load_history()
start_mqtt()

if __name__ == "__main__":
    thread = threading.Thread(target=check_offline_thread)
    thread.start()
    app.run(host="0.0.0.0", port=HTTP_PORT)
