"""Derived daily-energy sensors for the Smart Meter.

The EcoFlow Public API only exposes the Smart Meter's *instantaneous* grid
power (``powGetSysGrid``, watts). It does NOT expose the cumulative
lifetime/daily kWh totals that the private API used to provide. To make the
meter usable in the Home Assistant Energy Dashboard we integrate the live
power over time ourselves (a trapezoidal Riemann sum), producing two kWh
sensors: grid import and grid export.

The accumulators reset to zero at local midnight so the values represent
*today's* import/export, matching the Stream ``*_today`` energy sensors. The
``total_increasing`` state class lets HA treat the midnight drop as a new
cycle rather than recording negative energy.

This means the user does not have to configure Riemann-sum / integration or
utility-meter helpers manually - the integration ships ready-to-use sensors.
"""

from __future__ import annotations

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorStateClass,
)
from datetime import date

from homeassistant.const import UnitOfEnergy
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import dt as dt_util

from .coordinator import StreamMqttCoordinator

# The MQTT field carrying live signed grid power (watts) for the Smart Meter.
GRID_POWER_KEY = "powGetSysGrid"

# Sign convention for ``powGetSysGrid``.
#   True  -> a POSITIVE value means importing from the grid.
#   False -> a NEGATIVE value means importing from the grid.
# If, after running for a while, your Import/Export totals are swapped, flip
# this single constant.
IMPORT_IS_POSITIVE = True

# Ignore integration intervals longer than this (seconds). After a restart or
# a genuine telemetry outage the gap between samples can be large; integrating
# across it would inject a bogus energy spike, so we skip those intervals.
MAX_INTERVAL_SEC = 600.0


class MeterGridEnergySensor(RestoreSensor):
    """A kWh sensor produced by integrating live grid power over time."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 3

    def __init__(
        self,
        coordinator: StreamMqttCoordinator,
        sn: str,
        device_info: DeviceInfo,
        direction: str,
    ) -> None:
        """Initialise the sensor.

        :param direction: ``"import"`` or ``"export"``.
        """
        self._coordinator = coordinator
        self._direction = direction
        self._attr_unique_id = f"{sn}_meter_energy_{direction}"
        self._attr_device_info = device_info
        if direction == "import":
            self._attr_name = "Grid Import Today"
            self._attr_icon = "mdi:transmission-tower-import"
        else:
            self._attr_name = "Grid Export Today"
            self._attr_icon = "mdi:transmission-tower-export"

        self._energy_kwh: float = 0.0
        self._last_ts: float | None = None
        self._day: date | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the accumulated total and start listening for updates."""
        await super().async_added_to_hass()

        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            try:
                self._energy_kwh = float(last.native_value)
            except (TypeError, ValueError):
                self._energy_kwh = 0.0

        # Only carry the restored total forward if it belongs to today's date;
        # if HA was down over a midnight boundary, start a fresh daily total.
        last_state = await self.async_get_last_state()
        if last_state is not None:
            restored_day = dt_util.as_local(last_state.last_updated).date()
            if restored_day == dt_util.now().date():
                self._day = restored_day
            else:
                self._energy_kwh = 0.0

        self.async_on_remove(
            self._coordinator.async_add_listener(self._handle_update)
        )
        self._handle_update()

    @property
    def available(self) -> bool:
        return (
            GRID_POWER_KEY in self._coordinator.data
            and not self._coordinator.stale
        )

    @callback
    def _handle_update(self) -> None:
        raw = self._coordinator.data.get(GRID_POWER_KEY)
        now_local = dt_util.now()
        now = now_local.timestamp()
        today = now_local.date()

        # Reset the running total when the local calendar day rolls over.
        if self._day is not None and today != self._day:
            self._energy_kwh = 0.0
            self._last_ts = None
        self._day = today

        power = None
        if raw is not None:
            try:
                power = float(raw)
            except (TypeError, ValueError):
                power = None

        if power is not None:
            # Split the signed grid power into the component for this sensor's
            # direction (the other direction contributes zero for this sample).
            importing = power if IMPORT_IS_POSITIVE else -power
            if self._direction == "import":
                directional = max(0.0, importing)
            else:
                directional = max(0.0, -importing)

            if self._last_ts is not None:
                dt_sec = now - self._last_ts
                if 0.0 < dt_sec <= MAX_INTERVAL_SEC:
                    # watts * hours = Wh, then /1000 -> kWh.
                    self._energy_kwh += directional * (dt_sec / 3600.0) / 1000.0

            self._last_ts = now

        self._attr_native_value = round(self._energy_kwh, 6)
        if self.hass is not None:
            self.async_write_ha_state()


def build_meter_energy_sensors(
    coordinator: StreamMqttCoordinator,
    sn: str,
    device_info: DeviceInfo,
) -> list[MeterGridEnergySensor]:
    """Create the import/export energy sensors for a Smart Meter."""
    return [
        MeterGridEnergySensor(coordinator, sn, device_info, "import"),
        MeterGridEnergySensor(coordinator, sn, device_info, "export"),
    ]


__all__ = ["MeterGridEnergySensor", "build_meter_energy_sensors"]
