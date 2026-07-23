"""Binary sensor platform for EcoFlow Stream (Public API)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, device_model, is_smart_meter
from .coordinator import StreamMqttCoordinator


@dataclass(frozen=True, kw_only=True)
class StreamBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Binary sensor description with an optional value transform."""

    value_fn: Callable[[Any], bool] | None = None


# Binary telemetry for the Stream inverter (not the Smart Meter). Verified live
# against a Stream Ultra X and cross-checked with the EcoFlow Public API docs.
MQTT_BINARY_SENSORS: tuple[StreamBinarySensorEntityDescription, ...] = (
    # AC output switches. Per the EcoFlow Public API docs, relay2Onoff is the
    # "AC1" switch and relay3Onoff the "AC2" switch on the STREAM Ultra X.
    StreamBinarySensorEntityDescription(
        key="relay2Onoff",
        name="AC1 Output",
        device_class=BinarySensorDeviceClass.POWER,
        icon="mdi:power-socket-de",
    ),
    StreamBinarySensorEntityDescription(
        key="relay3Onoff",
        name="AC2 Output",
        device_class=BinarySensorDeviceClass.POWER,
        icon="mdi:power-socket-de",
    ),
    StreamBinarySensorEntityDescription(
        key="sysOffgrid",
        name="Off-Grid",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:transmission-tower-off",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EcoFlow Stream binary sensors from a config entry."""
    runtime = hass.data[DOMAIN][entry.entry_id]

    entities: list[BinarySensorEntity] = []
    for device in runtime["devices"]:
        sn = device["sn"]
        if is_smart_meter(sn):
            continue
        mqtt_coord: StreamMqttCoordinator = device["mqtt"]
        device_info = _device_info(sn, device["name"])
        for description in MQTT_BINARY_SENSORS:
            entities.append(
                StreamMqttBinarySensor(mqtt_coord, description, sn, device_info)
            )

    async_add_entities(entities)


def _device_info(sn: str, name: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, sn)},
        name=name,
        manufacturer="EcoFlow",
        model=device_model(sn),
        serial_number=sn,
    )


class StreamMqttBinarySensor(BinarySensorEntity):
    """A binary sensor backed by the merged MQTT telemetry store."""

    _attr_has_entity_name = True
    entity_description: StreamBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: StreamMqttCoordinator,
        description: StreamBinarySensorEntityDescription,
        sn: str,
        device_info: DeviceInfo,
    ) -> None:
        self._coordinator = coordinator
        self.entity_description = description
        self._attr_unique_id = f"{sn}_{description.key}"
        self._attr_device_info = device_info

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._coordinator.async_add_listener(self._handle_update)
        )
        self._handle_update()

    @property
    def available(self) -> bool:
        return (
            self.entity_description.key in self._coordinator.data
            and not self._coordinator.stale
        )

    @callback
    def _handle_update(self) -> None:
        raw = self._coordinator.data.get(self.entity_description.key)
        if raw is None:
            self._attr_is_on = None
        elif self.entity_description.value_fn is not None:
            self._attr_is_on = self.entity_description.value_fn(raw)
        else:
            self._attr_is_on = bool(raw)
        if self.hass is not None:
            self.async_write_ha_state()
