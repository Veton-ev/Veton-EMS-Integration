# Local MQTT

Each CHARX master runs a local MQTT broker that publishes live per-charging-point
data. It's the cheapest way to **read** metering and plug/charge state — it's
push-based (~5 s), carries real per-phase voltage, and needs no polling.

```
Broker:  charger IP, port 1883, anonymous (local network)
```

> **Firmware note:** FW < 1.8 leaves `:1883` open on the LAN. **FW ≥ 1.8 closes
> 1883 by default** — reach it on-device, open it via the firewall, or read the
> same data over [Modbus](modbus.md) instead.

> **⚠️ MQTT is read-only for control.** Publishing to `control/*` topics only
> updates a retained *display* value — the controller does **not** act on MQTT
> writes (it reads its setpoints from the Modbus register cache). **To control
> the charger, use [Modbus](modbus.md) or the [REST API](rest-api.md).**

## Topics

`<uid>` is the controller UID (see Modbus `X113` or the REST controller list).

| Topic | Payload |
|---|---|
| `charging_controllers/<uid>/data/energy` | JSON meter sample (see below) |
| `charging_controllers/<uid>/data/iec_61851_state` | `A1` `B1` `B2` `C1` `C2` … |
| `charging_controllers/<uid>/data/charge_time_sec` | seconds charging |
| `charging_controllers/<uid>/data/connected_time_sec` | seconds connected |
| `charging_controllers/<uid>/data/pwm_duty_cycle_percent` | `100` = no charge permitted |
| `charging_controllers/<uid>/data/error_status_enum` | `NO_ERRORS` / `ERR_STATE_*` |
| `charging_controllers/<uid>/control/maximum_current` | live setpoint **(read-only view)** |
| `applications/loadmanagement/data/load_circuit/*` | LM dispatch state |

In **master–slave** topologies the slaves re-publish under
`device-network/<slave-id>/charging_controllers/<uid>/...`. To get total EV load,
sum `real_power` across both namespaces.

### `data/energy` payload

```json
{
  "u1": 241.0, "u2": 240.6, "u3": 241.2,
  "i1": 16.0, "i2": 0.0, "i3": 0.0,
  "real_power": 3850.0,
  "reactive_power": 120.0,
  "apparent_power": 3860.0,
  "power_factor": 0.99,
  "frequency": 50.0,
  "energy_real_power": 132840.0,
  "part_energy_real_power": 4200.0,
  "energy_meter_info": { "model_number": "WM3M4", "serial_number": "…", "firmware_version": "…" }
}
```

- `u1/u2/u3` — phase voltage [V]  ·  `i1/i2/i3` — phase current [A]
- `real_power` [W] (signed)  ·  `energy_real_power` [Wh] cumulative
- Real voltage is present, so per-CP power is accurate and signed — no `I×230` estimate needed.

## Subscribe (example)

```bash
mosquitto_sub -h 192.168.0.50 -t 'charging_controllers/+/data/#' -v
```

See [examples/python/mqtt_monitor.py](../examples/python/mqtt_monitor.py) for a
paho-mqtt subscriber that decodes per-CP power, energy and IEC state.
