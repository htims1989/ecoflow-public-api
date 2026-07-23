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
from .coordinator import StreamEnergyCoordinator, StreamMqttCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


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

        mqtt_coord = StreamMqttCoordinator(hass, creds, sn, group, snapshot)
        await mqtt_coord.async_start()

        # Smart Meters have no historical energy aggregates (quota/data -> 1006),
        # so skip the energy coordinator for them entirely.
        energy_coord: StreamEnergyCoordinator | None = None
        if not is_smart_meter(sn):
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

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"devices": devices}

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
        for device in runtime["devices"]:
            await device["mqtt"].async_stop()
    return unload_ok
