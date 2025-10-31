import argparse
from dataset_utils import read_dataset
from utils import create_dirs, write_json, init_log, read_json
from tqdm import tqdm
import os
import time
from typing import List, Dict

from assert_group.assert_group import generate_assert

from utils.java_utils.pkg_utils import path_to_pkg, DEFAULT_SOURCE_ROOT
from utils.java_utils.java_file_utils import JAVA_ASSERT_PLACEHOLDER, JAVA_COM_ASSERT_PLACEHOLDER, get_java_method_name
from utils.python_utils.python_file_utils import PY_ASSERT_PLACEHOLDER, PY_COM_ASSERT_PLACEHOLDER, get_python_method_name

from utils import print_log


def get_placeholder_line(code: str, placeholder: str) -> int:
    lines = code.splitlines()
    for ln, line in enumerate(lines):
        if line.strip() == placeholder:
            return ln
    return 0


def make_java_input_data(
        data: Dict,
        repo_path: str,
        calls_extract_dir: str,
) -> Dict:
    placeholder = JAVA_ASSERT_PLACEHOLDER
    new_placeholder = JAVA_COM_ASSERT_PLACEHOLDER

    focal_method_sub_repo, focal_method_pkg = path_to_pkg(data['focal_method_file_path'])
    test_prefix_sub_repo, test_prefix_pkg = path_to_pkg(data['test_prefix_file_path'])
    test_setup_sub_repo, test_setup_pkg = path_to_pkg(data['test_setup_file_path'])

    input_data = {
        'index': i,

        'source_root': DEFAULT_SOURCE_ROOT,

        'repo_name': data['repo_name'],
        'repo_path': repo_path,
        'sub_repos': data['sub_repos'],

        'test_class': test_prefix_pkg,
        'test_method': data['test_name'],

        'test_target': data['test_target'],

        'focal_method': data['focal_method'],
        'focal_method_name': get_java_method_name(data['focal_method']),
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
        'test_prefix_name': get_java_method_name(data['test_prefix'].replace(placeholder, new_placeholder)),
        'test_prefix_sub_repo': test_prefix_sub_repo,
        'test_prefix_pkg': test_prefix_pkg,
        'test_prefix_start_lineno': data['test_prefix_start_lineno'],
        'test_prefix_end_lineno': data['test_prefix_end_lineno'],
        'test_prefix_file_path': data['test_prefix_file_path'],
        'test_prefix_path': os.path.join(repo_path, data['test_prefix_file_path']),

        'ground_truth_oracle_lineno': data['test_prefix_start_lineno'] + get_placeholder_line(data['test_prefix'], placeholder),

        'calls_extract_dir': calls_extract_dir,
        'placeholder': new_placeholder,
        'lang': 'Java',
    }

    return input_data


def make_python_input_data(
        data: Dict,
        repo_path: str,
):
    placeholder = PY_ASSERT_PLACEHOLDER
    new_placeholder = PY_COM_ASSERT_PLACEHOLDER

    return {
        'index': i,

        'repo_name': data['repo_name'],
        'repo_path': repo_path,

        'test_target': data['test_target'],

        'test_class_name': data['test_class_name'],

        'focal_method': data['focal_method'],
        'focal_method_name': get_python_method_name(data['focal_method']),
        'focal_method_start_lineno': data['focal_method_start_lineno'],
        'focal_method_end_lineno': data['focal_method_end_lineno'],
        'focal_method_file_path': data['focal_method_file_path'],
        'focal_method_path': os.path.join(repo_path, data['focal_method_file_path']),

        'test_setup': data['test_setup'],
        'test_setup_file_path': data['test_setup_file_path'],
        'test_setup_start_lineno': data['test_setup_start_lineno'],
        'test_setup_end_lineno': data['test_setup_end_lineno'],
        'test_setup_path': os.path.join(repo_path, data['test_setup_file_path']),

        'test_prefix': data['test_prefix'].replace(placeholder, new_placeholder),
        'test_prefix_name': get_python_method_name(data['test_prefix'].replace(placeholder, new_placeholder)),
        'test_prefix_start_lineno': data['test_prefix_start_lineno'],
        'test_prefix_end_lineno': data['test_prefix_end_lineno'],
        'test_prefix_file_path': data['test_prefix_file_path'],
        'test_prefix_path': os.path.join(repo_path, data['test_prefix_file_path']),

        'ground_truth_oracle_lineno': data['ground_truth_oracle_lineno'],

        'placeholder': new_placeholder,
        'lang': 'Python'
    }


