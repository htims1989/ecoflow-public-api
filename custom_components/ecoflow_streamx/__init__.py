"""The EcoFlow Stream (Public API) integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EcoflowApiError, EcoflowPublicApi
from .const import (
    CONF_ACCESS_KEY,
    CONF_API_HOST,
    CONF_DEVICES,
    CONF_GROUP,
    CONF_SECRET_KEY,
    DOMAIN,
    is_smart_meter,
)
from .coordinator import (
    StreamEnergyCoordinator,
    StreamMqttCoordinator,
    StreamMqttHub,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EcoFlow Stream from a config entry."""
    session = async_get_clientsession(hass)
    api = EcoflowPublicApi(
        session,
        entry.data[CONF_API_HOST],
        entry.data[CONF_ACCESS_KEY],
        entry.data[CONF_SECRET_KEY],
    )
    group = entry.data[CONF_GROUP]

    creds = await api.certification()

    configured_devices = await _resolve_devices(hass, entry, api)

    # Set commands must target the main device SN of the (possibly multi-device)
    # system. Resolve it once from the first configured device; fall back to the
    # device's own SN if the lookup is unavailable.
    main_sn: str | None = None
    if configured_devices:
        first_sn = configured_devices[0]["sn"]
        try:
            main_sn = await api.main_device_sn(first_sn)
        except EcoflowApiError as err:
            _LOGGER.debug("main device SN lookup failed: %s", err)
            main_sn = first_sn

    # A single MQTT connection serves the whole account; all device
    # coordinators are routed through it. This avoids the connect/disconnect
    # storm that a per-device client (sharing one broker client id) causes.
    hub = StreamMqttHub(hass, api, creds, group)

    devices: list[dict] = []
    for device in configured_devices:
        sn = device["sn"]

        # Seed the MQTT store with a REST snapshot so core sensors (battery
        # level, power flows) are populated immediately at startup rather than
        # waiting for the first BMS heartbeat.
        try:
            snapshot = await api.quota_all(sn)
        except EcoflowApiError as err:
            _LOGGER.debug("quota/all snapshot unavailable for %s: %s", sn, err)
            snapshot = {}

        mqtt_coord = StreamMqttCoordinator(hass, sn, snapshot)
        hub.register(mqtt_coord)
        mqtt_coord.start()

        # Historical energy aggregates are system-level (MASTER_DATA codes)
        # and only need to be fetched once, from the main device. Secondary
        # cascade batteries would return identical data, producing duplicates.
        # Smart Meters have no energy aggregates at all (quota/data -> 1006).
        energy_coord: StreamEnergyCoordinator | None = None
        if not is_smart_meter(sn) and sn == main_sn:
            energy_coord = StreamEnergyCoordinator(hass, api, sn)
            await energy_coord.async_config_entry_first_refresh()
            if not energy_coord.supported:
                energy_coord = None

        devices.append(
            {
                "sn": sn,
                "name": device["name"],
                "mqtt": mqtt_coord,
                "energy": energy_coord,
            }
        )

    # Connect once, after all device topics have been registered, so the
    # initial subscribe covers every device.
    await hub.async_start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "devices": devices,
        "api": api,
        "main_sn": main_sn,
        "hub": hub,
    }

    # Reload when the options flow changes the enabled-device selection.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when its options/devices change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _resolve_devices(
    hass: HomeAssistant, entry: ConfigEntry, api: EcoflowPublicApi
) -> list[dict]:
    """Return the devices to set up, based on the user's saved selection.

    The config/options flow lets the user choose exactly which devices to
    enable, and that selection (stored on the entry) is authoritative. We do
    NOT auto-add devices here: a device the user deselected (for example, a
    removed unit that the account API still reports) must stay disabled instead
    of reappearing on every restart. We only refresh the display names from the
    live account list when it is reachable.

    To add newly-purchased hardware, use the integration's **Configure**
    (options) screen to re-scan and tick the new device.
    """
    stored: list[dict] = list(entry.data[CONF_DEVICES])

    try:
        live = await api.device_list()
    except EcoflowApiError as err:
        _LOGGER.debug("device_list refresh failed, using stored devices: %s", err)
        return stored

    live_names = {d.sn: d.name for d in live}
    return [
        {"sn": d["sn"], "name": live_names.get(d["sn"], d["name"])}
        for d in stored
    ]


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        runtime = hass.data[DOMAIN].pop(entry.entry_id)
        await runtime["hub"].async_stop()
        for device in runtime["devices"]:
            device["mqtt"].stop()
    return unload_ok
