"""Select platform for EcoFlow Stream (Public API)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .control import StreamControlEntity, resolve_control_target

# Documented, settable operating modes. Self-powered and AI Mode are mutually
# exclusive per the EcoFlow Public API docs.
MODE_SELF_POWERED = "Self-powered"
MODE_AI = "AI Optimised"

_MODE_TO_CFG = {
    MODE_SELF_POWERED: "operateSelfPoweredOpen",
    MODE_AI: "operateIntelligentScheduleModeOpen",
}
_FLAG_TO_MODE = {v: k for k, v in _MODE_TO_CFG.items()}


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
    """System operating mode (Self-powered / AI Optimised)."""

    _attr_name = "Operating Mode"
    _attr_icon = "mdi:home-lightning-bolt"
    _attr_options = [MODE_SELF_POWERED, MODE_AI]

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
            return
        await self._send({"cfgEnergyStrategyOperateMode": {flag: True}})
        self._attr_current_option = option
        self.async_write_ha_state()
