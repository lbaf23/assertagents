import argparse
from dataset_utils import read_dataset
from models import model_factory
from prompt_utils import get_directly_prompt_messages
from utils import create_dirs, write_json, append_jsonl, extract_blocks, init_log, print_log
from tqdm import tqdm
import os
import time
from evaluate import evaluate_result
from utils.code_utils import extract_assert_statements
from datetime import datetime


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run_name', type=str, default='qwen3-coder-30b-a3b-instruct')
    parser.add_argument('--dataset_name', type=str, default='teco500', choices=['teco500', 'py500'])

    parser.add_argument('--model_path', type=str, default=None)
    parser.add_argument('--base_url', type=str)
    parser.add_argument('--api_key', type=str)
    parser.add_argument('--generation_mode', type=str, default='', choices=['think', 'no_think', ''])

    parser.add_argument('--lang', type=str, default='Java', choices=['Java', 'Python'])

    parser.add_argument('--temperature', type=float, default=1.0)
    parser.add_argument('--top_p', type=float, default=1.0)
    parser.add_argument('--top_k', type=int, default=-1)
    parser.add_argument('--max_tokens', type=int, default=1024)
    parser.add_argument('--repetition_penalty', type=float, default=1.0, help='For Qwen3-*, set it to 1.05.')

    parser.add_argument('--start_index', type=int, default=0)
    parser.add_argument('--end_index', type=int, default=-1)

    # parser.add_argument('--rerun', action='store_true')
    args = parser.parse_args()

    model = model_factory(
        model_type='openai_api',
        model_path=args.model_path if args.model_path else args.run_name,
        model_args={
            'api_key': args.api_key,
            'base_url': args.base_url,
        }
    )
    sampling_args = {
        'temperature': args.temperature,
        'top_p': args.top_p,
        'top_k': args.top_k,
        'max_tokens': args.max_tokens,
        'repetition_penalty': args.repetition_penalty
    }

    dataset = read_dataset(args.dataset_name)
    method = 'directly_prompt'

    log_dir = f'logs/{args.run_name}/{args.dataset_name}_{method}'
    create_dirs(log_dir)

    output_dir = f'results/{args.run_name}/{args.dataset_name}_{method}'
    create_dirs(output_dir)

    resource_dir = f'resources/{args.run_name}/{args.dataset_name}_{method}'
    create_dirs(resource_dir)

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
        sampling_args['cache_salt'] = f'assertagent_{i}_{time.time()}'

        data = dataset[i]

        log_file = os.path.join(log_dir, f'{i}.log')
        output_file = os.path.join(output_dir, f'{i}.json')
        resource_file = os.path.join(resource_dir, f'{i}.jsonl')

        if os.path.exists(output_file):
            print(f'Skip {i}')
            continue

        init_log(log_file=log_file, terminal=False, clear=True)

        messages = get_directly_prompt_messages(
            test_setup=data['test_setup'],
            test_prefix=data['test_prefix'],
            focal_method=data['focal_method'],
            generation_mode=args.generation_mode,
            lang=args.lang,
        )

        time_start = datetime.now()
        results = model.generate_chat(
            messages_list=[messages],
            sampling_args=sampling_args
        )
        time_end = datetime.now()

        output = results['output_list'][0]
        usage = results['usage_list'][0]
        seconds = results['seconds_list'][0]

        content = '\n'.join(extract_blocks(output))
        assert_stmts = extract_assert_statements(content, lang=args.lang)[ : 10]

        messages.append({'role': 'assistant', 'content': output})

        print_log(title='system', content=messages[0]['content'], level=0)
        print_log(title='user', content=messages[1]['content'], level=0)
        print_log(title='assistant', content=messages[2]['content'], level=0)

        output_content = {
            'index': i,
            'ground_truth_oracle': data['ground_truth_oracle'],
            'results': [
                {'gen_oracle': a} for a in assert_stmts
            ],
            'seconds': seconds,
        }
        write_json(output_file, output_content)

        resource_content = {
            'index': i,
            'messages': messages,
            'usage': usage,
            'seconds': seconds,
        }
        append_jsonl(resource_file, resource_content)

    evaluate_result(args.run_name, args.dataset_name, method, args.lang, result_type='json')
