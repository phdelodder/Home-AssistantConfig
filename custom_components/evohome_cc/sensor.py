#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by evohome & others.

Provides support for sensors.
"""

import logging
from typing import Any, Dict, Optional

from homeassistant.components.sensor import (
    STATE_CLASS_MEASUREMENT,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import (  # DEVICE_CLASS_BATTERY,; DEVICE_CLASS_PROBLEM,
    DEVICE_CLASS_HUMIDITY,
    DEVICE_CLASS_PRESSURE,
    DEVICE_CLASS_TEMPERATURE,
    TEMP_CELSIUS,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from . import EvoDeviceBase
from .const import ATTR_SETPOINT, BROKER, DOMAIN, PERCENTAGE

SENSOR_KEY_TEMPERATURE = "temperature"

SENSOR_DESCRIPTION_TEMPERATURE = SensorEntityDescription(
    key=SENSOR_KEY_TEMPERATURE,
    name="Temperature",
    device_class=DEVICE_CLASS_TEMPERATURE,
    native_unit_of_measurement=TEMP_CELSIUS,
    state_class=STATE_CLASS_MEASUREMENT,
)
# sensor.entity_description = SENSOR_DESCRIPTION_TEMPERATURE

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistantType,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info=None,
) -> None:
    """Set up the evohome sensor sensor entities."""
    if discovery_info is None:
        return

    devices = [
        v.get(ENTITY_CLASS, EvoSensor)(hass.data[DOMAIN][BROKER], device, k, **v)
        for device in discovery_info.get("devices", [])
        for k, v in SENSOR_ATTRS.items()
        if hasattr(device, k)
    ]  # and (not device._is_faked or device["fakable"])

    domains = [
        v.get(ENTITY_CLASS, EvoSensor)(hass.data[DOMAIN][BROKER], domain, k, **v)
        for domain in discovery_info.get("domains", [])
        for k, v in SENSOR_ATTRS.items()
        if k == "heat_demand" and hasattr(domain, k)
    ]

    async_add_entities(devices + domains)


class EvoSensor(EvoDeviceBase, SensorEntity):
    """Representation of a generic sensor."""

    _attr_state_class = STATE_CLASS_MEASUREMENT

    def __init__(
        self, broker, device, state_attr, device_class=None, device_units=None, **kwargs
    ) -> None:
        """Initialize a sensor."""
        _LOGGER.info("Found a Sensor (%s), id=%s", state_attr, device.id)
        super().__init__(broker, device, state_attr, device_class)

        self._unique_id = f"{device.id}-{state_attr}"
        self._unit_of_measurement = device_units or PERCENTAGE

    @property
    def state(self) -> Optional[Any]:  # int or float
        """Return the state of the sensor."""
        state = getattr(self._device, self._state_attr)
        if self.unit_of_measurement == PERCENTAGE:
            return int(state * 200) / 2 if state is not None else None
        # if self.unit_of_measurement == TEMP_CELSIUS:
        #     return int(state * 200) / 200 if state is not None else None
        return state

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement of the sensor."""
        return self._unit_of_measurement


class EvoHeatDemand(EvoSensor):
    """Representation of a heat demand sensor."""

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:radiator-off" if self.state == 0 else "mdi:radiator"


class EvoModLevel(EvoSensor):
    """Representation of a heat demand sensor."""

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        attrs = super().device_state_attributes

        if self._state_attr in "modulation_level":
            attrs["status"] = {
                self._device.ACTUATOR_CYCLE: self._device.actuator_cycle,
                self._device.ACTUATOR_STATE: self._device.actuator_state,
                self._device.BOILER_SETPOINT: self._device.boiler_setpoint,
            }
        else:  # self._state_attr == "relative_modulation_level"
            attrs["status"] = self._device.opentherm_status

        return attrs


class EvoRelayDemand(EvoSensor):
    """Representation of a relay demand sensor."""

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:power-plug" if self.state else "mdi:power-plug-off"


class EvoTemperature(EvoSensor):
    """Representation of a temperature sensor (incl. DHW sensor)."""

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        attrs = super().device_state_attributes
        if hasattr(self._device, ATTR_SETPOINT):
            attrs[ATTR_SETPOINT] = self._device.setpoint
        return attrs


class EvoFaultLog(EvoDeviceBase):
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
    def state(self) -> int:
        """Return the number of issues."""
        return len(self._fault_log)

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the device state attributes."""
        return {
            **super().device_state_attributes,
            "fault_log": self._device._fault_log,
        }

    async def async_update(self) -> None:
        """Process the sensor's state data."""
        # self._fault_log = self._device.fault_log()  # TODO: needs sorting out
        pass


DEVICE_CLASS = "device_class"
DEVICE_UNITS = "device_units"
ENTITY_CLASS = "entity_class"

SENSOR_ATTRS = {
    # SENSOR_ATTRS_BDR = {  # incl: actuator
    "relay_demand": {  # 0008
        DEVICE_UNITS: PERCENTAGE,
        ENTITY_CLASS: EvoRelayDemand,
    },
    "modulation_level": {  # 3EF0/3EF1
        DEVICE_UNITS: PERCENTAGE,
        ENTITY_CLASS: EvoModLevel,
    },
    # SENSOR_ATTRS_OTB = {  # excl. actuator
    "boiler_output_temp": {  # 3220
        DEVICE_CLASS: DEVICE_CLASS_TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    "boiler_return_temp": {  # 3220
        DEVICE_CLASS: DEVICE_CLASS_TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    "boiler_setpoint": {  # 3220
        DEVICE_CLASS: DEVICE_CLASS_TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    "ch_max_setpoint": {  # 3220
        DEVICE_CLASS: DEVICE_CLASS_TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    "ch_water_pressure": {  # 3220
        DEVICE_CLASS: DEVICE_CLASS_PRESSURE,
        DEVICE_UNITS: "bar",
    },
    "dhw_flow_rate": {  # 3220
        DEVICE_UNITS: "l/min",
    },
    "dhw_setpoint": {  # 3220
        DEVICE_CLASS: DEVICE_CLASS_TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    "dhw_temp": {  # 3220
        DEVICE_CLASS: DEVICE_CLASS_TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    "outside_temp": {  # 3220
        DEVICE_CLASS: DEVICE_CLASS_TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    "rel_modulation_level": {  # 3200
        DEVICE_UNITS: PERCENTAGE,
        ENTITY_CLASS: EvoModLevel,
    },
    # SENSOR_ATTRS_OTH = {
    "heat_demand": {  # 3150
        DEVICE_UNITS: PERCENTAGE,
        ENTITY_CLASS: EvoHeatDemand,
    },
    "temperature": {
        DEVICE_CLASS: DEVICE_CLASS_TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
        ENTITY_CLASS: EvoTemperature,
        "fakable": True,
    },
    # SENSOR_ATTRS_FAN = {
    "boost_timer": {
        DEVICE_UNITS: "min(s)",
    },
    "fan_rate": {
        DEVICE_UNITS: PERCENTAGE,
    },
    "relative_humidity": {
        DEVICE_CLASS: DEVICE_CLASS_HUMIDITY,
        DEVICE_UNITS: PERCENTAGE,
    },
}
