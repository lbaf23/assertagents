from utils import read_json, read_jsonl, extract_last_block, write_jsonl, write_json
from dataset_utils import read_dataset
import argparse
import os
import json
from typing import List, Tuple, Dict


def get_iter_results(resource_content: List[Dict], max_reviews: int) -> List:
    results = [
        {'gen_oracle': ''} for _ in range(10)
    ]
    for i in range(10):
        assert_code = ''
        revs = 0
        for r in resource_content:
            if r['gen_id'] != i:
                continue
            if r.__contains__('agent') and r['agent'] == 'AssertAgent':
                revs += 1
                try:
                    json_content = extract_last_block(r['messages'][-1]['content'])
                    if json_content.strip() == '':
                        json_content = r['messages'][-1]['content']
                    json_data = json.loads(json_content)
                    assert_code = json_data['assert_code']
                except Exception:
                    pass
            if revs == max_reviews + 1:
                break

        results[i]['gen_oracle'] = assert_code
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--run_name', type=str)
    parser.add_argument('--dataset_name', type=str, default='teco500')
    parser.add_argument('--max_reviews', type=int)
    args = parser.parse_args()

    method = 'assertagent'
    resource_dir = f'resources/{args.run_name}/{args.dataset_name}_{method}'

    new_resource_dir = f'resources/{args.run_name}/{args.dataset_name}_{method}_{args.max_reviews}'
    new_result_dir = f'results/{args.run_name}/{args.dataset_name}_{method}_{args.max_reviews}'

    os.makedirs(new_resource_dir, exist_ok=True)
    os.makedirs(new_result_dir, exist_ok=True)

    dataset = read_dataset(args.dataset_name)
    for i, data in enumerate(dataset):
        resource_file = os.path.join(resource_dir, f'{i}.jsonl')
        new_result_file = os.path.join(new_result_dir, f'{i}.json')
        resource = read_jsonl(resource_file)
        revs = 0
        assert_code = ''

        results = get_iter_results(resource, max_reviews=args.max_reviews)

        write_json(new_result_file, {
            'index': i,
            'ground_truth_oracle': data['ground_truth_oracle'],
            'results': results
        })
