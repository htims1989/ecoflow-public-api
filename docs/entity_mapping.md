# Entity mapping

This document lists every entity the integration can create and the exact data
source behind it. There are two kinds of source:

- **MQTT** — a field from the incremental telemetry the device pushes to the
  EcoFlow MQTT broker (topic `/open/{account}/{sn}/quota`). The coordinator
  keeps a merged snapshot of every field seen so far.
- **REST** — a value fetched over the signed HTTP API
  (`POST /iot-open/sign/device/quota/data`), polled every 5 minutes.

Some sensors are **derived**: computed locally from an MQTT field rather than
read directly (for example, integrating live power into daily kWh).

## Naming and IDs

- `_attr_has_entity_name` is `True`, so each entity's `entity_id` is generated
  from the **device name** (as it appears in the EcoFlow app) plus the sensor
  name, e.g. `sensor.stream_ultra_x_0253_solar_power`.
- Each entity's `unique_id` is stable and serial-based (`{serial}_{key}`), so
  renaming the device does not orphan history.
- "Diagnostic" entities are created in the **Diagnostic** category and are still
  enabled by default unless noted.

---

## Multi-battery (cascade) systems

When two or more Stream batteries are daisy-chained, one unit is elected as the
**cascade master** (identified by `GET /device/system/main/sn`). The master
device aggregates system-wide values and is the only device to push them over
MQTT. Secondary devices only report their own hardware state.

Sensors marked **⊕ Primary only** in the tables below are:
- Created **only** for the master device.
- **Disabled** in the entity registry for secondary devices (any stale entries
  from a previous integration version are automatically disabled at startup via
  `RegistryEntryDisabler.INTEGRATION`).

Sensors **not** marked are per-device and created for every battery — including
secondaries. PV-string sensors (`powGetPv*`) are per-device: they show
`unavailable` on a secondary until solar panels are physically connected, at
which point the device begins pushing them automatically.

---

## Stream Ultra X — live sensors (MQTT)

Source map: `sensor_map.py` → `MQTT_SENSORS`. `unique_id = {serial}_{MQTT field}`.

### Diagnostic

| Entity name | Source | Notes |
| --- | --- | --- |
| Device Role | static | `Primary` / `Secondary`; set at startup from main-SN lookup. Always available. |

### Power flow

| Entity name | MQTT field | Unit | Notes |
| --- | --- | --- | --- |
| Solar Power | `powGetPvSum` | W | ⊕ Primary only — total PV from all cascade devices |
| Battery Power | `powGetBpCms` | W | ⊕ Primary only — aggregated across all batteries; discharge is negative |
| Grid Power | `powGetSysGrid` | W | ⊕ Primary only — signed grid exchange |
| Load Power | `powGetSysLoad` | W | ⊕ Primary only — total home load |
| Load From Solar | `powGetSysLoadFromPv` | W | ⊕ Primary only |
| Load From Grid | `powGetSysLoadFromGrid` | W | ⊕ Primary only |
| Load From Battery | `powGetSysLoadFromBp` | W | ⊕ Primary only |
| Grid Connection Power | `gridConnectionPower` | W | Per-device — each battery's own DC bus contribution; input positive, feed-in negative |
| Inverter AC Output | `acTotalActivePower` | W | Per-device |
| AC1 Output Power | `powGetSchuko1` | W | Per-device — AC1 socket output |
| AC2 Output Power | `powGetSchuko2` | W | Per-device — AC2 socket output |
| Solar Power PV1 | `powGetPv` | W | Per-device — starts reporting once panels are connected |
| Solar Power PV2 | `powGetPv2` | W | Per-device |
| Solar Power PV3 | `powGetPv3` | W | Per-device |
| Solar Power PV4 | `powGetPv4` | W | Per-device |

### Battery

| Entity name | MQTT field | Unit | Notes |
| --- | --- | --- | --- |
| Battery Level | `cmsBattSoc` | % | ⊕ Primary only — system aggregate SoC across all batteries; 0 dp |
| Battery Level Precise | `f32ShowSoc` | % | Per-device SoC; 2 dp |
| Battery Health | `cmsBattSoh` | % | ⊕ Primary only — diagnostic |
| Max Charge Level | `cmsMaxChgSoc` | % | ⊕ Primary only — diagnostic |
| Min Discharge Level | `cmsMinDsgSoc` | % | ⊕ Primary only — diagnostic |
| Charge Remaining Time | `cmsChgRemTime` | min | ⊕ Primary only |
| Discharge Remaining Time | `cmsDsgRemTime` | min | ⊕ Primary only |
| Battery Full Energy | `cmsBattFullEnergy` | Wh | ⊕ Primary only — diagnostic |
| Battery Cycles | `cycles` | — | Per-device; `total_increasing`, diagnostic |
| Total Charge Energy | `accuChgEnergy` | Wh | Per-device; `total_increasing` (lifetime) |
| Total Discharge Energy | `accuDsgEnergy` | Wh | Per-device; `total_increasing` (lifetime) |

