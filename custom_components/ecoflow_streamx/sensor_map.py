"""Declarative MQTT sensor map for EcoFlow Stream (Public API).

Each :class:`StreamSensorEntityDescription` maps an MQTT telemetry key to a
Home Assistant sensor. Fields verified live against a Stream Ultra X
(378 fields observed; the useful scalar subset is exposed here). Diagnostic and
rarely-useful fields default to disabled so users can opt in.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)


@dataclass(frozen=True, kw_only=True)
class StreamSensorEntityDescription(SensorEntityDescription):
    """Sensor description with an optional value transform."""

    value_fn: Callable[[Any], Any] | None = None


def _milli(value: Any) -> float:
    return round(float(value) / 1000.0, 3)


def _centi(value: Any) -> float:
    return round(float(value) / 100.0, 2)


MQTT_SENSORS: tuple[StreamSensorEntityDescription, ...] = (
    # --- Power flow (near real-time, enabled by default) ---
    StreamSensorEntityDescription(
        key="powGetPvSum",
        name="Solar Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:solar-power",
    ),
    StreamSensorEntityDescription(
        key="powGetBpCms",
        name="Battery Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    StreamSensorEntityDescription(
        key="powGetSysGrid",
        name="Grid Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    StreamSensorEntityDescription(
        key="powGetSysLoad",
        name="Load Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    StreamSensorEntityDescription(
        key="gridConnectionPower",
        name="Grid Connection Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    StreamSensorEntityDescription(
        key="powGetSysLoadFromPv",
        name="Load From Solar",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    StreamSensorEntityDescription(
        key="powGetSysLoadFromGrid",
        name="Load From Grid",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    StreamSensorEntityDescription(
        key="powGetSysLoadFromBp",
        name="Load From Battery",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # --- AC output (inverter) ---
    StreamSensorEntityDescription(
        key="acTotalActivePower",
        name="Inverter AC Output",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    StreamSensorEntityDescription(
        key="powGetSchuko1",
        name="AC1 Output Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    StreamSensorEntityDescription(
        key="powGetSchuko2",
        name="AC2 Output Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    # Per-string PV power
    StreamSensorEntityDescription(
        key="powGetPv",
        name="Solar Power PV1",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    StreamSensorEntityDescription(
        key="powGetPv2",
        name="Solar Power PV2",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    StreamSensorEntityDescription(
        key="powGetPv3",
        name="Solar Power PV3",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    StreamSensorEntityDescription(
        key="powGetPv4",
        name="Solar Power PV4",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # --- Battery state ---
    StreamSensorEntityDescription(
        key="cmsBattSoc",
        name="Battery Level",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    StreamSensorEntityDescription(
        key="f32ShowSoc",
        name="Battery Level Precise",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    StreamSensorEntityDescription(
        key="cmsBattSoh",
        name="Battery Health",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    StreamSensorEntityDescription(
        key="cmsMaxChgSoc",
        name="Max Charge Level",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    StreamSensorEntityDescription(
        key="cmsMinDsgSoc",
        name="Min Discharge Level",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    StreamSensorEntityDescription(
        key="cmsChgRemTime",
        name="Charge Remaining Time",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
    ),
    StreamSensorEntityDescription(
        key="cmsDsgRemTime",
        name="Discharge Remaining Time",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
    ),
    StreamSensorEntityDescription(
        key="cmsBattFullEnergy",
        name="Battery Full Energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    StreamSensorEntityDescription(
        key="cycles",
        name="Battery Cycles",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:battery-sync",
    ),
    # --- Cumulative energy counters (Wh, total_increasing) ---
    StreamSensorEntityDescription(
        key="accuChgEnergy",
        name="Total Charge Energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    StreamSensorEntityDescription(
        key="accuDsgEnergy",
        name="Total Discharge Energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # --- Temperatures (diagnostic) ---
    StreamSensorEntityDescription(
        key="bmsMaxCellTemp",
        name="Max Cell Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    StreamSensorEntityDescription(
        key="bmsMinCellTemp",
        name="Min Cell Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    StreamSensorEntityDescription(
        key="maxMosTemp",
        name="Max MOSFET Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    StreamSensorEntityDescription(
        key="temp",
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # --- Cell voltages (mV -> V, diagnostic) ---
    StreamSensorEntityDescription(
        key="minCellVol",
        name="Min Cell Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=3,
        value_fn=_milli,
    ),
    StreamSensorEntityDescription(
        key="maxCellVol",
        name="Max Cell Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=3,
        value_fn=_milli,
    ),
    StreamSensorEntityDescription(
        key="vol",
        name="Battery Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
        value_fn=_milli,
    ),
    # --- Grid connection details (diagnostic) ---
    StreamSensorEntityDescription(
        key="gridConnectionVol",
        name="Grid Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
    ),
    StreamSensorEntityDescription(
        key="gridConnectionFreq",
        name="Grid Frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
    ),
    StreamSensorEntityDescription(
        key="gridConnectionSta",
        name="Grid Connection Status",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:transmission-tower",
    ),
    # --- Wi-Fi signal (diagnostic) ---
    StreamSensorEntityDescription(
        key="moduleWifiRssi",
        name="Wi-Fi Signal",
        native_unit_of_measurement="dBm",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


# Smart Meter telemetry. A Smart Meter only reports grid metering (per-phase
# power/current/voltage), so it gets its own compact map rather than the full
# Ultra X map. Fields verified live against a Smart Meter (BK21).
METER_SENSORS: tuple[StreamSensorEntityDescription, ...] = (
    StreamSensorEntityDescription(
        key="powGetSysGrid",
        name="Grid Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    StreamSensorEntityDescription(
        key="gridConnectionPowerL1",
        name="Grid Power L1",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    StreamSensorEntityDescription(
        key="gridConnectionPowerL2",
        name="Grid Power L2",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    StreamSensorEntityDescription(
        key="gridConnectionPowerL3",
        name="Grid Power L3",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    StreamSensorEntityDescription(
        key="gridConnectionPowerFactor",
        name="Grid Power Factor",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    StreamSensorEntityDescription(
        key="gridConnectionAmpL1",
        name="Grid Current L1",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    StreamSensorEntityDescription(
        key="gridConnectionAmpL2",
        name="Grid Current L2",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    StreamSensorEntityDescription(
        key="gridConnectionAmpL3",
        name="Grid Current L3",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    StreamSensorEntityDescription(
        key="gridConnectionVolL1",
        name="Grid Voltage L1",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
    ),
    StreamSensorEntityDescription(
        key="gridConnectionVolL2",
        name="Grid Voltage L2",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
    ),
    StreamSensorEntityDescription(
        key="gridConnectionVolL3",
        name="Grid Voltage L3",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
    ),
    StreamSensorEntityDescription(
        key="gridConnectionSta",
        name="Grid Connection Status",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

