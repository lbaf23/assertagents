from typing import Sequence, List, Dict, Tuple, Union, override
import os
from autogen_agentchat.messages import TextMessage, BaseChatMessage
from autogen_agentchat.base import Response
from autogen_core import CancellationToken
from autogen_core.models import SystemMessage, UserMessage, AssistantMessage
import json

from utils import print_log, append_jsonl, read_file, write_file, read_json, write_json

from utils.java_utils.java_file_utils import get_java_test_class_assert_preview
from utils.python_utils.python_file_utils import get_python_test_file_assert_preview
from utils.java_utils.java_file_utils import get_java_function_body_inline
from utils.python_utils.python_file_utils import get_python_function_body_inline

from .utils import extract_llm_messages
from .agent_with_tools import AgentWithTools
from ..model_client import OpenAIAPIClient


class ExploreAgent(AgentWithTools):
    def __init__(
            self,
            data: Dict,
            model_client: OpenAIAPIClient,
            sampling_args: Dict,
            generation_mode: str,
            lang: str,
            placeholder: str
    ) -> None:
        name = 'ExploreAgent'
        description = 'Explore the repository.'

        if lang.lower() == 'java':
            self.system_prompt_callee = f'''\
You are a professional software engineer.
You can summarize the functionality of a provided Java method or class.
Summarize in 2-4 sentences.'''
            self.system_prompt_style = f'''\
You are a professional software engineer.
You can summarize the writing style and habits of assert statements in the provided Java test methods.
You should list them in points, using clear and concise language, and you can use some assert examples to clarify.'''
        elif lang.lower() == 'python':
            self.system_prompt_callee = f'''\
You are a professional software engineer.
You can summarize the functionality of a provided Python function or class.
Summarize in 2-4 sentences.'''
            self.system_prompt_style = f'''\
You are a professional software engineer.
You can summarize the writing style and habits of assert statements in the provided Python functions.
You should list them in points, using clear and concise language, and you can use some assert examples to clarify.'''
        else:
            raise NotImplementedError

        super().__init__(
            name=name,
            description=description,
            model_client=model_client,
            sampling_args=sampling_args,
            generation_mode=generation_mode,
            tools=[],
            max_tool_calls=0,
            system_prompt=''
        )
        self.data = data
        self.lang = lang
        self.file_type = '.java' if self.lang.lower() == 'java' else '.py'
        self.placeholder = placeholder
        self.agent_cache_dir = os.path.join(self.data['agent_cache_dir'], self.name)
        os.makedirs(self.agent_cache_dir, exist_ok=True)

        self.max_callees = 10  # set to 10

    def _init_all(self):
        super()._init_all()
        self.act_status = None
        self.explore_focal_method = ''
        self.explore_test_prefix = ''

    def _clear_no_system_messages(self):
        self.llm_messages = self.llm_messages[:1]

    async def _explore_callees(
            self,
            callees: List[Dict],
            max_lineno: int,
            cancellation_token,
    ) -> str:
        calls_set = set()
        callees_summary = ''
        idx = 0
        for callee in callees:
            if len(calls_set) >= self.max_callees:
                break
            definition = callee['definition']
            if definition is None:
                continue
            file_path = str(os.path.join(self.data['repo_path'], definition['rel_file_path']))
            if not os.path.exists(file_path):
                continue

            # Ignore ...
            if max_lineno < 0 or max_lineno < (callee['start_line'] if callee.__contains__('start_line') else callee['line']) + 1:
                continue

            code = read_file(file_path)
            if self.lang.lower() == 'java':
                fbinfo = get_java_function_body_inline(code, definition['start_line'] + 1, show_parent_class=False, preview_add_lineno=False)
            else:
                fbinfo = get_python_function_body_inline(code, definition['start_line'] + 1, show_parent_class=False, preview_add_lineno=False)
            if fbinfo is None:
                continue

            if calls_set.__contains__(f'''{file_path}:{fbinfo['start_lineno']}'''):
                continue
            calls_set.add(f'''{file_path}:{fbinfo['start_lineno']}''')
            user_prompt = f'''\
### Target

```{self.lang.lower()}
{fbinfo['preview']}
```
'''
            self.llm_messages = [
                SystemMessage(content=self.system_prompt_callee),
                UserMessage(content=user_prompt, source='user'),
            ]
            response = await self._call_llm(cancellation_token)
            response_content = response.content
            usage = response.usage
            self.llm_messages.append(AssistantMessage(content=response_content, source='assistant'))
            self.handle_model_resource(user_prompt, response_content, usage=usage, seconds=0)

            target_defs = '\n'.join(code.splitlines()[fbinfo['start_lineno']-1 : fbinfo['body_start_lineno']])
            callees_summary += f'{idx + 1}: ' + target_defs.strip() + '\n' + response_content + '\n\n'
            idx += 1

        if callees_summary == '':
            callees_summary = '(empty)'

        return callees_summary

    async def _explore_assert_style(
            self,
            test_code_preview: str,
            cancellation_token
    ) -> str:
        if self.lang.lower() == 'java':
            user_prompt = f'''\
Please summarize the writing style and habits of assert statements in the following test methods:

{test_code_preview}
'''
        else:
            user_prompt = f'''\
Please summarize the writing style and habits of assert statements in the following test functions:

{test_code_preview}
'''
        self.llm_messages = [
            SystemMessage(content=self.system_prompt_style),
            UserMessage(content=user_prompt, source='user'),
        ]
        response = await self._call_llm(cancellation_token)
        response_content = response.content
        usage = response.usage
        self.llm_messages.append(AssistantMessage(content=response_content, source='assistant'))
        self.handle_model_resource(user_prompt, response_content, usage=usage, seconds=0)
        return response_content

    @override
    async def on_messages(
            self,
            messages: Sequence[BaseChatMessage],
            cancellation_token: CancellationToken
    ) -> Response:
        self.agent_messages.extend(messages)
        print(f'''>>> Call {self.name}, source: {self.agent_messages[-1].source}''')

        # Explore Callees of Focal method
        cache_dir = os.path.join(self.agent_cache_dir, self.data['repo_name'])
        os.makedirs(cache_dir, exist_ok=True)
        llm_cache_file1 = os.path.join(
            cache_dir,
            f'''func-{self.data['focal_method_file_path'].replace('/', '-')}:{self.data['focal_method_start_lineno']}.json'''
        )
        if os.path.exists(llm_cache_file1):
            content = read_json(llm_cache_file1)
            focal_method_callees = content['callees']
        else:
            call_extract_file = str(os.path.join(
                self.data['calls_extract_dir'],
                self.data['repo_name'],
                f'''{self.data['focal_method_file_path'].replace('/', '-')}:{self.data['focal_method_start_lineno']}.json'''
            ))
            calls = read_json(call_extract_file)
            focal_method_callees = await self._explore_callees(
                callees=calls['calls'],
                max_lineno=-1,
                cancellation_token=cancellation_token
            )
            write_json(llm_cache_file1, {'callees': focal_method_callees})

        # Explore Callees of Test prefix
        llm_cache_file2 = os.path.join(
            cache_dir,
            f'''func-{self.data['test_prefix_file_path'].replace('/', '-')}:{self.data['test_prefix_start_lineno']}.json'''
        )
        if os.path.exists(llm_cache_file2):
            content = read_json(llm_cache_file2)
            test_prefix_callees = content['callees']
        else:
            call_extract_file = str(os.path.join(
                self.data['calls_extract_dir'],
                self.data['repo_name'],
                f'''{self.data['test_prefix_file_path'].replace('/', '-')}:{self.data['test_prefix_start_lineno']}.json'''
            ))
            calls = read_json(call_extract_file)
            test_prefix_callees = await self._explore_callees(
                callees=calls['calls'],
                max_lineno=self.data['ground_truth_oracle_lineno'],
                cancellation_token=cancellation_token
            )
            write_json(llm_cache_file2, {'callees': test_prefix_callees})

        llm_cache_file3 = os.path.join(
            cache_dir,
            f'''style-{self.data['test_prefix_file_path'].replace('/', '-')}:{self.data['test_prefix_start_lineno']}.txt'''
        )
        if os.path.exists(llm_cache_file3):
            assert_style = read_file(llm_cache_file3)
        else:
            current_test_class = read_file(self.data['test_prefix_path'])
            if self.lang.lower() == 'java':
                test_code_preview = get_java_test_class_assert_preview(
                    code=current_test_class,
                    test_prefix=self.data['test_prefix'],
                    max_test_functions=10
                )
            else:
                test_code_preview = get_python_test_file_assert_preview(
                    code=current_test_class,
                    test_prefix=self.data['test_prefix'],
                    test_prefix_start_lineno=self.data['test_prefix_start_lineno'],
                    max_test_functions=10
                )
            assert_style = await self._explore_assert_style(
                test_code_preview=test_code_preview,
                cancellation_token=cancellation_token
            )
            write_file(llm_cache_file3, assert_style)

        explore_focal_method = f'''\
### Callees
{focal_method_callees}
'''
        explore_test_prefix = f'''\
### Callees
{test_prefix_callees}
'''
        output_message = {
            'explore_focal_method': explore_focal_method,
            'explore_test_prefix': explore_test_prefix,
            'explore_assert_style': assert_style,
            'termination': False
        }

        response_message = TextMessage(source=self.name, content=json.dumps(output_message))
        self.agent_messages.append(response_message)
        return Response(chat_message=response_message)

    def clear_later_messages(self):
        self.llm_messages = self.llm_messages[:1]

    async def before_call_llm(self) -> Tuple[bool, str]:
        raise NotImplementedError

    async def after_call_llm(self, response_content: str, text_calls: int) -> Tuple[bool, str]:
        raise NotImplementedError

    def handle_model_resource(self, user_prompt: str, response_content: Union[str, List], usage: Dict, seconds: float = 0) -> None:
        log = {
            'type': 'llm', 'gen_id': self.data['gen_id'], 'agent': self.name,
            'iters': self.iters, 'usage': usage,
            'messages': extract_llm_messages(self.llm_messages),
        }
        if seconds > 0:
            log['seconds'] = seconds
        append_jsonl(self.data['resource_file'], log)
        print_log(f'{self.name} - user', user_prompt, 0)
        print_log(f'{self.name} - assistant', response_content, 0)
