import argparse
import json
from utils.code_utils import is_assert_same
from typing import List, Tuple, Dict
from utils import read_jsonl, write_jsonl, write_json, read_json
import os


def count_tokens(resources: List, use_prefix_cache: bool) -> Tuple[int, int]:
    prompt_tokens = 0
    completion_tokens = 0

    for r in resources:
        if r['type'] != 'llm':
            continue

        if use_prefix_cache:
            prompt_tokens += r['usage']['prompt_tokens'] - (r['usage']['prompt_tokens_details']['cached_tokens'] if r['usage']['prompt_tokens_details'] is not None else 0)
        else:
            prompt_tokens += r['usage']['prompt_tokens']

        completion_tokens += r['usage']['completion_tokens']
        if r['gen_id'] > 0:
            break
    return prompt_tokens, completion_tokens


def count_directly_prompt_tokens(resources: List, use_prefix_cache: bool) -> Tuple[int, int]:
    prompt_tokens = 0
    completion_tokens = 0

    for r in resources:
        if use_prefix_cache:
            prompt_tokens += r['usage']['prompt_tokens'] - (r['usage']['prompt_tokens_details']['cached_tokens'] if r['usage']['prompt_tokens_details'] is not None else 0)
        else:
            prompt_tokens += r['usage']['prompt_tokens']

        completion_tokens += r['usage']['completion_tokens']
    return prompt_tokens, completion_tokens


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run_name', type=str)
    parser.add_argument('--dataset_name', type=str)
    parser.add_argument('--method', type=str)
    parser.add_argument('--result_type', type=str, default='jsonl')

    parser.add_argument('--use_prefix_cache', action='store_true')
    args = parser.parse_args()

    resources_dir = f'resources/{args.run_name}/{args.dataset_name}_{args.method}'

    avg_prompt_tokens, avg_completion_tokens = 0.0, 0.0
    for i in range(500):
        resources_file = os.path.join(resources_dir, f'{i}.jsonl')
        if args.method in {'chatassert', 'assertagent'}:
            prompt_tokens, completion_tokens = count_tokens(read_jsonl(resources_file), args.use_prefix_cache)
            avg_prompt_tokens += prompt_tokens
            avg_completion_tokens += completion_tokens
        elif args.method == 'directly_prompt':
            prompt_tokens, completion_tokens = count_directly_prompt_tokens(read_jsonl(resources_file), args.use_prefix_cache)
            avg_prompt_tokens += prompt_tokens
            avg_completion_tokens += completion_tokens
        else:
            raise NotImplementedError

    avg_prompt_tokens /= 500
    avg_completion_tokens /= 500
    avg_prompt_tokens = round(avg_prompt_tokens, 2)
    avg_completion_tokens = round(avg_completion_tokens, 2)

    w_prefix_cache = 'w prefix_cache' if args.use_prefix_cache else ''
    print(f'''\
=== {args.dataset_name} {args.run_name} {args.method} {w_prefix_cache} ===
avg prompt tokens: {avg_prompt_tokens}
avg completion tokens: {avg_completion_tokens}

''')
