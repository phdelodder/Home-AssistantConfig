import abc
import time
from collections import defaultdict
from functools import wraps
from typing import (
    Any,
    Callable,
    DefaultDict,
    Dict,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
)

from appdaemon.plugins.hass.hassapi import Hass  # type: ignore
from appdaemon.plugins.mqtt.mqttapi import Mqtt  # type: ignore

import cx_version
from cx_const import ActionFunction, TypeAction, TypeActionsMapping
from cx_core import integration as integration_module
from cx_core.integration import Integration

Service = Tuple[str, Dict]
Services = List[Service]

DEFAULT_DELAY = 350  # In milliseconds
DEFAULT_ACTION_DELTA = 300  # In milliseconds


def action(method) -> ActionFunction:
    @wraps(method)
    async def _action_impl(controller, *args, **kwargs):
        continue_call = await controller.before_action(method.__name__, *args, **kwargs)
        if continue_call:
            await method(controller, *args, **kwargs)

    return _action_impl


class Controller(Hass, Mqtt, abc.ABC):
    """
    This is the parent Controller, all controllers must extend from this class.
    """

    async def initialize(self) -> None:
        self.log(
            f"🎮 ControllerX {cx_version.__version__}", ascii_encode=False,
        )
        self.check_ad_version()

        # Get arguments
        self.controllers_ids = self.get_list(self.args["controller"])
        integration = self.get_integration(self.args["integration"])

        custom_mapping: Dict[Union[str, int], str] = self.args.get("mapping", None)
        self.actions_key_mapping = (
            self.get_actions_mapping(integration)
            if custom_mapping is None
            else {
                event: self.parse_action(action)
                for event, action in custom_mapping.items()
            }
        )

        self.type_actions_mapping = self.get_type_actions_mapping()
        if "actions" in self.args and "excluded_actions" in self.args:
            raise ValueError("`actions` and `excluded_actions` cannot be used together")
        included_actions = set(
            self.get_list(
                self.args.get("actions", list(self.actions_key_mapping.keys()))
            )
        )
        excluded_actions = set(self.get_list(self.args.get("excluded_actions", [])))
        included_actions = included_actions - excluded_actions
        default_action_delay = {action_key: 0 for action_key in included_actions}
        self.action_delay = {
            **default_action_delay,
            **self.args.get("action_delay", {}),
        }
        self.action_delta = self.args.get("action_delta", DEFAULT_ACTION_DELTA)
        self.action_times: DefaultDict[str, float] = defaultdict(lambda: 0.0)
        self.action_delay_handles: DefaultDict[str, Optional[float]] = defaultdict(
            lambda: None
        )

        # Filter the actions
        filter_actions_mapping: TypeActionsMapping = {
            key: value
            for key, value in self.actions_key_mapping.items()
            if key in included_actions
        }

        # Map the actions mapping with the real functions
        self.actions_mapping = {
            k: (self.type_actions_mapping[v] if isinstance(v, str) else v)
            for k, v in filter_actions_mapping.items()
        }

        for controller_id in self.controllers_ids:
            integration.listen_changes(controller_id)

    def get_option(self, value: str, options: List[str]) -> str:
        if value in options:
            return value
        else:
            raise ValueError(f"{value} is not an option. The options are {options}")

    def parse_integration(self, integration: Union[str, dict]) -> Dict[str, str]:
        if isinstance(integration, str):
            return {"name": integration}
        elif isinstance(integration, dict):
            if "name" in integration:
                return integration
            else:
                raise ValueError("'name' attribute is mandatory")
        else:
            raise ValueError(
                f"Type {type(integration)} is not supported for `integration` attribute"
            )

    def get_integration(self, integration: Union[str, dict]) -> Integration:
        parsed_integration = self.parse_integration(integration)
        kwargs = {k: v for k, v in parsed_integration.items() if k != "name"}
        integrations = integration_module.get_integrations(self, kwargs)
        integration_argument = self.get_option(
            parsed_integration["name"], [i.name for i in integrations]
        )
        return next(i for i in integrations if i.name == integration_argument)

    def check_ad_version(self) -> None:
        ad_version = self.get_ad_version()
        major, _, _ = ad_version.split(".")
        if int(major) < 4:
            raise ValueError("Please upgrade to AppDaemon 4.x")

    def get_actions_mapping(self, integration) -> TypeActionsMapping:
        actions_mapping = integration.get_actions_mapping()
        if actions_mapping is None:
            raise ValueError(f"This controller does not support {integration.name}.")
        return actions_mapping

    def get_list(self, entities: Union[Sequence[str], str]) -> List[str]:
        if isinstance(entities, str):
            return [entities]
        elif isinstance(entities, list):
            return entities
        else:
            return []

    async def call_service(self, service: str, **attributes) -> None:
        self.log(
            f"🤖 Service: \033[1m{service.replace('/', '.')}\033[0m",
            level="INFO",
            ascii_encode=False,
        )
        for attribute, value in attributes.items():
            if isinstance(value, float):
                value = f"{value:.2f}"
            self.log(
                f"  - {attribute}: {value}", level="INFO", ascii_encode=False,
            )
        return await Hass.call_service(self, service, **attributes)

    async def handle_action(self, action_key: str) -> None:
        if action_key in self.actions_mapping:
            previous_call_time = self.action_times[action_key]
            now = time.time() * 1000
            self.action_times[action_key] = now
            if now - previous_call_time > self.action_delta:
                self.log(
                    f"🎮 Button event triggered: `{action_key}`",
                    level="INFO",
                    ascii_encode=False,
                )
                await self.call_action(action_key)
        else:
            self.log(
                f"🎮 Button event triggered, but not registered: `{action_key}`",
                level="DEBUG",
                ascii_encode=False,
            )

    async def call_action(self, action_key: str):
        delay = self.action_delay[action_key]
        if delay > 0:
            handle = self.action_delay_handles[action_key]
            if handle is not None:
                await self.cancel_timer(handle)
            self.log(
                f"🕒 Running `{self.actions_key_mapping[action_key]}` in {delay} seconds",
                level="INFO",
                ascii_encode=False,
            )
            new_handle = await self.run_in(
                self.action_timer_callback, delay, action_key=action_key
            )
            self.action_delay_handles[action_key] = new_handle
        else:
            await self.action_timer_callback({"action_key": action_key})

    async def action_timer_callback(self, kwargs):
        action_key = kwargs["action_key"]
        self.action_delay_handles[action_key] = None
        self.log(
            f"🏃 Running `{self.actions_key_mapping[action_key]}` now",
            level="INFO",
            ascii_encode=False,
        )
        action, *args = self.get_action(self.actions_mapping[action_key])
        await action(*args)

    async def before_action(self, action: str, *args, **kwargs) -> bool:
        """
        Controllers have the option to implement this function, which is called
        everytime before an action is called and it has the check_before_action decorator.
        It should return True if the action shoul be called.
        Otherwise it should return False.
        """
        return True

    def get_action(self, action_value: Union[Sequence, Callable]):
        if isinstance(action_value, tuple) or isinstance(action_value, list):
            return action_value
        elif callable(action_value):
            return (action_value,)
        else:
            raise ValueError(
                "The action value from the action mapping should be a list or a function"
            )

    def parse_action(self, action) -> TypeAction:
        if isinstance(action, str):
            return action
        elif isinstance(action, dict) or isinstance(action, list):
            services: Services = []
            if isinstance(action, dict):
                action = [action]
            for act in action:
                service = act["service"].replace(".", "/")
                data = act.get("data", {})
                services.append((service, data))
            return (self.call_services, services)
        else:
            raise ValueError(
                f"{type(action)} is not supported for the mapping value attributes"
            )

    @action
    async def call_services(self, services: Services) -> None:
        for service, data in services:
            await self.call_service(service, **data)

    def get_z2m_actions_mapping(self) -> Optional[TypeActionsMapping]:
        """
        Controllers can implement this function. It should return a dict
        with the states that a controller can take and the functions as values.
        This is used for zigbee2mqtt support.
        """
        return None

    def get_deconz_actions_mapping(self) -> Optional[TypeActionsMapping]:
        """
        Controllers can implement this function. It should return a dict
        with the event id that a controller can take and the functions as values.
        This is used for deCONZ support.
        """
        return None

    def get_zha_actions_mapping(self) -> Optional[TypeActionsMapping]:
        """
        Controllers can implement this function. It should return a dict
        with the command that a controller can take and the functions as values.
        This is used for ZHA support.
        """
        return None

    def get_zha_action(self, data: dict) -> Optional[str]:
        """
        This method can be override for controllers that do not support
        the standard extraction of the actions on cx_core/integration/zha.py
        """
        return None

    def get_type_actions_mapping(self) -> TypeActionsMapping:
        return {}


