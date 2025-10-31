from typing import Sequence, List, Dict, Tuple, Union, Optional
from autogen_agentchat.agents import BaseChatAgent
from autogen_agentchat.messages import TextMessage
from autogen_agentchat.messages import BaseChatMessage
from autogen_agentchat.base import Response
from autogen_core import CancellationToken
from autogen_core.models import SystemMessage, UserMessage, AssistantMessage, LLMMessage, FunctionExecutionResult, FunctionExecutionResultMessage
from autogen_core import FunctionCall
from autogen_core.tools import Tool
from pydantic import BaseModel
from tenacity import retry, wait_random_exponential, stop_after_attempt

import datetime
import json
from abc import ABC, abstractmethod
import asyncio

from ..model_client import OpenAIAPIClient
from .utils import add_prompt_suffix


class AgentWithTools(BaseChatAgent):
    def __init__(
            self,
            name: str,
            description: str,
            model_client: OpenAIAPIClient,
            sampling_args: Dict,
            generation_mode: str,
            tools: List[Tool],
            max_tool_calls: int,
            system_prompt: str,
            json_output: Optional[bool | type(BaseModel)] = None,
    ) -> None:
        super().__init__(name=name, description=description)
        self.model_client = model_client
        self.sampling_args = sampling_args
        self.generation_mode = generation_mode
        self.tools = tools
        self.max_tool_calls = max_tool_calls
        self.system_prompt = system_prompt
        self.json_output = json_output
        self._init_all()

    def _init_all(self):
        self.llm_messages: List[LLMMessage] = [SystemMessage(content=self.system_prompt)]
        self.agent_messages: List[BaseChatMessage] = []
        self.iters = 0

    @property
    def produced_message_types(self) -> Sequence[type[BaseChatMessage]]:
        return (TextMessage,)

    @abstractmethod
    async def before_call_llm(self) -> Tuple[bool, str]:
        raise NotImplementedError()

    @abstractmethod
    async def after_call_llm(self, response_content: str, text_calls: int) -> Tuple[bool, Dict]:
        raise NotImplementedError()

    def handle_model_resource(self, user_prompt: str, response_content: Union[str, List], usage: Dict, seconds: float) -> None:
        pass

    def get_last_source_content(self, source: str) -> Optional[Dict]:
        for i in range(len(self.agent_messages) - 1, -1, -1):
            if self.agent_messages[i].source == source:
                return json.loads(self.agent_messages[i].content)
        return None

    async def on_messages(
            self,
            messages: Sequence[BaseChatMessage],
            cancellation_token: CancellationToken
    ) -> Response:
        self.agent_messages.extend(messages)
        print(f'''>>> Call {self.name}, source: {self.agent_messages[-1].source}''')

        call_llm = True
        text_calls = 0
        tool_calls = 0

        output_message = {}
        mode = 'text'

        while call_llm:
            self.iters += 1

            if mode == 'text':
                call_llm, user_prompt = await self.before_call_llm()
                response_content = user_prompt
            else:
                if tool_calls == self.max_tool_calls:
                    user_prompt = 'Okay, please stop calling tools now and provide the final answer.'
                    user_prompt = add_prompt_suffix(user_prompt, self.generation_mode)
                    self.llm_messages.append(UserMessage(content=user_prompt, source='user'))
                elif tool_calls > self.max_tool_calls:
                    # if still call tools, retry user_prompt(stop calling tools)
                    self.llm_messages.pop()  # pop FunctionExecutionResultMessage
                    self.llm_messages.pop()  # pop AssistantMessage
                    # self.llm_messages: [..., user_message("Okay, please stop calling ...")]


                call_llm = True
                user_prompt = ''
                response_content = ''

            if call_llm:
                if mode == 'text':
                    user_prompt = add_prompt_suffix(user_prompt, self.generation_mode)
                    self.llm_messages.append(UserMessage(content=user_prompt, source='user'))

                start_t = datetime.datetime.now()
                response = await self._call_llm(cancellation_token)
                end_t = datetime.datetime.now()
                seconds = (end_t - start_t).total_seconds()

                response_content = response.content
                usage = response.usage
                self.llm_messages.append(AssistantMessage(content=response_content, source='assistant'))

                self.handle_model_resource(user_prompt=user_prompt, response_content=response_content, usage=usage, seconds=seconds)

            # Tool calls
            if call_llm and type(response_content) == list and len(response_content) > 0:
                mode = 'tool'
                tool_calls += 1
                call_llm = True
                # Execute the tool calls.
                tool_results = await asyncio.gather(
                    *[self._execute_tool_call(call, cancellation_token) for call in response_content]
                )
                self.llm_messages.append(FunctionExecutionResultMessage(content=tool_results))

            # text response
            else:
                mode = 'text'
                text_calls += 1
                call_llm, output_message = await self.after_call_llm(response_content, text_calls)


        response_message = TextMessage(source=self.name, content=json.dumps(output_message))
        self.agent_messages.append(response_message)
        return Response(chat_message=response_message)

    @retry(wait=wait_random_exponential(min=3, max=10), stop=stop_after_attempt(5))
    async def _call_llm(self, cancellation_token):
        return await self.model_client.create(
            messages=self.llm_messages,
            tools=self.tools,
            extra_create_args=self.sampling_args,
            json_output=self.json_output,
            cancellation_token=cancellation_token,
        )

    async def _execute_tool_call(self, call: FunctionCall, cancellation_token: CancellationToken) -> FunctionExecutionResult:
        tool = next((tool for tool in self.tools if tool.name == call.name), None)
        try:
            # assert tool is not None
            arguments = json.loads(call.arguments)
            result = await tool.run_json(arguments, cancellation_token)
            return FunctionExecutionResult(
                call_id=call.id, content=tool.return_value_as_string(result), is_error=False, name=tool.name
            )
        except Exception as e:
            return FunctionExecutionResult(call_id=call.id, content=str(e), is_error=True, name=tool.name if tool else '')

    async def on_reset(self, cancellation_token: CancellationToken) -> None:
        pass
