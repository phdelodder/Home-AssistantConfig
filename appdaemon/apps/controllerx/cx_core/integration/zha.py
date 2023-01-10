from typing import Any, Dict, Optional

from appdaemon.plugins.hass.hassapi import Hass
from cx_const import DefaultActionsMapping
from cx_core.integration import EventData, Integration


class ZHAIntegration(Integration):
    name = "zha"

    def get_default_actions_mapping(self) -> Optional[DefaultActionsMapping]:
        return self.controller.get_zha_actions_mapping()

    async def listen_changes(self, controller_id: str) -> None:
        await Hass.listen_event(
            self.controller, self.event_callback, "zha_event", device_ieee=controller_id
        )

    def get_action(self, data: EventData) -> str:
        command = data["command"]
        args = data["args"]
        if isinstance(args, dict):
            args = args["args"]
        args = list(map(str, args))
        action = command
        if not (command == "stop" or command == "release"):
            if len(args) > 0:
                action += "_" + "_".join(args)
        return action

    async def event_callback(
        self, event_name: str, data: EventData, kwargs: Dict[str, Any]
    ) -> None:
        action = self.controller.get_zha_action(data)
        if action is None:
            # If there is no action extracted from the controller then
            # we extract with the standard function
            try:
                action = self.get_action(data)
            except Exception:
                self.controller.log(
                    f"The following event could not be parsed: {data}", level="WARNING"
                )
                return

        await self.controller.handle_action(action, extra=data)
