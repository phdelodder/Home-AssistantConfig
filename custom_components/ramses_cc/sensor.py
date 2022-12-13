#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by CH/DHW & HVAC.

Provides support for sensors.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import DOMAIN as PLATFORM
from homeassistant.components.sensor import (
    TEMP_CELSIUS,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    TIME_MINUTES,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import (
    AddEntitiesCallback,
    async_get_current_platform,
)
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from ramses_rf.device.heat import (
    SZ_BOILER_OUTPUT_TEMP,
    SZ_BOILER_RETURN_TEMP,
    SZ_BOILER_SETPOINT,
    SZ_CH_MAX_SETPOINT,
    SZ_CH_SETPOINT,
    SZ_CH_WATER_PRESSURE,
    SZ_DHW_FLOW_RATE,
    SZ_DHW_SETPOINT,
    SZ_DHW_TEMP,
    SZ_MAX_REL_MODULATION,
    SZ_OEM_CODE,
    SZ_OUTSIDE_TEMP,
    SZ_REL_MODULATION_LEVEL,
)
from ramses_rf.protocol.const import (
    SZ_AIR_QUALITY,
    SZ_AIR_QUALITY_BASE,
    SZ_CO2_LEVEL,
    SZ_EXHAUST_FAN_SPEED,
    SZ_EXHAUST_FLOW,
    SZ_EXHAUST_TEMPERATURE,
    SZ_FAN_INFO,
    SZ_INDOOR_HUMIDITY,
    SZ_INDOOR_TEMPERATURE,
    SZ_OUTDOOR_HUMIDITY,
    SZ_OUTDOOR_TEMPERATURE,
    SZ_POST_HEAT,
    SZ_PRE_HEAT,
    SZ_REMAINING_TIME,
    SZ_SPEED_CAP,
    SZ_SUPPLY_FAN_SPEED,
    SZ_SUPPLY_FLOW,
    SZ_SUPPLY_TEMPERATURE,
)

from . import RamsesDeviceBase as RamsesDeviceBase
from .const import (
    ATTR_SETPOINT,
    BROKER,
    DOMAIN,
    VOLUME_FLOW_RATE_LITERS_PER_MINUTE,
    VOLUME_FLOW_RATE_LITERS_PER_SECOND,
)
from .helpers import migrate_to_ramses_rf
from .schemas import SVCS_SENSOR

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    _: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType = None,
) -> None:
    """Create sensors for CH/DHW (heat) & HVAC.

    discovery_info keys:
      gateway: is the ramses_rf protocol stack (gateway/protocol/transport/serial)
      devices: heat (e.g. CTL, OTB, BDR, TRV) or hvac (e.g. FAN, CO2, SWI)
      domains: TCS, DHW and Zones
    """

    def entity_factory(broker, device, attr, *, entity_class=None, **kwargs):
        migrate_to_ramses_rf(hass, PLATFORM, f"{device.id}-{attr}")
        return (entity_class or RamsesSensor)(broker, device, attr, **kwargs)

    if discovery_info is None:
        return

    broker = hass.data[DOMAIN][BROKER]

    new_sensors = [
        entity_factory(broker, device, k, **v)
        for device in discovery_info.get("devices", [])
        for k, v in SENSOR_ATTRS.items()
        if hasattr(device, k)
    ]  # and (not device._is_faked or device["fakable"])
    new_sensors += [
        entity_factory(broker, device, f"{k}_ot", **v)
        for device in discovery_info.get("devices", [])
        for k, v in SENSOR_ATTRS_HEAT.items()
        if device._SLUG == "OTB" and hasattr(device, f"{k}_ot")
    ]
    new_sensors += [
        entity_factory(broker, domain, k, **v)
        for domain in discovery_info.get("domains", [])
        for k, v in SENSOR_ATTRS_HEAT.items()
        if k == "heat_demand" and hasattr(domain, k)
    ]

    async_add_entities(new_sensors)

    if not broker._services.get(PLATFORM) and new_sensors:
        broker._services[PLATFORM] = True

        register_svc = async_get_current_platform().async_register_entity_service
        [register_svc(k, v, f"svc_{k}") for k, v in SVCS_SENSOR.items()]