def generate(
        i: int,
        agent_cache_dir: str,
        calls_msg_cache_dir: str,
        repo_cache_dir: str,
        calls_extract_dir: str,
        model_path: str,
        base_url: str,
        api_key: str,
        data: Dict,
        generation_mode: str,
        lang: str,
        sampling_args: Dict,
        resource_file: str,
        nums: int,
        debug_port: int,

        with_dynamic: bool,
        with_explore_agent: bool,
        with_locals: bool,
        debug_cache_dir: str,

        max_tries: int,
        existing_assert_code: List[str],
) -> List:
    """
    Args:
        repo_cache_dir: abs path
        generation_mode: '', 'think', 'no_think'
        lang: Java or Python

    Returns:
        gen_oracles: ['assert ...', ]
        resources: ["messages": [], "input_tokens": ..., "output_tokens": ...}]
    """
    sampling_args['prompt_cache_key'] = f'assertagent_{i}_{time.time()}'
    sampling_args['extra_body']['cache_salt'] = sampling_args['prompt_cache_key']

    if lang.lower() == 'java':
        repo_path = os.path.abspath(os.path.join(f'''{repo_cache_dir}/{data['repo_name']}'''))
    else:
        repo_path = os.path.abspath(os.path.join(f'''{repo_cache_dir}/{data['repo_name']}'''))

    if lang.lower() == 'java':
        input_data = make_java_input_data(data, repo_path, calls_extract_dir)
    else:
        input_data = make_python_input_data(data, repo_path)

    input_data['agent_cache_dir'] = agent_cache_dir
    input_data['calls_msg_cache_dir'] = calls_msg_cache_dir
    input_data['calls_extract_dir'] = calls_extract_dir
    input_data['debug_cache_dir'] = debug_cache_dir
    input_data['resource_file'] = resource_file

    gen_oracles = generate_assert(
        data=input_data,
        generation_mode=generation_mode,
        lang=lang,

        sampling_args=sampling_args,
        model_path=model_path,
        base_url=base_url,
        api_key=api_key,

        max_tool_calls=5,
        max_reviews=3,
        debug_port=debug_port,

        with_explore_agent=with_explore_agent,
        with_dynamic=with_dynamic,
        with_locals=with_locals,
        debug_cache_dir=debug_cache_dir,
        nums=nums,
        max_tries=max_tries,
        existing_assert_code=existing_assert_code,
    )
    return gen_oracles


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run_name', type=str, default='Qwen3-Coder-30B-A3B-Instruct')
    parser.add_argument('--dataset_name', type=str, default='teco500')

    parser.add_argument('--repo_cache_dir', type=str, default='/tmp/teco500')
    parser.add_argument('--debug_cache_dir', type=str, default='/tmp/teco500_debug')

    parser.add_argument('--calls_extract_dir', type=str, default='cache/teco500')
    parser.add_argument('--calls_msg_cache_dir', type=str, default='cache/teco500_calls_msg')

    parser.add_argument('--model_path', type=str, default=None)
    parser.add_argument('--base_url', type=str)
    parser.add_argument('--api_key', type=str)
    parser.add_argument('--generation_mode', type=str, default='', choices=['think', 'no_think', ''], help='For Qwen3, set this to think or no_think, for Qwen3-Coder set to empty.')

    parser.add_argument('--lang', type=str, default='Java', choices=['Java', 'Python'])

    parser.add_argument('--temperature', type=float, default=1.0)
    parser.add_argument('--top_p', type=float, default=1.0)
    parser.add_argument('--top_k', type=int, default=-1)
    parser.add_argument('--max_tokens', type=int, default=1024)
    parser.add_argument('--repetition_penalty', type=float, default=1.0, help='For Qwen3-Coder*, set it to 1.05.')

    parser.add_argument('--nums', type=int, default=10)

    parser.add_argument('--start_index', type=int, default=0)
    parser.add_argument('--end_index', type=int, default=500)

    parser.add_argument('--debug_port', type=int, default=6001)

    parser.add_argument('--v', type=int, default=-1)

    parser.add_argument('--max_tries', type=int, default=10)

    parser.add_argument('--with_dynamic', action='store_true')
    parser.add_argument('--with_explore_agent', action='store_true')

    parser.add_argument('--with_locals', action='store_true')
    args = parser.parse_args()

    assert args.lang in {'Java', 'Python'}, f'Unknown language: {args.lang}'

    sampling_args = {
        'temperature': args.temperature,
        'top_p': args.top_p,
        'max_completion_tokens': args.max_tokens,
        'extra_body': {
            'top_k': args.top_k,
            'repetition_penalty': args.repetition_penalty
        }
    }

    dataset = read_dataset(args.dataset_name)
    method = 'assertagent'

    log_dir = f'logs/{args.run_name}/{args.dataset_name}_{method}'
    output_dir = f'results/{args.run_name}/{args.dataset_name}_{method}'
    resource_dir = f'resources/{args.run_name}/{args.dataset_name}_{method}'
    agent_cache_dir = f'cache/{args.run_name}/{args.dataset_name}_{method}'

    create_dirs(log_dir)
    create_dirs(output_dir)
    create_dirs(resource_dir)
    create_dirs(agent_cache_dir)

    # generate
    if args.start_index < args.end_index:
        start_index = args.start_index
        end_index = args.end_index
    else:
        start_index = 0
        end_index = len(dataset)

    assert args.start_index >= 0
    assert args.end_index <= len(dataset)

    for i in tqdm(range(start_index, end_index)):
        data = dataset[i]
        output_file = os.path.join(output_dir, f'{i}.json')

        existing_assert_code = []
        if os.path.exists(output_file):
            output = read_json(output_file)
            existing_assert_code = [r['gen_oracle'] for r in output['results']]

        if len(existing_assert_code) >= args.nums:
            print_log(content=f'Skip {i}.')
            continue

        log_file = os.path.join(log_dir, f'{i}.log')
        resource_file = os.path.join(resource_dir, f'{i}.jsonl')

        init_log(log_file=log_file, terminal=False)

        gen_oracles = generate(
            i=i,
            agent_cache_dir=agent_cache_dir,
            calls_msg_cache_dir=args.calls_msg_cache_dir,
            calls_extract_dir=args.calls_extract_dir,
            repo_cache_dir=os.path.abspath(args.repo_cache_dir),
            model_path=args.model_path,
            base_url=args.base_url,
            api_key=args.api_key,
            data=data,
            generation_mode=args.generation_mode,
            lang=args.lang,
            sampling_args=sampling_args,
            resource_file=resource_file,
            nums=args.nums,
            debug_port=args.debug_port,

            with_dynamic=args.with_dynamic,
            with_explore_agent=args.with_explore_agent,
            with_locals=args.with_locals,

            debug_cache_dir=os.path.abspath(args.debug_cache_dir),

            max_tries=args.max_tries,
            existing_assert_code=existing_assert_code,
        )

        output_content = {
            'index': i,
            'ground_truth_oracle': data['ground_truth_oracle'],
            'results': [
                {'gen_oracle': a} for a in gen_oracles
            ],
        }
        write_json(output_file, output_content)
