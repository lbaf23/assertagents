from typing import Sequence

from autogen_agentchat.agents import BaseChatAgent
from autogen_agentchat.base import Response
from autogen_agentchat.messages import BaseChatMessage
from autogen_core import CancellationToken
from autogen_agentchat.messages import TextMessage

import json


class PassAgent(BaseChatAgent):
    def __init__(self) -> None:
        name = 'PassAgent'
        description = 'An empty agent that only pass messages.'
        super().__init__(name=name, description=description)

    @property
    def produced_message_types(self) -> Sequence[type[BaseChatMessage]]:
        return (TextMessage,)

    async def on_messages(self, messages: Sequence[BaseChatMessage], cancellation_token: CancellationToken) -> Response:
        return Response(chat_message=TextMessage(source=self.name, content=json.dumps({'termination': False})))

    async def on_reset(self, cancellation_token: CancellationToken) -> None:
        pass
