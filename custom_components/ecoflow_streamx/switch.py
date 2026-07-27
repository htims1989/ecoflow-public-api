"""Switch platform for EcoFlow Stream (Public API)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, ac_relay_keys
from .control import StreamControlEntity, control_devices, resolve_control_target


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EcoFlow Stream switches from a config entry."""
    runtime = hass.data[DOMAIN][entry.entry_id]

    entities: list[SwitchEntity] = []

    # AC output sockets are per-battery: each device has its own AC1/AC2
    # relays, so add a pair of switches to every controllable device that
    # actually exposes them. Not all Stream batteries have AC sockets, so we
    # only add a switch when its feedback key is present in the device's store.
    for target in control_devices(runtime):
        common = {
            "coordinator": target["coordinator"],
            "api": target["api"],
            "target_sn": target["target_sn"],
            "device_sn": target["device_sn"],
            "device_info": target["device_info"],
        }
        relay_keys = ac_relay_keys(target["device_sn"])
        if "relay2Onoff" in relay_keys:
            entities.append(
                StreamRelaySwitch(
                    name="AC1 Output", feedback_key="relay2Onoff",
                    cfg_key="cfgRelay2Onoff", **common,
                )
            )
        if "relay3Onoff" in relay_keys:
            entities.append(
                StreamRelaySwitch(
                    name="AC2 Output", feedback_key="relay3Onoff",
                    cfg_key="cfgRelay3Onoff", **common,
                )
            )

    # Feed-in Control is a system-wide setting: attach it once to the main
    # device.
    target = resolve_control_target(runtime)
    if target is not None:
        entities.append(
            StreamFeedGridSwitch(
                feedback_key="feedGridMode",
                coordinator=target["coordinator"],
                api=target["api"],
                target_sn=target["target_sn"],
                device_sn=target["device_sn"],
                device_info=target["device_info"],
            )
        )

    async_add_entities(entities)


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
    """Feed-in Control, mirroring the EcoFlow app toggle of the same name.

    ``feedGridMode``: 2 = Feed-in Control ON (system powers home loads but is
    prevented from exporting to the grid), 1 = OFF (export allowed). Works with
    the Smart Meter to discharge only what the house is consuming.
    """

    _attr_name = "Feed-in Control"
    _attr_icon = "mdi:transmission-tower-off"

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
