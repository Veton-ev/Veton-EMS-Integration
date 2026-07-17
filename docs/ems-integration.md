# Building an EMS control loop

This is the synthesis: how to actually wire a Veton/CHARX charger into an EMS
safely. The recommended control path is **Modbus**, optionally reading live data
from **MQTT** and doing one-time setup over **REST**.

## Two integration patterns

### Pattern A — current capping (✅ the recommended pattern for Veton chargers)
Veton chargers ship with **release mode = OCPP** — leave it that way.
Authorization stays with the charger/backend; your EMS only **limits** the
charging current by writing `X301`. The car still has to be authorized to
charge; you decide how fast.

- Pros: zero reconfiguration, keeps OCPP authorization/billing/app visibility intact, `X301` works in any release mode.
- Cons: the EMS can't *start/stop* a session — by design: that is OCPP's job (see [ocpp.md](ocpp.md)).

### Pattern B — full Modbus control

> ⚠️ **Not recommended on Veton chargers — release/authorization belongs to
> OCPP.** Switching the release mode to Modbus breaks **OCPP authorization**,
> **transaction records / billing**, and **app & backend visibility**. Use this
> pattern only in standalone deployments without an OCPP backend.

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
- ⚠️ Caveat: register 167 only caps charging points **bound to the first load
  circuit** in the charger's load-management config. If that circuit has no
  charging points bound (common when another controller manages the sockets),
  writes to 167 are accepted but **inert**. Verify the binding via REST:
  `GET :1603/api/v1.0/loadmanagement/load_circuits` — `charging_points[]` must
  contain the controller UIDs.

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
  leave the release mode as it is (OCPP on Veton chargers) — the EMS only caps current
  arm watchdog:  write X306 = 6,  write X307 = 30

every N seconds (N << X307, e.g. 5 s):
  read state:   X299 vehicle status, X244 power, X250 energy, X238/240/242 currents
  decide:       target_A = your_ems_policy(...)        # clamp to [6, 80]; to back off, go to the 6 A minimum — do NOT write 0
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
| `C1` | vehicle ready, charging paused by EVSE (no PWM offered) — no current flows | **no (paused)** |
| `C2` | charging active | yes |
| `D1` | as `C1` but ventilation required (IEC 61851 completeness — CHARX does not report D states on `X299`) | **no (paused)** |
| `D2` | charging active, ventilation required (IEC 61851 completeness — CHARX does not report D states on `X299`) | yes |
| `E0/F0/IN` | fault / unavailable / invalid | no |

A vehicle only draws current in `C2`/`D2`. Setting `X301` low in `B2` simply caps
the current the car will be allowed once it starts.

## Double charging points (master/slave)

A multi-socket Veton charger (e.g. a two-socket unit) is internally several
CHARX charging controllers: one is the server (**master**), the others are
clients (**slaves**) attached to it. The key fact for an EMS:

**There is only one Modbus server — the master's IP, `:502` — and it serves
all charging points.** Charging point *n* lives at register block `n × 1000`
(a master can serve up to 48 points). You never connect to a slave directly.

For a double charger:

| Register | Socket 1 | Socket 2 |
|---|---|---|
| Vehicle state `X299` | `1299` | `2299` |
| Current cap `X301` | `1301` | `2301` |
| Watchdog fallback `X306` | `1306` | `2306` |
| Watchdog timeout `X307` | `1307` | `2307` |

- **Discovery:** master register `114` = number of charging controllers in the
  system. Per-CP `X113` (3 words, ASCII) is that controller's UID; REST
  `GET :5555/api/v1.0/charging-controllers` maps UIDs too.
- **Watchdog per charging point:** arm `X306`/`X307` at every CP's offset.
- **The sockets share one supply feed — splitting the budget is on you.** The
  **sum of the `X301` values must respect the supply**: your EMS divides the
  budget itself (see the example below), or you delegate to the charger's
  internal load management via master register **167** — with the load-circuit
  caveat from [Pattern C](#pattern-c--site-budget-via-internal-lm).
- **MQTT:** charging points on a slave controller republish under
  `device-network/<slave-id>/charging_controllers/<uid>/…`.

A runnable, commented budget-splitting demo:
[examples/python/dual_point.py](../examples/python/dual_point.py).

## Gotchas checklist

- **Arm the watchdog.** Non-negotiable for any current-setting EMS.
- **Never write `X301 = 0`.** A zero cap withdraws charging release — that is
  release control by the back door, and it interacts badly with the float-bug:
  a stuck retained 0 leaves the charger refusing to charge
  (`ERR_STATE_NO_AVAILABLE_CURRENT`). To pause, drop to the 6 A minimum;
  stopping a session is OCPP's job.
- **Leave release to OCPP** — don't drive `X300`/`X304` on Veton chargers.
  `X301` caps current in every release mode; that's all an EMS needs.
- **Read `X301` back** — some firmware resets an externally-written `X301` to 0 (the "float-bug"); re-issue, and power-cycle the controller if it persists.
- **MQTT `control/*` writes do nothing** — display only. Control via Modbus/REST.
- **MSW-first** word order for 32/64-bit values.
- **FW ≥ 1.8 closes `:1883`/`:5555` externally** — plan your transport accordingly.

## Related

- [modbus.md](modbus.md) — full register map
- [mqtt.md](mqtt.md) — live data without polling
- [rest-api.md](rest-api.md) — configuration & release-mode setup
- [ocpp.md](ocpp.md) — authorization + smart charging