class TypeController(Controller, abc.ABC):
    @abc.abstractmethod
    def get_domain(self) -> List[str]:
        raise NotImplementedError

    async def check_domain(self, entity: str) -> None:
        domains = self.get_domain()
        if entity.startswith("group."):
            entities = await self.get_state(entity, attribute="entity_id")
            same_domain = all(
                (
                    any(elem.startswith(domain + ".") for domain in domains)
                    for elem in entities
                )
            )
            if not same_domain:
                raise ValueError(
                    f"All entities from '{entity}' must be from one "
                    f"of the following domains {domains} (e.g. {domains[0]}.bedroom)"
                )
        elif not any(entity.startswith(domain + ".") for domain in domains):
            raise ValueError(
                f"'{entity}' must be from one of the following domains "
                f"{domains} (e.g. {domains[0]}.bedroom)"
            )

    async def get_entity_state(self, entity: str, attribute: str = None) -> Any:
        if entity.startswith("group."):
            entities = await self.get_state(entity, attribute="entity_id")
            if len(entities) == 0:
                raise ValueError(
                    f"The group `{entity}` does not have any entities registered."
                )
            entity = entities[0]
        out = await self.get_state(entity, attribute=attribute)
        return out


class ReleaseHoldController(Controller, abc.ABC):
    DEFAULT_MAX_LOOPS = 50

    async def initialize(self):
        self.on_hold = False
        self.delay = self.args.get("delay", self.default_delay())
        self.max_loops = self.args.get(
            "max_loops", ReleaseHoldController.DEFAULT_MAX_LOOPS
        )
        self.hold_release_toggle: bool = self.args.get("hold_release_toggle", False)
        await super().initialize()

    @action
    async def release(self) -> None:
        self.on_hold = False

    @action
    async def hold(self, *args) -> None:
        loops = 0
        self.on_hold = True
        stop = False
        while self.on_hold and not stop:
            stop = await self.hold_loop(*args)
            # Stop the iteration if we either stop from the hold_loop
            # or we reached the max loop number
            stop = stop or loops >= self.max_loops
            await self.sleep(self.delay / 1000)
            loops += 1
        self.on_hold = False

    async def before_action(self, action: str, *args, **kwargs) -> bool:
        super_before_action = await super().before_action(action, *args, **kwargs)
        to_return = not (action == "hold" and self.on_hold)
        if action == "hold" and self.on_hold and self.hold_release_toggle:
            self.on_hold = False
        return super_before_action and to_return

    @abc.abstractmethod
    async def hold_loop(self, *args) -> bool:
        """
        This function is called by the ReleaseHoldController depending on the settings.
        It stops calling the function once release action is called or when this function
        returns True.
        """
        raise NotImplementedError

    def default_delay(self) -> int:
        """
        This function can be overwritten for each device to indeicate the delay
        for the specific device, by default it returns the default delay from the app
        """
        return DEFAULT_DELAY
