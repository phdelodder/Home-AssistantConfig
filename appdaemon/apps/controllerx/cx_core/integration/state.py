from typing import Any, Dict, Optional

from appdaemon.plugins.hass.hassapi import Hass
from cx_const import DefaultActionsMapping
from cx_core.integration import Integration


class StateIntegration(Integration):
    name = "state"

    def get_default_actions_mapping(self) -> Optional[DefaultActionsMapping]:
        return self.controller.get_state_actions_mapping()

    async def listen_changes(self, controller_id: str) -> None:
        attribute = self.kwargs.get("attribute", None)
        await Hass.listen_state(
            self.controller, self.state_callback, controller_id, attribute=attribute
        )

    async def state_callback(
        self,
        entity: Optional[str],
        attribute: Optional[str],
        old: Optional[str],
        new: str,
        kwargs: Dict[str, Any],
    ) -> None:
        await self.controller.handle_action(new, previous_state=old)