### Temperatures and voltages (diagnostic)

| Entity name | MQTT field | Unit | Notes |
| --- | --- | --- | --- |
| Max Cell Temperature | `bmsMaxCellTemp` | °C | ⊕ Primary only — BMS summary field |
| Min Cell Temperature | `bmsMinCellTemp` | °C | ⊕ Primary only — BMS summary field |
| Max MOSFET Temperature | `maxMosTemp` | °C | Per-device |
| Temperature | `temp` | °C | Per-device |
| Min Cell Voltage | `minCellVol` | V | Per-device; mV ÷ 1000 |
| Max Cell Voltage | `maxCellVol` | V | Per-device; mV ÷ 1000 |
| Battery Voltage | `vol` | V | Per-device; mV ÷ 1000 |

### Grid connection & system (diagnostic)

| Entity name | MQTT field | Unit | Notes |
| --- | --- | --- | --- |
| Grid Voltage | `gridConnectionVol` | V | ⊕ Primary only |
| Grid Frequency | `gridConnectionFreq` | Hz | ⊕ Primary only |
| Grid Connection Status | `gridConnectionSta` | — | ⊕ Primary only (e.g. `PANEL_FEED_GRID`) |
| Wi-Fi Signal | `moduleWifiRssi` | dBm | Per-device |

### Binary sensors

Source map: `binary_sensor.py` → `MQTT_BINARY_SENSORS`.
`unique_id = {serial}_{key}`.

| Entity name | MQTT field | Notes |
| --- | --- | --- |
| AC1 Output | `relay2Onoff` | AC1 switch on/off (per EcoFlow docs) |
| AC2 Output | `relay3Onoff` | AC2 switch on/off (per EcoFlow docs) |
| Off-Grid | `sysOffgrid` | Diagnostic; `true` when running off-grid |

### Controls (write)

Source maps: `switch.py`, `number.py`, `select.py` (shared helpers in
`control.py`). There are two kinds of control:

- **Per-device** — the AC output sockets. Each battery has its own AC1/AC2
  relays, so a pair of switches is added to every controllable device that
  exposes them (`relay2Onoff` / `relay3Onoff` present in its store). Set
  commands go to that device's own SN.
- **System-wide** — Feed-in Control, Backup Reserve Level, and Operating Mode.
  These go to the system's **main device SN** (resolved via
  `GET /device/system/main/sn`).

All set commands use `PUT /device/quota`. Each control reads its current state
back from the MQTT feedback field shown below.
`unique_id = {device serial}_{feedback field}`.

| Entity | Platform | Set param | Feedback field | Values |
| --- | --- | --- | --- | --- |
| AC1 Output | switch | `cfgRelay2Onoff` | `relay2Onoff` | on/off; per-device (one per battery with AC sockets) |
| AC2 Output | switch | `cfgRelay3Onoff` | `relay3Onoff` | on/off; per-device (one per battery with AC sockets) |
| Feed-in Control | switch | `cfgFeedGridMode` | `feedGridMode` | on=2 (blocks grid export), off=1 (export allowed); mirrors the app toggle |
| Backup Reserve Level | number | `cfgBackupReverseSoc` | `backupReverseSoc` | 3–95 % |
| Operating Mode | select | `cfgEnergyStrategyOperateMode` | `energyStrategyOperateMode` | Settable: Self-powered / AI Optimised. Display-only: Scheduled / Time-of-Use (set in the app; API returns 8524) |

---

## Stream Ultra X — daily energy sensors (REST)

Source map: `energy_map.py` → `ENERGY_SENSORS`, polled by
`StreamEnergyCoordinator` from `POST /device/quota/data`.
`unique_id = {serial}_energy_{key}`. All are kWh, `total_increasing`, and reset
at local midnight (the poll queries the midnight → now window).

**⊕ Primary only** — the energy codes are `MASTER_DATA` level and return
identical data regardless of which device SN is queried. The coordinator is
therefore only created for the master device; secondary devices have these
entities disabled in the registry to avoid duplicates.

