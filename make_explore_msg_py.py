import os

from utils import read_jsonl, write_file, read_file
from utils.python_utils.msg_utils import get_method_deps_msg
from utils.python_utils.python_file_utils import get_python_method_name, PY_ASSERT_PLACEHOLDER, PY_COM_ASSERT_PLACEHOLDER
import argparse
from tqdm import tqdm
from utils.code_file_utils.code_file_utils import replace_code_lines
from utils.code_file_utils.code_repo_utils import backup_file, recover_file


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo_cache_dir', type=str, default="/tmp/pywork1/py500")
    parser.add_argument('--calls_cache_dir', type=str, default="./cache/py500")
    parser.add_argument('--calls_msg_cache_dir', type=str, default="./cache/py500_calls_msg")
    args = parser.parse_args()

    teco500 = read_jsonl('./data/py500.jsonl')
    os.makedirs(args.calls_msg_cache_dir, exist_ok=True)

    for i, data in enumerate(tqdm(teco500)):
        repo_path = str(os.path.join(args.repo_cache_dir, data['repo_name']))

        # Mask the ground truth
        test_prefix = data['test_prefix'].replace(PY_ASSERT_PLACEHOLDER, PY_COM_ASSERT_PLACEHOLDER)
        test_file_path = str(os.path.join(repo_path, data['test_prefix_file_path']))
        original_file_content, masked_file_content = backup_file(
            file_path=test_file_path,
            code=test_prefix,
            start_lineno=data['test_prefix_start_lineno'],
            end_lineno=data['test_prefix_end_lineno'],
        )

        repo_call_msg_cache_dir = str(os.path.join(args.calls_msg_cache_dir, data['repo_name']))
        os.makedirs(repo_call_msg_cache_dir, exist_ok=True)

        fm_msg = get_method_deps_msg(
            calls_cache_dir=args.calls_cache_dir,
            repo_name=data['repo_name'],
            repo_path=repo_path,
            method_file_path=data['focal_method_file_path'],
            method_start_lineno=data['focal_method_start_lineno'],
            with_calls=True,
            calls_exclude_path=[],
            with_called_by=True,
            max_calls=5,
            max_called_by=2
        )

        fm_msg_cache_file = os.path.join(
            repo_call_msg_cache_dir,
            f'''{data['focal_method_file_path'].replace('/', '-')}:{data['focal_method_start_lineno']}.txt'''
        )

        write_file(fm_msg_cache_file, fm_msg)


        tp_msg = get_method_deps_msg(
            calls_cache_dir=args.calls_cache_dir,
            repo_name=data['repo_name'],
            repo_path=repo_path,
            method_file_path=data['test_prefix_file_path'],
            method_start_lineno=data['test_prefix_start_lineno'],
            with_calls=True,
            calls_exclude_path=[],
            with_called_by=False,
            max_calls=5,
            max_called_by=0
        )

        tp_msg_cache_file = os.path.join(
            repo_call_msg_cache_dir,
            f'''{data['test_prefix_file_path'].replace('/', '-')}:{data['test_prefix_start_lineno']}.txt'''
        )

        write_file(tp_msg_cache_file, tp_msg)

        # Recover
        recover_file(file_path=test_file_path)
