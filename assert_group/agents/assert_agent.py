from typing import List, Dict, Tuple, Union, override
from autogen_core.tools import Tool
import json

from .utils import extract_llm_messages, add_line_number

from utils import print_log, append_jsonl
from utils.code_utils import extract_last_block

from .agent_with_tools import AgentWithTools
from ..model_client import OpenAIAPIClient
from ..tools.project_tools import ProjectTools


class AssertAgent(AgentWithTools):
    def __init__(
            self,
            data: Dict,
            model_client: OpenAIAPIClient,
            sampling_args: Dict,
            generation_mode: str,
            tools: List[Tool],
            project_tools: ProjectTools,
            max_tool_calls: int,
            lang: str,
            placeholder: str,
            with_dynamic: bool,
            with_locals: bool,
            with_explore_agent: bool,
            existing_assert_codes: List[str],
    ) -> None:
        name = 'AssertAgent'
        description = 'Generate assert statement.'
        self.with_dynamic = with_dynamic and len(tools) > 0
        self.with_locals = with_locals and len(tools) > 0

        system_prompt = 'You are a professional software engineer.'
        if lang.lower() == 'java':
            system_prompt += '\nYou can write Java assert statements based on the method under test, unit test prefix and test setup.'
        elif lang.lower() == 'python':
            system_prompt += '\nYou can write Python assert statements based on the method under test, unit test prefix and test setup.'
        else:
            raise NotImplementedError

        if self.with_dynamic:
            system_prompt += '\nYou can use the `get_debug_value` tool to query the values of variables or expressions in the test function. Do not repeat the query and call this tool up to 5 times at most.'

        super().__init__(
            name=name,
            description=description,
            model_client=model_client,
            sampling_args=sampling_args,
            generation_mode=generation_mode,
            tools=tools,
            max_tool_calls=max_tool_calls,
            system_prompt=system_prompt,
            json_output=None
        )

        self.data = data
        self.project_tools = project_tools
        self.lang = lang
        self.placeholder = placeholder
        self.with_explore_agent = with_explore_agent
        self.existing_assert_codes = existing_assert_codes

    @override
    def _init_all(self):
        super()._init_all()
        self.act_status = 'user'
        self.local_vars = None

    async def before_call_llm(self) -> Tuple[bool, str]:
        if self.act_status == 'retry':
            return True, '''Okay, please write the final result now in a markdown JSON block, for example:
```json
{
    "assert_code": "..."
}
```
'''

        if self.act_status == 'user':
            focal_method = self.data['focal_method']
            test_prefix = self.data['test_prefix']

            focal_method = add_line_number(
                focal_method,
                [i for i in range(self.data['focal_method_start_lineno'], self.data['focal_method_end_lineno'] + 1)],
            )
            if self.lang.lower() == 'java':
                test_setup = '\n...\n'.join([
                    add_line_number(
                        ts['test_setup'],
                        [i for i in range(ts['start_lineno'], ts['end_lineno'] + 1)]
                    ) for ts in self.data['test_setup_list']
                ])
            else:
                test_setup = add_line_number(
                    self.data['test_setup'],
                    [i for i in range(self.data['test_setup_start_lineno'], self.data['test_setup_end_lineno'] + 1)]
                )
            test_prefix = add_line_number(
                test_prefix,
                [i for i in range(self.data['test_prefix_start_lineno'], self.data['test_prefix_end_lineno'] + 1)]
            )

            if self.lang.lower() == 'java':
                user_prompt = f'''\
You will be provided with the file path and function body of a method under test, a test setup, and the corresponding unit test.
The other parts of the unit test have already been written, but there is still one assert statement that has not been completed, which is located in the `{self.data['placeholder']}` position.
This assert statement should meet the following requirements:
1. Test the method under test.
2. Be a single line of `org.junit.Assert` statement.
3. Maintain consistent writing habits and styles with other assert statements.
4. Cannot introduce any additional dependencies that are not currently introduced.
'''
            elif self.lang.lower() == 'python':
                user_prompt = f'''\
You will be provided with the file path and function body of a method under test, a test setup, and the corresponding unit test.
The other parts of the unit test have already been written, but there is still one assert statement that has not been completed, which is located in the `{self.data['placeholder']}` position.
This assert statement should meet the following requirements:
1. Test the method under test.
2. Be a single line of Python assert statement.
3. Maintain consistent writing habits and styles with other assert statements.
'''
            else:
                raise NotImplementedError

            if self.with_explore_agent:
                user_prompt += '\nYou will also be provided with the callees of method under test and unit test, along with the advice on the style of assert statement writing.\n'

            user_prompt += '\nYour task is to write this assert statement.\n'
            if len(self.existing_assert_codes) > 0:
                ext = '\n'.join(list(set(self.existing_assert_codes))).strip()
                user_prompt += f'''\
Here are some candidate answers, you must write one that is **completely different** from them.
```{self.lang.lower()}
{ext}
```

'''

            if self.lang.lower() == 'java':
                user_prompt += '''\
Your final answer needs to be in strictly JSON dictionary format, with a field `assert_code` representing this assert statement. It must be a single Java assert statement ending with a semicolon rather than multiple lines of code. You should write your final answer in a markdown JSON block. For example:
```json
{
    "assert_code": "..."
}
```
'''
            else:
                user_prompt += '''\
Your final answer needs to be in strictly JSON dictionary format, with a field `assert_code` representing this assert statement. It must be a single Python assert statement rather than multiple lines of code. You should write your final answer in a markdown JSON block. For example:
```json
{
    "assert_code": "..."
}
```
'''

            if self.with_explore_agent:
                explore_content = self.get_last_source_content('ExploreAgent')
                if explore_content['explore_focal_method'] != '':
                    user_prompt += f'''\n\n\n# Code Context Related to Method Under Test\n\n{explore_content['explore_focal_method']}\n'''

            user_prompt += f'''\n# Method Under Test\n...\n{focal_method}\n...\n'''
            user_prompt += f'''\n\n# Test Setup\n...\n{test_setup}\n...\n'''

            if self.with_explore_agent:
                explore_content = self.get_last_source_content('ExploreAgent')
                if explore_content['explore_test_prefix'] != '':
                    user_prompt += f'''\n\n# Code Context Related to Unit Test\n\n{explore_content['explore_test_prefix']}\n'''

            user_prompt += f'''\n# Unit Test\n...\n{test_prefix}\n...\n'''

            if self.with_explore_agent:
                explore_content = self.get_last_source_content('ExploreAgent')
                if self.lang.lower() == 'java':
                    user_prompt += f'''\n\n# Conclusion of Assert Statement Style in the Current Test Class\n\n{explore_content['explore_assert_style']}\n'''
                elif self.lang.lower() == 'python':
                    user_prompt += f'''\n\n# Conclusion of Assert Statement Style in the Current Test File\n\n{explore_content['explore_assert_style']}\n'''
                else:
                    raise NotImplementedError

            if self.with_locals:
                local_vars = await self.project_tools.get_locals()
                user_prompt += f'''\n\n# Local Variable Information\n{local_vars}\n'''

        else:
            reviewer_content = self.get_last_source_content('ReviewerAgent')
            if self.with_dynamic:
                user_prompt = 'Your answer has undergone automatic static check and running, '
            else:
                user_prompt = 'Your answer has undergone automatic static check, '
            user_prompt += f'''\
and the reviewer has provided some suggestions. Please try to rewrite the assert statement.
Also write it in a markdown JSON block.


# Static Check Result
{reviewer_content['static_check_result']}
'''
            if self.with_dynamic:
                user_prompt += f'''

# Test Run Result
{reviewer_content['test_run_result']}
'''

            user_prompt += f'''

# Suggestions
{reviewer_content['suggestions']}
'''
        return True, user_prompt

    async def after_call_llm(self, response_content: str, text_calls: int) -> Tuple[bool, Dict]:
        max_retries = 5
        try:
            self.act_status = 'review'
            json_content = extract_last_block(response_content)
            if json_content.strip() == '':
                json_content = response_content

            json_data = json.loads(json_content)
            assert json_data.__contains__('assert_code')
            assert_code = json_data['assert_code']
            return False, {
                'assert_code': assert_code,
                'termination': False
            }
        except Exception:
            if text_calls >= max_retries:
                self.act_status = 'user'
                return False, {
                    'assert_code': '',
                    'termination': True
                }
            else:
                self.act_status = 'retry'
                return True, {}

    def handle_model_resource(self, user_prompt: str, response_content: Union[str, List], usage: Dict, seconds: float) -> None:
        append_jsonl(
            self.data['resource_file'],
            {
                'type': 'llm', 'gen_id': self.data['gen_id'], 'agent': self.name,
                'iters': self.iters, 'usage': usage,
                'messages': extract_llm_messages(self.llm_messages), 'seconds': seconds
            }
        )
        print_log(f'{self.name} - user', user_prompt, 0)
        print_log(f'{self.name} - assistant', response_content, 0)
