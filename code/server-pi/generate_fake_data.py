"""Generate realistic fake data for Lightbrary server-pi (status.csv & optional live updates)."""

import argparse
import csv
import json
import random
import time
from pathlib import Path

try:
    import paho.mqtt.client as mqtt
    HAS_MQTT = True
except ImportError:
    HAS_MQTT = False

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_FILE = DATA_DIR / "status.csv"

DEFAULT_ROOMS = [
    "Room 101",
    "Room 102",
    "Room 103",
    "Room 201",
    "Room 202",
    "Silent Pod A",
    "Silent Pod B",
    "Media Lab",
]


def generate_history(rooms: list[str], days: int = 7) -> list[tuple[str, int, str]]:
    """Generate historical room transitions over the past `days` days up to current timestamp."""
    now = int(time.time())
    start_time = now - (days * 86400)
    records: list[tuple[str, int, str]] = []

    for room in rooms:
        # Give each room a starting record near start_time
        current_time = start_time + random.randint(0, 1800)
        current_status = random.choice(["Available", "Occupied"])
        records.append((room, current_time, current_status))

        while current_time < now:
            # Simulate realistic library room occupancy intervals
            local_hour = time.localtime(current_time).tm_hour

            # Busy library hours: 8 AM to 10 PM
            if 8 <= local_hour < 22:
                # 15 mins to 2.5 hours duration
                duration = random.randint(900, 9000)
            else:
                # Night/off-peak hours: longer idle periods (2 to 6 hours)
                duration = random.randint(7200, 21600)

            current_time += duration
            if current_time >= now:
                break

            # State transitions
            if current_status == "Occupied":
                current_status = "Available"
            elif current_status == "Available":
                # Small chance of sensor going offline temporarily
                if random.random() < 0.04:
                    current_status = "Offline"
                else:
                    current_status = "Occupied"
            else:  # Offline
                current_status = "Available"

            records.append((room, current_time, current_status))

    # Sort all records by timestamp ascending
    records.sort(key=lambda r: r[1])
    return records


def write_history_csv(records: list[tuple[str, int, str]]) -> None:
    """Write records to data/status.csv."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["room", "time", "status"])
        for room, timestamp, status in records:
            writer.writerow([room, timestamp, status])
    print(f"✅ Created {LOG_FILE} with {len(records)} historical events across 7 days.")


def run_live_simulation(rooms: list[str], mqtt_host: str = "127.0.0.1", mqtt_port: int = 1883, interval: float = 3.0):
    """Continuously publish simulated room status updates via MQTT or append to CSV."""
    print(f"🚀 Starting live room simulator (updating random room every {interval}s)...")

    client = None
    mqtt_connected = False

    if HAS_MQTT:
        try:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="lightbrary-simulator")
            client.connect(mqtt_host, mqtt_port, keepalive=60)
            client.loop_start()
            mqtt_connected = True
            print(f"📡 Connected to MQTT broker at {mqtt_host}:{mqtt_port}")
        except Exception as e:
            print(f"⚠️ Could not connect to MQTT broker ({e}). Will append directly to CSV instead.")

    # Maintain current status per room
    current_states = {room: random.choice(["Available", "Occupied"]) for room in rooms}

    try:
        while True:
            room = random.choice(rooms)
            # Toggle status
            new_status = "Occupied" if current_states[room] == "Available" else "Available"
            current_states[room] = new_status
            now = int(time.time())

            if mqtt_connected and client:
                topic = f"rooms/{room}/status"
                payload = json.dumps({"status": new_status, "timestamp": now})
                client.publish(topic, payload)
                print(f"📡 Published to {topic}: {new_status}")
            else:
                # Direct append to status.csv
                with LOG_FILE.open("a", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow([room, now, new_status])
                print(f"📝 Appended event: {room} -> {new_status} at {now}")

            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopping simulator.")
        if client:
            client.loop_stop()
            client.disconnect()


def main():
    parser = argparse.ArgumentParser(description="Generate fake data for server-pi")
    parser.add_argument("--days", type=int, default=7, help="Number of past days for history generation (default: 7)")
    parser.add_argument("--live", action="store_true", help="Start continuous live simulation after seeding history")
    parser.add_argument("--interval", type=float, default=3.0, help="Live simulation interval in seconds (default: 3.0)")
    parser.add_argument("--mqtt-host", type=str, default="127.0.0.1", help="MQTT broker host")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker port")
    args = parser.parse_args()

    # 1. Generate & write historical CSV
    records = generate_history(DEFAULT_ROOMS, days=args.days)
    write_history_csv(records)

    # 2. Run live simulation if requested
    if args.live:
        run_live_simulation(DEFAULT_ROOMS, mqtt_host=args.mqtt_host, mqtt_port=args.mqtt_port, interval=args.interval)


if __name__ == "__main__":
    main()
