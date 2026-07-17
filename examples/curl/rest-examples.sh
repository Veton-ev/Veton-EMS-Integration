#!/usr/bin/env bash
# REST examples for Veton / Phoenix Contact CHARX + the vetond agent.
# These configure the charger; for live current control prefer Modbus (see ../python).
#
# Usage: edit HOST/UID, then copy-paste the blocks you need.
set -euo pipefail

HOST="192.168.0.50"
UID_CP="<CONTROLLER_UID>"     # from: GET /api/v1.0/charging-controllers

# ─────────────────────────────────────────────────────────────────────
# CHARX :5555 — local service API, NO AUTH (on-device / tunnel only)
# ─────────────────────────────────────────────────────────────────────

# List charging controllers (find the UID + charging-point mapping)
curl -s "http://${HOST}:5555/api/v1.0/charging-controllers"

# Read control flags
curl -s "http://${HOST}:5555/api/v1.0/charging-controllers/${UID_CP}/control?param_list=charge_enable,external_release,external_locking,external_status,force_unlocking"

# Write a control flag (these stick). DO NOT set external_release=false with a car plugged in (→ fault F).
# ⚠️ On Veton chargers charging release stays with OCPP — external_release is another
#    release-control door; shown for completeness / standalone non-OCPP setups only.
curl -s -X PUT "http://${HOST}:5555/api/v1.0/charging-controllers/${UID_CP}/control" \
     -H 'Content-Type: application/json' \
     -d '{"external_release": true}'

# Read/write load-management config. watchdog params take; maximum_current is owned by LM and dropped.
curl -s "http://${HOST}:5555/api/v1.0/charging-controllers/${UID_CP}/load-management-config?param_list=maximum_current,maximum_current_on_expired_watchdog,watchdog_timer_sec"

# ─────────────────────────────────────────────────────────────────────
# CHARX :1603 — load management (PUT needs an LM restart to take effect)
# ─────────────────────────────────────────────────────────────────────
curl -s "http://${HOST}:1603/api/v1.0/loadmanagement/load_circuits"

# ─────────────────────────────────────────────────────────────────────
# CHARX :80/:443 — authenticated Web API
# password varies by FW: "manufacturer" (<=1.6.x) or "Manufacturer2025%" (1.7.x+)
# ─────────────────────────────────────────────────────────────────────
TOKEN=$(curl -sk -X POST "https://${HOST}/api/v1.0/web/login" \
  -H 'Content-Type: application/json' \
  -d '{"username":"manufacturer","password":"manufacturer"}' | jq -r .token)

# Restart the load-management service (app code "llm"; also stop-app/start-app/reboot-all)
curl -sk -X POST "https://${HOST}/api/v1.0/web/restart-app" \
  -H "Authorization: Bearer ${TOKEN}" -H 'Content-Type: application/json' \
  -d '{"app":"llm"}'

# ─────────────────────────────────────────────────────────────────────
# vetond agent :8080 (if installed) — JSON API + authenticated proxy
# ─────────────────────────────────────────────────────────────────────
curl -s "http://${HOST}:8080/api/status"                 # {"agent":"vetond",...}
curl -s "http://${HOST}:8080/api/charging-points/live"
curl -s "http://${HOST}:8080/api/power/recent"

# Authenticated write (JWT from vetond, CHARX manufacturer/operator creds)
VTOKEN=$(curl -s -X POST "http://${HOST}:8080/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"username":"manufacturer","password":"manufacturer"}' | jq -r .token)

curl -s "http://${HOST}:8080/api/solar/config" -H "Authorization: Bearer ${VTOKEN}"
