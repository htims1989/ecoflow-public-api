"""Select platform for EcoFlow Stream (Public API)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .control import StreamControlEntity, resolve_control_target

# Documented, settable operating modes. Self-powered and AI Mode are mutually
# exclusive per the EcoFlow Public API docs.
MODE_SELF_POWERED = "Self-powered"
MODE_AI = "AI Optimised"

# Additional modes the device can report but that the Public API refuses to set
# directly (returns 8524: Validation failed). They are configured through the
# EcoFlow app's schedule/tariff setup, so we display them read-only.
MODE_SCHEDULED = "Scheduled"
MODE_TIME_OF_USE = "Time-of-Use"

_MODE_TO_CFG = {
    MODE_SELF_POWERED: "operateSelfPoweredOpen",
    MODE_AI: "operateIntelligentScheduleModeOpen",
}
# All modes the device may report, for display purposes.
_FLAG_TO_MODE = {
    "operateSelfPoweredOpen": MODE_SELF_POWERED,
    "operateIntelligentScheduleModeOpen": MODE_AI,
    "operateScheduledOpen": MODE_SCHEDULED,
    "operateTouModeOpen": MODE_TIME_OF_USE,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EcoFlow Stream selects from a config entry."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    target = resolve_control_target(runtime)
    if target is None:
        return

    async_add_entities(
        [
            StreamOperatingModeSelect(
                coordinator=target["coordinator"],
                api=target["api"],
                target_sn=target["target_sn"],
                feedback_key="energyStrategyOperateMode",
                device_sn=target["device_sn"],
                device_info=target["device_info"],
            )
        ]
    )


class StreamOperatingModeSelect(StreamControlEntity, SelectEntity):
    """System operating mode.

    Self-powered and AI Optimised can be set via the API. Scheduled and
    Time-of-Use are shown for display only (set through the EcoFlow app).
    """

    _attr_name = "Operating Mode"
    _attr_icon = "mdi:home-lightning-bolt"
    _attr_options = [MODE_SELF_POWERED, MODE_AI, MODE_SCHEDULED, MODE_TIME_OF_USE]

    @callback
    def _handle_update(self) -> None:
        modes = self._feedback()
        current: str | None = None
        if isinstance(modes, dict):
            for flag, mode in _FLAG_TO_MODE.items():
                if modes.get(flag):
                    current = mode
                    break
        self._attr_current_option = current
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        flag = _MODE_TO_CFG.get(option)
        if flag is None:
            raise HomeAssistantError(
                f"'{option}' can only be configured in the EcoFlow app, "
                "not via the Public API."
            )
        await self._send({"cfgEnergyStrategyOperateMode": {flag: True}})
        self._attr_current_option = option
        self.async_write_ha_state()
