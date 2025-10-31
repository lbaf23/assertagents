"""
LLM4AG

prompt format:

... "<AssertPlaceHolder>" ; } "<FocalMethod>" ...


"""

import argparse
from transformers import AutoTokenizer, AutoModelForCausalLM
from dataset_utils import read_dataset
import torch
from utils import create_dirs, read_jsonl, write_jsonl, create_or_clear_file
from utils.train_utils import set_seed
from tqdm import tqdm
import os
from evaluate import evaluate_result
from typing import Dict, List
import re
from transformers import RobertaTokenizer, T5ForConditionalGeneration


def clean_tokens(tokens):
    tokens = tokens.replace("<pad>", "")
    tokens = tokens.replace("<s>", "")
    tokens = tokens.replace("</s>", "")
    tokens = tokens.strip("\n")
    tokens = tokens.strip()
    return tokens


def format_java_code(code: str) -> str:
    string_pattern = r'(["\'])(?:(?=(\\?))\2.)*?\1'  # 匹配 "..." 或 '...'
    strings = []
    def _replace_string(m):
        strings.append(m.group(0))
        return f"__STRING_{len(strings) - 1}__"
    code = re.sub(string_pattern, _replace_string, code)
    code = re.sub(r'\s+', ' ', code.strip())
    code = re.sub(r'([()\[\]{};,.=+\-*/<>!&|?:])', r' \1 ', code)
    code = re.sub(r'\s+', ' ', code).strip()
    for i, s in enumerate(strings):
        code = code.replace(f"__STRING_{i}__", s)
    return code


def remove_spaces_in_code(code: str) -> str:
    string_pattern = r'(["\'])(?:(?=(\\?))\2.)*?\1'
    strings = []
    def _replace_string(m):
        strings.append(m.group(0))
        return f"__STRING_{len(strings) - 1}__"

    code = re.sub(string_pattern, _replace_string, code)
    code = re.sub(r'\s+', ' ', code.strip())
    symbols = r'([()\[\]{};,.=+\-*/<>!&|?:])'
    code = re.sub(r'\s+' + symbols, r'\1', code)
    code = re.sub(symbols + r'\s+', r'\1', code)
    for i, s in enumerate(strings):
        code = code.replace(f"__STRING_{i}__", s)
    code = code.strip()
    if not code.endswith(';'):
        code += ';'
    return code


def generate(tokenizer, model, data: Dict, max_length: int, nums: int) -> List[str]:
    test_prefix = data['test_prefix'].split('<AssertPlaceHolder>;')[0] + '<AssertPlaceHolder> ; }'
    prompt = format_java_code(test_prefix).strip().replace('< AssertPlaceHolder >', '"<AssertPlaceHolder>"') + ' "<FocalMethod>" ' + format_java_code(data['focal_method']).strip()

    print('=====================================')
    print(prompt)
    print('=====================================')

    input_ids = tokenizer.encode(
        prompt,
        truncation=True,
        max_length=max_length,
        padding='max_length',
        return_tensors='pt',
    ).to(device)
    attention_mask = input_ids.ne(0)

    with torch.no_grad():
        outputs = model.generate(
            input_ids=input_ids,
            attention_mask=attention_mask,
            do_sample=True,  # sample nums results
            num_return_sequences=nums,
            max_length=max_length,
        )
    outputs_text = [tokenizer.decode(
        outputs[i],
        skip_special_tokens=True,
        clean_up_tokenization_spaces=True
    ) for i in range(len(outputs))]

    outputs_text = [remove_spaces_in_code(clean_tokens(t)) for t in outputs_text]
    return outputs_text


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run_name', type=str, default='llm4ag-codet5')
    parser.add_argument('--dataset_name', type=str, default='teco500')

    parser.add_argument('--model_path', type=str, default='Salesforce/codet5-base')
    parser.add_argument('--finetune_model_path', type=str, default='')

    parser.add_argument('--nums', type=int, default=10)
    parser.add_argument('--lang', type=str, default='Java', choices=['Java'])

    parser.add_argument('--seed', type=int, default=3407)
    parser.add_argument('--rerun', action='store_true')
    args = parser.parse_args()

    set_seed(args.seed)

    device = 'cuda'

    tokenizer = RobertaTokenizer.from_pretrained(args.model_path)
    model = T5ForConditionalGeneration.from_pretrained(args.model_path)
    model.load_state_dict(torch.load(args.finetune_model_path, map_location=device))
    model.to(device)

    max_length = 512

    dataset = read_dataset(args.dataset_name)
    method = 'llm4ag'

    log_dir = f'logs/{args.run_name}'
    create_dirs(log_dir)

    output_dir = f'results/{args.run_name}'
    create_dirs(output_dir)

    output_file = os.path.join(output_dir, f'{args.dataset_name}_{method}.jsonl')

    if args.rerun:
        create_or_clear_file(output_file)

    output_content = read_jsonl(output_file)

    last_index = -1
    if len(output_content) > 0:
        last_index = output_content[-1]['index']

    # generate
    for i, data in enumerate(tqdm(dataset)):
        if i <= last_index:
            continue

        results = []
        gen_oracles = generate(tokenizer, model, data, max_length=max_length, nums=args.nums)
        for gen_oracle in gen_oracles:
            results.append({
                'gen_oracle': gen_oracle,
            })

        output_content.append({
            'index': len(output_content),
            'ground_truth_oracle': data['ground_truth_oracle'],
            'results': results
        })
        write_jsonl(output_file, output_content)
    evaluate_result(args.run_name, args.dataset_name, method, args.lang, result_type='jsonl')
