# REST APIs

The charger exposes several HTTP/REST surfaces. Use these for **configuration**
(load management, control flags, release mode, service restarts) — for live
control of current prefer [Modbus](modbus.md).

CHARX paths are **not** all under the same prefix:
- `/api/v1.0/web/…` — Web Backend Management: `login`, `network`, `firewall`, `restart-app`, `update*`, `user/*`
- `/api/v1.0/…` — service APIs: `charging-controllers`, `loadmanagement/*`, `modbus-client/*`, `ocpp16/*`

Never blanket-prefix everything with `web/`.

---

## CHARX `:5555` — local service API (no auth)

Port 5555 exposes the service API **without authentication** (nginx on `:80/:443`
is the auth wrapper; `:5555` is the unwrapped backend). It is only reachable
**on the device or over a tunnel** — treat it as a localhost API, never expose it
to an untrusted network.

```bash
# List controllers
curl http://127.0.0.1:5555/api/v1.0/charging-controllers

# Read control flags
curl "http://127.0.0.1:5555/api/v1.0/charging-controllers/<UID>/control?param_list=charge_enable,external_release,external_locking,external_status,force_unlocking"

# Write control flags (these stick)
curl -X PUT http://127.0.0.1:5555/api/v1.0/charging-controllers/<UID>/control \
     -H 'Content-Type: application/json' \
     -d '{"external_release": true}'
```

> ⚠️ **On Veton chargers, don't drive `external_release`.** Charging release
> stays with **OCPP** (see [ocpp.md](ocpp.md)) — `external_release` is another
> release-control door, just like Modbus `X300`/`X304`. Shown for completeness
> and for standalone **non-OCPP** setups only.

```bash
# Read / write load-management config (watchdog params take; maximum_current is owned by LM and dropped)
curl "http://127.0.0.1:5555/api/v1.0/charging-controllers/<UID>/load-management-config?param_list=maximum_current,maximum_current_on_expired_watchdog,watchdog_timer_sec"
```

> ⚠️ **Do not set `external_release: false` while a car is connected** — the
> controller jumps to IEC state **F** (fault) immediately.

## CHARX `:1603` — load-management service

```bash
# The load-management circuit config. charging_points[] takes controller UIDs (not CP ids).
curl http://127.0.0.1:1603/api/v1.0/loadmanagement/load_circuits
```

> A `PUT` to `load_circuits` **does not take effect until the LM agent is
> restarted** (see `restart-app {"app":"llm"}` below).

## CHARX `:80` / `:443` — authenticated Web API

```bash
# 1) Log in (manufacturer creds; password varies by FW: "manufacturer" on ≤1.6.x, "Manufacturer2025%" on 1.7.x+)
TOKEN=$(curl -sk -X POST https://192.168.0.50/api/v1.0/web/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"manufacturer","password":"manufacturer"}' | jq -r .token)

# 2) Restart a service (app codes incl. "llm" = load management; also stop-app/start-app/reboot-all)
curl -sk -X POST https://192.168.0.50/api/v1.0/web/restart-app \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"app":"llm"}'
```

> Web-API auth can be flaky over a tunnel — only the first login in a session
> reliably returns a token. Re-login fresh and chain the authed call.

---

## vetond HTTP API (`:8080`)

If the **Veton agent (`vetond`)** is installed on the charger, it offers a clean
JSON API on `:8080` (no TLS; JWT for writes; read endpoints are public). It also
proxies the CHARX services above, injecting CHARX auth for you.

```bash
# Is vetond running? (canonical detector)
curl http://192.168.0.50:8080/api/status        # → {"agent":"vetond","version":"…", ...}

# Live per-charging-point state
curl http://192.168.0.50:8080/api/charging-points/live

# Power history
curl http://192.168.0.50:8080/api/power/recent
curl http://192.168.0.50:8080/api/power/monthly-peak

# Solar / EMS config (read public)
curl http://192.168.0.50:8080/api/solar/status
curl http://192.168.0.50:8080/api/solar/config
```

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/status` | agent presence, version, machine_id, active sessions |
| GET | `/api/charging-points/live` | live per-CP state |
| GET | `/api/sessions`, `/api/sessions/{id}` | charging sessions |
| GET | `/api/power/recent` · `/quarter` · `/monthly-peak` | power history |
| GET / PUT | `/api/solar/config` | EMS / load-management settings |
| GET / PUT | `/api/rfid/release-mode` | release-mode toggle |
| POST | `/api/auth/login` | obtain a JWT (CHARX manufacturer/operator creds) |
| ANY | `/proxy/{service}/{path}` | authenticated passthrough to `rest` (:5555), `loadmgmt` (:1603), `web` (:80), `ocpp` (:2106), `modbus` (:9555) |

Auth for writes:

```bash
TOKEN=$(curl -s -X POST http://192.168.0.50:8080/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"manufacturer","password":"…"}' | jq -r .token)

curl -X PUT http://192.168.0.50:8080/api/solar/config \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{ ... }'
```

Full curl set: [examples/curl/rest-examples.sh](../examples/curl/rest-examples.sh).
