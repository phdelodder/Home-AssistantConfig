"""Vehicle detection using Plate Recognizer cloud service."""
import logging
import requests
import voluptuous as vol
import re
import io
from typing import List, Dict

from PIL import Image, ImageDraw, UnidentifiedImageError
from pathlib import Path

from homeassistant.components.image_processing import (
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_SOURCE,
    PLATFORM_SCHEMA,
    ImageProcessingEntity,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import split_entity_id
import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util
from homeassistant.util.pil import draw_box

_LOGGER = logging.getLogger(__name__)

PLATE_READER_URL = "https://api.platerecognizer.com/v1/plate-reader/"
STATS_URL = "https://api.platerecognizer.com/v1/statistics/"

EVENT_VEHICLE_DETECTED = "platerecognizer.vehicle_detected"

ATTR_PLATE = "plate"
ATTR_CONFIDENCE = "confidence"
ATTR_REGION_CODE = "region_code"
ATTR_VEHICLE_TYPE = "vehicle_type"

CONF_API_TOKEN = "api_token"
CONF_REGIONS = "regions"
CONF_SAVE_FILE_FOLDER = "save_file_folder"
CONF_SAVE_TIMESTAMPTED_FILE = "save_timestamped_file"
CONF_ALWAYS_SAVE_LATEST_FILE = "always_save_latest_file"
CONF_WATCHED_PLATES = "watched_plates"

DATETIME_FORMAT = "%Y-%m-%d_%H-%M-%S"
RED = (255, 0, 0)  # For objects within the ROI
DEFAULT_REGIONS = ['None']

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_API_TOKEN): cv.string,
        vol.Optional(CONF_REGIONS, default=DEFAULT_REGIONS): vol.All(
            cv.ensure_list, [cv.string]
        ),
        vol.Optional(CONF_SAVE_FILE_FOLDER): cv.isdir,
        vol.Optional(CONF_SAVE_TIMESTAMPTED_FILE, default=False): cv.boolean,
        vol.Optional(CONF_ALWAYS_SAVE_LATEST_FILE, default=False): cv.boolean,
        vol.Optional(CONF_WATCHED_PLATES): vol.All(
            cv.ensure_list, [cv.string]
        ),
    }
)

