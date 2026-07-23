"""Switch platform for EcoFlow Stream (Public API)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .control import StreamControlEntity, resolve_control_target


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EcoFlow Stream switches from a config entry."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    target = resolve_control_target(runtime)
    if target is None:
        return

    common = {
        "coordinator": target["coordinator"],
        "api": target["api"],
        "target_sn": target["target_sn"],
        "device_sn": target["device_sn"],
        "device_info": target["device_info"],
    }

    async_add_entities(
        [
            StreamRelaySwitch(
                name="AC1 Output", feedback_key="relay2Onoff",
                cfg_key="cfgRelay2Onoff", **common,
            ),
            StreamRelaySwitch(
                name="AC2 Output", feedback_key="relay3Onoff",
                cfg_key="cfgRelay3Onoff", **common,
            ),
            StreamFeedGridSwitch(feedback_key="feedGridMode", **common),
        ]
    )


class StreamRelaySwitch(StreamControlEntity, SwitchEntity):
    """A boolean AC relay switch (AC1/AC2), on/off via ``cfgRelay*Onoff``."""

    _attr_device_class = SwitchDeviceClass.OUTLET

    def __init__(self, *, name: str, cfg_key: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._attr_name = name
        self._cfg_key = cfg_key

    @callback
    def _handle_update(self) -> None:
        raw = self._feedback()
        self._attr_is_on = None if raw is None else bool(raw)
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._send({self._cfg_key: True})
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send({self._cfg_key: False})
        self._attr_is_on = False
        self.async_write_ha_state()


class StreamFeedGridSwitch(StreamControlEntity, SwitchEntity):
    """Grid feed-in control. ``feedGridMode``: 1 = off, 2 = on."""

    _attr_name = "Grid Feed-in"
    _attr_icon = "mdi:transmission-tower-import"

    @callback
    def _handle_update(self) -> None:
        raw = self._feedback()
        self._attr_is_on = None if raw is None else int(raw) == 2
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._send({"cfgFeedGridMode": 2})
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send({"cfgFeedGridMode": 1})
        self._attr_is_on = False
        self.async_write_ha_state()
