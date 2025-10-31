from utils import read_jsonl
import os
import argparse
from utils.python_utils.py_repo import download_py_dependencies


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo_cache_dir', type=str, default='/tmp/pywork1/py500')
    args = parser.parse_args()

    py500 = read_jsonl('data/py500.jsonl')

    repos = set()

    for i, data in enumerate(py500):
        print(f'=== {i} ===')

        if repos.__contains__(data['repo_name']):
            print(f'Skip {i}')
            continue

        repo_path = str(os.path.join(
            args.repo_cache_dir,
            data['repo_name']
        ))

        res = download_py_dependencies(
            repo_path=repo_path,
            install_cmd=data['install_cmd'],
        )
        print(res)

        repos.add(data['repo_name'])

        assert res
