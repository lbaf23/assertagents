from typing import List, Dict, Tuple, Union
import json

from .utils import extract_llm_messages, add_line_number
from .agent_with_tools import AgentWithTools
from ..model_client import OpenAIAPIClient

from ..tools.project_tools import ProjectTools

from .utils import handle_assert_code

from utils.code_utils import extract_last_block
from utils import print_log, append_jsonl


class ReviewerAgent(AgentWithTools):
    def __init__(
            self,
            data: Dict,
            model_client: OpenAIAPIClient,
            sampling_args: Dict,
            generation_mode: str,
            project_tools: ProjectTools,
            tools: List,
            max_tool_calls: int,
            lang: str,
            placeholder: str,
            max_reviews: int,
            with_locals: bool,
            with_dynamic: bool,
            with_explore_agent: bool,
    ) -> None:
        name = 'ReviewerAgent'
        description = 'Generate the assert statement based on the check target and expected behaviour.'

        self.with_dynamic = with_dynamic and len(tools) > 0
        self.with_locals = with_locals and len(tools) > 0

        if lang.lower() == 'java':
            system_prompt = f'''\
You are a professional software reviewer.
You can determine whether the assert statement written by the programmer is correct based on static check result and test run result.'''
        elif lang.lower() == 'python':
            system_prompt = f'''\
You are a professional software reviewer.
You can determine whether the assert statement written by the programmer is correct based on static check result and test run result.'''
        else:
            raise ValueError()

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
        self.reviews = 0
        self.max_reviews = max_reviews
        self.with_explore_agent = with_explore_agent

    def _init_all(self):
        super()._init_all()
        self.act_status = 'recv'
        self.termination = False

    async def before_call_llm(self) -> Tuple[bool, str]:
        if self.act_status == 'retry':
            return True, '''Okay, please write the final result now in a markdown JSON block, for example:
```json
{
    "decision": ...,
    "suggestions": "..."
}
```
'''
        if self.reviews >= self.max_reviews:
            self.termination = True
            user_prompt = 'termination'
            call_llm = False
        else:
            assert_content = self.get_last_source_content('AssertAgent')

            call_llm = True

            ## Do dynamic check
            self.static_check_passed, self.static_check_result = await self.project_tools.static_check_assert(assert_code=assert_content['assert_code'])
            if not self.static_check_passed:
                self.test_run_passed, self.test_run_result = False, 'Static check failed, did not start running.'
            elif not self.with_dynamic:
                self.test_run_passed, self.test_run_result = True, ''
            else:
                self.test_run_passed, self.test_run_result, seconds = await self.project_tools.run_test(
                    assert_code=handle_assert_code(assert_content['assert_code'], self.lang)
                )
                append_jsonl(self.data['resource_file'],{'type': 'test', 'gen_id': self.data['gen_id'], 'seconds': seconds})

            # first round
            if self.iters == 1:
                focal_method = self.data['focal_method']
                test_prefix = self.data['test_prefix']
                focal_method = add_line_number(
                    focal_method,
                    [i for i in range(self.data['focal_method_start_lineno'], self.data['focal_method_end_lineno'] + 1)]
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

A programmer is trying to write this assert statement.
Your task is to determine if the programmer's answer is correct and provide suggestions.
This assert statement should meet the following requirements:
1. Test the method under test.
2. Be a single line of `org.junit.Assert` statement.
3. Passed static check and test run check.
4. Maintain consistent writing habits and styles with other assert statements.
5. Cannot introduce any additional dependencies that are not currently introduced.
'''
                elif self.lang.lower() == 'python':
                    user_prompt = f'''\
You will be provided with the file path and function body of a method under test, a test setup, and the corresponding unit test.
The other parts of the unit test have already been written, but there is still one assert statement that has not been completed, which is located in the `{self.data['placeholder']}` position.

A programmer is trying to write this assert statement.
Your task is to determine if the programmer's answer is correct and provide suggestions.
This assert statement should meet the following requirements:
1. Test the method under test.
2. Be a single line of Python assert statement.
3. Passed static check and test run check.
4. Maintain consistent writing habits and styles with other assert statements.
'''
                else:
                    raise NotImplementedError()

                if self.with_explore_agent:
                    user_prompt += '\nYou will also be provided with the callees of method under test and unit test, along with the advice on the style of assert statement writing.\n'

                user_prompt += '''
Your final result needs to be in strictly JSON dictionary type, which includes a boolean type field `decision` indicating whether the assert statement is correct (true means correct), and a string type field `suggestions` indicating your suggestions. For example:
```json
{
    "decision": ...,
    "suggestions": "..."
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
                        raise NotImplementedError()

                if self.with_locals:
                    local_vars = await self.project_tools.get_locals()
                    user_prompt += f'''\n\n# Local Variable Information\n{local_vars}\n'''

                user_prompt += f'''

# Answer to Check
Here is the programmer's answer. '''
                if self.with_dynamic:
                    user_prompt += 'It has undergone automatic static check and running.\n'
                else:
                    user_prompt += 'It has undergone automatic static check.\n'

                assert_code = assert_content['assert_code']
                user_prompt += f'''\
Please check if it is correct and provide suggestions.

```{self.lang.lower()}
{assert_code}
```


# Static Check Result
{self.static_check_result}
'''
                if self.with_dynamic:
                    user_prompt += f'''

# Test Run Result
{self.test_run_result}
'''
            else:
                user_prompt = 'The programmer has revised and written a new version. '
                if self.with_dynamic:
                    user_prompt += 'It has undergone automatic static check and running.\n'
                else:
                    user_prompt += 'It has undergone automatic static check.\n'

                assert_code = assert_content['assert_code']
                user_prompt += f'''\
Please check again if it is correct and provide suggestions.
Your check result needs to be strictly JSON type, which includes a boolean type field `decision` indicating whether the assert statement is correct, and a string type field `suggestions` indicating your modification suggestions.

```{self.lang.lower()}
{assert_code}
```


# Static Check Result
{self.static_check_result}
'''
                user_prompt += f'''

# Test Run Result
{self.test_run_result}
'''
        return call_llm, user_prompt

    async def after_call_llm(self, response_content: str, text_calls: int) -> Tuple[bool, Dict]:
        last_content = json.loads(self.agent_messages[-1].content)
        if self.termination:
            return False, {
                'decision': True,
                'termination': True,
                'static_check_result': self.static_check_result,
                'static_check_passed': self.static_check_passed,
                'test_run_result': self.test_run_result,
                'test_run_passed': self.test_run_passed,
                'suggestions': '',
                'assert_code': handle_assert_code(last_content['assert_code'], self.lang.lower()),
            }

        max_retries = 5
        self.reviews += 1  # review 1
        try:
            self.act_status = 'recv'
            json_content = extract_last_block(response_content)
            if json_content.strip() == '':
                json_content = response_content

            json_data = json.loads(json_content)
            assert json_data.__contains__('decision')
            return False, {
                'decision': json_data['decision'],
                'termination': json_data['decision'],
                'static_check_result': self.static_check_result,
                'static_check_passed': self.static_check_passed,
                'test_run_result': self.test_run_result,
                'test_run_passed': self.test_run_passed,
                'suggestions': json_data['suggestions'] if json_data.__contains__('suggestions') else '',
                'assert_code': handle_assert_code(last_content['assert_code'], self.lang.lower()),
            }
        except Exception:
            if text_calls >= max_retries:
                self.act_status = 'recv'
                return False, {
                    'decision': True,
                    'termination': True,
                    'static_check_result': self.static_check_result,
                    'static_check_passed': self.static_check_passed,
                    'test_run_result': self.test_run_result,
                    'test_run_passed': self.test_run_passed,
                    'suggestions': '',
                    'assert_code': handle_assert_code(last_content['assert_code'], self.lang.lower()),
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
