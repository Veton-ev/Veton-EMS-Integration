# Integrating Veton EV chargers into an EMS

Developer guide for integrating **Veton EV chargers** (built on the Phoenix
Contact **CHARX SEC** controller) into an Energy Management System (EMS),
building controller, or any home/building automation platform.

It covers every interface the charger exposes, when to use each, and how to
build a safe control loop — with runnable code examples.

> Already have a turnkey integration? See **[Home Assistant](https://github.com/Veton-ev/HA-Veton)**
> and **[Loxone](https://github.com/Veton-ev/Veton-Loxone)**. This repo is the
> protocol-level reference behind both.

## Interfaces at a glance

| Interface | Direction | Use it for | Notes |
|---|---|---|---|
| **[Modbus TCP](docs/modbus.md)** (`:502`) | read + **write** | The primary EMS path: read metering/status, set current (X301), drive release (X300), arm the safety watchdog (X306/X307) | Always available. Recommended for control. |
| **[Local MQTT](docs/mqtt.md)** (`:1883`) | **read only** | Cheap, push-based per-charging-point metering (real V/I/P/energy) + plug/charge state | Publishing to `control/*` is **display-only — it does not control the charger.** FW ≥ 1.8 closes 1883 by default. |
| **[CHARX REST API](docs/rest-api.md)** (`:5555` / `:1603` / `:80`) | read + write | Configuration: load-management config, control flags, restart services | `:5555`/`:1603` are local & unauthenticated; `:80` is the authenticated Web API. |
| **[vetond HTTP API](docs/rest-api.md#vetond-http-api-8080)** (`:8080`) | read + write | If the Veton agent is installed: sessions, power history, solar/EMS config, live CP state, a proxy to all of the above | JSON over HTTP, JWT for writes. |
| **[OCPP 1.6](docs/ocpp.md)** | read + write | Authorization + smart-charging profiles via your OCPP backend | Use if you already run an OCPP CSMS. |

## Which one should I use?

- **Cap/steer charging current from an EMS** → **Modbus** `X301` + the watchdog. Start here: [docs/ems-integration.md](docs/ems-integration.md).
- **Start/stop charging from the EMS** → Modbus `X300`, which requires the charger's **release mode = Modbus** (see [release modes](docs/modbus.md#release-modes)).
- **Just read live power/energy per charging point** → **MQTT** (push, ~5 s) or Modbus (poll).
- **Feed a site-wide budget and let the charger distribute it** → Modbus master register **167** (cooperates with CHARX internal load management).

## Quick start (Modbus, Python)

```bash
cd examples/python
pip install -r requirements.txt
python read_state.py 192.168.0.50 --connector 1      # print live charger state
python ems_loop.py   192.168.0.50 --connector 1      # safe demo control loop
```

## ⚠️ Safety first — arm the watchdog

An EMS that sets the charging current **must** arm the charger's watchdog
(`X306` fallback current + `X307` timeout). If your EMS crashes, the network
drops, or the process is killed, the charger falls back to a safe current
instead of holding the last setpoint forever. See
[docs/ems-integration.md](docs/ems-integration.md#the-watchdog-is-mandatory).

## Contents

- [docs/modbus.md](docs/modbus.md) — full register map, data encoding, read & write, watchdog
- [docs/mqtt.md](docs/mqtt.md) — local broker topics, payloads, the read-only caveat
- [docs/rest-api.md](docs/rest-api.md) — CHARX REST (`:5555`/`:1603`/`:80`) + vetond (`:8080`)
- [docs/ocpp.md](docs/ocpp.md) — OCPP 1.6 smart charging
- [docs/ems-integration.md](docs/ems-integration.md) — putting it together: the control loop, gotchas, multi-charging-point
- [examples/](examples/) — runnable Python + curl

## License

[MIT](LICENSE) — free to use and modify. This is reference documentation;
register addresses and behaviour are based on Phoenix Contact CHARX SEC
firmware 1.7+. Verify against your charger's firmware.