| Entity name | Key | REST code (`code`) | Split |
| --- | --- | --- | --- |
| Solar Energy Today | `solar` | `ENERGY_CODE_SOLAR` | — |
| Consumption Today | `consumption` | `ENERGY_CODE_CONSUMPTION` | — |
| Grid Import Today | `grid_import` | `ENERGY_CODE_GRID` | `extra="1"` |
| Grid Export Today | `grid_export` | `ENERGY_CODE_GRID` | `extra="2"` |
| Battery Charge Today | `battery_charge` | `ENERGY_CODE_BATTERY` | `extra="1"` |
| Battery Discharge Today | `battery_discharge` | `ENERGY_CODE_BATTERY` | `extra="2"` |

> The `ENERGY_CODE_*` values (see `const.py`) are hard-coded to the Stream
> Ultra X product prefix `BK621`. Device SNs start with `BK61`. On other models
> the API returns code `1006` (unsupported), so these six sensors are not created.

---

## Smart Meter — live sensors (MQTT)

Source map: `sensor_map.py` → `METER_SENSORS`. A Smart Meter (SN prefix `BK21`)
reports only grid metering. `unique_id = {serial}_{MQTT field}`.

| Entity name | MQTT field | Unit | Notes |
| --- | --- | --- | --- |
| Grid Power | `powGetSysGrid` | W | Signed total |
| Grid Power L1 | `gridConnectionPowerL1` | W | |
| Grid Power L2 | `gridConnectionPowerL2` | W | |
| Grid Power L3 | `gridConnectionPowerL3` | W | |
| Grid Power Factor | `gridConnectionPowerFactor` | — | |
| Grid Current L1 | `gridConnectionAmpL1` | A | |
| Grid Current L2 | `gridConnectionAmpL2` | A | |
| Grid Current L3 | `gridConnectionAmpL3` | A | |
| Grid Voltage L1 | `gridConnectionVolL1` | V | Diagnostic |
| Grid Voltage L2 | `gridConnectionVolL2` | V | Diagnostic |
| Grid Voltage L3 | `gridConnectionVolL3` | V | Diagnostic |
| Grid Connection Status | `gridConnectionSta` | — | Diagnostic |

## Smart Meter — daily energy sensors (derived)

Source: `meter_energy.py`. The Public API exposes only the meter's instantaneous
power, so these kWh totals are **integrated locally** (trapezoidal) from the live
`powGetSysGrid` field, reset at local midnight, `total_increasing`.
`unique_id = {serial}_meter_energy_{direction}`.

| Entity name | Derived from | Unit | Notes |
| --- | --- | --- | --- |
| Grid Import Today | `powGetSysGrid` (integrated) | kWh | Import when sign matches `IMPORT_IS_POSITIVE` |
| Grid Export Today | `powGetSysGrid` (integrated) | kWh | Opposite sign of import |

---

## Availability

MQTT-backed sensors report their last value across brief broker reconnects and
only become **unavailable** after a genuine outage (no telemetry for
`MQTT_OUTAGE_SEC`, default 300 s). A sensor also stays unavailable until its
field has been seen at least once, so expect some sensors to populate gradually
after startup. See the README "Notes & caveats" for details.

Per-device sensors on a secondary battery with no solar panels (e.g. `Solar
Power PV1–PV4`) will remain `unavailable` until panels are connected; this is
expected and those entities should not be disabled.


- **MQTT** — a field from the incremental telemetry the device pushes to the
  EcoFlow MQTT broker (topic `/open/{account}/{sn}/quota`). The coordinator
  keeps a merged snapshot of every field seen so far.
- **REST** — a value fetched over the signed HTTP API
  (`POST /iot-open/sign/device/quota/data`), polled every 5 minutes.

Some sensors are **derived**: computed locally from an MQTT field rather than
read directly (for example, integrating live power into daily kWh).

## Naming and IDs

- `_attr_has_entity_name` is `True`, so each entity's `entity_id` is generated
  from the **device name** (as it appears in the EcoFlow app) plus the sensor
  name, e.g. `sensor.stream_ultra_x_solar_power`.
- Each entity's `unique_id` is stable and serial-based (`{serial}_{key}`), so
  renaming the device does not orphan history.
- "Diagnostic" entities are created in the **Diagnostic** category and are still
  enabled by default unless noted.

---

## Stream Ultra X — live sensors (MQTT)

Source map: `sensor_map.py` → `MQTT_SENSORS`. `unique_id = {serial}_{MQTT field}`.

