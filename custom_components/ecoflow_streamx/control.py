"""Shared helpers for EcoFlow Stream control entities (switch/number/select).

Control entities write ``cfg*`` set commands to the *main* device SN and read
their current state back from the merged MQTT store (the device echoes the new
value within a few seconds).
"""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, device_model, is_smart_meter
from .coordinator import StreamMqttCoordinator


def resolve_control_target(runtime: dict) -> dict | None:
    """Pick the device that system-level controls should attach to.

    Controls target the main device SN. We bind them to the configured device
    whose SN matches ``main_sn`` (so its MQTT store provides the feedback
    fields); if that is not found we fall back to the first non-meter device.
    Returns ``None`` when there is no controllable inverter.
    """
    devices = runtime["devices"]
    main_sn = runtime.get("main_sn")

    chosen = next(
        (d for d in devices if d["sn"] == main_sn and not is_smart_meter(d["sn"])),
        None,
    )
    if chosen is None:
        chosen = next(
            (d for d in devices if not is_smart_meter(d["sn"])), None
        )
    if chosen is None:
        return None

    return {
        "coordinator": chosen["mqtt"],
        "api": runtime["api"],
        "target_sn": main_sn or chosen["sn"],
        "device_info": DeviceInfo(
            identifiers={(DOMAIN, chosen["sn"])},
            name=chosen["name"],
            manufacturer="EcoFlow",
            model=device_model(chosen["sn"]),
            serial_number=chosen["sn"],
        ),
        "device_sn": chosen["sn"],
    }


class StreamControlEntity:
    """Mixin providing MQTT-feedback availability and a set-command helper."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: StreamMqttCoordinator,
        api: Any,
        target_sn: str,
        feedback_key: str,
        device_sn: str,
        device_info: DeviceInfo,
    ) -> None:
        self._coordinator = coordinator
        self._api = api
        self._target_sn = target_sn
        self._feedback_key = feedback_key
        self._attr_device_info = device_info
        self._attr_unique_id = f"{device_sn}_{feedback_key}"

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(  # type: ignore[attr-defined]
            self._coordinator.async_add_listener(self._handle_update)
        )
        self._handle_update()

    @property
    def available(self) -> bool:
        return (
            self._feedback_key in self._coordinator.data
            and not self._coordinator.stale
        )

    def _feedback(self) -> Any:
        return self._coordinator.data.get(self._feedback_key)

    async def _send(self, params: dict[str, Any]) -> None:
        """Send a set command to the main device SN."""
        await self._api.set_quota(self._target_sn, params)

    def _handle_update(self) -> None:  # overridden by subclasses
        raise NotImplementedError
