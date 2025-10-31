import os
from typing import List
from utils import read_file, read_json

from .java_file_utils import get_java_function_body_inline, remove_java_preview_comments, remove_java_preview_imports


def get_method_deps_msg(
        calls_cache_dir: str,
        repo_name: str,
        repo_path: str,
        method_file_path: str,
        method_start_lineno: str,
        with_calls: bool,
        calls_exclude_path: List[str],
        with_called_by: bool,
        max_calls: int,
        max_called_by: int,
) -> str:
    cache_file = os.path.join(
        calls_cache_dir,
        repo_name,
        f'''{method_file_path.replace('/', '-')}:{method_start_lineno}.json'''
    )
    deps = read_json(cache_file)
    calls = deps['calls']
    called_by = deps['called_by']

    calls_msg = ''
    called_by_msg = ''

    calls_set = set()
    if with_calls:
        for func in calls:
            if len(calls_set) >= max_calls:
                break

            definition = func['definition']
            if definition is None:
                continue

            if calls_exclude_path.__contains__(definition['rel_file_path']):
                continue

            file_path = os.path.join(repo_path, definition['rel_file_path'])
            if not os.path.exists(file_path):
                continue

            java_code = read_file(file_path)
            fbinfo = get_java_function_body_inline(java_code, definition['start_line'] + 1, False)
            if fbinfo is None:
                continue

            if calls_set.__contains__(f'''{file_path}:{fbinfo['start_lineno']}'''):
                continue
            calls_set.add(f'''{file_path}:{fbinfo['start_lineno']}''')

            # preview = remove_java_preview_imports(remove_java_preview_comments(fbinfo['preview']))
            calls_msg += f'''
File path: "{definition['rel_file_path']}"
Function body:
{fbinfo['preview']}
'''

    called_by_set = set()
    if with_called_by:
        for func in called_by:
            if len(called_by_set) >= max_called_by:
                break

            file_path = os.path.join(repo_path, func['rel_file_path'])
            if not os.path.exists(file_path):
                continue

            java_code = read_file(file_path)
            fbinfo = get_java_function_body_inline(java_code, func['lineno'], False)
            if fbinfo is None:
                continue

            if called_by_set.__contains__(f'''{file_path}:{fbinfo['start_lineno']}'''):
                continue
            called_by_set.add(f'''{file_path}:{fbinfo['start_lineno']}''')

            called_by_msg += f'''
File path: "{func['rel_file_path']}"
Function body:
{fbinfo['preview']}
'''

    msg = ''
    if with_calls:
        msg += f'''\
### Calls
{calls_msg}
'''
    if with_called_by:
        msg += f'''


### Called By
{called_by_msg}
'''
    return msg.strip()
