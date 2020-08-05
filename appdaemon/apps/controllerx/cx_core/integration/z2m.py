from typing import Optional

from appdaemon.plugins.hass.hassapi import Hass  # type: ignore

from cx_const import TypeActionsMapping
from cx_core.integration import Integration


class Z2MIntegration(Integration):
    def get_name(self) -> str:
        return "z2m"

    def get_actions_mapping(self) -> Optional[TypeActionsMapping]:
        return self.controller.get_z2m_actions_mapping()

    def listen_changes(self, controller_id: str) -> None:
        Hass.listen_state(self.controller, self.state_callback, controller_id)

    async def state_callback(
        self, entity: Optional[str], attribute: Optional[str], old, new, kwargs
    ) -> None:
        await self.controller.handle_action(new)
