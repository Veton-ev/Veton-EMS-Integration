# Veton-EMS-Integration — Claude Code instructions

<!-- Template from veton-handbook/templates/CLAUDE.md.template. Keep every section; write
"none" rather than deleting one. Facts here must be checked against the code, not remembered.
Cross-cutting knowledge (fleet, runbooks, access, suppliers) lives in the handbook — link, don't copy. -->

> **THIS REPOSITORY IS PUBLIC** (`github.com/Veton-ev/Veton-EMS-Integration`, MIT).
> Nothing internal may be committed: no hostnames (plane/tailnet/`*.vetoncontrol.com` internals),
> no customer or site names, no fleet numbers, no charger UIDs, no credentials of any kind.
> Only the vendor-documented CHARX defaults that are already public may appear. When in doubt,
> leave it out and put it in the handbook instead.

## What this is
Public **developer guide for integrating a Veton charger (Phoenix Contact CHARX SEC) into a
third-party EMS**: Markdown docs for every interface the charger exposes (Modbus TCP `:502`,
local MQTT `:1883`, CHARX REST `:5555`/`:1603`/`:80`, vetond HTTP `:8080`, OCPP 1.6) plus
runnable Python (`pymodbus`, `paho-mqtt`) and curl examples. Consumers are external EMS /
building-automation developers and the two turnkey integrations that sit on top of it
(`Veton-ev/HA-Veton`, `Veton-ev/Veton-Loxone`). **Not deployed** — it is documentation; the
"product" is the rendered GitHub README. Handbook: `veton-handbook/10-fleet/`.

## Ownership
Owners: TBD (Brend / Andrii). Escalation: Jens. Handbook page: `veton-handbook/10-fleet/`.

## Run / test / build
```bash
# install (examples only)
cd examples/python && pip install -r requirements.txt      # pymodbus>=3.10, paho-mqtt>=2.0
# run locally (against a real charger on the LAN; no simulator exists in this repo)
python read_state.py <charger-ip> --connector 1
python ems_loop.py   <charger-ip> --connector 1              # demo control loop, arms the watchdog
python dual_point.py <charger-ip> --budget 32                # master/slave: split one budget
python mqtt_monitor.py <charger-ip>
bash examples/curl/rest-examples.sh                          # edit HOST first
# test — there is NO test suite. The only mechanical check that exists (ran green 2026-08-26):
python3 -m py_compile examples/python/*.py && bash -n examples/curl/rest-examples.sh
# build: none (no build step)
```
CI: **none** — there is no `.github/workflows/` directory. Target state: a `ci.yml` (job id
`ci`) running the compile check above + a link check + gitleaks; see
`veton-handbook/HANDOVER-PLAN.md` Phase 4. Until then nothing gates a push.

## Deploy
**Not deployed.** Not in the 2026-08-26 deploy survey
(`veton-handbook/70-runbooks/deploy-paths-survey-2026-08-26.md`). Publishing = merging to
`main`; GitHub renders it. No trigger, no smoke check; rollback = revert the commit.
Blast radius of a bad change: external integrators (and HA-Veton / Veton-Loxone users) follow
wrong register numbers or, worse, an unsafe control pattern — nothing on the fleet changes.

## Talks to (seams)
- **CHARX Modbus register map** (X301 setpoint, X306/X307 watchdog, `n×1000` per charging
  point, master reg 114 / 167, X113) — described in `docs/modbus.md` and hard-coded in
  `examples/python/charx.py`. The same map is duplicated in `vetonlm/registers`,
  `savings-collector`, `charx-doctor/references`, `veton-ha`, `Veton-Loxone/MB_Veton.xml` and
  `veton-evse-agent/internal/charx`. Change a register here → check every copy.
- **vetond HTTP API `:8080`** — `docs/rest-api.md#vetond-http-api-8080` documents the shape
  owned by `vetond/`. If vetond changes a route, this doc is stale.
- **Local MQTT topics** `charging_controllers/<uid>/data/energy` etc. — `docs/mqtt.md`;
  published by the charger/vetond, no shared schema file anywhere.
- **Turnkey integrations** `Veton-ev/HA-Veton` and `Veton-ev/Veton-Loxone` cite this repo as
  the protocol reference; a policy change here (see Gotchas) must be propagated there.
See handbook `00-orientation/seams.md`.

## Gotchas (this repo only)
- **Integration policy is deliberate and non-obvious: the EMS must never control charging
  release.** Commit `e7b3555` ("Leave charging release to OCPP") rewrote the docs so an EMS only
  caps current via X301 in the 6–80 A band and arms X306/X307. Writing X300/X304, switching
  release mode, or writing **X301 = 0** is documented as wrong. Do not "helpfully" add release
  control to an example — the README's "Which one should I use?" section is the policy.
- **`pymodbus>=3.10` is a hard floor**, not a suggestion: the examples use the `device_id=`
  keyword, which 3.7–3.9 spell `slave=`. Older installs fail at call time, not import time.
- **Local MQTT is read-only.** `docs/mqtt.md`: publishing to `control/*` changes the display
  only. An example that "controls" via MQTT is a bug.
- **Port availability depends on firmware/provisioning** (README "Port availability"): factory
  FW ≥ 1.8 only opens `:80`/`:443`. Examples assume a Veton-provisioned charger.
- **The CHARX factory-default manufacturer login appears in `docs/rest-api.md` and
  `examples/curl/rest-examples.sh`.** It is the vendor default (already public), but never
  replace it with a real per-device or fleet credential, and never add the `user-app`/SSH
  passwords from other repos.
- `examples/python/__pycache__/` exists on Jens's disk; it is gitignored — do not commit it.

## Agent rules
- Work on a branch; open a PR; never push to `main` (to be enforced by `.claude/settings.json`
  + `.claude/hooks/guard.sh` and by branch protection — HANDOVER-PLAN Phase 4/5).
- Never run deploy/ssh-to-production commands; there is nothing to deploy from this repo.
- **Public repo:** never commit secrets, internal hostnames, customer names, fleet numbers or
  charger UIDs; `gitleaks` pre-commit + CI will fail the commit/PR once Phase 4 lands. There
  are no secrets for this repo; the handbook `60-access/` says where fleet secrets live, never
  the value.
- Write durable lessons to `veton-handbook/lessons/` (one file per lesson), not to
  personal memory.
