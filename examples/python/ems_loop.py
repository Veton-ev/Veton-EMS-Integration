#!/usr/bin/env python3
"""Minimal, SAFE EMS control loop for a Veton/CHARX charging point.

Demonstrates the recommended pattern:
  1. arm the watchdog (safe fallback if this process dies)
  2. every cycle: read state, decide a target current, write X301, verify, pet watchdog

The demo policy here is a placeholder: it caps at --max while a car is charging
and backs off to 6 A otherwise. Replace decide_target() with your real EMS logic
(surplus PV, dynamic tariff, site-load headroom, ...).

    python ems_loop.py 192.168.0.50 --connector 1 --max 16

Stop with Ctrl-C; the watchdog stays armed so the charger stays safe.
"""

from __future__ import annotations

import argparse
import time

from charx import Charx

WATCHDOG_FALLBACK_A = 6     # X306: current applied if the loop stops
WATCHDOG_TIMEOUT_S = 30     # X307: must pet within this window
CYCLE_S = 5                 # loop period (must be << WATCHDOG_TIMEOUT_S)
# States where the vehicle wants current: C2/D2 draw it, C1/D1 are paused by
# the EVSE (no current flows) but the car is ready to resume.
WANTS_CURRENT_STATES = {"C1", "C2", "D1", "D2"}


def decide_target(state, max_a: int) -> int:
    """Placeholder EMS policy — replace with your own.

    Return the desired charging current in A (6..80), or 6 to back off.
    """
    if state.vehicle_status in WANTS_CURRENT_STATES or state.vehicle_status == "B2":
        return max_a
    return WATCHDOG_FALLBACK_A


def main():
    ap = argparse.ArgumentParser(description="Demo EMS control loop (Modbus)")
    ap.add_argument("host")
    ap.add_argument("--connector", type=int, default=1)
    ap.add_argument("--port", type=int, default=502)
    ap.add_argument("--max", type=int, default=16, help="max current the EMS will set [A]")
    args = ap.parse_args()

    with Charx(args.host, connector=args.connector, port=args.port) as c:
        s = c.read_state()
        print(f"Release mode: {s.release_mode} (X120={s.release_mode_code})")
        # Modbus release mode is NOT expected (or wanted) here: on Veton
        # chargers charging release stays with OCPP — the backend decides
        # WHETHER a car may charge, this loop only decides HOW FAST via the
        # X301 cap, which works in every release mode. That is the
        # recommended setup.
        if s.release_mode_code != 5:
            print("  release stays with the charger's backend (OCPP on Veton chargers) —")
            print("  recommended. This loop only caps the current via X301.")

        # 1) Safety net first.
        c.arm_watchdog(fallback_a=WATCHDOG_FALLBACK_A, timeout_s=WATCHDOG_TIMEOUT_S)
        print(f"Watchdog armed: fallback {WATCHDOG_FALLBACK_A} A, timeout {WATCHDOG_TIMEOUT_S} s")

        try:
            while True:
                # A transient Modbus/network error skips one cycle instead of
                # killing the loop — safe, because the armed watchdog covers
                # the gap: if we stay silent, the charger falls back to 6 A.
                try:
                    s = c.read_state()
                    target = decide_target(s, args.max)
                    applied = c.set_max_current(target)          # writes X301 + verifies
                    c.pet_watchdog(WATCHDOG_TIMEOUT_S)           # keep the watchdog alive
                    flag = "" if applied == max(6, min(80, target)) else "  <-- did not stick!"
                    print(f"[{time.strftime('%H:%M:%S')}] {s.vehicle_status:>2}  "
                          f"{s.active_power_w:6.0f} W  target={target}A  X301={applied}A{flag}")
                except (IOError, OSError) as e:
                    print(f"[{time.strftime('%H:%M:%S')}] cycle skipped ({e}) — "
                          f"watchdog covers the gap")
                    time.sleep(CYCLE_S)
                    continue
                time.sleep(CYCLE_S)
        except KeyboardInterrupt:
            print("\nstopped — watchdog left armed (charger stays safe).")


if __name__ == "__main__":
    main()
