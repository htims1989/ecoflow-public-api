# EcoFlow Stream (Public API) — Home Assistant Integration

A lightweight, independent Home Assistant integration for the **EcoFlow Stream Ultra X**
inverter and the EcoFlow **Smart Meter**, built on EcoFlow's
**official public developer API** (IoT Open) — HMAC-signed HTTP plus the EcoFlow MQTT
broker for near-real-time push telemetry.

> **Supported devices:** this integration has only been developed and verified against
> the **Stream Ultra X** inverter and the **Smart Meter**. Other Stream models
> (Stream, Stream Max, Stream Ultra) are **not officially supported** — see
> [Supported devices](#supported-devices) below.

> This is a clean-room integration that uses only EcoFlow's documented public API.
> It is **not** derived from any other integration's code. It was inspired by the
> excellent [tolwi/hassio-ecoflow-cloud](https://github.com/tolwi/hassio-ecoflow-cloud)
> project, which takes a different (private-API / protobuf) approach.

## Features

- **Near-real-time power flow** via MQTT push — solar, battery, grid, and home load.
- **Per-string PV power** (PV1–PV4) for the Stream Ultra X inverter.
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

## Supported devices

This integration is developed and tested **only** against:

| Device | Live power sensors | Daily energy (`*_today`) sensors |
| --- | :---: | :---: |
| **Stream Ultra X** (inverter) | ✅ verified | ✅ verified |
| **Smart Meter** | ✅ verified | ✅ (derived from live power) |

**Other Stream models (Stream, Stream Max, Stream Ultra) are not officially
supported.** They will still be *discovered* and set up without errors, but:

- Live power sensors may or may not populate, depending on whether the model
  publishes the same MQTT field names as the Ultra X (unverified).
- The **daily energy sensors will not work** — the historical-energy API codes are
  specific to the Stream Ultra X (`BK621`), so those sensors are skipped on other
  models.

Nothing should crash on an unsupported model — it simply degrades: unsupported sensors
stay unavailable or are not created. If you have another Stream model and want to
help add support, please open an issue with a diagnostic dump.

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

### Overview

Live power flow between solar, battery, grid, and home, plus "right now" and "today"
summary tiles.

![Overview dashboard](docs/images/dashboard-overview.png)

### Solar

Solar power today, per-string (PV1–PV4) output gauges, and a 7-day energy history.

![Solar dashboard](docs/images/dashboard-solar.png)

### Battery

State of charge, health, cycles, temperature, full-energy capacity, and
charge/discharge time estimates.

![Battery dashboard](docs/images/dashboard-battery.png)

### Grid

Whole-house grid power, per-phase power/voltage/current, and system health
(inverter temperature, frequency, Wi-Fi signal).

![Grid dashboard](docs/images/dashboard-grid.png)

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
