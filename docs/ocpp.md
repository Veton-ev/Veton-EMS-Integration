# OCPP 1.6

The CHARX controller includes an **OCPP 1.6J** charge-point agent. If you already
run an OCPP backend (CSMS), it is a valid integration path — especially for
**authorization** (RFID → Authorize) and **smart charging** (current limits via
charging profiles).

## When to use OCPP vs. Modbus

| Goal | OCPP 1.6 | Modbus |
|---|---|---|
| Authorize users (RFID, app) | ✅ native | — |
| Per-session billing / transactions | ✅ native | — |
| Set a current limit | `SetChargingProfile` (TxProfile / TxDefaultProfile) | `X301` (simpler, lower latency) |
| Start/stop remotely | `RemoteStart/StopTransaction` | `X300` — not recommended on Veton chargers (requires taking release away from OCPP) |
| Live metering | `MeterValues` (configurable interval) | `X232…X250` (poll) or MQTT (push) |

For a **pure current-steering EMS**, Modbus `X301` + the watchdog is simpler and
faster than maintaining OCPP charging profiles. Use OCPP when you also need
authorization, roaming, or transaction records, or when your platform already
speaks OCPP.

## Configuration

- The OCPP backend URL and identity are set in the charger Web UI, or via the
  CHARX config service (`/api/v1.0/web/ocpp16/...`) / the vetond
  `/api/ocpp/*` endpoints (see [rest-api.md](rest-api.md)).
- Release mode must be **OCPP** (`X120 = 4`) for the OCPP agent to authorize charging. Veton chargers ship in this mode — leave it as is.
- `FreeMode` + `FreeModeUID` let a cached UID auto-authorize on every plug-in
  (no swipe), while still using the OCPP path.

## Combining OCPP + Modbus — the recommended Veton architecture

This is how Veton chargers are meant to be integrated: **OCPP authorizes**
(release mode = OCPP, as shipped) and the **EMS caps current via Modbus
`X301`**. `X301` works as a ceiling in any release mode, so the two coexist —
OCPP decides *whether* to charge, the EMS decides *how fast*. The EMS must
**not** take over charging release (`X300`/`X304`): doing so breaks OCPP
authorization, transaction records/billing, and app/backend visibility.

Keep `X301` within **6–80 A** and **never write 0** — a zero cap withholds
charging release regardless of OCPP state; to back off, drop to the 6 A minimum.

The OCPP spec and message reference live at
[openchargealliance.org](https://www.openchargealliance.org/).
