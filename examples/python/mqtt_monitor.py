#!/usr/bin/env python3
"""Subscribe to a CHARX master's local MQTT broker and print per-CP data.

    python mqtt_monitor.py 192.168.0.50

Reads (push, ~5 s) per charging point:
  - charging_controllers/<uid>/data/energy        (JSON: u1..u3, i1..i3, real_power, energy_real_power)
  - charging_controllers/<uid>/data/iec_61851_state (A1/B2/C2/...)

MQTT is READ-ONLY for control here: publishing to control/* does not steer the
charger (use Modbus). FW >= 1.8 closes port 1883 by default.
"""

from __future__ import annotations

import argparse
import json

import paho.mqtt.client as mqtt


def on_connect(client, userdata, flags, reason_code, properties=None):
    print(f"connected ({reason_code}); subscribing…")
    client.subscribe("charging_controllers/+/data/energy")
    client.subscribe("charging_controllers/+/data/iec_61851_state")
    # master-slave topologies also republish under device-network/<id>/...
    client.subscribe("device-network/+/charging_controllers/+/data/energy")


def on_message(client, userdata, msg):
    parts = msg.topic.split("/")
    uid = parts[parts.index("charging_controllers") + 1]
    leaf = parts[-1]
    payload = msg.payload.decode("utf-8", "replace").strip()
    if leaf == "iec_61851_state":
        print(f"{uid}  state={payload}")
    elif leaf == "energy":
        try:
            d = json.loads(payload)
            print(f"{uid}  P={d.get('real_power',0):.0f} W  "
                  f"E={d.get('energy_real_power',0)/1000:.3f} kWh  "
                  f"U=({d.get('u1')},{d.get('u2')},{d.get('u3')}) V  "
                  f"I=({d.get('i1')},{d.get('i2')},{d.get('i3')}) A")
        except json.JSONDecodeError:
            print(f"{uid}  energy (raw): {payload[:120]}")


def main():
    ap = argparse.ArgumentParser(description="CHARX local MQTT monitor")
    ap.add_argument("host", help="charger IP (master broker)")
    ap.add_argument("--port", type=int, default=1883)
    args = ap.parse_args()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.host, args.port, keepalive=60)
    print("Ctrl-C to stop")
    client.loop_forever()


if __name__ == "__main__":
    main()
