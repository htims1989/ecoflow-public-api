# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.3] - 2026-07-23

### Changed
- Renamed the **AC Output Power** sensor (`acTotalActivePower`) to **Inverter AC
  Output** to distinguish it from **Grid Connection Power** (`gridConnectionPower`).
  The two read almost identically when all inverter output feeds the grid, but
  they are separate API measurements and can diverge.

## [0.4.2] - 2026-07-23

### Fixed
- Operating Mode select showed **Unknown** when the device was in a mode other
  than Self-powered or AI Optimised. It now also recognises and displays
  **Scheduled** and **Time-of-Use**. These two are read-only (the Public API
  rejects setting them with `8524: Validation failed` — they are configured in
  the EcoFlow app); selecting them raises a clear error instead of silently
  doing nothing.

## [0.4.1] - 2026-07-23

### Fixed
- Control set commands failed with `8521: signature is wrong`. Booleans are now
  serialised as lowercase `true`/`false` in the request signature (matching the
  JSON body), and list values are flattened with `key[i]` indices. Switches,
  the backup-reserve number, and the operating-mode select now work.

## [0.4.0] - 2026-07-23

### Added
- **Device control** (write support) for the Stream inverter, using the
  documented EcoFlow Public API set commands (`PUT /device/quota`):
  - `switch` **AC1 Output** (`cfgRelay2Onoff`) and **AC2 Output**
    (`cfgRelay3Onoff`).
  - `switch` **Grid Feed-in** (`cfgFeedGridMode`; 1 = off, 2 = on).
  - `number` **Backup Reserve Level** (`cfgBackupReverseSoc`, 3–95%).
  - `select` **Operating Mode** (Self-powered / AI Optimised, via
    `cfgEnergyStrategyOperateMode`).
  Controls target the system's main device SN (resolved via
  `GET /device/system/main/sn`) and reflect live state from MQTT feedback.
- New `switch`, `number`, and `select` platforms.
- AC output entities for the Stream inverter, mapped from live telemetry and
  cross-checked against the EcoFlow Public API field reference:
  - `sensor` **AC Output Power** (`acTotalActivePower`), **AC1 Output Power**
    (`powGetSchuko1`), **AC2 Output Power** (`powGetSchuko2`).
  - `sensor` **Grid Connection Status** (`gridConnectionSta`, diagnostic text).
  - `binary_sensor` **AC1 Output** (`relay2Onoff`) and **AC2 Output**
    (`relay3Onoff`) — the documented AC1/AC2 switches — plus **Off-Grid**
    (`sysOffgrid`, diagnostic).
- New `binary_sensor` platform.

## [0.2.2] - 2026-07-23

### Changed
- Energy-aggregate requests within a poll are now issued **sequentially with a
  short gap** (`ENERGY_REQUEST_STAGGER_SEC`, default 1 s) instead of concurrently,
  to stay under EcoFlow's per-second HTTP burst limit.

### Added
- "Rate limiting" section in the README documenting how the integration stays
  within EcoFlow's Public API limits (push-based MQTT, fixed client ID, reconnect
  backoff, infrequent staggered REST polls).

## [0.2.1] - 2026-07-23

### Added
- Integration icon, shipped locally via `custom_components/ecoflow_streamx/brand/`
  (`icon.png`, `icon@2x.png`). Home Assistant 2026.3+ serves local brand images
  directly and they take precedence over the home-assistant/brands repository, so
  the icon now appears via HACS with no external PR required.
- `scripts/generate_icon.py` to (re)generate the icon assets. It lives outside the
  integration directory so it is not shipped to users installing via HACS.

## [0.2.0] - 2026-07-23

### Added
- **Device selection** during setup. The config flow now has a second step that
  lists the devices discovered on your account and lets you tick exactly which
  ones Home Assistant should set up.
- **Options flow** (integration → **Configure**) to change the enabled-device
  selection at any time. It re-scans your account so newly added hardware
  appears, and reloads the integration automatically when the selection
  changes.
- **Entity mapping reference** documentation
  ([`docs/entity_mapping.md`](docs/entity_mapping.md)) listing every sensor and
  the exact MQTT field or REST endpoint it is sourced from, plus units and
  value transforms. Linked from the README.
- README disclaimer that MQTT telemetry is incremental, so entities may show as
  **unavailable** for a few minutes after setup or a restart until each field
  has been seen at least once.
- Dashboard screenshots (Overview, Solar, Battery, Grid) in the README.
- "Supported devices" section in the README clarifying that only the Stream
  Ultra X and Smart Meter are fully supported.

### Changed
- **Device resolution is now selection-driven rather than auto-adding.** The
  saved device selection is authoritative: a device you did not select (for
  example, one removed from your account that the API still reports) is no
  longer set up. Display names are still refreshed from the live account list
  when reachable. To add newly purchased hardware, use the **Configure**
  screen.

### Fixed
- **MQTT reconnect storm.** A device that the broker keeps dropping (such as a
  removed unit still returned by the API) previously triggered a tight
  reconnect loop that logged tens of thousands of warnings. The MQTT client now
  uses exponential reconnect backoff (2 s → 300 s), and a disconnect is logged
  once at `WARNING` and then stays quiet until the connection is restored.

## [0.1.0] - 2026-07-22

### Added
- Initial release of the EcoFlow Stream (Public API) integration.
- Near-real-time power-flow sensors (solar, battery, grid, home load) via the
  EcoFlow MQTT broker, seeded from a REST `quota/all` snapshot at startup.
- Per-string PV power, battery state (SoC, health, cycles, temperatures,
  time-to-full/empty) and diagnostic sensors for the Stream Ultra X.
- Daily energy sensors (`*_today`) for solar, consumption, grid import/export
  and battery charge/discharge, polled from the historical `quota/data`
  aggregates for the Energy Dashboard.
- Smart Meter support: whole-house grid power (per phase) plus derived daily
  grid import/export energy, integrated locally from live power and reset at
  local midnight.
- Config flow with region selection and HMAC-signed Public API authentication.
- Ready-made Lovelace dashboard (`dashboards/solar_dashboard.yaml`).

[0.4.3]: https://github.com/htims1989/ecoflow-public-api/releases/tag/v0.4.3
[0.4.2]: https://github.com/htims1989/ecoflow-public-api/releases/tag/v0.4.2
[0.4.1]: https://github.com/htims1989/ecoflow-public-api/releases/tag/v0.4.1
[0.4.0]: https://github.com/htims1989/ecoflow-public-api/releases/tag/v0.4.0
[0.2.2]: https://github.com/htims1989/ecoflow-public-api/releases/tag/v0.2.2
[0.2.1]: https://github.com/htims1989/ecoflow-public-api/releases/tag/v0.2.1
[0.2.0]: https://github.com/htims1989/ecoflow-public-api/releases/tag/v0.2.0
[0.1.0]: https://github.com/htims1989/ecoflow-public-api/releases/tag/v0.1.0
