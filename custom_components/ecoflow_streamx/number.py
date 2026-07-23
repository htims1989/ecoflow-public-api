"""Number platform for EcoFlow Stream (Public API)."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .control import StreamControlEntity, resolve_control_target


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EcoFlow Stream numbers from a config entry."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    target = resolve_control_target(runtime)
    if target is None:
        return

    async_add_entities(
        [
            StreamBackupReserveNumber(
                coordinator=target["coordinator"],
                api=target["api"],
                target_sn=target["target_sn"],
                feedback_key="backupReverseSoc",
                device_sn=target["device_sn"],
                device_info=target["device_info"],
            )
        ]
    )


class StreamBackupReserveNumber(StreamControlEntity, NumberEntity):
    """Backup reserve level (``cfgBackupReverseSoc``), recommended 3–95%."""

    _attr_name = "Backup Reserve Level"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_min_value = 3
    _attr_native_max_value = 95
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:battery-charging-30"

    @callback
    def _handle_update(self) -> None:
        raw = self._feedback()
        self._attr_native_value = None if raw is None else float(raw)
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        await self._send({"cfgBackupReverseSoc": int(value)})
        self._attr_native_value = value
        self.async_write_ha_state()