class RamsesSensor(RamsesDeviceBase, SensorEntity):
    """Representation of a generic sensor."""

    # Strictly: fan_info, oem_code are not a measurements
    # _attr_native_unit_of_measurement: str = PERCENTAGE  # most common
    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT  # all but 2

    def __init__(
        self,
        broker,  # ramses_cc broker
        device,  # ramses_rf device
        state_attr,  # key of attr_dict +/- _ot suffix
        device_class=None,  # attr_dict value
        device_units=None,  # attr_dict value
        state_class=SensorStateClass.MEASUREMENT,  # attr_dict value, maybe None
        **kwargs,  # leftover attr_dict values
    ) -> None:
        """Initialize a sensor."""

        _LOGGER.info("Found a Sensor for %s: %s", device.id, state_attr)

        super().__init__(
            broker,
            device,
            state_attr,
            device_class=device_class,
        )

        self._attr_native_unit_of_measurement = device_units
        self._attr_state_class = state_class

    @property
    def native_value(self) -> Any | None:  # int or float
        """Return the state of the sensor."""
        state = getattr(self._device, self._state_attr)
        if self._attr_native_unit_of_measurement == PERCENTAGE:
            return None if state is None else state * 100
        return state


class RamsesCo2Sensor(RamsesSensor):
    """Representation of a generic sensor."""

    @callback
    def svc_put_co2_level(self, co2_level: int = None, **kwargs) -> None:
        """Set the state of the Sensor."""
        self._device.co2_level = co2_level


class RamsesIndoorHumidity(RamsesSensor):
    """Representation of a generic sensor."""

    @callback
    def svc_put_indoor_humidity(self, indoor_humidity: float = None, **kwargs) -> None:
        """Set the state of the Sensor."""
        self._device.indoor_humidity = indoor_humidity / 100


class RamsesHeatDemand(RamsesSensor):
    """Representation of a heat demand sensor."""

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:radiator-off" if self.state == 0 else "mdi:radiator"


class RamsesModLevel(RamsesSensor):
    """Representation of a heat demand sensor."""

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the integration-specific state attributes."""
        attrs = super().extra_state_attributes

        if self._state_attr[-3:] == "_ot":
            attrs.update(self._device.opentherm_status)
        else:
            attrs.update(self._device.ramses_status)
        attrs.pop("rel_modulation_level")

        return attrs


class RamsesRelayDemand(RamsesSensor):
    """Representation of a relay demand sensor."""

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:power-plug" if self.state else "mdi:power-plug-off"


class RamsesTemperature(RamsesSensor):
    """Representation of a temperature sensor (incl. DHW sensor)."""

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the integration-specific state attributes."""
        attrs = super().extra_state_attributes
        if hasattr(self._device, ATTR_SETPOINT):
            attrs[ATTR_SETPOINT] = self._device.setpoint
        return attrs


class RamsesFaultLog(RamsesDeviceBase):
    """Representation of a system's fault log."""

    # DEVICE_CLASS = DEVICE_CLASS_PROBLEM
    DEVICE_UNITS = "entries"

    def __init__(self, broker, device) -> None:
        """Initialize the sensor."""
        super().__init__(broker, device, None, None)  # TODO

        self._fault_log = None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._device._fault_log._fault_log_done

    @property
    def native_value(self) -> int:
        """Return the number of issues."""
        return len(self._fault_log)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the device state attributes."""
        return {
            **super().extra_state_attributes,
            "fault_log": self._device._fault_log,
        }

    async def async_update(self) -> None:
        """Process the sensor's state data."""
        # self._fault_log = self._device.fault_log()  # TODO: needs sorting out
        pass


DEVICE_CLASS = "device_class"  # _attr_device_class
DEVICE_UNITS = "device_units"  # _attr_native_unit_of_measurement
ENTITY_CLASS = "entity_class"  # subclass of RamsesSensor
STATE_CLASS = "state_class"  # _attr_state_class

# These are all: SensorStateClass.MEASUREMENT

