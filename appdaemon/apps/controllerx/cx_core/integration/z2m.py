import json
from typing import Optional

from appdaemon.plugins.hass.hassapi import Hass  # type: ignore
from appdaemon.plugins.mqtt.mqttapi import Mqtt  # type: ignore

from cx_const import TypeActionsMapping
from cx_core.integration import Integration

LISTENS_TO_HA = "ha"
LISTENS_TO_MQTT = "mqtt"


class Z2MIntegration(Integration):
    def get_name(self) -> str:
        return "z2m"

    def get_actions_mapping(self) -> Optional[TypeActionsMapping]:
        return self.controller.get_z2m_actions_mapping()

    def listen_changes(self, controller_id: str) -> None:
        listens_to = self.kwargs.get("listen_to", LISTENS_TO_HA)
        if listens_to == LISTENS_TO_HA:
            Hass.listen_state(self.controller, self.state_callback, controller_id)
        elif listens_to == LISTENS_TO_MQTT:
            Mqtt.listen_event(
                self.controller,
                self.event_callback,
                topic=f"zigbee2mqtt/{controller_id}",
                namespace="mqtt",
            )
        else:
            raise ValueError(
                "`listen_to` has to be either `ha` or `mqtt`. Default is `ha`."
            )

    async def event_callback(self, event_name: str, data: dict, kwargs: dict) -> None:
        self.controller.log(f"MQTT data event: {data}", level="DEBUG")
        action_key = self.kwargs.get("action_key", "action")
        if "payload" not in data:
            return
        payload = json.loads(data["payload"])
        if action_key not in data["payload"]:
            self.controller.log(
                f"⚠️ There is no `{action_key}` in the MQTT topic payload",
                level="WARNING",
                ascii_encode=False,
            )
            return
        await self.controller.handle_action(payload[action_key])

    async def state_callback(
        self, entity: Optional[str], attribute: Optional[str], old, new, kwargs
    ) -> None:
        await self.controller.handle_action(new)
