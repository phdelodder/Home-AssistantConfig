from typing import Optional

from core.integration import Integration, TypeActionsMapping


class DeCONZIntegration(Integration):
    def get_name(self) -> str:
        return "deconz"

    def get_actions_mapping(self) -> Optional[TypeActionsMapping]:
        return self.controller.get_deconz_actions_mapping()

    def listen_changes(self, controller_id: str) -> None:
        self.controller.listen_event(self.callback, "deconz_event", id=controller_id)

    async def callback(self, event_name: str, data: dict, kwargs: dict) -> None:
        type_ = self.kwargs.get("type", "event")
        await self.controller.handle_action(data[type_])
