import ast
import warnings
from typing import List, Any, Tuple
import re

from .java_utils.java_assert import extract_java_asserts, is_java_assert_same, is_java_code_valid
from .python_utils.python_assert import extract_python_asserts, is_python_assert_same


def is_code_valid(code: str, lang: str) -> bool:
    if lang.lower() == 'java':
        return is_java_code_valid(code)
    elif lang.lower() == 'python':
        return is_python_code_valid(code)
    else:
        raise ValueError(f'Unknown language: {lang}')


def is_python_code_valid(code: str) -> bool:
    try:
        ast.parse(code)
        return True
    except Exception:
        return False


def add_block(content: str, lang: str) -> str:
    return f'''\
```{lang.lower()}
{content}
```'''


def try_format_code(code: str, lang: str, mode: str = 'soft') -> str:
    try:
        code = format_code(code, lang, mode)
    except Exception as e:
        pass
    return code


def format_code(code: str, lang: str, mode: str = 'soft') -> str:
    import black
    if lang == 'python':
        if mode == 'hard':
            # code = remove_comments(code)
            code = ast.unparse(ast.parse(code))
        code = black.format_str(code, mode=black.Mode(line_length=100000))
        code = code.strip()
        return code
    else:
        raise NotImplementedError


def extract_blocks(content: str) -> List[str]:
    pattern = r"```[ \t]*(?:[\w+-]+)?[ \t]*\r?\n([\s\S]*?)```"
    return re.findall(pattern, content)


def extract_first_block(content: str) -> str:
    blocks = extract_blocks(content)
    return blocks[0] if len(blocks) > 0 else ''


def extract_last_block(content: str) -> str:
    blocks = extract_blocks(content)
    return blocks[-1] if len(blocks) > 0 else ''


def extract_boxed(content: str) -> List[str]:
    return re.findall(r'\\boxed\{(.*?)\}', content)


def extract_first_boxed(content: str) -> str:
    boxes = extract_boxed(content)
    return boxes[0] if len(boxes) > 0 else ''


def extract_assert_statements(content: str, lang: str) -> List[str]:
    if lang.lower() == 'java':
        return extract_java_asserts(content)
    elif lang.lower() == 'python':
        return extract_python_asserts(content)
    else:
        raise NotImplementedError


def is_assert_same(assert_stmt1: str, assert_stmt2: str, lang: str, mask_str: bool) -> bool:
    if lang.lower() == 'java':
        return is_java_assert_same(assert_stmt1, assert_stmt2, mask_str)
    elif lang.lower() == 'python':
        return is_python_assert_same(assert_stmt1, assert_stmt2, mask_str)
    else:
        raise NotImplementedError


def filter_assert_statement(assert_code: str, lang: str) -> str:
    if lang.lower() == 'java':
        return assert_code.replace('org.junit.Assert.', '').replace('Assert.', '').strip()
    elif lang.lower() == 'python':
        return assert_code.strip()
    else:
        raise NotImplementedError
