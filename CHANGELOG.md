# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.2.2]: https://github.com/htims1989/ecoflow-public-api/releases/tag/v0.2.2
[0.2.1]: https://github.com/htims1989/ecoflow-public-api/releases/tag/v0.2.1
[0.2.0]: https://github.com/htims1989/ecoflow-public-api/releases/tag/v0.2.0
[0.1.0]: https://github.com/htims1989/ecoflow-public-api/releases/tag/v0.1.0
