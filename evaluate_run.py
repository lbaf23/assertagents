import argparse
import json
from tqdm import tqdm
from dataset_utils import read_dataset
from typing import List, Tuple, Dict
from utils import read_jsonl, write_jsonl, write_json, read_json, read_file, write_file
import os
from utils.code_file_utils.code_file_utils import replace_code_lines, clean_content
from utils.java_utils.pkg_utils import path_to_pkg
from utils.java_utils.java_file_utils import JAVA_ASSERT_PLACEHOLDER
from utils.python_utils.python_file_utils import PY_ASSERT_PLACEHOLDER
from utils.python_utils.python_tester import run_py_repo_test
from utils.java_utils.java_tester import run_java_repo_test


def evaluate_run(dataset: List, repo_cache_dir: str, output_content: List[Dict], lang: str, rerun: bool) -> Tuple:
    count_result = {
        'run@1': 0.0
    }
    for i, o in enumerate(tqdm(output_content)):
        results = o['results']
        data = dataset[i]

        if len(results) > 0 and (not rerun or not results[0].__contains__('run')):
            gen_oracle = results[0]['gen_oracle']

            if gen_oracle == '':
                results[0]['run'] = False
            else:
                repo_path = os.path.join(repo_cache_dir, data['repo_name'])
                if lang.lower() == "java":
                    test_file_path = os.path.join(repo_path, data['test_prefix_file_path'])
                    original_test_file_content = read_file(test_file_path)
                    original_test_file_content = clean_content(original_test_file_content)
                    run_test_file_content = replace_code_lines(
                        file_code=original_test_file_content,
                        code=data['test_prefix'].replace(JAVA_ASSERT_PLACEHOLDER, gen_oracle),
                        start_lineno=data['test_prefix_start_lineno'],
                        end_lineno=data['test_prefix_end_lineno']
                    )
                    write_file(test_file_path, run_test_file_content)

                    test_prefix_sub_repo, test_prefix_pkg = path_to_pkg(data['test_prefix_file_path'])
                    res, _ = run_java_repo_test(
                        repo_path=repo_path,
                        sub_repo=test_prefix_sub_repo,
                        test_class=test_prefix_pkg,
                        test_target=data['test_target'],
                    )
                    write_file(test_file_path, original_test_file_content)
                else:
                    test_file_path = os.path.join(repo_path, data['test_prefix_file_path'])
                    original_test_file_content = read_file(test_file_path)
                    run_test_file_content = replace_code_lines(
                        file_code=original_test_file_content,
                        code=data['test_prefix'].replace(PY_ASSERT_PLACEHOLDER, gen_oracle),
                        start_lineno=data['test_prefix_start_lineno'],
                        end_lineno=data['test_prefix_end_lineno']
                    )
                    write_file(test_file_path, run_test_file_content)

                    res, _ = run_py_repo_test(
                        repo_path=repo_path,
                        test_target=data['test_target'],
                    )
                    write_file(test_file_path, original_test_file_content)
                results[0]['run'] = res['score'] == 1.0

            if results[0]['run']:
                count_result['run@1'] += 1

    count_result['run@1'] /= len(output_content)
    print(f'''\
=== Result ===
{json.dumps(count_result, indent=4)}
''')
    return output_content, count_result


def evaluate_result(
        run_name: str,
        dataset_name: str,
        repo_cache_dir: str,
        method: str,
        lang: str,
        result_type: str,
        rerun: bool,
        start_index: int,
        end_index: int,
) -> None:
    count_output_file = f'results/{run_name}/{dataset_name}_{method}_result_run.json'
    if result_type == 'jsonl':
        output_file = f'results/{run_name}/{dataset_name}_{method}.jsonl'
        assert os.path.exists(output_file), f'Output file {output_file} does not exist.'
        output_content = read_jsonl(output_file)
    elif result_type == 'json':
        output_dir = f'results/{run_name}/{dataset_name}_{method}'
        output_content = []
        for i in range(start_index, end_index):
            output_content.append(read_json(os.path.join(output_dir, f'{i}.json')))
    else:
        raise NotImplementedError()

    dataset = read_dataset(dataset_name)
    output_content, count_result = evaluate_run(dataset, repo_cache_dir, output_content, lang, rerun)

    if result_type == 'jsonl':
        write_jsonl(output_file, output_content)
    elif result_type == 'json':
        for i, o in enumerate(output_content):
            write_json(os.path.join(output_dir, f'{i}.json'), o)

    write_json(count_output_file, count_result)
    print(f'Run result saved to {count_output_file}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run_name', type=str)
    parser.add_argument('--repo_cache_dir', type=str, required=True)

    parser.add_argument('--dataset_name', type=str)
    parser.add_argument('--method', type=str)
    parser.add_argument('--result_type', type=str, default='json')
    parser.add_argument('--lang', type=str)
    parser.add_argument('--start_index', type=int, default=0)
    parser.add_argument('--end_index', type=int, default=500)
    parser.add_argument('--rerun', action='store_true')
    args = parser.parse_args()
    evaluate_result(
        run_name=args.run_name,
        dataset_name=args.dataset_name,
        repo_cache_dir=args.repo_cache_dir,
        method=args.method,
        lang=args.lang,
        result_type=args.result_type,
        rerun=args.rerun,
        start_index=args.start_index,
        end_index=args.end_index
    )
