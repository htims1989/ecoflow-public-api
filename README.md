# EcoFlow Stream (Public API) — Home Assistant Integration

A lightweight, independent Home Assistant integration for **EcoFlow Stream** devices
(Stream Ultra / Ultra X inverters and the EcoFlow **Smart Meter**), built on EcoFlow's
**official public developer API** (IoT Open) — HMAC-signed HTTP plus the EcoFlow MQTT
broker for near-real-time push telemetry.

> This is a clean-room integration that uses only EcoFlow's documented public API.
> It is **not** derived from any other integration's code. It was inspired by the
> excellent [tolwi/hassio-ecoflow-cloud](https://github.com/tolwi/hassio-ecoflow-cloud)
> project, which takes a different (private-API / protobuf) approach.

## Features

- **Near-real-time power flow** via MQTT push — solar, battery, grid, and home load.
- **Per-string PV power** (PV1–PV4) for Stream inverters.
- **Battery detail** — state of charge, health, cycles, temperature, time-to-full/empty.
- **Daily energy sensors** (`*_today`) for solar, consumption, grid import/export, and
  battery charge/discharge — ready to drop into the Home Assistant **Energy Dashboard**.
- **Smart Meter support** — whole-house grid power (per phase), plus derived daily
  grid import/export energy sensors (integrated from live power, reset at local midnight).
- **Multi-device** — every entity is scoped by serial number, so multiple Stream units
  coexist without collision.
- **Auto-discovery** — new devices added to your EcoFlow account appear automatically
  on the next Home Assistant restart.

## Requirements

- Home Assistant 2024.1.0 or newer.
- An EcoFlow **Developer** account with an **Access Key** and **Secret Key**
  (create these at <https://developer.ecoflow.com/>).
- One or more supported devices registered to that account.

## Installation

### HACS (custom repository)

1. In HACS → **Integrations** → three-dot menu → **Custom repositories**.
2. Add this repository URL, category **Integration**.
3. Install **EcoFlow Stream (Public API)** and restart Home Assistant.

### Manual

Copy `custom_components/ecoflow_streamx` into your Home Assistant
`config/custom_components/` directory and restart.

## Configuration

1. **Settings → Devices & Services → Add Integration → EcoFlow Stream (Public API)**.
2. Enter your **Access Key**, **Secret Key**, a **Group** name (any label, e.g. `Home`),
   and pick your **region host**:
   - **EU:** `api-e.ecoflow.com`
   - **US / Global:** `api.ecoflow.com`
3. The integration validates your credentials, discovers your devices, and creates
   entities for each.

If you add a new device to your EcoFlow account later, just restart Home Assistant —
it will be picked up automatically.

## Energy Dashboard

The `*_today` energy sensors use `state_class: total_increasing` and reset at local
midnight, so they map cleanly onto the Energy Dashboard:

| Energy Dashboard slot | Sensor |
| --- | --- |
| Solar production | `sensor.<stream>_solar_energy_today` |
| Grid consumption | `sensor.<meter>_grid_import_energy` |
| Return to grid | `sensor.<meter>_grid_export_energy` |
| Battery in | `sensor.<stream>_battery_charge_today` |
| Battery out | `sensor.<stream>_battery_discharge_today` |

## Dashboard

A ready-made Lovelace dashboard is included at
[`dashboards/solar_dashboard.yaml`](dashboards/solar_dashboard.yaml). It uses the
following HACS frontend cards:

- Power Flow Card Plus (`custom:power-flow-card-plus`)
- ApexCharts Card (`custom:apexcharts-card`)
- Mushroom (`custom:mushroom-*`)

Copy its contents into a new dashboard via **Edit → Raw configuration editor**, then
adjust the entity IDs to match your device serial numbers.

## Notes & caveats

- **Grid sign convention:** the Smart Meter's derived import/export energy depends on
  the sign of `powGetSysGrid`. If import/export appear swapped, flip `IMPORT_IS_POSITIVE`
  in `custom_components/ecoflow_streamx/meter_energy.py`.
- The Smart Meter's public API only exposes instantaneous power, so daily import/export
  kWh are integrated locally (trapezoidal) rather than read from a native counter.
- Historical energy aggregates are polled every 5 minutes to respect API rate limits.

## License

Released under the [MIT License](LICENSE). This project contains only original code and
does not redistribute any third-party integration source.
