from utils import read_jsonl, read_file
from assert_group.tools.java_project_tools import JavaProjectTools
from utils.java_utils.pkg_utils import pkg_to_path, path_to_pkg, DEFAULT_SOURCE_ROOT
from utils.java_utils.java_file_utils import get_method_name, ASSERT_PLACEHOLDER, COM_ASSERT_PLACEHOLDER
import os
import argparse
import re


def clean_content(content: str):
    return re.sub(r'[\u2028\u2029]', '', content)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo_cache_dir', type=str, default='/tmp/work1/teco500')
    parser.add_argument('--start_index', type=int, default=0)
    parser.add_argument('--end_index', type=int, default=500)
    args = parser.parse_args()

    teco500 = read_jsonl('data/teco500.jsonl')


    for i in range(args.start_index, args.end_index):
        data = teco500[i]
        placeholder = ASSERT_PLACEHOLDER
        new_placeholder = COM_ASSERT_PLACEHOLDER

        repo_path = os.path.abspath(os.path.join(f'''{args.repo_cache_dir}/{data['repo_name']}'''))

        focal_method_sub_repo, focal_method_pkg = path_to_pkg(data['focal_method_file_path'])
        test_prefix_sub_repo, test_prefix_pkg = path_to_pkg(data['test_prefix_file_path'])
        test_setup_sub_repo, test_setup_pkg = path_to_pkg(data['test_setup_file_path'])

        input_data = {
            'index': i,

            'source_root': DEFAULT_SOURCE_ROOT,

            'test_target': data['test_target'],

            'repo_name': data['repo_name'],
            'repo_path': repo_path,
            'sub_repos': data['sub_repos'],

            'test_class': test_prefix_pkg,
            'test_method': data['test_name'],

            'focal_method': data['focal_method'],
            'focal_method_name': get_method_name(data['focal_method']),
            'focal_method_sub_repo': focal_method_sub_repo,
            'focal_method_pkg': focal_method_pkg,
            'focal_method_start_lineno': data['focal_method_start_lineno'],
            'focal_method_end_lineno': data['focal_method_end_lineno'],
            'focal_method_file_path': data['focal_method_file_path'],
            'focal_method_path': os.path.join(repo_path, data['focal_method_file_path']),

            'test_setup_list': data['test_setup_list'],

            'test_setup': data['test_setup'],
            'test_setup_sub_repo': test_setup_sub_repo,
            'test_setup_pkg': test_setup_pkg,
            'test_setup_file_path': data['test_setup_file_path'],
            'test_setup_path': os.path.join(repo_path, data['test_setup_file_path']),

            'test_prefix': data['test_prefix'].replace(placeholder, new_placeholder),
            'test_prefix_name': get_method_name(data['test_prefix'].replace(placeholder, new_placeholder)),
            'test_prefix_sub_repo': test_prefix_sub_repo,
            'test_prefix_pkg': test_prefix_pkg,
            'test_prefix_start_lineno': data['test_prefix_start_lineno'],
            'test_prefix_end_lineno': data['test_prefix_end_lineno'],
            'test_prefix_file_path': data['test_prefix_file_path'],
            'test_prefix_path': os.path.join(repo_path, data['test_prefix_file_path']),

            'placeholder': new_placeholder,
            'lang': 'Java',
        }

        print(f'====== {i} ======')
        print(repo_path + '/' + input_data['test_prefix_sub_repo'])
        print(input_data['test_prefix_path'])

        test_file_content1 = clean_content(read_file(input_data['test_prefix_path']))


        java_tools = JavaProjectTools(
            data=input_data,
            debug_port=6001,
            debug_cache_dir=f'{args.repo_cache_dir}_debug',
        )

        test_file_content2 = clean_content(read_file(input_data['test_prefix_path']))

        java_tools.start_debugger()

        assert java_tools.java_debugger.started, f'Java debugger not running!'

        local_vars = await java_tools.get_locals()
        print('=== locals 1 ===\n' + str(local_vars) + '\n===')

        local_vars = await java_tools.get_locals()
        print('=== locals 2 ===\n' + str(local_vars) + '\n===')

        print('Close debugger')
        java_tools.close_debugger()

        test_file_content3 = clean_content(read_file(input_data['test_prefix_path']))

        java_tools.close()
        assert test_file_content2 == test_file_content3, f'Test file: run debug check failed.'

        test_file_content4 = clean_content(read_file(input_data['test_prefix_path']))
        assert test_file_content1 == test_file_content4, f'Test file: final close check failed.'


import asyncio
if __name__ == '__main__':
    asyncio.run(main())
