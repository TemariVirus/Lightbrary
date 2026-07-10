#!/usr/bin/env python3
"""Lightbrary Server Pi: MQTT status collector and Flask dashboard."""

import csv
import json
import logging
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt
from flask import Flask, jsonify, render_template, request


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("LIGHTBRARY_DATA_DIR", BASE_DIR / "data"))
MQTT_HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
OFFLINE_AFTER_SECONDS = 60
TOPIC_PATTERN = re.compile(r"^rooms/([^/]+)/status$")
VALID_STATUSES = {"Available", "Occupied"}

app = Flask(__name__)
# TODO: open the file with an exclusive lock and keep it open for the processes lifetime.
# Only use this lock for coordinating within this process
lock = threading.RLock()
# room -> {status, last_seen, changed_at}
rooms: dict[str, dict[str, Any]] = {}


def log_path(timestamp: int) -> Path:
    """Return the daily, append-only log path for a Unix timestamp."""
    return DATA_DIR / f"status-{datetime.fromtimestamp(timestamp).date().isoformat()}.csv"


def ensure_log_file(path: Path) -> None:
    """Create a new log with its header exactly once (exclusive creation)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # x is Python's exclusive-create flag: existing logs are never replaced.
        with path.open("x", newline="", encoding="utf-8") as file:
            csv.writer(file).writerow(["room", "time", "status"])
    except FileExistsError:
        pass


def append_change(room: str, timestamp: int, status: str) -> None:
    """Append, never rewrite, one status change to that day's CSV file."""
    path = log_path(timestamp)
    ensure_log_file(path)
    with path.open("a", newline="", encoding="utf-8") as file:
        csv.writer(file).writerow([room, timestamp, status])


def load_history() -> None:
    """Restore the most recent known status per room without editing old logs."""
    if not DATA_DIR.exists():
        return
    with lock:
        for path in sorted(DATA_DIR.glob("status-*.csv")):
            with path.open(newline="", encoding="utf-8") as file:
                for row in csv.DictReader(file):
                    try:
                        timestamp = int(row["time"])
                    except (KeyError, TypeError, ValueError):
                        logging.warning("Skipping malformed row in %s: %s", path, row)
                        continue
                    room = row.get("room", "")
                    status = row.get("status", "")
                    if room and timestamp >= rooms.get(room, {}).get("changed_at", -1):
                        rooms[room] = {
                            "status": status,
                            "last_seen": timestamp,
                            "changed_at": timestamp,
                        }


def record_status(room: str, status: str, timestamp: int | None = None) -> None:
    """Accept a device update and persist it only when the visible status changed."""
    timestamp = timestamp or int(time.time())
    with lock:
        previous = rooms.get(room)
        if previous is None or previous["status"] != status:
            append_change(room, timestamp, status)
            changed_at = timestamp
        else:
            changed_at = previous["changed_at"]
        rooms[room] = {"status": status, "last_seen": timestamp, "changed_at": changed_at}


def refresh_offline_rooms(now: int | None = None) -> None:
    """Record one Offline transition after a device has been silent for 60 seconds."""
    now = now or int(time.time())
    with lock:
        for room, state in list(rooms.items()):
            if state["status"] != "Offline" and now - state["last_seen"] > OFFLINE_AFTER_SECONDS:
                append_change(room, now, "Offline")
                rooms[room] = {"status": "Offline", "last_seen": state["last_seen"], "changed_at": now}


def room_snapshot() -> list[dict[str, Any]]:
    refresh_offline_rooms()
    with lock:
        return [
            {"room": room, "status": state["status"], "time": state["changed_at"]}
            for room, state in sorted(rooms.items())
        ]


def changes_since(timestamp: int) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    if not DATA_DIR.exists():
        return changes
    for path in sorted(DATA_DIR.glob("status-*.csv")):
        with path.open(newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                try:
                    if int(row["time"]) > timestamp:
                        changes.append({"room": row["room"], "time": int(row["time"]), "status": row["status"]})
                except (KeyError, TypeError, ValueError):
                    continue
    return sorted(changes, key=lambda change: change["time"])


@app.get("/dashboard")
def dashboard():
    return render_template("dashboard.html", rooms=room_snapshot(), changes=changes_since(0))


@app.get("/api/status")
def api_status():
    """Return append-only changes after ?timestamp=Unix-seconds and current state."""
    raw_timestamp = request.args.get("timestamp", "0")
    try:
        timestamp = int(raw_timestamp)
    except ValueError:
        return jsonify({"error": "timestamp must be a Unix timestamp in seconds"}), 400
    refresh_offline_rooms()
    return jsonify({"timestamp": int(time.time()), "changes": changes_since(timestamp), "rooms": room_snapshot()})


def on_connect(client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any = None) -> None:
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
        if status not in VALID_STATUSES or isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
            raise ValueError("invalid status")
        record_status(match.group(1), status, int(timestamp))
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, ValueError) as error:
        logging.warning("Ignoring invalid MQTT message on %s: %s", message.topic, error)


def start_mqtt() -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="lightbrary-dashboard")
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()
    return client


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    load_history()
    start_mqtt()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "80")))