SENSOR_ATTRS_HEAT = {
    # Special projects
    SZ_OEM_CODE: {STATE_CLASS: None},  # 3220/73
    "percent": {  # TODO: 2401
        DEVICE_UNITS: PERCENTAGE,
        ENTITY_CLASS: RamsesRelayDemand,
    },
    "value": {  # TODO: 2401
        DEVICE_UNITS: "units",
    },
    # SENSOR_ATTRS_BDR = {  # incl: actuator
    "relay_demand": {  # 0008
        DEVICE_UNITS: PERCENTAGE,
        ENTITY_CLASS: RamsesRelayDemand,
    },
    "relay_demand_fa": {  # 0008
        DEVICE_UNITS: PERCENTAGE,
        ENTITY_CLASS: RamsesRelayDemand,
    },
    "modulation_level": {  # 3EF0/3EF1
        DEVICE_UNITS: PERCENTAGE,
        ENTITY_CLASS: RamsesModLevel,
    },
    # SENSOR_ATTRS_OTB = {  # excl. actuator
    SZ_BOILER_OUTPUT_TEMP: {  # 3200, 3220|19
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    SZ_BOILER_RETURN_TEMP: {  # 3210, 3220|1C
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    SZ_BOILER_SETPOINT: {  # 22D9, 3220|01
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    SZ_CH_MAX_SETPOINT: {  # 1081, 3220|39
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    SZ_CH_SETPOINT: {  # 3EF0
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    SZ_CH_WATER_PRESSURE: {  # 1300, 3220|12
        DEVICE_CLASS: SensorDeviceClass.PRESSURE,
        DEVICE_UNITS: "bar",
    },
    SZ_DHW_FLOW_RATE: {  # 12F0, 3220|13
        DEVICE_UNITS: VOLUME_FLOW_RATE_LITERS_PER_MINUTE,
    },
    SZ_DHW_SETPOINT: {  # 10A0, 3220|38
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    SZ_DHW_TEMP: {  # 1290, 3220|1A
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    SZ_MAX_REL_MODULATION: {  # 3200|0E
        DEVICE_UNITS: PERCENTAGE,
        ENTITY_CLASS: RamsesModLevel,
    },
    SZ_OUTSIDE_TEMP: {  # 1290, 3220|1B
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    SZ_REL_MODULATION_LEVEL: {  # 3EFx, 3200|11
        DEVICE_UNITS: PERCENTAGE,
        ENTITY_CLASS: RamsesModLevel,
    },
    # SENSOR_ATTRS_OTH = {
    "heat_demand": {  # 3150
        DEVICE_UNITS: PERCENTAGE,
        ENTITY_CLASS: RamsesHeatDemand,
    },
    "temperature": {
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
        ENTITY_CLASS: RamsesTemperature,
        "fakable": True,
    },
}


SENSOR_ATTRS_HVAC = {
    # "boost_timer": {DEVICE_UNITS: TIME_MINUTES,},
    # "fan_rate":    {DEVICE_UNITS: PERCENTAGE,},
    SZ_AIR_QUALITY: {
        DEVICE_UNITS: PERCENTAGE,
        # DEVICE_CLASS: SensorDeviceClass.AQI,
    },
    SZ_AIR_QUALITY_BASE: {
        DEVICE_UNITS: PERCENTAGE,
        # DEVICE_CLASS: SensorDeviceClass.AQI,
    },
    SZ_CO2_LEVEL: {
        DEVICE_CLASS: SensorDeviceClass.CO2,
        DEVICE_UNITS: CONCENTRATION_PARTS_PER_MILLION,
        ENTITY_CLASS: RamsesCo2Sensor,
    },
    SZ_EXHAUST_FAN_SPEED: {
        DEVICE_UNITS: PERCENTAGE,
    },
    SZ_EXHAUST_FLOW: {
        DEVICE_UNITS: VOLUME_FLOW_RATE_LITERS_PER_SECOND,
    },
    SZ_EXHAUST_TEMPERATURE: {
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    SZ_FAN_INFO: {STATE_CLASS: None},
    SZ_INDOOR_HUMIDITY: {
        DEVICE_CLASS: SensorDeviceClass.HUMIDITY,
        DEVICE_UNITS: PERCENTAGE,
        ENTITY_CLASS: RamsesIndoorHumidity,
    },
    SZ_INDOOR_TEMPERATURE: {
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    SZ_OUTDOOR_HUMIDITY: {
        DEVICE_CLASS: SensorDeviceClass.HUMIDITY,
        DEVICE_UNITS: PERCENTAGE,
    },
    SZ_OUTDOOR_TEMPERATURE: {
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    SZ_POST_HEAT: {
        DEVICE_UNITS: PERCENTAGE,
    },
    SZ_PRE_HEAT: {
        DEVICE_UNITS: PERCENTAGE,
    },
    SZ_REMAINING_TIME: {
        DEVICE_UNITS: TIME_MINUTES,
        # DEVICE_CLASS: SensorDeviceClass.DURATION,
    },
    SZ_SPEED_CAP: {
        DEVICE_UNITS: "units",
    },
    SZ_SUPPLY_FAN_SPEED: {
        DEVICE_UNITS: PERCENTAGE,
    },
    SZ_SUPPLY_FLOW: {
        DEVICE_UNITS: VOLUME_FLOW_RATE_LITERS_PER_SECOND,
    },
    SZ_SUPPLY_TEMPERATURE: {
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
}

SENSOR_ATTRS = SENSOR_ATTRS_HEAT | SENSOR_ATTRS_HVAC
