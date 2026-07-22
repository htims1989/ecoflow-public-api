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

    configured_devices = await _discover_devices(hass, entry, api)

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

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _discover_devices(
    hass: HomeAssistant, entry: ConfigEntry, api: EcoflowPublicApi
) -> list[dict]:
    """Return the devices to set up, auto-discovering any newly added ones.

    The stored config entry holds the devices captured when the integration
    was first added. On every startup we re-query the account so that a device
    added later (e.g. a second Stream Ultra X) is picked up automatically,
    without deleting and re-adding the integration. If the account query fails
    we fall back to the devices already stored on the entry.
    """
    stored: list[dict] = list(entry.data[CONF_DEVICES])

    try:
        live = await api.device_list()
    except EcoflowApiError as err:
        _LOGGER.debug("device_list refresh failed, using stored devices: %s", err)
        return stored

    known_sns = {d["sn"] for d in stored}
    new_devices = [
        {"sn": d.sn, "name": d.name} for d in live if d.sn not in known_sns
    ]
    if not new_devices:
        return stored

    merged = stored + new_devices
    _LOGGER.info(
        "Discovered %d new EcoFlow device(s): %s",
        len(new_devices),
        ", ".join(d["sn"] for d in new_devices),
    )
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_DEVICES: merged}
    )
    return merged


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        runtime = hass.data[DOMAIN].pop(entry.entry_id)
        for device in runtime["devices"]:
            await device["mqtt"].async_stop()
    return unload_ok
