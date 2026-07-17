# Modbus TCP

The CHARX controller exposes a Modbus/TCP server. This is the **primary**
interface for an EMS — always available on Veton-provisioned chargers: read
metering and status, set the charging current, and arm the safety watchdog.
(Charging *release* stays with OCPP on Veton chargers — see below.)

> **Port availability:** on factory firmware ≥ 1.8 the charger's firewall
> allows only `:80`/`:443` until it is provisioned. Veton-provisioned chargers
> have `:502` (and typically `:1883`/`:5555`) open.

```
Host:           charger IP
Port:           502
Unit / slave:   1
Object type:    holding registers, 16-bit (FC03 read, FC06/FC16 write)
                FC04 (input registers) returns the same values as FC03.
```

## Addressing: one charger, many charging points

A CHARX master can host several charging points (controllers) — up to 48,
including those on attached client ("slave") controllers. **There is only one
Modbus server: the master's, on `:502`** — you never connect to a slave
directly. Registers are laid out in 1000-register blocks:

```
addresses 0   – 999   →  whole-installation / master data
addresses x000– x999  →  per-charging-point data, where x = charging-point number
```

So the **per-CP register `Xnnn` lives at address `connector * 1000 + nnn`.**
Charging point 1 → `1nnn`, point 2 → `2nnn`, etc. All per-CP registers below
are written `Xnnn`.

## Data encoding

- **16-bit** values: a single register.
- **32-bit** values (V, I, power): **2 registers, most-significant word first**, big-endian.
- **64-bit** values (energy counters): **4 registers, most-significant word first**, big-endian.
- **ASCII** values (UIDs, vehicle status): each register holds 2 bytes; concatenate big-endian and strip trailing `\x00`.
- Currents/voltages/power are in **milli-units** (`mV`, `mA`, `mW`) — divide by 1000 for V/A/W.

```python
import struct
def i32(regs):  return struct.unpack(">i",  struct.pack(">HH",  *regs))[0]   # signed 32-bit
def u32(regs):  return struct.unpack(">I",  struct.pack(">HH",  *regs))[0]   # unsigned 32-bit
def i64(regs):  return struct.unpack(">q",  struct.pack(">HHHH", *regs))[0]  # signed 64-bit
def ascii_(regs):
    raw = b"".join(struct.pack(">H", r) for r in regs)
    return raw.decode("ascii", "replace").rstrip("\x00").strip()
```

## Per-charging-point registers (`X = connector × 1000`)

### Read — configuration
| Reg | Words | Meaning |
|----|----|----|
| `X100` | 1 | Charging case (0 = socket / type B, 1 = attached cable / type C) |
| `X101` | 1 | Configured **max** charging current [A] |
| `X102` | 1 | Configured **min** charging current [A] |
| `X112` | 1 | Energy-meter type (enum) |
| `X113` | 3 | Controller UID (ASCII) |
| `X120` | 1 | **Release mode** (0 Dashboard, 1 Whitelist, 2 External, 3 Permanent, 4 OCPP, 5 Modbus) |

### Read — live metering & status
| Reg | Words | Meaning |
|----|----|----|
| `X232 / X234 / X236` | 2 each | Voltage L1 / L2 / L3 [mV] |
| `X238 / X240 / X242` | 2 each | Current L1 / L2 / L3 [mA] |
| `X244` | 2 | Active power [mW] |
| `X246 / X248` | 2 each | Reactive [mVAR] / apparent [mVA] power |
| `X250` | 4 | Active-energy counter [Wh] |
| `X265` | 10 | Last EVCC ID (ASCII) |
| `X275` | 10 | Last RFID UID (ASCII) |
| `X285` | 2 | Time connected (B/C/D) [s] |
| `X287` | 2 | Charge duration (C/D) [s] |
| `X289` | 4 | Energy of current charging session [Wh] |
| `X293` | 2 | Error code (hex bitfield) |
| `X296` | 1 | Current PWM duty cycle [%] |
| `X297` | 1 | Charging current currently **signalled to the vehicle via PWM** [A] — the offer, not the draw; actually drawn current is `X238`/`X240`/`X242` |
| `X298` | 1 | Cable current-carrying capacity [A] |
| `X299` | 1 | **Vehicle status** (ASCII: `A1 A2 B1 B2 C1 C2 E0 F0 IN`) |

> **No D states on `X299`.** IEC 61851 also defines `D1`/`D2` (charging with
> ventilation required), but the CHARX controller does not report them on
> `X299` — vehicle-with-ventilation acceptance only exists as the `X109`
> configuration flag.

