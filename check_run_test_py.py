from utils import read_jsonl
import os
import argparse
from utils.python_utils.python_tester import run_py_repo_test


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo_cache_dir', type=str, default='/tmp/pywork1/py500')
    parser.add_argument('--start_index', type=int, default=0)
    parser.add_argument('--end_index', type=int, default=500)
    args = parser.parse_args()

    py500 = read_jsonl('data/py500.jsonl')

    failed = []
    for i in range(args.start_index, args.end_index):
        data = py500[i]
        print(f'=== {i} ===')

        repo_path = str(os.path.join(
            args.repo_cache_dir,
            data['repo_name']
        ))

        res, output = run_py_repo_test(
            repo_path=repo_path,
            test_target=data['test_target'],
        )

        print(output)
        try:
            assert res['score'] == 1.0
        except Exception as e:
            print(e)
            failed.append(i)

    
        print('=== Failed ===')
        print(failed)

