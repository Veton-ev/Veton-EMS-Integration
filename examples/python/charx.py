"""Minimal, dependency-light Modbus client for Veton / Phoenix Contact CHARX.

Reusable core for the examples in this folder. Requires pymodbus >= 3.7
(``pip install -r requirements.txt``).

Per-charging-point registers are offset by ``connector * 1000``.
32-bit values are 2 registers (MSW first); 64-bit are 4 registers (MSW first).
Currents/voltages/power are in milli-units.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from pymodbus.client import ModbusTcpClient

DEFAULT_PORT = 502
DEFAULT_UNIT = 1  # Modbus server address / slave / device_id

RELEASE_MODES = {
    0: "Dashboard", 1: "Whitelist", 2: "External",
    3: "Permanent", 4: "OCPP", 5: "Modbus",
}


# ── decoding helpers ────────────────────────────────────────────────
def i32(regs):  return struct.unpack(">i", struct.pack(">HH", *regs))[0]
def u32(regs):  return struct.unpack(">I", struct.pack(">HH", *regs))[0]
def i64(regs):  return struct.unpack(">q", struct.pack(">HHHH", *regs))[0]
def ascii_(regs):
    raw = b"".join(struct.pack(">H", r) for r in regs)
    return raw.decode("ascii", "replace").rstrip("\x00").strip()


@dataclass
class ChargerState:
    vehicle_status: str          # IEC 61851: A1/B2/C2/...
    release_mode: str            # human-readable
    release_mode_code: int       # X120
    max_current_setting_a: int   # X101 (configured cap)
    present_current_a: int       # X297
    active_power_w: float        # X244 (mW -> W)
    voltage_v: tuple             # (L1, L2, L3) from X232/234/236
    current_a: tuple             # (L1, L2, L3) from X238/240/242
    total_energy_wh: int         # X250


class Charx:
    """Synchronous Modbus client for one CHARX charging point."""

    def __init__(self, host, connector=1, port=DEFAULT_PORT, unit=DEFAULT_UNIT):
        self.base = connector * 1000
        self.unit = unit
        self._c = ModbusTcpClient(host, port=port)

    def __enter__(self):
        if not self._c.connect():
            raise ConnectionError("could not connect to CHARX Modbus server")
        return self

    def __exit__(self, *exc):
        self._c.close()

    # ``device_id`` is the pymodbus >= 3.7 name; older 3.x used ``slave=``.
    def _read(self, addr, count):
        rr = self._c.read_holding_registers(addr, count=count, device_id=self.unit)
        if rr.isError():
            raise IOError(f"read {addr}+{count} failed: {rr}")
        return rr.registers

    def _write(self, addr, value):
        rr = self._c.write_register(addr, int(value), device_id=self.unit)
        if rr.isError():
            raise IOError(f"write {addr}={value} failed: {rr}")

    # ── reads ────────────────────────────────────────────────────────
    def read_state(self) -> ChargerState:
        b = self.base
        rm = self._read(b + 120, 1)[0]
        volts = self._read(b + 232, 6)   # X232/234/236, 2 words each
        amps = self._read(b + 238, 6)    # X238/240/242
        return ChargerState(
            vehicle_status=ascii_(self._read(b + 299, 1)),
            release_mode=RELEASE_MODES.get(rm, f"? ({rm})"),
            release_mode_code=rm,
            max_current_setting_a=self._read(b + 101, 1)[0],
            present_current_a=self._read(b + 297, 1)[0],
            active_power_w=i32(self._read(b + 244, 2)) / 1000,
            voltage_v=tuple(round(i32(volts[i:i+2]) / 1000, 1) for i in (0, 2, 4)),
            current_a=tuple(round(i32(amps[i:i+2]) / 1000, 2) for i in (0, 2, 4)),
            total_energy_wh=i64(self._read(b + 250, 4)),
        )

    def read_max_current(self) -> int:
        return self._read(self.base + 301, 1)[0]

    # ── writes ───────────────────────────────────────────────────────
    def set_max_current(self, amps: int, verify: bool = True) -> int:
        """Write X301 (clamped 6-80). Returns the read-back value.

        Some firmware resets an externally-written X301 to 0 (the 'float-bug');
        with verify=True we re-issue once if the read-back doesn't match.
        """
        amps = max(6, min(80, int(amps)))
        self._write(self.base + 301, amps)
        if verify:
            back = self.read_max_current()
            if back != amps:
                self._write(self.base + 301, amps)
                back = self.read_max_current()
            return back
        return amps

    def arm_watchdog(self, fallback_a: int = 6, timeout_s: int = 30) -> None:
        """Set X306 (fallback current) + X307 (timeout). Call pet_watchdog within timeout_s."""
        self._write(self.base + 306, max(6, min(80, int(fallback_a))))
        self._write(self.base + 307, int(timeout_s))

    def pet_watchdog(self, timeout_s: int = 30) -> None:
        """Re-write X307 to keep the watchdog from expiring."""
        self._write(self.base + 307, int(timeout_s))

    def set_charge_release(self, enabled: bool) -> None:
        """Write X300. Only effective when release mode = Modbus (X120 = 5)."""
        self._write(self.base + 300, 1 if enabled else 0)

    def set_available(self, available: bool) -> None:
        """Write X304. Only effective when release mode = Modbus (X120 = 5)."""
        self._write(self.base + 304, 1 if available else 0)