### Write — control
| Reg | Range | Meaning | Writable when |
|----|----|----|----|
| `X300` | 0/1 | **Charging release** (0 = off, 1 = allow) | release mode = **Modbus** |
| `X301` | 6–80 | **Max charging current [A]** — your main setpoint | always |
| `X303` | 0/1 | Connector locking | locking mode = external |
| `X304` | 0/1 | Availability (0 = unavailable/F, 1 = available) | release mode = **Modbus** |
| `X306` | 6–80 | **Watchdog fallback current [A]** (applied when X307 expires) | always |
| `X307` | seconds | **Watchdog timer [s]** — re-write within the interval to keep alive; `65535` = disabled | always |

> **`X301` is a cap that works in every release mode.** You can steer current
> from an EMS without changing the release mode. Note `X301 = 0` withdraws
> charging release regardless of release mode — never write 0; pause at the
> 6 A minimum instead.

> ⚠️ **On Veton chargers, don't use `X300`/`X304`.** Veton chargers ship with
> **release mode = OCPP**: the OCPP backend decides *whether* a car may charge
> (authorization, start/stop, billing, app visibility) and the EMS only decides
> *how fast* via `X301`. Driving `X300`/`X304` requires taking release away
> from OCPP, which breaks authorization, session/transaction records, and
> app/backend visibility. The `X300`/`X303`/`X304` rows are documented for
> completeness and for standalone **non-OCPP** deployments only.

## Master registers (addresses 0–999)

| Reg | Words | Meaning |
|----|----|----|
| `100` | 10 | Device designation (ASCII) |
| `110` | 4 | Linux software version (ASCII) |
| `114` | 1 | Number of charging controllers |
| `147–151` | 1 each | Count of controllers in error / E-F / status A / occupied / charging |
| `152` | 2 | Total active power [mW] |
| `158 / 160 / 162` | 2 each | Total current L1 / L2 / L3 [mA] |
| `164` | 1 | Availability gate (0 = force all CPs to F, 1 = normal) — R/W, but only writable when the availability gate is configured (`writeable_if: configured` in the Phoenix register map) |
| `167` | 1 | **Dynamic max current for internal load management** [A], first load circuit. `65535` = no dynamic cap. R/W |

> **Register 167** is the "cooperate with CHARX internal load management" path:
> instead of driving each CP's `X301` yourself, write one site-wide budget and
> let the charger's own LM distribute it across charging points. Use this if you
> want a simple total-power limit rather than per-socket control.
>
> ⚠️ **Caveat:** register 167 only caps charging points **bound to the first
> load circuit** in the charger's load-management config. If that circuit has
> no charging points bound (common when another controller manages the
> sockets), writes to 167 are accepted but **inert**. Verify the binding via
> REST: `GET :1603/api/v1.0/loadmanagement/load_circuits` — `charging_points[]`
> must contain the controller UIDs.

## Release modes

`X120` reports how charging is authorized. It matters because **`X300`/`X303`/
`X304` only become writable in `Modbus` mode**:

| `X120` | Mode | Who releases charging |
|----|----|----|
| 0 | Dashboard | Web UI manual release |
| 1 | Local whitelist | On-device RFID whitelist |
| 2 | External | Generic external (gated I/O) |
| 3 | Permanent | Releases on plug-in, no auth |
| 4 | OCPP | OCPP backend Authorize |
| 5 | **Modbus** | Your Modbus client drives `X300` + `X301` |

The release mode is set in the charger's Web UI / via [REST](rest-api.md), not
over Modbus. Two EMS patterns:

1. **Current-capping only (✅ recommended on Veton chargers)** — leave the
   release mode as shipped (**OCPP**), just write `X301`. OCPP authorizes and
   starts/stops; you throttle. `X301` works in every release mode, so nothing
   needs reconfiguring.
2. **Full Modbus control (❌ not recommended on Veton chargers)** — set release
   mode = Modbus, then drive `X300` (start/stop) + `X301` (current) yourself.
   This takes release away from OCPP and breaks authorization, transaction
   records/billing, and app/backend visibility. Only appropriate for standalone
   deployments **without** an OCPP backend.

## Gotchas

- **`X301` "float-bug" on some firmware.** When an external client drives `X301`,
  certain CHARX firmware can silently reset it to `0` shortly after the write
  (a parse error in the controller's internal float-publish loop). **Always
  read `X301` back** after writing and re-issue if it didn't stick. If it
  persistently reverts to 0, the only known fix is a controller power-cycle.
- **`X301 = 0` blocks charging in every mode** — switching release mode does not
  override a zero current cap. Never write 0 from an EMS; pause at the 6 A
  minimum instead (stopping a session is OCPP's job).
- **32/64-bit word order is MSW-first.** Reading the low word first yields garbage.
- **Currents return `-1`** at master level when phase rotation is unknown.

See [examples/python/charx.py](../examples/python/charx.py) for a tested client,
and [ems-integration.md](ems-integration.md) for the full control loop.
