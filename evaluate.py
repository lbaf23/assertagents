import argparse
import json
from utils.code_utils import is_assert_same, filter_assert_statement
from typing import List, Tuple, Dict
from utils import read_jsonl, write_jsonl, write_json, read_json
import os
from nltk.translate.bleu_score import corpus_bleu, SmoothingFunction
from tree_sitter import Language, Parser
import tree_sitter_java, tree_sitter_python
from codebleu import calc_codebleu
from rouge import Rouge
from nltk import edit_distance


def extract_tokens(code: str, lang):
    if lang.lower() == 'java':
        lang_ptr = tree_sitter_java.language()
    else:
        lang_ptr = tree_sitter_python.language()
    parser = Parser(language=Language(lang_ptr))
    tree = parser.parse(bytes(code, "utf8"))
    root_node = tree.root_node

    def traverse(node):
        if node.child_count == 0:
            text = code[node.start_byte:node.end_byte]
            return [text]
        tokens = []
        for child in node.children:
            tokens.extend(traverse(child))
        return tokens

    return traverse(root_node)

def cal_bleu(ref_codes: List[str], gen_codes: List[str], lang) -> float:
    ref_codes = [[extract_tokens(r, lang)] for r in ref_codes]
    score = corpus_bleu(ref_codes, [extract_tokens(g, lang) for g in gen_codes], smoothing_function=SmoothingFunction().method2)
    return score


def cal_codebleu(ref_codes: List[str], gen_codes: List[str], lang: str) -> float:
    score = calc_codebleu(ref_codes, gen_codes, lang=lang.lower())
    return score['codebleu']


def cal_rouge(ref_codes: List[str], gen_codes: List[str], lang) -> float:
    rouge = Rouge()
    score = 0.0
    for r, g in zip(ref_codes, gen_codes):
        if g == '':
            continue
        rg = rouge.get_scores(' '.join(extract_tokens(g, lang)), ' '.join(extract_tokens(r, lang)))
        score += rg[0]['rouge-l']['f']
    score /= len(ref_codes)
    return score


def cal_editsim(ref_codes: List[str], gen_codes: List[str]) -> float:
    score = 0.0
    for r, g in zip(ref_codes, gen_codes):
        score += edit_distance(r, g)/max(len(r), len(g))
    return 1 - score/len(ref_codes)


def evaluate(output_content: List[Dict], suffix: str, lang: str, mask_str: bool) -> Tuple:
    count_result = {
        'acc@1': 0.0,
        'acc@3': 0.0,
        'acc@5': 0.0,
        'acc@10': 0.0,

        'bleu': 0.0,
        'codebleu': 0.0,
        'rouge': 0.0,
        'editsim': 0.0
    }

    ref_codes = []
    gen_codes = []

    for i, o in enumerate(output_content):
        results = o['results']
        for r in results:
            r[f'corr{suffix}'] = is_assert_same(r['gen_oracle'], o['ground_truth_oracle'], lang, mask_str)

        corr_list = [r[f'corr{suffix}'] for r in results]

        if corr_list[: 1].__contains__(True):
            count_result['acc@1'] += 1

        if corr_list[: 3].__contains__(True):
            count_result['acc@3'] += 1

        if corr_list[: 5].__contains__(True):
            count_result['acc@5'] += 1

        if corr_list[: 10].__contains__(True):
            count_result['acc@10'] += 1

        ref_codes.append(filter_assert_statement(o['ground_truth_oracle'], lang))
        gen_codes.append(filter_assert_statement(results[0]['gen_oracle'] if len(results) > 0 else '', lang))

    count_result['acc@1'] /= len(output_content)
    count_result['acc@3'] /= len(output_content)
    count_result['acc@5'] /= len(output_content)
    count_result['acc@10'] /= len(output_content)

    count_result['bleu'] = round(cal_bleu(ref_codes, gen_codes, lang), 5)
    count_result['codebleu'] = round(cal_codebleu(ref_codes, gen_codes, lang), 5)
    count_result['rouge'] = round(cal_rouge(ref_codes, gen_codes, lang), 5)
    count_result['editsim'] = round(cal_editsim(ref_codes, gen_codes), 5)


    # print('=== Cal BLEU ===')
    # count_result['bleu'] = round(bleu(data), 5)
    # print('=== Cal CodeBLEU ===')
    # count_result['codebleu'] = round(code_bleu(data, lang), 5)
    # # print('=== Cal Rouge ===')
    # # count_result['rouge'] = round(rouge(data), 5)
    # print('=== Cal EditSim ===')
    # count_result['editsim'] = round(edit_sim(data), 5)


    print(f'''\
=== Result ===
{json.dumps(count_result, indent=4)}
''')
    return output_content, count_result


def evaluate_result(
        run_name: str,
        dataset_name: str,
        method: str,
        lang: str,
        result_type: str = 'jsonl',
        suffix: str = '',
        mask_str: bool = False,
        start_index: int = 0,
        end_index: int = 500,
) -> None:
    count_output_file = f'results/{run_name}/{dataset_name}_{method}_result{suffix}.json'

    if result_type == 'jsonl':
        output_file = f'results/{run_name}/{dataset_name}_{method}.jsonl'
        assert os.path.exists(output_file), f'Output file {output_file} does not exist.'
        output_content = read_jsonl(output_file)
        print(f'Jsonl size: {len(output_content)}.')

    elif result_type == 'json':
        output_dir = f'results/{run_name}/{dataset_name}_{method}'
        output_content = []
        size = 0
        for filename in os.listdir(output_dir):
            if filename.endswith('.json'):
                size += 1

        print(f'Start: {start_index}, End: {end_index}')
        for i in range(start_index, end_index):
            output_content.append(read_json(os.path.join(output_dir, f'{i}.json')))

    else:
        raise NotImplementedError()

    output_content, count_result = evaluate(output_content, suffix, lang, mask_str)

    if result_type == 'jsonl':
        write_jsonl(output_file, output_content)
    elif result_type == 'json':
        for i in range(start_index, end_index):
            write_json(os.path.join(output_dir, f'{i}.json'), output_content[i])

    write_json(count_output_file, count_result)
    print(f'Count result saved to {count_output_file}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run_name', type=str)
    parser.add_argument('--dataset_name', type=str)
    parser.add_argument('--method', type=str)
    parser.add_argument('--result_type', type=str, default='json')
    parser.add_argument('--lang', type=str)
    parser.add_argument('--suffix', type=str, default='')

    parser.add_argument('--mask_str', action='store_true')
    parser.add_argument('--start_index', type=int, default=0)
    parser.add_argument('--end_index', type=int, default=500)
    args = parser.parse_args()

    evaluate_result(
        run_name=args.run_name,
        dataset_name=args.dataset_name,
        method=args.method,
        lang=args.lang,
        result_type=args.result_type,
        suffix=args.suffix,
        mask_str=args.mask_str,
        start_index=args.start_index,
        end_index=args.end_index
    )
