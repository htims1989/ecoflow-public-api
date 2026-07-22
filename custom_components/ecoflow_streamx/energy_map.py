"""Declarative energy-sensor map for EcoFlow Stream (Public API).

These sensors are backed by the historical ``quota/data`` aggregates polled by
:class:`StreamEnergyCoordinator`. Each poll queries the local-midnight -> now
window, so the values climb from zero during the day and reset to zero at
midnight. That daily-reset pattern maps to ``state_class = total_increasing``,
which lets HA auto-detect the reset (a decrease starts a new cycle) instead of
recording the drop as negative energy on the Energy Dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy


@dataclass(frozen=True, kw_only=True)
class StreamEnergySensorEntityDescription(SensorEntityDescription):
    """Description for a daily-reset energy sensor."""


ENERGY_SENSORS: tuple[StreamEnergySensorEntityDescription, ...] = (
    StreamEnergySensorEntityDescription(
        key="solar",
        name="Solar Energy Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        icon="mdi:solar-power",
    ),
    StreamEnergySensorEntityDescription(
        key="consumption",
        name="Consumption Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
    ),
    StreamEnergySensorEntityDescription(
        key="grid_import",
        name="Grid Import Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        icon="mdi:transmission-tower-import",
    ),
    StreamEnergySensorEntityDescription(
        key="grid_export",
        name="Grid Export Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        icon="mdi:transmission-tower-export",
    ),
    StreamEnergySensorEntityDescription(
        key="battery_charge",
        name="Battery Charge Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
    ),
    StreamEnergySensorEntityDescription(
        key="battery_discharge",
        name="Battery Discharge Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
    ),
)
