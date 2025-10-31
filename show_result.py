import argparse
from utils import read_json
from tabulate import tabulate


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset_name', type=str, default='teco500')

    parser.add_argument('--run_name_list', nargs='+', type=str)
    parser.add_argument('--method_list', nargs='+', type=str)
    parser.add_argument('--suffix', type=str, default='')
    args = parser.parse_args()
    run_name_list = args.run_name_list
    method_list = args.method_list

    assert len(run_name_list) == len(method_list)

    # results = ['acc@1', 'acc@3', 'acc@5', 'acc@10', 'method']
    results = []
    for i in range(len(run_name_list)):
        run_name = run_name_list[i]
        method = method_list[i]

        if run_name == '':
            line = {
                'method': '---',
                'acc@1': '---', 'acc@3': '---', 'acc@5': '---', 'acc@10': '---',
                'bleu': '---', 'codebleu': '---', 'rouge': '---', 'editsim': '---',
            }
        else:
            file_path = f'results/{run_name}/{args.dataset_name}_{method}_result{args.suffix}.json'
            result = read_json(file_path)

            for k in result.keys():
                if type(result[k]) == float:
                    result[k] = round(result[k], 3)
            # result['codebleu'] = round(result['codebleu'], 3)
            # result['rouge'] = round(result['rouge'], 3)
            # result['editsim'] = round(result['editsim'], 3)

            line = {
                'method': f'{run_name}_{method}'
            }
            line.update(result)

        results.append(line)

    print(f'========== {args.dataset_name} {args.suffix} ==========')
    print(tabulate(results, headers='keys', tablefmt=''))
