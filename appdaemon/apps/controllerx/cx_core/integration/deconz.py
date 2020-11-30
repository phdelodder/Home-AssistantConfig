from typing import Optional

from appdaemon.plugins.hass.hassapi import Hass  # type:ignore
from cx_core.integration import EventData, Integration, TypeActionsMapping


class DeCONZIntegration(Integration):
    name = "deconz"

    def get_actions_mapping(self) -> Optional[TypeActionsMapping]:
        return self.controller.get_deconz_actions_mapping()

    def listen_changes(self, controller_id: str) -> None:
        Hass.listen_event(
            self.controller, self.event_callback, "deconz_event", id=controller_id
        )

    async def event_callback(
        self, event_name: str, data: EventData, kwargs: dict
    ) -> None:
        type_ = self.kwargs.get("type", "event")
        await self.controller.handle_action(data[type_])
