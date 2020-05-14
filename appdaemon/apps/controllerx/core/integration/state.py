from typing import Optional

from const import TypeActionsMapping
from core.integration import Integration


class StateIntegration(Integration):
    def get_name(self) -> str:
        return "state"

    def get_actions_mapping(self) -> Optional[TypeActionsMapping]:
        return self.controller.get_z2m_actions_mapping()

    def listen_changes(self, controller_id: str) -> None:
        self.controller.listen_state(self.callback, controller_id)

    async def callback(
        self, entity: Optional[str], attribute: Optional[str], old, new, kwargs
    ) -> None:
        await self.controller.handle_action(new)
