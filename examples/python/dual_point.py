#!/usr/bin/env python3
"""Split one current budget across a DOUBLE charging point (two sockets).

A multi-socket Veton charger is internally several CHARX charging
controllers: one is the server ("master"), the others are clients ("slaves")
attached to it. For the EMS the key fact is:

    There is only ONE Modbus server — the master's IP, port 502 — and it
    serves ALL charging points: charging point n lives at register block
    n * 1000 (a master can serve up to 48). You never connect to a slave
    directly.

Authorization / start / stop is OCPP's job (Veton chargers ship with release
mode = OCPP) — this loop only divides the available current between the
sockets via each point's X301 cap. No X300 anywhere.

    python dual_point.py 192.168.0.50 --budget 32

--budget is the TOTAL current [A] available for the whole charger, i.e. what
the shared supply feed can carry across both sockets. Stop with Ctrl-C; the
watchdogs stay armed so the charger stays safe.
"""

from __future__ import annotations

import argparse
import time

from charx import Charx

WATCHDOG_FALLBACK_A = 6     # X306: current applied if this loop stops
WATCHDOG_TIMEOUT_S = 30     # X307: must pet within this window
CYCLE_S = 5                 # loop period (must be << WATCHDOG_TIMEOUT_S).
                            # Per-CP Modbus round-trips add up: with many
                            # charging points, keep the full cycle (reads +
                            # writes for every CP) comfortably below the
                            # watchdog window.
MIN_A = 6                   # IEC 61851 minimum — we never go below, never 0


def has_car(vehicle_status: str) -> bool:
    """A socket 'has a car' in IEC 61851 states B/C/D (connected or charging)."""
    return vehicle_status[:1] in ("B", "C", "D")


def main():
    ap = argparse.ArgumentParser(
        description="Split one current budget across a double charging point")
    ap.add_argument("host", help="the MASTER's IP address (the only Modbus server)")
    ap.add_argument("--budget", type=int, default=32,
                    help="total A available for the whole charger, both sockets (default 32)")
    ap.add_argument("--port", type=int, default=502)
    args = ap.parse_args()

    # ── 1) Connect ONCE, to the master ──────────────────────────────────
    # Its Modbus server serves every socket; master register 114 tells us
    # how many charging points there are (a double charger reports 2).
    with Charx(args.host, port=args.port) as master:
        n = master.num_charging_points()
        if not 1 <= n <= 48:  # a master serves at most 48 points
            raise SystemExit(f"implausible charging-point count from register 114: {n}")
        print(f"Charger reports {n} charging point(s) (master register 114)")

        # One 'view' per socket, all sharing the master's single TCP
        # connection (the CHARX server serialises requests and accepts few
        # concurrent clients — one connection is all you need).
        # Socket n's registers live at n*1000 + offset.
        points = [master.point(i) for i in range(1, n + 1)]

        # Print each point's identity and state so you can tell them apart.
        for i, cp in enumerate(points, start=1):
            s = cp.read_state()
            print(f"  CP{i}: uid={cp.read_uid()}  state={s.vehicle_status}  "
                  f"configured max (X101)={s.max_current_setting_a} A")

        # ── 2) Arm the watchdog PER charging point ──────────────────────
        # Each socket has its own watchdog at its own offset
        # (1306/1307, 2306/2307, ...). If this loop dies, BOTH sockets
        # fall back to a safe 6 A instead of holding our last split.
        for cp in points:
            cp.arm_watchdog(fallback_a=WATCHDOG_FALLBACK_A,
                            timeout_s=WATCHDOG_TIMEOUT_S)
        print(f"Watchdogs armed on all {n} point(s): "
              f"fallback {WATCHDOG_FALLBACK_A} A, timeout {WATCHDOG_TIMEOUT_S} s")

        # ── 3) The loop: read states, split the budget, write the caps ──
        try:
            while True:
                # A transient Modbus/network error skips one cycle instead of
                # killing the loop — safe, because the armed watchdogs cover
                # the gap: if we stay silent, the charger falls back to 6 A.
                try:
                    states = [cp.read_state() for cp in points]
                    occupied = [has_car(s.vehicle_status) for s in states]
                    active = sum(occupied)

                    for i, (cp, s, car) in enumerate(zip(points, states, occupied), 1):
                        # Budget split: one active car gets the whole budget,
                        # two share it half/half. A real EMS can be smarter here
                        # (priority sockets, first-come-first-served, rotation,
                        # PV surplus, ...) — this just shows the mechanics.
                        if car:
                            share = args.budget // active
                        else:
                            # A parked no-car socket doesn't need 0 — and we
                            # never write 0 (a zero X301 withdraws charging
                            # release; see docs). 6 A is a harmless floor.
                            share = MIN_A

                        # Clamp to [6, min(share, configured max X101)].
                        # (Note: the 6 A floor means the sum can exceed --budget
                        # if budget < 6 * active — size your budget accordingly.)
                        target = max(MIN_A, min(share, s.max_current_setting_a))

                        # ── 4) Write X301 (verified) + pet THIS point's watchdog
                        applied = cp.set_max_current(target)   # re-issues if it didn't stick
                        cp.pet_watchdog(WATCHDOG_TIMEOUT_S)

                        flag = "" if applied == target else "  <-- did not stick!"
                        print(f"[{time.strftime('%H:%M:%S')}] CP{i} "
                              f"{s.vehicle_status:>2}  {s.active_power_w:6.0f} W  "
                              f"target={target}A  X301={applied}A{flag}")
                except (IOError, OSError) as e:
                    print(f"[{time.strftime('%H:%M:%S')}] cycle skipped ({e}) — "
                          f"watchdogs cover the gap")
                    time.sleep(CYCLE_S)
                    continue

                time.sleep(CYCLE_S)
        except KeyboardInterrupt:
            print("\nstopped — watchdogs left armed (charger stays safe).")


if __name__ == "__main__":
    main()