def get_plates(results : List[Dict]) -> List[str]:
    """
    Return the list of candidate plates. 
    If no plates empty list returned.
    """
    plates = []
    candidates = [result['candidates'] for result in results]
    for candidate in candidates:
        cand_plates = [cand['plate'] for cand in candidate]
        for plate in cand_plates:
            plates.append(plate)
    return list(set(plates))

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the platform."""
    # Validate credentials by processing image.
    save_file_folder = config.get(CONF_SAVE_FILE_FOLDER)
    if save_file_folder:
        save_file_folder = Path(save_file_folder)

    entities = []
    for camera in config[CONF_SOURCE]:
        platerecognizer = PlateRecognizerEntity(
            api_token=config.get(CONF_API_TOKEN),
            regions = config.get(CONF_REGIONS),
            save_file_folder=save_file_folder,
            save_timestamped_file=config.get(CONF_SAVE_TIMESTAMPTED_FILE),
            always_save_latest_file=config.get(CONF_ALWAYS_SAVE_LATEST_FILE),
            watched_plates=config.get(CONF_WATCHED_PLATES),
            camera_entity=camera[CONF_ENTITY_ID],
            name=camera.get(CONF_NAME),
        )
        entities.append(platerecognizer)
    add_entities(entities)


class PlateRecognizerEntity(ImageProcessingEntity):
    """Create entity."""

    def __init__(
        self,
        api_token,
        regions,
        save_file_folder,
        save_timestamped_file,
        always_save_latest_file,
        watched_plates,
        camera_entity,
        name,
    ):
        """Init."""
        self._headers = {"Authorization": f"Token {api_token}"}
        self._regions = regions
        self._camera = camera_entity
        if name:
            self._name = name
        else:
            camera_name = split_entity_id(camera_entity)[1]
            self._name = f"platerecognizer_{camera_name}"
        self._save_file_folder = save_file_folder
        self._save_timestamped_file = save_timestamped_file
        self._always_save_latest_file = always_save_latest_file
        self._watched_plates = watched_plates
        self._state = None
        self._results = {}
        self._vehicles = [{}]
        self._plates = []
        self._statistics = {}
        self._last_detection = None
        self._image_width = None
        self._image_height = None
        self._image = None
        self.get_statistics()

    def process_image(self, image):
        """Process an image."""
        self._state = None
        self._results = {}
        self._vehicles = [{}]
        self._plates = []
        self._image = Image.open(io.BytesIO(bytearray(image)))
        self._image_width, self._image_height = self._image.size
        if self._regions == DEFAULT_REGIONS:
            regions = None
        else:
            regions = self._regions
        try:
            response = requests.post(
                PLATE_READER_URL, 
                data=dict(regions=regions, camera_id=self.name),  
                files={"upload": image}, 
                headers=self._headers
            ).json()
            self._results = response["results"]
            self._plates = get_plates(response['results'])
            self._vehicles = [
                {
                    ATTR_PLATE: r["plate"],
                    ATTR_CONFIDENCE: r["score"],
                    ATTR_REGION_CODE: r["region"]["code"],
                    ATTR_VEHICLE_TYPE: r["vehicle"]["type"],
                }
                for r in self._results
            ]
        except Exception as exc:
            _LOGGER.error("platerecognizer error: %s", exc)
            _LOGGER.error(f"platerecognizer api response: {response}")

        self._state = len(self._vehicles)
        if self._state > 0:
            self._last_detection = dt_util.now().strftime(DATETIME_FORMAT)
            for vehicle in self._vehicles:
                self.fire_vehicle_detected_event(vehicle)
        if self._save_file_folder:
            if self._state > 0 or self._always_save_latest_file:
                self.save_image()
        self.get_statistics()

    def get_statistics(self):
        try:
            response = requests.get(STATS_URL, headers=self._headers).json()
            calls_remaining = response["total_calls"] - response["usage"]["calls"]
            response.update({"calls_remaining": calls_remaining})
            self._statistics = response.copy()
        except Exception as exc:
            _LOGGER.error("platerecognizer error getting statistics: %s", exc)

    def fire_vehicle_detected_event(self, vehicle):
        """Send event."""
        vehicle_copy = vehicle.copy()
        vehicle_copy.update({ATTR_ENTITY_ID: self.entity_id})
        self.hass.bus.fire(EVENT_VEHICLE_DETECTED, vehicle_copy)

    def save_image(self):
        """Save a timestamped image with bounding boxes around plates."""
        draw = ImageDraw.Draw(self._image)

        decimal_places = 3
        for vehicle in self._results:
            box = (
                    round(vehicle['box']["ymin"] / self._image_height, decimal_places),
                    round(vehicle['box']["xmin"] / self._image_width, decimal_places),
                    round(vehicle['box']["ymax"] / self._image_height, decimal_places),
                    round(vehicle['box']["xmax"] / self._image_width, decimal_places),
            )
            text = vehicle['plate']
            draw_box(
                draw,
                box,
                self._image_width,
                self._image_height,
                text=text,
                color=RED,
                )

        latest_save_path = self._save_file_folder / f"{self._name}_latest.png"
        self._image.save(latest_save_path)

        if self._save_timestamped_file:
            timestamp_save_path = self._save_file_folder / f"{self._name}_{self._last_detection}.png"
            self._image.save(timestamp_save_path)
            _LOGGER.info("platerecognizer saved file %s", timestamp_save_path)

    @property
    def camera_entity(self):
        """Return camera entity id from process pictures."""
        return self._camera

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    @property
    def state(self):
        """Return the state of the entity."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return ATTR_PLATE

    @property
    def device_state_attributes(self):
        """Return the attributes."""
        attr = {}
        attr.update({"last_detection": self._last_detection})
        attr.update({"vehicles": self._vehicles})
        if self._watched_plates:
            watched_plates_results = {plate : False for plate in self._watched_plates}
            for plate in self._watched_plates:
                if plate in self._plates:
                    watched_plates_results.update({plate: True})
            attr[CONF_WATCHED_PLATES] = watched_plates_results
        attr.update({"statistics": self._statistics})
        if self._regions != DEFAULT_REGIONS:
            attr[CONF_REGIONS] = self._regions
        if self._save_file_folder:
            attr[CONF_SAVE_FILE_FOLDER] = str(self._save_file_folder)
            attr[CONF_SAVE_TIMESTAMPTED_FILE] = self._save_timestamped_file
            attr[CONF_ALWAYS_SAVE_LATEST_FILE] = self._always_save_latest_file
        return attr