### Power flow

| Entity name | MQTT field | Unit | Notes |
| --- | --- | --- | --- |
| Solar Power | `powGetPvSum` | W | Total PV input |
| Battery Power | `powGetBpCms` | W | Signed; discharge is negative |
| Grid Power | `powGetSysGrid` | W | Signed grid exchange |
| Load Power | `powGetSysLoad` | W | Total home load |
| Grid Connection Power | `gridConnectionPower` | W | Grid port active power; input positive, feed-in negative |
| Load From Solar | `powGetSysLoadFromPv` | W | |
| Load From Grid | `powGetSysLoadFromGrid` | W | |
| Load From Battery | `powGetSysLoadFromBp` | W | |
| Inverter AC Output | `acTotalActivePower` | W | Total inverter AC active power (grid-tie output) |
| AC1 Output Power | `powGetSchuko1` | W | AC1 socket output |
| AC2 Output Power | `powGetSchuko2` | W | AC2 socket output |
| Solar Power PV1 | `powGetPv` | W | Per-string input |
| Solar Power PV2 | `powGetPv2` | W | Per-string input |
| Solar Power PV3 | `powGetPv3` | W | Per-string input |
| Solar Power PV4 | `powGetPv4` | W | Per-string input |

### Battery

| Entity name | MQTT field | Unit | Notes |
| --- | --- | --- | --- |
| Battery Level | `cmsBattSoc` | % | Displayed to 0 dp |
| Battery Level Precise | `f32ShowSoc` | % | Displayed to 2 dp |
| Battery Health | `cmsBattSoh` | % | Diagnostic |
| Max Charge Level | `cmsMaxChgSoc` | % | Diagnostic |
| Min Discharge Level | `cmsMinDsgSoc` | % | Diagnostic |
| Charge Remaining Time | `cmsChgRemTime` | min | |
| Discharge Remaining Time | `cmsDsgRemTime` | min | |
| Battery Full Energy | `cmsBattFullEnergy` | Wh | Diagnostic |
| Battery Cycles | `cycles` | — | `total_increasing`, diagnostic |
| Total Charge Energy | `accuChgEnergy` | Wh | `total_increasing` (lifetime) |
| Total Discharge Energy | `accuDsgEnergy` | Wh | `total_increasing` (lifetime) |

### Temperatures and voltages (diagnostic)

| Entity name | MQTT field | Unit | Transform |
| --- | --- | --- | --- |
| Max Cell Temperature | `bmsMaxCellTemp` | °C | — |
| Min Cell Temperature | `bmsMinCellTemp` | °C | — |
| Max MOSFET Temperature | `maxMosTemp` | °C | — |
| Temperature | `temp` | °C | — |
| Min Cell Voltage | `minCellVol` | V | mV ÷ 1000 |
| Max Cell Voltage | `maxCellVol` | V | mV ÷ 1000 |
| Battery Voltage | `vol` | V | mV ÷ 1000 |

### Grid connection & system (diagnostic)

| Entity name | MQTT field | Unit |
| --- | --- | --- |
| Grid Voltage | `gridConnectionVol` | V |
| Grid Frequency | `gridConnectionFreq` | Hz |
| Grid Connection Status | `gridConnectionSta` | — (text, e.g. `PANEL_FEED_GRID`) |
| Wi-Fi Signal | `moduleWifiRssi` | dBm |

### Binary sensors

Source map: `binary_sensor.py` → `MQTT_BINARY_SENSORS`.
`unique_id = {serial}_{key}`.

| Entity name | MQTT field | Notes |
| --- | --- | --- |
| AC1 Output | `relay2Onoff` | AC1 switch on/off (per EcoFlow docs) |
| AC2 Output | `relay3Onoff` | AC2 switch on/off (per EcoFlow docs) |
| Off-Grid | `sysOffgrid` | Diagnostic; `true` when running off-grid |

### Controls (write)

Source maps: `switch.py`, `number.py`, `select.py` (shared helpers in
`control.py`). There are two kinds of control:

- **Per-device** — the AC output sockets. Each battery has its own AC1/AC2
  relays, so a pair of switches is added to every controllable device that
  exposes them (`relay2Onoff` / `relay3Onoff` present in its store). Set
  commands go to that device's own SN.
- **System-wide** — Feed-in Control, Backup Reserve Level, and Operating Mode.
  These go to the system's **main device SN** (resolved via
  `GET /device/system/main/sn`).

