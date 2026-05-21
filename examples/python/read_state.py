#!/usr/bin/env python3
"""Print the live state of one Veton/CHARX charging point over Modbus.

    python read_state.py 192.168.0.50 --connector 1
"""

from __future__ import annotations

import argparse

from charx import Charx


def main():
    ap = argparse.ArgumentParser(description="Read Veton/CHARX state over Modbus TCP")
    ap.add_argument("host", help="charger IP address")
    ap.add_argument("--connector", type=int, default=1, help="charging point number (default 1)")
    ap.add_argument("--port", type=int, default=502)
    args = ap.parse_args()

    with Charx(args.host, connector=args.connector, port=args.port) as c:
        s = c.read_state()
        print(f"Vehicle status     : {s.vehicle_status}")
        print(f"Release mode       : {s.release_mode}")
        print(f"Max current (cfg)  : {s.max_current_setting_a} A")
        print(f"Max current (X301) : {c.read_max_current()} A")
        print(f"Present current    : {s.present_current_a} A")
        print(f"Active power       : {s.active_power_w:.0f} W")
        print(f"Voltage L1/L2/L3   : {s.voltage_v} V")
        print(f"Current L1/L2/L3   : {s.current_a} A")
        print(f"Total energy       : {s.total_energy_wh/1000:.3f} kWh")


if __name__ == "__main__":
    main()
