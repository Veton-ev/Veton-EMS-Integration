# Building an EMS control loop

This is the synthesis: how to actually wire a Veton/CHARX charger into an EMS
safely. The recommended control path is **Modbus**, optionally reading live data
from **MQTT** and doing one-time setup over **REST**.

## Two integration patterns

### Pattern A — current capping (recommended default)
Leave authorization to the charger (OCPP / whitelist / permanent). Your EMS only
**limits** the charging current by writing `X301`. The car still has to be
authorized to charge; you decide how fast.

- Pros: minimal config, coexists with existing OCPP/RFID setups, `X301` works in any release mode.
- Cons: you can't *start* a session from the EMS (the charger's release mode does that).

### Pattern B — full Modbus control
Set the charger's **release mode = Modbus** (`X120 = 5`, via Web UI / REST). Now
your EMS owns charging: `X300` to release, `X301` for current, `X304` for
availability.

- Pros: full start/stop/throttle control.
- Cons: you take over authorization; nothing else (OCPP/RFID) releases charging.

### Pattern C — site budget via internal LM
Don't touch per-CP registers at all. Write a single site-wide current budget to
master register **167** and let the charger's internal load management distribute
it across charging points.

- Pros: one number, charger handles fair distribution.
- Cons: coarser; per-socket control is delegated to the charger.

## The watchdog is mandatory

Any EMS that writes `X301` **must** arm the watchdog. Otherwise a crashed EMS,
a dropped network, or a killed process leaves the charger pinned at the last
setpoint indefinitely.

```
X306 = safe fallback current (e.g. 6 A)     # applied when the timer expires
X307 = timeout in seconds (e.g. 30)         # re-write it within the interval to keep alive
```

Your loop must re-write `X307` (pet the watchdog) every cycle, comfortably faster
than the timeout. If the EMS stops petting it, the charger drops to `X306` after
`X307` seconds — a safe, known current — instead of holding your last command.

## The control loop

```
once at startup:
  read X120 (release mode); if you need start/stop, ensure it is Modbus(5)
  arm watchdog:  write X306 = 6,  write X307 = 30

every N seconds (N << X307, e.g. 5 s):
  read state:   X299 vehicle status, X244 power, X250 energy, X238/240/242 currents
  decide:       target_A = your_ems_policy(...)        # clamp to [6, 80] or 0 to pause
  write X301 = target_A
  read back X301; if it didn't stick, re-write (see float-bug)
  write X307 = 30                                      # pet the watchdog

on shutdown:
  leave the watchdog armed — it is your safety net, not something to disable
```

A tested implementation is in
[examples/python/ems_loop.py](../examples/python/ems_loop.py).

## Reading the vehicle state

Use `X299` (or MQTT `iec_61851_state`) to know what the car is doing:

| State | Meaning | Charging? |
|---|---|---|
| `A1/A2` | no vehicle connected | no |
| `B1` | connected, not ready | no |
| `B2` | connected, ready (EVSE permitted, relay still open) | no |
| `C1` | charging paused (relay closed, current 0) | yes |
| `C2` | charging active | yes |
| `D1/D2` | charging, ventilation required | yes |
| `E0/F0/IN` | fault / unavailable / invalid | no |

A vehicle only draws current in `C2`/`D2`. Setting `X301` low in `B2` simply caps
the current the car will be allowed once it starts.

## Multiple charging points

Every per-CP register is offset by `connector × 1000`. To control point 2, use
`2300/2301/2306/2307`; for point 3, `3300/3301/...`. Read the controller list
(Modbus `X113` per CP, or `GET /api/v1.0/charging-controllers`) to map UIDs to
charging-point numbers. Arm a watchdog **per charging point**.

## Gotchas checklist

- **Arm the watchdog.** Non-negotiable for any current-setting EMS.
- **`X301 = 0` withholds release** in every mode — use it to pause, but know it's not "0 A trickle".
- **`X300`/`X304` need release mode = Modbus.** `X301` does not.
- **Read `X301` back** — some firmware resets an externally-written `X301` to 0 (the "float-bug"); re-issue, and power-cycle the controller if it persists.
- **MQTT `control/*` writes do nothing** — display only. Control via Modbus/REST.
- **MSW-first** word order for 32/64-bit values.
- **FW ≥ 1.8 closes `:1883`/`:5555` externally** — plan your transport accordingly.

## Related

- [modbus.md](modbus.md) — full register map
- [mqtt.md](mqtt.md) — live data without polling
- [rest-api.md](rest-api.md) — configuration & release-mode setup
- [ocpp.md](ocpp.md) — authorization + smart charging