All set commands use `PUT /device/quota`. Each control reads its current state
back from the MQTT feedback field shown below.
`unique_id = {device serial}_{feedback field}`.

| Entity | Platform | Set param | Feedback field | Values |
| --- | --- | --- | --- | --- |
| AC1 Output | switch | `cfgRelay2Onoff` | `relay2Onoff` | on/off; per-device (one per battery with AC sockets) |
| AC2 Output | switch | `cfgRelay3Onoff` | `relay3Onoff` | on/off; per-device (one per battery with AC sockets) |
| Feed-in Control | switch | `cfgFeedGridMode` | `feedGridMode` | on=2 (blocks grid export), off=1 (export allowed); mirrors the app toggle |
| Backup Reserve Level | number | `cfgBackupReverseSoc` | `backupReverseSoc` | 3–95 % |
| Operating Mode | select | `cfgEnergyStrategyOperateMode` | `energyStrategyOperateMode` | Settable: Self-powered / AI Optimised. Display-only: Scheduled / Time-of-Use (set in the app; API returns 8524) |

---

## Stream Ultra X — daily energy sensors (REST)

Source map: `energy_map.py` → `ENERGY_SENSORS`, polled by
`StreamEnergyCoordinator` from `POST /device/quota/data`.
`unique_id = {serial}_energy_{key}`. All are kWh, `total_increasing`, and reset
at local midnight (the poll queries the midnight → now window).

| Entity name | Key | REST code (`code`) | Split |
| --- | --- | --- | --- |
| Solar Energy Today | `solar` | `ENERGY_CODE_SOLAR` | — |
| Consumption Today | `consumption` | `ENERGY_CODE_CONSUMPTION` | — |
| Grid Import Today | `grid_import` | `ENERGY_CODE_GRID` | `extra="1"` |
| Grid Export Today | `grid_export` | `ENERGY_CODE_GRID` | `extra="2"` |
| Battery Charge Today | `battery_charge` | `ENERGY_CODE_BATTERY` | `extra="1"` |
| Battery Discharge Today | `battery_discharge` | `ENERGY_CODE_BATTERY` | `extra="2"` |

> The `ENERGY_CODE_*` values (see `const.py`) are hard-coded to the Stream
> Ultra X product prefix `BK621`. On other models the API returns code `1006`
> (unsupported) for these, so these six sensors are **not** created.

---

## Smart Meter — live sensors (MQTT)

Source map: `sensor_map.py` → `METER_SENSORS`. A Smart Meter reports only grid
metering. `unique_id = {serial}_{MQTT field}`.

| Entity name | MQTT field | Unit | Notes |
| --- | --- | --- | --- |
| Grid Power | `powGetSysGrid` | W | Signed total |
| Grid Power L1 | `gridConnectionPowerL1` | W | |
| Grid Power L2 | `gridConnectionPowerL2` | W | |
| Grid Power L3 | `gridConnectionPowerL3` | W | |
| Grid Power Factor | `gridConnectionPowerFactor` | — | |
| Grid Current L1 | `gridConnectionAmpL1` | A | |
| Grid Current L2 | `gridConnectionAmpL2` | A | |
| Grid Current L3 | `gridConnectionAmpL3` | A | |
| Grid Voltage L1 | `gridConnectionVolL1` | V | Diagnostic |
| Grid Voltage L2 | `gridConnectionVolL2` | V | Diagnostic |
| Grid Voltage L3 | `gridConnectionVolL3` | V | Diagnostic |
| Grid Connection Status | `gridConnectionSta` | — | Diagnostic |

## Smart Meter — daily energy sensors (derived)

Source: `meter_energy.py`. The Public API exposes only the meter's instantaneous
power, so these kWh totals are **integrated locally** (trapezoidal) from the live
`powGetSysGrid` field, reset at local midnight, `total_increasing`.
`unique_id = {serial}_meter_energy_{direction}`.

| Entity name | Derived from | Unit | Notes |
| --- | --- | --- | --- |
| Grid Import Today | `powGetSysGrid` (integrated) | kWh | Import when sign matches `IMPORT_IS_POSITIVE` |
| Grid Export Today | `powGetSysGrid` (integrated) | kWh | Opposite sign of import |

---

## Availability

MQTT-backed sensors report their last value across brief broker reconnects and
only become **unavailable** after a genuine outage (no telemetry for
`MQTT_OUTAGE_SEC`, default 300 s). A sensor also stays unavailable until its
field has been seen at least once, so expect some sensors to populate gradually
after startup. See the README "Notes & caveats" for details.
