from typing import Dict, List, Sequence
import asyncio
import json

from autogen_agentchat.conditions import FunctionalTermination
from autogen_agentchat.messages import BaseAgentEvent, BaseChatMessage, TextMessage
from autogen_agentchat.teams import DiGraphBuilder, GraphFlow

import logging

from .agents.explore_agent import ExploreAgent
from .agents.assert_agent import AssertAgent
from .agents.reviewer_agent import ReviewerAgent
from .agents.empty_agent import EmptyAgent
from .agents.pass_agent import PassAgent

from utils import print_log
from .tools.java_project_tools import get_java_project_tools
from .tools.python_project_tools import get_python_project_tools
from .model_client.openai_api_client import OpenAIAPIClient


def check_termination(messages: Sequence[BaseAgentEvent | BaseChatMessage]) -> bool:
    content = json.loads(messages[-1].content)
    return content['termination']


async def run_pipeline(
        data: Dict,
        sampling_args: Dict,
        generation_mode: str,
        lang: str,

        model_path: str,
        api_key: str,
        base_url: str,
        max_tool_calls: int,
        max_reviews: int,
        debug_port: int,

        with_dynamic: bool,
        with_explore_agent: bool,

        with_locals: bool,

        debug_cache_dir: str,
        nums: int,
        max_tries: int,
        existing_assert_code: List[str],
) -> List[str]:
    logging.getLogger('autogen').setLevel(logging.CRITICAL)

    kwargs = {
        'model': model_path,
        'base_url': base_url,
        'api_key': api_key,
        'model_info': {
            'vision': False,
            'function_calling': True,
            'json_output': True,
            'structured_output': True,
            'family': 'api'
        },
    }
    model_client = OpenAIAPIClient(**kwargs)

    if lang.lower() == 'java':
        project_tools, tools = get_java_project_tools(data, debug_port, debug_cache_dir)
    else:
        project_tools, tools = get_python_project_tools(data, debug_cache_dir)

    if with_dynamic or with_locals:
        project_tools.start_debugger()

    tries = 0
    all_assert_codes = [a for a in existing_assert_code]
    while tries < max_tries:
        gen_id = len(all_assert_codes)
        data['gen_id'] = gen_id
        print_log(f'[{gen_id}]', level=2)

        builder = DiGraphBuilder()
        part = []

        if with_explore_agent:
            explore_agent = ExploreAgent(
                data=data,
                model_client=model_client,
                sampling_args=sampling_args,
                generation_mode=generation_mode,
                lang=data['lang'],
                placeholder=data['placeholder'],
            )
            builder.add_node(explore_agent)
            part.append(explore_agent)
        else:
            starter = PassAgent()
            builder.add_node(starter)
            part.append(starter)

        if with_dynamic:
            debug_tool = [tools['get_debug_value']]
        else:
            debug_tool = []

        assert_agent = AssertAgent(
            data=data,
            model_client=model_client,
            sampling_args=sampling_args,
            generation_mode=generation_mode,
            tools=[],
            project_tools=project_tools,
            max_tool_calls=max_tool_calls,
            lang=data['lang'],
            placeholder=data['placeholder'],
            with_dynamic=with_dynamic,
            with_locals=with_locals,
            with_explore_agent=with_explore_agent,
            existing_assert_codes=all_assert_codes,
        )
        reviewer_agent = ReviewerAgent(
            data=data,
            model_client=model_client,
            sampling_args=sampling_args,
            generation_mode=generation_mode,
            tools=debug_tool,
            project_tools=project_tools,
            max_tool_calls=max_tool_calls,
            lang=data['lang'],
            placeholder=data['placeholder'],
            max_reviews=max_reviews,
            with_dynamic=with_dynamic,
            with_locals=with_locals,
            with_explore_agent=with_explore_agent,
        )
        empty_agent = EmptyAgent()
        builder.add_node(assert_agent)
        part.append(assert_agent)

        builder.add_node(reviewer_agent)
        part.append(reviewer_agent)

        builder.add_node(empty_agent)
        part.append(empty_agent)

        if with_explore_agent:
            builder.add_edge(explore_agent, assert_agent, activation_group='initial')
        else:
            builder.add_edge(starter, assert_agent, activation_group='initial')

        builder.add_edge(assert_agent, reviewer_agent)

        builder.add_edge(reviewer_agent, assert_agent, activation_group='feedback', condition=lambda msg: not json.loads(msg.content)['termination'])
        builder.add_edge(reviewer_agent, empty_agent, condition=lambda msg: json.loads(msg.content)['termination'])

        graph = builder.build()

        print(f'Graph: {graph}')

        flow = GraphFlow(
            part,
            graph=graph,
            termination_condition=FunctionalTermination(check_termination),
        )

        data['termination'] = False
        user_msg = TextMessage(
            source='user',
            content=json.dumps(data)
        )
        result = await flow.run(task=user_msg)

        print(result.stop_reason)
        final_result = json.loads(result.messages[-1].content)['assert_code']

        if final_result != '':
            all_assert_codes.append(final_result)

        if len(all_assert_codes) >= nums:
            break

        tries += 1

    project_tools.close()
    await model_client.close()

    return all_assert_codes


def generate_assert(
        data: Dict,
        sampling_args: Dict,
        generation_mode: str,
        lang: str,

        model_path: str,
        base_url: str,
        api_key: str,
        max_tool_calls: int,
        max_reviews: int,
        debug_port: int,

        with_dynamic: bool,
        with_explore_agent: bool,
        with_locals: bool,
        debug_cache_dir: str,

        nums: int,
        max_tries: int,
        existing_assert_code: List[str],
) -> List[str]:
    return asyncio.run(
        run_pipeline(
            data=data,
            sampling_args=sampling_args,
            generation_mode=generation_mode,
            lang=lang,

            model_path=model_path,
            base_url=base_url,
            api_key=api_key,
            max_tool_calls=max_tool_calls,
            max_reviews=max_reviews,
            debug_port=debug_port,

            with_explore_agent=with_explore_agent,
            debug_cache_dir=debug_cache_dir,
            with_dynamic=with_dynamic,
            with_locals=with_locals,

            nums=nums,
            max_tries=max_tries,
            existing_assert_code=existing_assert_code,
        )
    )
