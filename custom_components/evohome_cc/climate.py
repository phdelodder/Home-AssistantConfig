#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by evohome.

Provides support for climate entities.
"""
import logging
from datetime import datetime as dt
from typing import Any, Dict, List, Optional

from evohome_rf.const import SystemMode, ZoneMode
from homeassistant.components.climate import DOMAIN as PLATFORM
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (  # PRESET_BOOST,
    CURRENT_HVAC_HEAT,
    CURRENT_HVAC_IDLE,
    CURRENT_HVAC_OFF,
    HVAC_MODE_AUTO,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    PRESET_AWAY,
    PRESET_ECO,
    PRESET_HOME,
    PRESET_NONE,
    SUPPORT_PRESET_MODE,
    SUPPORT_TARGET_TEMPERATURE,
)
from homeassistant.helpers import entity_platform
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from . import EvoZoneBase
from .const import ATTR_SETPOINT, BROKER, DOMAIN, MODE, SYSTEM_MODE
from .schema import CLIMATE_SERVICES, SVC_RESET_SYSTEM, SVC_SET_SYSTEM_MODE

_LOGGER = logging.getLogger(__name__)


PRESET_RESET = "Reset"  # reset all child zones to EVO_FOLLOW
PRESET_CUSTOM = "Custom"

TCS_PRESET_TO_HA = {
    SystemMode.AUTO: None,
    SystemMode.AWAY: PRESET_AWAY,
    SystemMode.CUSTOM: PRESET_CUSTOM,
    SystemMode.DAY_OFF: PRESET_HOME,
    SystemMode.ECO_BOOST: PRESET_ECO,
    SystemMode.RESET: PRESET_RESET,
}

HA_PRESET_TO_TCS = {v: k for k, v in TCS_PRESET_TO_HA.items()}
HA_HVAC_TO_TCS = {HVAC_MODE_OFF: SystemMode.HEAT_OFF, HVAC_MODE_HEAT: SystemMode.AUTO}

TCS_MODE_TO_HA_PRESET = {
    SystemMode.AWAY: PRESET_AWAY,
    SystemMode.CUSTOM: "custom",
    SystemMode.DAY_OFF: PRESET_HOME,
    SystemMode.DAY_OFF_ECO: PRESET_HOME,
    SystemMode.ECO_BOOST: PRESET_ECO,
}

EVOZONE_PRESET_TO_HA = {
    ZoneMode.SCHEDULE: PRESET_NONE,
    ZoneMode.TEMPORARY: "temporary",
    ZoneMode.PERMANENT: "permanent",
}
HA_PRESET_TO_EVOZONE = {v: k for k, v in EVOZONE_PRESET_TO_HA.items()}


async def async_setup_platform(
    hass: HomeAssistantType, config: ConfigType, async_add_entities, discovery_info=None
) -> None:
    """Create the evohome Controller, and its Zones, if any."""
    if discovery_info is None:
        return

    broker = hass.data[DOMAIN][BROKER]
    new_entities = []

    if broker.client.evo not in broker.climates:
        new_entities.append(EvoController(broker, broker.client.evo))
        broker.climates.append(broker.client.evo)

    for zone in [z for z in broker.client.evo.zones if z not in broker.climates]:
        new_entities.append(EvoZone(broker, zone))
        broker.climates.append(zone)

    if new_entities:
        async_add_entities(new_entities, update_before_add=True)

    if broker.services.get(PLATFORM):
        return
    broker.services[PLATFORM] = True

    register_svc = entity_platform.current_platform.get().async_register_entity_service
    [register_svc(k, v, f"svc_{k}") for k, v in CLIMATE_SERVICES.items()]


class EvoZone(EvoZoneBase, ClimateEntity):
    """Base for a Honeywell evohome Zone."""

    def __init__(self, broker, device) -> None:
        """Initialize a Zone."""
        _LOGGER.info("Found a Zone (%s), id=%s", device.heating_type, device.idx)
        super().__init__(broker, device)

        self._unique_id = device.id
        self._icon = "mdi:radiator"

        self._supported_features = SUPPORT_PRESET_MODE | SUPPORT_TARGET_TEMPERATURE
        self._preset_modes = list(HA_PRESET_TO_EVOZONE)

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            **super().device_state_attributes,
            "heating_type": self._device.heating_type,
            "config": self._device.config,
            "heat_demand": self._device.heat_demand,
        }

    @property
    def hvac_action(self) -> Optional[str]:
        """Return the current running hvac operation if supported."""

        if self._device.heat_demand:
            return CURRENT_HVAC_HEAT
        if self._device._evo.system_mode is None:
            return
        if self._device._evo.system_mode[SYSTEM_MODE] == SystemMode.HEAT_OFF:
            return CURRENT_HVAC_OFF
        if self._device._evo.system_mode is not None:
            return CURRENT_HVAC_IDLE

    @property
    def hvac_mode(self) -> Optional[str]:
        """Return hvac operation ie. heat, cool mode."""

        if self._device._evo.system_mode is None:
            return
        if self._device._evo.system_mode[SYSTEM_MODE] == SystemMode.HEAT_OFF:
            return HVAC_MODE_OFF
        if self._device._evo.system_mode[SYSTEM_MODE] == SystemMode.AWAY:
            return HVAC_MODE_AUTO

        if self._device.mode is None:
            return
        if (
            self._device.config
            and self._device.mode[ATTR_SETPOINT] <= self._device.config["min_temp"]
        ):
            return HVAC_MODE_OFF
        return HVAC_MODE_HEAT

    @property
    def hvac_modes(self) -> List[str]:
        """Return the list of available hvac operation modes."""
        return [HVAC_MODE_HEAT, HVAC_MODE_OFF]  # HVAC_MODE_AUTO,

    @property
    def max_temp(self) -> Optional[float]:
        """Return the maximum target temperature of a Zone."""
        if self._device.config:
            return self._device.config["max_temp"]

    @property
    def min_temp(self) -> Optional[float]:
        """Return the minimum target temperature of a Zone."""
        if self._device.config:
            return self._device.config["min_temp"]

    @property
    def preset_mode(self) -> Optional[str]:
        """Return the current preset mode, e.g., home, away, temp."""
        if self._device._evo.system_mode is None or self._device.mode is None:
            return

        if self._device._evo.system_mode[SYSTEM_MODE] in (
            SystemMode.AWAY,
            SystemMode.HEAT_OFF,
        ):
            return TCS_PRESET_TO_HA.get(self._device._evo.system_mode[SYSTEM_MODE])
        return EVOZONE_PRESET_TO_HA.get(self._device.mode[MODE])

    @property
    def preset_modes(self) -> Optional[List[str]]:
        """Return a list of available preset modes."""
        return self._preset_modes

    @property
    def target_temperature(self) -> Optional[float]:
        """Return the temperature we try to reach."""
        return self._device.setpoint

    def set_hvac_mode(self, hvac_mode: str) -> None:
        """Set a Zone to one of its native operating modes."""
        if hvac_mode == HVAC_MODE_AUTO:  # FollowSchedule
            self._device.reset_mode()

        elif hvac_mode == HVAC_MODE_HEAT:  # TemporaryOverride
            self._device.set_mode(mode=ZoneMode.PERMANENT, setpoint=25)

        else:  # HVAC_MODE_OFF, PermentOverride, temp = min
            self._device.set_frost_mode()

    def set_temperature(self, **kwargs) -> None:
        """Set a new target temperature."""
        setpoint = kwargs["temperature"]
        mode = kwargs.get(MODE)
        until = kwargs.get("until")

        if mode is None and until is None:
            self._device.setpoint = setpoint
        else:
            self._device(mode=mode, setpoint=setpoint, until=until)

    def set_preset_mode(self, preset_mode: Optional[str]) -> None:
        """Set the preset mode; if None, then revert to following the schedule."""
        evozone_preset_mode = HA_PRESET_TO_EVOZONE.get(preset_mode, ZoneMode.SCHEDULE)
        setpoint = self._device.setpoint

        if evozone_preset_mode == ZoneMode.SCHEDULE:
            self._device.reset_mode()
        elif evozone_preset_mode == ZoneMode.TEMPORARY:
            self._device.set_mode(mode=ZoneMode.TEMPORARY, setpoint=setpoint)
        elif evozone_preset_mode == ZoneMode.PERMANENT:
            self._device.set_mode(mode=ZoneMode.PERMANENT, setpoint=setpoint)

    def svc_reset_zone_config(self) -> None:
        """Reset the configuration of the Zone."""
        self._device.reset_config()

    def svc_set_zone_config(self, **kwargs) -> None:
        """Set the configuration of the Zone (min/max temp, etc.)."""
        self.svc_set_zone_mode(**kwargs)

    def svc_reset_zone_mode(self) -> None:
        """Reset the operating mode of the Zone."""
        self._device.reset_mode()

    def svc_set_zone_mode(
        self, mode=None, setpoint=None, duration=None, until=None
    ) -> None:
        """Set the (native) operating mode of the Zone."""
        if until is None and duration is not None:
            until = dt.now() + duration
        self._device.set_mode(mode=mode, setpoint=setpoint, until=until)


class EvoController(EvoZoneBase, ClimateEntity):
    """Base for a Honeywell Controller/Location."""

    def __init__(self, broker, device) -> None:
        """Initialize a Controller."""
        _LOGGER.info("Found a Controller, id=%s", device.id)
        super().__init__(broker, device)

        self._unique_id = device.id
        self._icon = "mdi:thermostat"

        self._supported_features = SUPPORT_PRESET_MODE | SUPPORT_TARGET_TEMPERATURE

    def _handle_dispatch(self, *args) -> None:
        """Process a service request (system mode) for a controller.

        Data validation is not required, it will have been done upstream.
        """
        if not args:
            self.async_schedule_update_ha_state(force_refresh=True)
            return

        payload = args[0]
        if payload.get("unique_id") != self._device.id:
            return
        elif payload["service"] == SVC_RESET_SYSTEM:
            self.svc_reset_system()
        elif payload["service"] == SVC_SET_SYSTEM_MODE:
            self.svc_set_system_mode(**payload["data"])

    @property
    def current_temperature(self) -> Optional[float]:
        """Return the average current temperature of the heating Zones.

        Controllers do not have a current temp, but one is expected by HA.
        """
        temps = [z.temperature for z in self._device.zones if z.temperature is not None]
        return round(sum(temps) / len(temps), 1) if temps else None

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            "heat_demand": self._device.heat_demand,
            "heat_demands": self._device.heat_demands,
            "relay_demands": self._device.relay_demands,
        }

    @property
    def hvac_action(self) -> Optional[str]:
        """Return the current running hvac operation if supported."""

        # return

        if self._device.system_mode is None:
            return
        if self._device.system_mode[SYSTEM_MODE] == SystemMode.HEAT_OFF:
            return CURRENT_HVAC_OFF
        if self._device.heat_demand:  # TODO: is maybe because of DHW
            return CURRENT_HVAC_HEAT
        return CURRENT_HVAC_IDLE
        # return CURRENT_HVAC_HEAT

    @property
    def hvac_mode(self) -> Optional[str]:
        """Return the current operating mode of a Controller."""

        if self._device.system_mode is None:
            return
        if self._device.system_mode[SYSTEM_MODE] == SystemMode.HEAT_OFF:
            return HVAC_MODE_OFF
        if self._device.system_mode[SYSTEM_MODE] == SystemMode.AWAY:
            return HVAC_MODE_AUTO  # users can't adjust setpoints in away mode
        return HVAC_MODE_HEAT

    @property
    def hvac_modes(self) -> List[str]:
        """Return the list of available hvac operation modes."""

        return [HVAC_MODE_OFF, HVAC_MODE_HEAT]  # HVAC_MODE_AUTO,

    @property
    def max_temp(self) -> None:
        """Return None as Controllers don't have a target temperature."""
        return

    @property
    def min_temp(self) -> None:
        """Return None as Controllers don't have a target temperature."""
        return

    @property
    def name(self) -> str:
        """Return the name of the Controller."""
        return "Controller"

    @property
    def preset_mode(self) -> Optional[str]:
        """Return the current preset mode, e.g., home, away, temp."""

        if self._device.system_mode is None:
            return

        return TCS_MODE_TO_HA_PRESET.get(
            self._device.system_mode[SYSTEM_MODE], PRESET_NONE
        )

    @property
    def preset_modes(self) -> Optional[List[str]]:
        """Return a list of available preset modes.

        Requires SUPPORT_PRESET_MODE.
        """
        return [PRESET_NONE, PRESET_ECO, PRESET_AWAY, PRESET_HOME, "custom"]

    @property
    def target_temperature(self) -> Optional[float]:
        """Return the temperature we try to reach."""
        zones = [z for z in self._device.zones if z.setpoint is not None]
        temps = [z.setpoint for z in zones if z.heat_demand is not None]
        if temps:
            return min(temps)
        return max([z.setpoint for z in zones]) if temps else None

        # temps = [z.setpoint for z in self._device.zones]
        # return round(sum(temps) / len(temps), 1) if temps else None

    def set_hvac_mode(self, hvac_mode: str) -> None:
        """Set an operating mode for a Controller."""
        self.svc_set_system_mode(HA_HVAC_TO_TCS.get(hvac_mode))

    def set_preset_mode(self, preset_mode: Optional[str]) -> None:
        """Set the preset mode; if None, then revert to 'Auto' mode."""
        self.svc_set_system_mode(HA_PRESET_TO_TCS.get(preset_mode, SystemMode.AUTO))

    def svc_reset_system(self) -> None:
        """Reset the operating mode of the Controller."""
        self._device.reset_mode()

    def svc_set_system_mode(self, mode, period=None, days=None) -> None:
        """Set the (native) operating mode of the Controller."""
        if period is not None:
            until = dt.now() + period
        elif days is not None:
            until = dt.now() + period
        else:
            until = None
        self._device.set_mode(system_mode=mode, until=until)
