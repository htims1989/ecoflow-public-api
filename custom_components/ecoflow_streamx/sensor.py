"""Sensor platform for EcoFlow Stream (Public API)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import RestoreSensor, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, device_model, is_smart_meter
from .coordinator import StreamEnergyCoordinator, StreamMqttCoordinator, StreamMqttHub
from .energy_map import ENERGY_SENSORS, StreamEnergySensorEntityDescription
from .meter_energy import build_meter_energy_sensors
from .sensor_map import (
    METER_SENSORS,
    MQTT_SENSORS,
    StreamSensorEntityDescription,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EcoFlow Stream sensors from a config entry."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    main_sn = runtime.get("main_sn")
    hub: StreamMqttHub = runtime["hub"]

    entities: list[SensorEntity] = []
    for device in runtime["devices"]:
        sn = device["sn"]
        name = device["name"]
        mqtt_coord: StreamMqttCoordinator = device["mqtt"]
        energy_coord: StreamEnergyCoordinator | None = device["energy"]
        device_info = _device_info(sn, name)
        is_main_device = sn == main_sn

        # Role sensor — static diagnostic showing Primary / Secondary.
        if not is_smart_meter(sn):
            entities.append(StreamRoleSensor(sn, is_main_device, device_info))

        # MQTT health — every device rides the same shared connection, so
        # each gets its own freshness reading plus the connection-wide
        # reconnect count.
        entities.append(StreamMqttStatusSensor(mqtt_coord, hub, sn, device_info))

        mqtt_map = METER_SENSORS if is_smart_meter(sn) else MQTT_SENSORS
        for description in mqtt_map:
            # System-level sensors (aggregated power flows, combined SoC, …)
            # are only pushed by the cascade-system master device. Skip them
            # for secondary batteries to avoid showing stale 0 values.
            if description.system_only and not is_main_device:
                continue
            entities.append(
                StreamMqttSensor(mqtt_coord, description, sn, device_info)
            )

        # Disable any stale system_only / energy entities that remain in the
        # registry for this secondary device from a previous integration run
        # (before the system_only flag was introduced). They will never be
        # provided again, so marking them disabled keeps the device page clean
        # while still allowing the user to re-enable them if desired.
        if not is_main_device and not is_smart_meter(sn):
            registry = er.async_get(hass)
            stale_unique_ids = (
                [f"{sn}_{d.key}" for d in MQTT_SENSORS if d.system_only]
                + [f"{sn}_energy_{d.key}" for d in ENERGY_SENSORS]
            )
            for uid in stale_unique_ids:
                entity_id = registry.async_get_entity_id("sensor", DOMAIN, uid)
                if entity_id:
                    entry = registry.async_get(entity_id)
                    if entry and not entry.disabled:
                        registry.async_update_entity(
                            entity_id,
                            disabled_by=er.RegistryEntryDisabler.INTEGRATION,
                        )
        if is_smart_meter(sn):
            # The Public API exposes only live grid power for the meter, so we
            # derive cumulative import/export kWh sensors for the Energy
            # Dashboard by integrating that power over time.
            entities.extend(
                build_meter_energy_sensors(mqtt_coord, sn, device_info)
            )
        if energy_coord is not None:
            for description in ENERGY_SENSORS:
                entities.append(
                    StreamEnergySensor(energy_coord, description, sn, device_info)
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


class StreamMqttSensor(SensorEntity):
    """A sensor backed by the merged MQTT telemetry store."""

    _attr_has_entity_name = True
    entity_description: StreamSensorEntityDescription

    def __init__(
        self,
        coordinator: StreamMqttCoordinator,
        description: StreamSensorEntityDescription,
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
        # The coordinator keeps a persistent merged store, so once a key has
        # been seen we keep reporting its last value across brief MQTT
        # reconnects (incremental payloads only carry a few keys at a time).
        # We only drop to "unavailable" during a genuine outage, i.e. when no
        # telemetry has arrived for MQTT_OUTAGE_SEC.
        return (
            self.entity_description.key in self._coordinator.data
            and not self._coordinator.stale
        )

    @callback
    def _handle_update(self) -> None:
        raw = self._coordinator.data.get(self.entity_description.key)
        if raw is not None and self.entity_description.value_fn is not None:
            try:
                raw = self.entity_description.value_fn(raw)
            except (TypeError, ValueError):
                raw = None
        self._attr_native_value = raw
        if self.hass is not None:
            self.async_write_ha_state()


class StreamEnergySensor(
    CoordinatorEntity[StreamEnergyCoordinator], RestoreSensor
):
    """A daily-reset energy sensor backed by the quota/data poller."""

    _attr_has_entity_name = True
    entity_description: StreamEnergySensorEntityDescription

    def __init__(
        self,
        coordinator: StreamEnergyCoordinator,
        description: StreamEnergySensorEntityDescription,
        sn: str,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{sn}_energy_{description.key}"
        self._attr_device_info = device_info

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self.entity_description.key)


class StreamRoleSensor(SensorEntity):
    """Static diagnostic sensor reporting whether this device is the cascade master.

    Reads "Primary" for the main_sn device and "Secondary" for all others.
    The value never changes at runtime — it reflects the topology resolved at
    startup via the /device/system/main/sn API.
    """

    _attr_has_entity_name = True
    _attr_name = "Device Role"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:identifier"
    _attr_should_poll = False

    def __init__(self, sn: str, is_main: bool, device_info: DeviceInfo) -> None:
        self._attr_unique_id = f"{sn}_device_role"
        self._attr_device_info = device_info
        self._attr_native_value = "Primary" if is_main else "Secondary"

    @property
    def available(self) -> bool:
        return True


class StreamMqttStatusSensor(SensorEntity):
    """Diagnostic sensor surfacing this device's MQTT health.

    Two things that were previously only visible in the log, if at all:
    - This device's own telemetry freshness as "healthy" / "degraded" /
      "unavailable", naming the gap the coordinator already computes between
      still-available-with-slightly-old-data and actually-gone-unavailable.
    - The shared connection's reconnect_attempts, since every device on the
      account rides the same StreamMqttHub connection and is equally affected
      if it drops.

    Always available, even during an outage — that visibility is the point.
    """

    _attr_has_entity_name = True
    _attr_name = "MQTT Status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:wifi"
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: StreamMqttCoordinator,
        hub: StreamMqttHub,
        sn: str,
        device_info: DeviceInfo,
    ) -> None:
        self._coordinator = coordinator
        self._hub = hub
        self._attr_unique_id = f"{sn}_mqtt_status"
        self._attr_device_info = device_info

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._coordinator.async_add_listener(self._handle_update)
        )
        self._handle_update()

    @property
    def available(self) -> bool:
        return True

    @callback
    def _handle_update(self) -> None:
        self._attr_native_value = self._coordinator.status
        age = self._coordinator.last_message_age
        self._attr_extra_state_attributes = {
            "last_message_seconds_ago": round(age) if age is not None else None,
            "mqtt_connected": self._hub.is_connected,
            "reconnect_attempts": self._hub.reconnect_attempts,
        }
        if self.hass is not None:
            self.async_write_ha_state()
