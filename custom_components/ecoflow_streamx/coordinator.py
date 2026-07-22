"""Coordinators for the EcoFlow Stream (Public API) integration.

``StreamMqttCoordinator`` maintains a persistent merged view of the incremental
MQTT telemetry pushed by the device (~2s cadence). ``StreamEnergyCoordinator``
polls the historical energy aggregates (Wh) used by the Energy Dashboard.
"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import time
from datetime import timedelta
from typing import Any

import paho.mqtt.client as mqtt

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    EcoflowPublicApi,
    EcoflowUnsupportedError,
    MqttCredentials,
)
from .const import (
    AVAILABILITY_CHECK_SEC,
    ENERGY_CODE_BATTERY,
    ENERGY_CODE_CONSUMPTION,
    ENERGY_CODE_GRID,
    ENERGY_CODE_SOLAR,
    ENERGY_POLL_INTERVAL_SEC,
    MQTT_OUTAGE_SEC,
    MQTT_STALE_SEC,
)

_LOGGER = logging.getLogger(__name__)


class StreamMqttCoordinator:
    """Subscribes to a device's MQTT quota topic and merges partial payloads.

    The EcoFlow Public API pushes *incremental* JSON payloads: each message
    carries only the fields that changed. Consumers need the full current
    state, so this coordinator keeps a persistent dict and merges every
    message into it, notifying listeners after each update.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        creds: MqttCredentials,
        sn: str,
        group: str,
        initial: dict[str, Any] | None = None,
    ) -> None:
        self.hass = hass
        self.sn = sn
        # Seed with a REST snapshot (quota/all) so core sensors such as the
        # battery level are available immediately, without waiting for the
        # first ~20s BMS heartbeat over MQTT.
        self.data: dict[str, Any] = dict(initial) if initial else {}
        self._creds = creds
        self._listeners: list[Any] = []
        self._client: mqtt.Client | None = None
        self._last_message_ts: float = 0.0
        self._cancel_timer: Any = None
        # A fixed client id keeps us within the 10-unique-ids-per-day limit
        # imposed by the EcoFlow Public API MQTT broker.
        safe_group = group.replace(" ", "-")
        self._client_id = f"Hassio-streamx-{creds.account}-{safe_group}"
        self._topic = f"/open/{creds.account}/{sn}/quota"

    @property
    def online(self) -> bool:
        """Whether a fresh MQTT payload has been seen recently."""
        if self._last_message_ts == 0.0:
            return False
        return (time.time() - self._last_message_ts) < MQTT_STALE_SEC

    @property
    def stale(self) -> bool:
        """Whether telemetry has been absent long enough to be a real outage.

        Unlike :attr:`online`, this tolerates brief MQTT reconnects: sensors
        keep their last value until no telemetry has arrived for
        ``MQTT_OUTAGE_SEC``, at which point they become unavailable.
        """
        if self._last_message_ts == 0.0:
            return False
        return (time.time() - self._last_message_ts) >= MQTT_OUTAGE_SEC

    @callback
    def async_add_listener(self, update_callback: Any) -> Any:
        """Register a listener; returns an unsubscribe callable."""
        self._listeners.append(update_callback)

        def _remove() -> None:
            if update_callback in self._listeners:
                self._listeners.remove(update_callback)

        return _remove

    async def async_start(self) -> None:
        """Create the MQTT client and connect in the executor."""
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id=self._client_id
        )
        client.username_pw_set(self._creds.account, self._creds.password)
        context = ssl.create_default_context()
        client.tls_set_context(context)
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect
        self._client = client

        await self.hass.async_add_executor_job(
            client.connect, self._creds.host, self._creds.port, 60
        )
        client.loop_start()

        # Periodically re-notify listeners so entities can transition to
        # "unavailable" during a real outage even though no messages arrive.
        self._cancel_timer = async_track_time_interval(
            self.hass,
            self._async_availability_tick,
            timedelta(seconds=AVAILABILITY_CHECK_SEC),
        )

    @callback
    def _async_availability_tick(self, _now: Any) -> None:
        self._notify_listeners()

    async def async_stop(self) -> None:
        """Disconnect and tear down the MQTT client."""
        if self._cancel_timer is not None:
            self._cancel_timer()
            self._cancel_timer = None
        if self._client is not None:
            await self.hass.async_add_executor_job(self._client.loop_stop)
            await self.hass.async_add_executor_job(self._client.disconnect)
            self._client = None

    # --- paho callbacks (run in the MQTT network thread) ---

    def _on_connect(self, client: mqtt.Client, _userdata, _flags, reason_code, _props=None) -> None:
        _LOGGER.debug("MQTT connected for %s (rc=%s); subscribing %s", self.sn, reason_code, self._topic)
        client.subscribe(self._topic, qos=0)

    def _on_disconnect(self, _client, _userdata, _flags, reason_code, _props=None) -> None:
        _LOGGER.warning("MQTT disconnected for %s (rc=%s); paho will auto-reconnect", self.sn, reason_code)

    def _on_message(self, _client, _userdata, message: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(message.payload.decode())
        except (ValueError, UnicodeDecodeError):
            _LOGGER.debug("Ignoring non-JSON MQTT payload for %s", self.sn)
            return
        params = payload.get("param", payload.get("params", payload.get("data", payload)))
        if not isinstance(params, dict):
            return
        # Merge into the persistent store and notify listeners on the HA loop.
        self.data.update(params)
        self._last_message_ts = time.time()
        self.hass.loop.call_soon_threadsafe(self._notify_listeners)

    @callback
    def _notify_listeners(self) -> None:
        for update_callback in list(self._listeners):
            update_callback()


class StreamEnergyCoordinator(DataUpdateCoordinator[dict[str, float]]):
    """Polls daily energy aggregates (Wh) for the Energy Dashboard.

    Each poll queries the local-midnight -> now window so the values behave as
    daily-reset totals. Sensors expose them with ``last_reset`` at local
    midnight and ``state_class = total``.
    """

    def __init__(self, hass: HomeAssistant, api: EcoflowPublicApi, sn: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"ecoflow_streamx_energy_{sn}",
            update_interval=timedelta(seconds=ENERGY_POLL_INTERVAL_SEC),
        )
        self._api = api
        self._sn = sn
        # Set False once the device is confirmed to not expose energy
        # aggregates (e.g. a Smart Meter returns 1006 for every code).
        self.supported = True

    async def _async_update_data(self) -> dict[str, float]:
        now = dt_util.now()
        begin = now.replace(hour=0, minute=0, second=0, microsecond=0)
        begin_str = begin.strftime("%Y-%m-%d %H:%M:%S")
        end_str = now.strftime("%Y-%m-%d %H:%M:%S")

        result: dict[str, float] = {}

        async def fetch(code: str) -> list[dict[str, Any]]:
            return await self._api.energy_aggregate(self._sn, code, begin_str, end_str)

        codes = (
            ENERGY_CODE_SOLAR,
            ENERGY_CODE_CONSUMPTION,
            ENERGY_CODE_GRID,
            ENERGY_CODE_BATTERY,
        )
        gathered = await asyncio.gather(
            *(fetch(code) for code in codes), return_exceptions=True
        )

        lists: list[list[dict[str, Any]]] = []
        unsupported = 0
        for outcome in gathered:
            if isinstance(outcome, EcoflowUnsupportedError):
                unsupported += 1
                lists.append([])
            elif isinstance(outcome, BaseException):
                raise UpdateFailed(str(outcome)) from outcome
            else:
                lists.append(outcome)

        if unsupported == len(codes):
            # This device has no energy aggregates at all.
            self.supported = False
            return {}

        solar, consumption, grid, battery = lists
        result["solar"] = _single_wh(solar)
        result["consumption"] = _single_wh(consumption)
        result["grid_import"] = _extra_wh(grid, "1")
        result["grid_export"] = _extra_wh(grid, "2")
        result["battery_charge"] = _extra_wh(battery, "1")
        result["battery_discharge"] = _extra_wh(battery, "2")
        return result


def _single_wh(data: list[dict[str, Any]]) -> float:
    for item in data:
        if "extra" not in item:
            return float(item.get("indexValue", 0)) / 1000.0
    if data:
        return float(data[0].get("indexValue", 0)) / 1000.0
    return 0.0


def _extra_wh(data: list[dict[str, Any]], extra: str) -> float:
    for item in data:
        if str(item.get("extra")) == extra:
            return float(item.get("indexValue", 0)) / 1000.0
    return 0.0
