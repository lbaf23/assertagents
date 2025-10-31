from utils import read_jsonl, read_file
from assert_group.tools.python_project_tools import PythonProjectTools
from utils.python_utils.python_file_utils import get_python_method_name, PY_ASSERT_PLACEHOLDER, PY_COM_ASSERT_PLACEHOLDER
import os
import argparse


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo_cache_dir', type=str, default='/tmp/pywork1/py500')
    parser.add_argument('--start_index', type=int, default=0)
    parser.add_argument('--end_index', type=int, default=500)
    args = parser.parse_args()

    teco500 = read_jsonl('data/py500.jsonl')

    failed = []

    for i in range(args.start_index, args.end_index):
        data = teco500[i]
        placeholder = PY_ASSERT_PLACEHOLDER
        new_placeholder = PY_COM_ASSERT_PLACEHOLDER

        repo_path = os.path.abspath(str(os.path.join(args.repo_cache_dir, data['repo_name'])))
        input_data = {
            'index': i,

            'test_target': data['test_target'],

            'repo_name': data['repo_name'],
            'repo_path': repo_path,

            'focal_method': data['focal_method'],
            'focal_method_name': get_python_method_name(data['focal_method']),
            'focal_method_start_lineno': data['focal_method_start_lineno'],
            'focal_method_end_lineno': data['focal_method_end_lineno'],
            'focal_method_file_path': data['focal_method_file_path'],
            'focal_method_path': os.path.join(repo_path, data['focal_method_file_path']),

            'test_prefix': data['test_prefix'].replace(placeholder, new_placeholder),
            'test_prefix_name': get_python_method_name(data['test_prefix'].replace(placeholder, new_placeholder)),
            'test_prefix_start_lineno': data['test_prefix_start_lineno'],
            'test_prefix_end_lineno': data['test_prefix_end_lineno'],
            'test_prefix_file_path': data['test_prefix_file_path'],
            'test_prefix_path': os.path.join(repo_path, data['test_prefix_file_path']),

            'ground_truth_oracle_lineno': data['ground_truth_oracle_lineno'],

            'placeholder': new_placeholder,
            'lang': 'Python',
        }

        print(f'====== {i} ======')
        print(repo_path)
        print(input_data['test_prefix_path'])

        test_file_content1 = read_file(input_data['test_prefix_path'])

        python_tools = PythonProjectTools(
            data=input_data,
            debug_cache_dir=f'{args.repo_cache_dir}_debug',
        )

        try:
            test_file_content2 = read_file(input_data['test_prefix_path'])

            python_tools.start_debugger()

            assert python_tools.python_debugger.started, f'Python debugger not running!'

            local_vars = await python_tools.get_locals()
            print('=== locals 1 ===\n' + str(local_vars) + '\n===')

            local_vars = await python_tools.get_locals()
            print('=== locals 2 ===\n' + str(local_vars) + '\n===')

            print('Close debugger')
            python_tools.close_debugger()

            test_file_content3 = read_file(input_data['test_prefix_path'])

            assert test_file_content2 == test_file_content3, f'Test file: run debug check failed.'
        except Exception as e:
            print(f'Failed: {i}')
            print(e)
            failed.append(i)
        finally:
            python_tools.close()
    
        print('=== Failed ===')
        print(failed)


import asyncio
if __name__ == '__main__':
    asyncio.run(main())
