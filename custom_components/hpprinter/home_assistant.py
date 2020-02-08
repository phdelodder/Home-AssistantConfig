"""
Support for Blue Iris.
For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/hpprinter/
"""
import sys
import logging

from homeassistant.const import (STATE_ON, STATE_OFF)
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.util import slugify

from .const import *

_LOGGER = logging.getLogger(__name__)


class HPPrinterHomeAssistant:
    def __init__(self, hass, scan_interval, name, hp_data):
        self._scan_interval = scan_interval
        self._hass = hass
        self._name = name
        self._hp_data = hp_data

    def initialize(self):
        if self._hp_data is not None:
            async_track_time_interval(self._hass, self.async_update, SCAN_INTERVAL)

            async_call_later(self._hass, 5, self.async_finalize)

    async def async_finalize(self, event_time):
        _LOGGER.debug(f"async_finalize called at {event_time}")

        self._hass.services.async_register(DOMAIN, 'save_debug_data', self.save_debug_data)

        self.update()

    async def async_update(self, event_time):
        _LOGGER.debug(f"async_update called at {event_time}")

        self.update()

    def save_debug_data(self, service_data):
        """Call BlueIris to refresh information."""
        _LOGGER.debug(f"Saving debug data {DOMAIN} ({service_data})")

        self._hp_data.get_data(self.store_data)

    def notify_error(self, ex, line_number):
        _LOGGER.error(f"Error while initializing {DOMAIN}, exception: {ex},"
                      f" Line: {line_number}")

        self._hass.components.persistent_notification.create(
            f"Error: {ex}<br /> You will need to restart hass after fixing.",
            title=NOTIFICATION_TITLE,
            notification_id=NOTIFICATION_ID)

    def notify_error_message(self, message):
        _LOGGER.error(f"Error while initializing {DOMAIN}, Error: {message}")

        self._hass.components.persistent_notification.create(
            (f"Error: {message}<br /> You will need to restart hass after"
             " fixing."),
            title=NOTIFICATION_TITLE,
            notification_id=NOTIFICATION_ID)

    def store_data(self, file, content):
        try:
            path = self._hass.config.path(file)

            with open(path, 'w+') as out:
                out.write(content)

        except Exception as ex:
            exc_type, exc_obj, tb = sys.exc_info()
            line_number = tb.tb_lineno

            _LOGGER.error(f'Failed to log {file} data, Error: {ex}, Line: {line_number}')

    def update(self):
        data = self._hp_data.get_data()

        cartridges_data = data.get(HP_DEVICE_CARTRIDGES)

        is_online = self.create_status_sensor(data)

        if is_online:
            self.create_printer_sensor(data)
            self.create_scanner_sensor(data)

            if cartridges_data is not None:
                for key in cartridges_data:
                    cartridge = cartridges_data.get(key)

                    if cartridge is not None:
                        self.create_cartridge_sensor(data, cartridge, key)

    def create_status_sensor(self, data):
        is_online = data.get(HP_DEVICE_IS_ONLINE, False)

        name = data.get("Name", DEFAULT_NAME)
        sensor_name = f"{name} {HP_DEVICE_STATUS}"
        entity_id = f"binary_sensor.{slugify(sensor_name)}"

        state = STATE_OFF
        if is_online:
            state = STATE_ON

        attributes = {
            "friendly_name": sensor_name,
            "device_class": "connectivity"
        }

        self._hass.states.async_set(entity_id, state, attributes)

        return is_online

    def create_printer_sensor(self, data):
        printer_data = data.get(HP_DEVICE_PRINTER)

        if printer_data is not None:
            name = data.get("Name", DEFAULT_NAME)
            sensor_name = f"{name} {HP_DEVICE_PRINTER}"
            entity_id = f"sensor.{slugify(sensor_name)}"

            state = printer_data.get(HP_DEVICE_PRINTER_STATE)

            attributes = {
                "unit_of_measurement": "Pages",
                "friendly_name": sensor_name
            }

            for key in printer_data:
                if key != HP_DEVICE_PRINTER_STATE:
                    attributes[key] = printer_data[key]

            self._hass.states.async_set(entity_id, state, attributes)

    def create_scanner_sensor(self, data):
        scanner_data = data.get(HP_DEVICE_SCANNER)

        if scanner_data is not None:
            name = data.get("Name", DEFAULT_NAME)
            sensor_name = f"{name} {HP_DEVICE_SCANNER}"
            entity_id = f"sensor.{slugify(sensor_name)}"

            state = scanner_data.get(HP_DEVICE_SCANNER_STATE)

            attributes = {
                "unit_of_measurement": "Pages",
                "friendly_name": sensor_name
            }

            for key in scanner_data:
                if key != HP_DEVICE_SCANNER_STATE:
                    attributes[key] = scanner_data[key]

            self._hass.states.async_set(entity_id, state, attributes)

    def create_cartridge_sensor(self, data, cartridge, key):
        name = data.get("Name", DEFAULT_NAME)
        sensor_name = f"{name} {key}"
        entity_id = f"sensor.{slugify(sensor_name)}"

        state = cartridge.get(HP_DEVICE_CARTRIDGE_STATE, 0)

        attributes = {
            "unit_of_measurement": "%",
            "friendly_name": sensor_name
        }

        for key in cartridge:
            if key != HP_DEVICE_CARTRIDGE_STATE:
                attributes[key] = cartridge[key]

        self._hass.states.async_set(entity_id, state, attributes)
