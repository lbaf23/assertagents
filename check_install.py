from utils import read_jsonl
import os
import argparse
from utils.java_utils.java_repo import download_java_dependencies


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo_cache_dir', type=str, required=True)
    parser.add_argument('--start_index', type=int, default=0)
    parser.add_argument('--end_index', type=int, default=500)
    args = parser.parse_args()

    lang = 'Java'
    teco500 = read_jsonl('data/teco500.jsonl')

    build_set = set()
    for i in range(args.start_index, args.end_index):
        data = teco500[i]
        print(f'========== {i} ==========')
        if build_set.__contains__(data['repo_name'] + '/' + data['sub_repo']):
            print('Skip.')
            continue

        run_repo_path = str(os.path.join(args.repo_cache_dir, data['repo_name']))
        build_set.add(run_repo_path)
        res = download_java_dependencies(run_repo_path, data['sub_repo'])
        build_set.add(data['repo_name'] + '/' + data['sub_repo'])
        print(f'Install finished.')
