import json
from typing import List, Dict, Union
from autogen_core.models import LLMMessage


def handle_assert_code(assert_code: str, lang: str) -> str:
    if lang.lower() == 'java':
        assert_code = assert_code.strip().replace('org.junit.Assert.', '').replace('Assert.', '')
        return f'org.junit.Assert.{assert_code}'
    else:
        return assert_code


def add_line_number(code_lines: Union[List[str] | str], code_linenos: List[int]) -> str:
    if type(code_lines) is str:
        code_lines = code_lines.splitlines()

    assert len(code_lines) <= len(code_linenos)

    for i in range(len(code_lines)):
        code_lines[i] = f'[{code_linenos[i]}] ' + code_lines[i]
    return '\n'.join(code_lines)


def add_prompt_suffix(prompt: str, generation_mode: str) -> str:
    if generation_mode == 'think':
        return prompt + ' /think'
    elif generation_mode == 'no_think':
        return prompt + ' /no_think'
    else:
        return prompt


def add_markdown_block(content: str, lang: str) -> str:
    return f'''\
```{lang.lower()}
{content}
```
'''


def extract_llm_messages(llm_messages: List[LLMMessage]) -> List[Dict]:
    messages = []
    for llm_message in llm_messages:
        d = json.loads(llm_message.json())
        if d['type'] == 'SystemMessage':
            role = 'system'
        elif d['type'] == 'UserMessage':
            role = 'user'
        elif d['type'] == 'AssistantMessage':
            role = 'assistant'
        elif d['type'] == 'FunctionExecutionResultMessage':
            role = 'tool'
        else:
            role = d['type']

        content = d['content']
        # if type(content) == list:
        #     content = [asdict(c) for c in content]
        messages.append({'role': role, 'content': content})
    return messages
