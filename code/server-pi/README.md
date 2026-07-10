# Server Pi

This service subscribes to `rooms/+/status`, stores only status transitions in
daily CSV files, and serves the dashboard.

## Run

This project requires **Python 3.10** or newer. It is recommended to use a virtual environment:

```sh
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

To run the server locally, use an unprivileged port like 3000:

```sh
PORT=3000 python3 main.py
```

The server listens on port 80 by default. Set `PORT=3000` for an unprivileged
local test (macOS may use 5000 for AirPlay). Set `MQTT_HOST`, `MQTT_PORT`, or `LIGHTBRARY_DATA_DIR` when needed.

## Routes

- `http://dashboard.lightbrary/dashboard` shows the current state of every room.
- `/api/status?timestamp=1710000000` returns each CSV change after the supplied
  Unix timestamp and a current room snapshot. A client uses the returned
  `timestamp` for its next poll.

Each file in `data/` is named `status-YYYY-MM-DD.csv` and has exactly these
columns: `room,time,status`. New daily files are made with Python's exclusive
`x` creation mode; entries are subsequently appended, never rewritten.

## Pi services

Run Mosquitto as the local MQTT broker (port 1883), and configure your DNS
server (for example dnsmasq) with:

```conf
address=/dashboard.lightbrary/<SERVER_PI_IP>
```

The Flask service connects to that local broker by default.
