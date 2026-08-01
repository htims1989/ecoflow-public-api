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
    EcoflowApiError,
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
    ENERGY_REQUEST_STAGGER_SEC,
    MQTT_CRED_REFRESH_COOLDOWN_SEC,
    MQTT_OUTAGE_SEC,
    MQTT_STALE_SEC,
    MQTT_WATCHDOG_CHECK_SEC,
    MQTT_WATCHDOG_SEC,
)

_LOGGER = logging.getLogger(__name__)


class StreamMqttCoordinator:
    """Holds a single device's merged telemetry state.

    The EcoFlow Public API pushes *incremental* JSON payloads: each message
    carries only the fields that changed. Consumers need the full current
    state, so this coordinator keeps a persistent dict and merges every
    message into it, notifying listeners after each update.

    This class no longer owns an MQTT connection. A single shared
    :class:`StreamMqttHub` per config entry maintains one broker connection for
    the whole account and routes each device's messages to its coordinator via
    :meth:`ingest`. That matches the EcoFlow broker's model (one client id is
    bound to the account and may subscribe to any of its devices) and avoids
    the mutual-kickout disconnect loop that arises when several clients share a
    client id.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        sn: str,
        initial: dict[str, Any] | None = None,
    ) -> None:
        self.hass = hass
        self.sn = sn
        # Seed with a REST snapshot (quota/all) so core sensors such as the
        # battery level are available immediately, without waiting for the
        # first ~20s BMS heartbeat over MQTT.
        self.data: dict[str, Any] = dict(initial) if initial else {}
        self._listeners: list[Any] = []
        self._last_message_ts: float = 0.0
        self._cancel_timer: Any = None
        # Whether the "gone stale" transition has already been logged, so the
        # availability tick (every AVAILABILITY_CHECK_SEC) doesn't repeat it.
        self._stale_logged = False

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

    @property
    def last_message_age(self) -> float | None:
        """Seconds since the last telemetry message, or None if never seen."""
        if self._last_message_ts == 0.0:
            return None
        return time.time() - self._last_message_ts

    @property
    def status(self) -> str:
        """Graduated freshness: healthy / degraded / unavailable.

        ``online``/``stale`` already drive entity availability (unchanged);
        this just names the gap between them for display, rather than
        entities snapping straight from fresh to unavailable with nothing
        in between visible to the user.
        """
        if self.online:
            return "healthy"
        if not self.stale:
            return "degraded"
        return "unavailable"

    @callback
    def async_add_listener(self, update_callback: Any) -> Any:
        """Register a listener; returns an unsubscribe callable."""
        self._listeners.append(update_callback)

        def _remove() -> None:
            if update_callback in self._listeners:
                self._listeners.remove(update_callback)

        return _remove

    def start(self) -> None:
        """Start the availability tick timer.

        The shared hub owns the MQTT connection; this only arms the periodic
        re-notification so entities can transition to "unavailable" during a
        real outage even though no messages arrive.
        """
        self._cancel_timer = async_track_time_interval(
            self.hass,
            self._async_availability_tick,
            timedelta(seconds=AVAILABILITY_CHECK_SEC),
        )

    def stop(self) -> None:
        """Cancel the availability tick timer."""
        if self._cancel_timer is not None:
            self._cancel_timer()
            self._cancel_timer = None

    @callback
    def _async_availability_tick(self, _now: Any) -> None:
        if self.stale and not self._stale_logged:
            self._stale_logged = True
            _LOGGER.warning(
                "%s: no MQTT telemetry for %.0fs; sensors going unavailable",
                self.sn,
                time.time() - self._last_message_ts,
            )
        self._notify_listeners()

    def ingest(self, params: dict[str, Any]) -> None:
        """Merge an incremental payload into the store (called by the hub).

        Runs in the MQTT network thread. The merge and timestamp update happen
        here; listener notification is marshalled onto the HA event loop.
        """
        if self._stale_logged:
            self._stale_logged = False
            _LOGGER.info("%s: MQTT telemetry resumed after outage", self.sn)
        self.data.update(params)
        self._last_message_ts = time.time()
        self.hass.loop.call_soon_threadsafe(self._notify_listeners)

    @callback
    def _notify_listeners(self) -> None:
        for update_callback in list(self._listeners):
            update_callback()


class StreamMqttHub:
    """A single MQTT connection for one account, shared across all its devices.

    The EcoFlow Public API broker binds a client id to the account, and that
    one client may subscribe to any device registered to the account. Using a
    single connection (rather than one per device sharing a client id) avoids
    the broker kicking earlier connections off when a new one with the same id
    arrives, which previously produced a storm of connect/disconnect warnings
    on multi-device systems.
    """

    def __init__(
        self, hass: HomeAssistant, api: EcoflowPublicApi, creds: MqttCredentials, group: str
    ) -> None:
        self.hass = hass
        self._api = api
        self._creds = creds
        self._client: mqtt.Client | None = None
        # topic -> coordinator that should receive its payloads.
        self._routes: dict[str, StreamMqttCoordinator] = {}
        # A fixed, deterministic client id keeps us within the
        # 10-unique-ids-per-day limit: the same id is reused on every restart
        # so restarts don't burn through the quota. One id serves the whole
        # account, since a single client can subscribe to every device topic.
        safe_group = group.replace(" ", "-")
        self._client_id = f"ecoflow-streamx-{creds.account}-{safe_group}"
        # Whether an active disconnect has already been logged at WARNING, so a
        # flapping broker does not spam the log on every retry.
        self._disconnect_logged = False
        # Guards against overlapping /certification calls and throttles how
        # often a persistently-refused connection re-fetches credentials.
        self._refresh_task: Any = None
        self._last_cred_refresh: float = 0.0
        # Timestamp of the last activity of any kind on the connection
        # (a successful connect or any inbound message, regardless of topic).
        # The watchdog force-reconnects when this goes stale for too long, as
        # a backstop against failures paho itself never notices (see
        # _async_watchdog_tick).
        self._last_activity_ts: float = time.time()
        self._cancel_watchdog: Any = None
        # Counts consecutive recovery attempts (auth refusals + watchdog
        # force-reconnects) since data last flowed successfully. Drives log
        # severity: a first, isolated hiccup logs quietly since paho/the
        # watchdog resolve most of these on their own; only a *sustained*
        # run of failures (this counter climbing) is worth a WARNING.
        # Resets to 0 the moment any message arrives.
        self._reconnect_attempts: int = 0
        # Guards the client-mutating sections of _async_force_reconnect and
        # _async_refresh_credentials. Both run as separate event-loop tasks
        # (one from the watchdog tick, one triggered from the MQTT thread via
        # call_soon_threadsafe) and could otherwise interleave — e.g. a
        # credential refresh updating username/password on the same client
        # object the watchdog is mid-way through tearing down and recreating.
        self._client_lock = asyncio.Lock()

    @property
    def reconnect_attempts(self) -> int:
        """Consecutive recovery attempts since data last flowed. See __init__."""
        return self._reconnect_attempts

    @property
    def is_connected(self) -> bool:
        """Whether the underlying paho client currently reports connected.

        Reflects TCP/MQTT session state only — a connected-but-silent client
        (the exact failure mode the watchdog exists for) still reports True
        here. Per-device data freshness is ``StreamMqttCoordinator.status``.
        """
        return self._client is not None and self._client.is_connected()

    def register(self, coordinator: StreamMqttCoordinator) -> None:
        """Route a device's quota topic to its coordinator.

        Must be called before :meth:`async_start` (topics are subscribed on
        connect).
        """
        topic = f"/open/{self._creds.account}/{coordinator.sn}/quota"
        self._routes[topic] = coordinator

    async def async_start(self) -> None:
        """Create the single MQTT client and connect in the executor."""
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id=self._client_id
        )
        client.username_pw_set(self._creds.account, self._creds.password)
        context = await self.hass.async_add_executor_job(ssl.create_default_context)
        client.tls_set_context(context)
        # Exponential reconnect backoff caps the retry rate if the broker keeps
        # dropping the connection.
        client.reconnect_delay_set(min_delay=2, max_delay=300)
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect
        self._client = client

        await self.hass.async_add_executor_job(
            client.connect, self._creds.host, self._creds.port, 60
        )
        client.loop_start()
        self._last_activity_ts = time.time()

        self._cancel_watchdog = async_track_time_interval(
            self.hass,
            self._async_watchdog_tick,
            timedelta(seconds=MQTT_WATCHDOG_CHECK_SEC),
        )

    async def async_stop(self) -> None:
        """Disconnect and tear down the MQTT client."""
        if self._cancel_watchdog is not None:
            self._cancel_watchdog()
            self._cancel_watchdog = None
        if self._client is not None:
            await self.hass.async_add_executor_job(self._client.loop_stop)
            await self.hass.async_add_executor_job(self._client.disconnect)
            self._client = None

    # --- paho callbacks (run in the MQTT network thread) ---

    def _on_connect(self, client: mqtt.Client, _userdata, _flags, reason_code, _props=None) -> None:
        # Every paho callback runs in the background network thread, and paho
        # re-raises callback exceptions by default (suppress_exceptions is
        # False). An uncaught exception here would propagate out of
        # loop_forever() and silently kill that thread — the `finally` in
        # paho's _thread_main clears self._thread but nothing else notices,
        # so the client goes permanently quiet with no error logged anywhere.
        # The watchdog (_async_watchdog_tick) is the backstop for that; this
        # try/except is the prevention.
        try:
            self._on_connect_impl(client, reason_code)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unhandled error in MQTT on_connect callback")

    def _on_connect_impl(self, client: mqtt.Client, reason_code) -> None:
        self._last_activity_ts = time.time()
        # paho calls on_connect for every CONNACK, including refusals (e.g.
        # bad/expired credentials). The broker closes the socket right after a
        # refusal, so treating this as a live connection would reset the
        # disconnect-log suppression and attempt to subscribe on a connection
        # that's already dead, masking the real reason in the logs.
        if reason_code.is_failure:
            self._reconnect_attempts += 1
            _log = _LOGGER.warning if self._reconnect_attempts > 1 else _LOGGER.info
            _log(
                "MQTT connection refused (%s); refreshing credentials from"
                " /certification (attempt %d)",
                reason_code,
                self._reconnect_attempts,
            )
            # paho retries forever with the *same* username/password it was
            # given at connect() time — it never re-fetches credentials on its
            # own. If /certification issues a short-lived password, every
            # retry after expiry fails identically and only a full integration
            # reload (which re-runs certification()) used to recover. Refresh
            # here instead so the existing connection self-heals.
            self.hass.loop.call_soon_threadsafe(self._schedule_cred_refresh)
            return

        self._disconnect_logged = False
        # (Re)subscribe to every device topic on each successful connect so a
        # reconnect restores all subscriptions.
        for topic in self._routes:
            _LOGGER.debug("MQTT connected (rc=%s); subscribing %s", reason_code, topic)
            client.subscribe(topic, qos=0)

    def _on_disconnect(self, _client, _userdata, _flags, reason_code, _props=None) -> None:
        try:
            self._on_disconnect_impl(reason_code)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unhandled error in MQTT on_disconnect callback")

    def _on_disconnect_impl(self, reason_code) -> None:
        # Log the first drop at WARNING, then stay quiet until we reconnect, so
        # a persistently unreachable broker cannot flood the log (paho keeps
        # retrying in the background with the configured backoff).
        if self._disconnect_logged:
            _LOGGER.debug("MQTT still disconnected (rc=%s)", reason_code)
            return
        self._disconnect_logged = True
        # A first, isolated disconnect is normal (broker-side session
        # rotation, brief network blip) and paho's own reconnect usually
        # clears it — not worth a WARNING. Escalate only once attempts are
        # already piling up, i.e. the previous recovery try didn't stick.
        _log = _LOGGER.warning if self._reconnect_attempts > 0 else _LOGGER.info
        _log("MQTT disconnected (rc=%s); paho will auto-reconnect", reason_code)

    @callback
    def _schedule_cred_refresh(self) -> None:
        """Kick off a throttled, de-duplicated credential refresh.

        Runs on the HA event loop (marshalled from the MQTT thread via
        call_soon_threadsafe). Skips if a refresh is already in flight or one
        completed too recently — a broker that keeps refusing for a
        non-credential reason would otherwise hammer /certification on every
        paho retry (as fast as every 2s).
        """
        if self._refresh_task is not None and not self._refresh_task.done():
            _LOGGER.debug("Credential refresh already in progress; skipping")
            return
        elapsed = time.time() - self._last_cred_refresh
        if elapsed < MQTT_CRED_REFRESH_COOLDOWN_SEC:
            _LOGGER.debug(
                "Credential refresh requested %.0fs ago; waiting out cooldown",
                elapsed,
            )
            return
        self._last_cred_refresh = time.time()
        self._refresh_task = self.hass.async_create_task(
            self._async_refresh_credentials(), name="ecoflow_streamx_mqtt_cred_refresh"
        )

    async def _async_refresh_credentials(self) -> None:
        try:
            creds = await self._api.certification()
        except EcoflowApiError as err:
            _LOGGER.warning("MQTT credential refresh failed: %s", err)
            return

        changed = creds.password != self._creds.password
        self._creds = creds
        async with self._client_lock:
            if self._client is not None:
                self._client.username_pw_set(creds.account, creds.password)
                _LOGGER.info(
                    "MQTT credentials refreshed (password changed: %s);"
                    " paho will use them on its next reconnect attempt",
                    changed,
                )

    def _on_message(self, _client, _userdata, message: mqtt.MQTTMessage) -> None:
        try:
            self._on_message_impl(message)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unhandled error in MQTT on_message callback")

    def _on_message_impl(self, message: mqtt.MQTTMessage) -> None:
        # Any inbound message, even on a topic we don't route, proves the
        # connection and network thread are alive — feed the watchdog before
        # the (much more common) early-return below.
        self._last_activity_ts = time.time()
        # Proof of a genuinely recovered connection, not just a reconnected
        # socket — reset the failure streak so the next isolated hiccup logs
        # quietly again instead of inheriting an old, unrelated attempt count.
        self._reconnect_attempts = 0
        coordinator = self._routes.get(message.topic)
        if coordinator is None:
            return
        try:
            payload = json.loads(message.payload.decode())
        except (ValueError, UnicodeDecodeError):
            _LOGGER.debug("Ignoring non-JSON MQTT payload for %s", coordinator.sn)
            return
        params = payload.get("param", payload.get("params", payload.get("data", payload)))
        if not isinstance(params, dict):
            return
        coordinator.ingest(params)

    # --- watchdog (runs on the HA event loop) ---

    async def _async_watchdog_tick(self, _now: Any) -> None:
        """Force a full reconnect if the connection has gone silent too long.

        paho's own reconnect machinery only engages when paho itself believes
        it is disconnected. A background network thread that dies from an
        uncaught exception, or a TCP session that goes half-open without a
        clean FIN/RST, never trips that path — the client sits there
        indefinitely, connected as far as paho knows, receiving nothing. This
        is a root-cause-agnostic backstop: prolonged silence forces a full
        stop/reconnect/restart regardless of why.
        """
        if self._client is None:
            return
        elapsed = time.time() - self._last_activity_ts
        if elapsed < MQTT_WATCHDOG_SEC:
            return
        self._reconnect_attempts += 1
        # A first, isolated silence is the routine case this watchdog exists
        # for — it's expected to self-heal, so INFO is enough. Escalate to
        # WARNING only once attempts are already piling up, meaning a prior
        # reconnect in this streak didn't actually restore data flow.
        _log = _LOGGER.warning if self._reconnect_attempts > 1 else _LOGGER.info
        _log(
            "No MQTT activity for %.0fs; forcing a full reconnect (attempt %d)",
            elapsed,
            self._reconnect_attempts,
        )
        # Reset immediately so a slow/failed reconnect attempt doesn't cause
        # the next tick (MQTT_WATCHDOG_CHECK_SEC later) to pile on another one.
        self._last_activity_ts = time.time()
        await self._async_force_reconnect()

    async def _async_force_reconnect(self) -> None:
        if self._client_lock.locked():
            _LOGGER.debug(
                "Force-reconnect skipped — a credential refresh or another"
                " reconnect is already in flight"
            )
            return
        async with self._client_lock:
            client = self._client
            if client is None:
                return
            try:
                # Stops (and joins) the background thread if it's still
                # alive; a no-op if it already died on its own, per paho's
                # own bookkeeping.
                await self.hass.async_add_executor_job(client.loop_stop)
                # reconnect() closes any stale socket and opens a fresh one
                # using the credentials already set on the client (possibly
                # refreshed by _async_refresh_credentials since the original
                # connect()).
                await self.hass.async_add_executor_job(client.reconnect)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Watchdog reconnect attempt failed: %s", err)
                return
            client.loop_start()
            _LOGGER.info("MQTT watchdog reconnect issued")


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

        codes = (
            ENERGY_CODE_SOLAR,
            ENERGY_CODE_CONSUMPTION,
            ENERGY_CODE_GRID,
            ENERGY_CODE_BATTERY,
        )
        # Issue the per-code requests sequentially with a short gap rather than
        # concurrently, to stay under EcoFlow's per-second HTTP burst limit.
        gathered: list[list[dict[str, Any]] | BaseException] = []
        for index, code in enumerate(codes):
            if index:
                await asyncio.sleep(ENERGY_REQUEST_STAGGER_SEC)
            try:
                gathered.append(
                    await self._api.energy_aggregate(
                        self._sn, code, begin_str, end_str
                    )
                )
            except BaseException as err:  # noqa: BLE001
                gathered.append(err)

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


def _to_wh(value: Any) -> float:
    """Convert an indexValue to Wh.

    The API returns the string "-" instead of a number for a period with no
    recorded data yet (observed right after local midnight, before any grid
    activity has been logged for the new day) — treat that as zero rather
    than letting the whole coordinator update crash.
    """
    try:
        return float(value) / 1000.0
    except (TypeError, ValueError):
        return 0.0


def _single_wh(data: list[dict[str, Any]]) -> float:
    for item in data:
        if "extra" not in item:
            return _to_wh(item.get("indexValue", 0))
    if data:
        return _to_wh(data[0].get("indexValue", 0))
    return 0.0


def _extra_wh(data: list[dict[str, Any]], extra: str) -> float:
    for item in data:
        if str(item.get("extra")) == extra:
            return _to_wh(item.get("indexValue", 0))
    return 0.0
