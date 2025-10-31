import shutil
from typing import Tuple
from dataset_utils import read_dataset
from utils import read_file, write_file, write_json
from utils.code_file_utils.code_file_utils import replace_code_lines
from utils.python_utils.python_file_utils import PY_ASSERT_PLACEHOLDER, PY_COM_ASSERT_PLACEHOLDER
from utils.python_utils.python_code_utils import get_python_method_name_pos
from utils.python_utils.python_repo_utils import find_python_function_calls
from utils.python_utils.py_lsp_client import PyLSPClient

import os
import argparse


from pathlib import Path
def is_subpath(path, base):
    try:
        Path(path).resolve().relative_to(Path(base).resolve())
        return True
    except ValueError:
        return False


def backup_file(file_path: str, code: str, start_lineno: int, end_lineno: int) -> Tuple:
    backup_file_path = file_path[ : file_path.rindex('.')] + '.backup'
    shutil.copy(file_path, backup_file_path)
    original_file_content = read_file(file_path)

    masked_file_content = replace_code_lines(
        file_code=original_file_content,
        code=code,
        start_lineno=start_lineno,
        end_lineno=end_lineno,
    )
    write_file(file_path, masked_file_content)

    return original_file_content, masked_file_content


def recover_file(file_path: str) -> bool:
    backup_file_path = file_path[ : file_path.rindex('.')] + '.backup'
    if not os.path.exists(backup_file_path):
        return False
    shutil.copy(backup_file_path, file_path)
    os.remove(backup_file_path)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--pyright_executable_path', type=str, default="pyright-langserver")
    parser.add_argument('--start_index', type=int, default=0)
    parser.add_argument('--end_index', type=int, default=500)
    parser.add_argument('--dataset_name', type=str, default="py500")

    parser.add_argument('--repo_cache_dir', type=str, default="/tmp/pywork1/py500")
    args = parser.parse_args()

    dataset = read_dataset(args.dataset_name)

    for i in range(args.start_index, args.end_index):
        print(f'====== {i} ======')
        data = dataset[i]

        repo_path = str(os.path.join(args.repo_cache_dir, data['repo_name']))

        save_dir = f'''./cache/py500/{data['repo_name']}'''
        os.makedirs(save_dir, exist_ok=True)

        fm_cache_file_path = os.path.join(
            save_dir,
            f'''{data['focal_method_file_path'].replace('/', '-')}:{data['focal_method_start_lineno']}.json'''
        )

        tp_cache_file_path = os.path.join(
            save_dir,
            f'''{data['test_prefix_file_path'].replace('/', '-')}:{data['test_prefix_start_lineno']}.json'''
        )

        if os.path.exists(fm_cache_file_path) and os.path.exists(tp_cache_file_path):
            print(f'Skip {i}')
            continue


        #### Mask the ground truth
        test_prefix = data['test_prefix'].replace(PY_ASSERT_PLACEHOLDER, PY_COM_ASSERT_PLACEHOLDER)
        test_file_path = str(os.path.join(repo_path, data['test_prefix_file_path']))

        original_file_content, masked_file_content = backup_file(
            file_path=test_file_path,
            code=test_prefix,
            start_lineno=data['test_prefix_start_lineno'],
            end_lineno=data['test_prefix_end_lineno'],
        )

        lsp_client = PyLSPClient(args.pyright_executable_path, repo_path)
        print("=" * 60)
        print("Starting LSP server...")
        print("=" * 60)
        lsp_client.start_server()

        if not os.path.exists(fm_cache_file_path):
            calls = find_python_function_calls(
                code=data['focal_method'],
                start_lineno=data['focal_method_start_lineno'],
            )
            for c in range(len(calls)):
                calls[c]['definition'] = lsp_client.find_definition(
                    rel_file_path=data['focal_method_file_path'],
                    line=calls[c]['line'],
                    character=calls[c]['character'],
                )
            pos = get_python_method_name_pos(
                method_code=data['focal_method'],
                start_lineno=data['focal_method_start_lineno'],
            )
            called_by = lsp_client.find_references(
                rel_file_path=data['focal_method_file_path'],
                line=pos[0],
                character=pos[1],
            )
            print('=== Focal Method Calls ===')
            for c in calls: print(c)
            print('=== Focal Method Called By ===')
            for c in called_by: print(c)

            write_json(fm_cache_file_path, {
                'rel_file_path': data['focal_method_file_path'],
                'start_lineno': data['focal_method_start_lineno'],
                'calls': calls,
                'called_by': called_by,
            })

        if not os.path.exists(tp_cache_file_path):
            calls = find_python_function_calls(
                code=test_prefix,
                start_lineno=data['test_prefix_start_lineno'],
            )
            for c in range(len(calls)):
                calls[c]['definition'] = lsp_client.find_definition(
                    rel_file_path=data['test_prefix_file_path'],
                    line=calls[c]['line'],
                    character=calls[c]['character'],
                )

            print('=== Test Prefix Calls ===')
            for c in calls: print(c)
            write_json(tp_cache_file_path, {
                'rel_file_path': data['test_prefix_file_path'],
                'start_lineno': data['test_prefix_start_lineno'],
                'calls': calls,
                'called_by': [],
            })

        print("\n" + "=" * 60)
        print("Shutting down LSP server...")
        print("=" * 60)
        lsp_client.shutdown()

        #### Recover
        recover_file(file_path=test_file_path)
