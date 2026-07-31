"""Constants for the EcoFlow Stream (Public API) integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "ecoflow_streamx"

# Config entry keys
CONF_ACCESS_KEY: Final = "access_key"
CONF_SECRET_KEY: Final = "secret_key"
CONF_API_HOST: Final = "api_host"
CONF_GROUP: Final = "group"
CONF_DEVICES: Final = "devices"

# Region hosts for the EcoFlow Developer (IoT Open) platform.
API_HOSTS: Final = {
    "EU (api-e.ecoflow.com)": "api-e.ecoflow.com",
    "US / Global (api.ecoflow.com)": "api.ecoflow.com",
}
DEFAULT_API_HOST: Final = "api-e.ecoflow.com"

# Poll interval for historical energy aggregates (quota/data). These change
# slowly and count against the REST rate limit, so poll infrequently.
ENERGY_POLL_INTERVAL_SEC: Final = 300

# Delay between the individual energy-aggregate requests within a single poll.
# The energy coordinator makes one request per code; issuing them sequentially
# with a short gap keeps well under EcoFlow's per-second HTTP burst limit
# instead of firing them all at once.
ENERGY_REQUEST_STAGGER_SEC: Final = 1.0

# The MQTT keep-alive / staleness threshold. If no push arrives within this
# window the device is treated as offline.
MQTT_STALE_SEC: Final = 90

# Longer outage threshold. Sensors keep their last value across brief MQTT
# reconnects, but if no telemetry arrives at all for this long the device is
# treated as genuinely offline and its sensors become unavailable.
MQTT_OUTAGE_SEC: Final = 300

# How often to re-evaluate availability while no telemetry is arriving, so
# sensors can transition to "unavailable" during a real outage.
AVAILABILITY_CHECK_SEC: Final = 60

# Minimum gap between MQTT credential refresh attempts. The broker refuses
# the CONNACK once the certificatePassword from /certification goes stale;
# paho then retries forever with the same (now-permanently-bad) password
# since it never re-fetches credentials on its own. This cooldown stops a
# persistently-refused connection from hammering /certification on every
# retry (paho's own backoff can be as low as 2s).
MQTT_CRED_REFRESH_COOLDOWN_SEC: Final = 60

# How often the hub checks for total MQTT silence (no message on ANY routed
# topic), and how long that silence must persist before it force-reconnects.
# paho's own reconnect logic only runs if paho itself believes it is
# disconnected; a background network thread that dies silently (an uncaught
# exception in a callback, or a TCP session that goes half-open without a
# clean FIN/RST) never trips that path and never recovers on its own. This
# watchdog is a root-cause-agnostic backstop: any prolonged silence forces a
# full stop/reconnect/restart of the client, whatever caused it. The
# threshold is kept below MQTT_OUTAGE_SEC so a recoverable stall gets a
# chance to heal before sensors actually go unavailable.
MQTT_WATCHDOG_CHECK_SEC: Final = 60
MQTT_WATCHDOG_SEC: Final = 240

# Historical energy aggregate codes (verified live for Stream Ultra X, BK621).
# Each maps to POST /device/quota/data with {code, beginTime, endTime}.
ENERGY_CODE_SOLAR: Final = (
    "BK621-App-HOME-SOLAR-ENERGY-FLOW-solor-line-NOTDISTINGUISH-MASTER_DATA"
)
ENERGY_CODE_CONSUMPTION: Final = (
    "BK621-App-HOME-LOAD-ENERGY-FLOW-consumption-prop_arc-NOTDISTINGUISH-MASTER_DATA"
)
ENERGY_CODE_GRID: Final = (
    "BK621-App-HOME-GRID-ENERGY-FLOW-grid_prop_bar-NOTDISTINGUISH-MASTER_DATA"
)
ENERGY_CODE_BATTERY: Final = (
    "BK621-App-HOME-SOC-ENERGY-FLOW-battery-prop_bar-NOTDISTINGUISH-MASTER_DATA"
)


def device_model(sn: str) -> str:
    """Best-effort device model from the serial-number prefix."""
    if sn.startswith("BK21"):
        return "Smart Meter"
    if sn.startswith("BK61"):
        return "Stream Ultra X"
    return "Stream"


def is_smart_meter(sn: str) -> bool:
    """Whether the serial number belongs to a Smart Meter."""
    return sn.startswith("BK21")


def ac_relay_keys(sn: str) -> tuple[str, ...]:
    """Return the AC relay feedback keys that this device's hardware supports.

    The quota/all REST snapshot and MQTT payloads often contain relay fields
    even for models that have no physical AC sockets (the broker returns
    default values for all known keys). Filtering on field presence is
    therefore unreliable; this function uses the SN prefix instead.

    - Smart Meter (BK21): no AC sockets.
    - Stream Max (BK41): one AC socket, ``relay2Onoff`` only.
    - Stream Ultra X (BK61) and all other Stream inverters: two AC sockets,
      ``relay2Onoff`` (AC1) + ``relay3Onoff`` (AC2).
    """
    if is_smart_meter(sn):
        return ()
    if sn.startswith("BK41"):  # Stream Max — single AC socket
        return ("relay2Onoff",)
    # Stream Ultra X (BK61), BK51, BK31, and unknown Stream inverters
    return ("relay2Onoff", "relay3Onoff")

