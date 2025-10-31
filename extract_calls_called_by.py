from utils import read_jsonl, write_json
from utils.java_utils.java_code_utils import get_java_method_name_pos
from utils.java_utils.java_repo_utils import find_java_function_calls
from utils.java_utils.java_lsp_client import JavaLSPClient
from utils.java_utils.java_file_utils import JAVA_ASSERT_PLACEHOLDER, JAVA_COM_ASSERT_PLACEHOLDER
from utils.code_file_utils.code_repo_utils import backup_file, recover_file
import os
import argparse


if __name__ == "__main__":
    teco500 = read_jsonl('./data/teco500.jsonl')

    parser = argparse.ArgumentParser()
    parser.add_argument('--jdtls_path', type=str, default="./data/resources/jdt-language-server")
    parser.add_argument('--start_index', type=int, default=0)
    parser.add_argument('--end_index', type=int, default=500)

    parser.add_argument('--repo_cache_dir', type=str, default="/tmp/work1/teco500")
    parser.add_argument('--workspace_dir', type=str, default="./cache/teco500_jdt_cache")
    args = parser.parse_args()

    for i in range(args.start_index, args.end_index):
        print(f'====== {i} ======')
        data = teco500[i]

        repo_path = str(os.path.join(args.repo_cache_dir, data['repo_name']))

        save_dir = f'''./cache/teco500/{data['repo_name']}'''
        os.makedirs(save_dir, exist_ok=True)

        fm_cache_file_path = os.path.join(
            save_dir,
            f'''{data['focal_method_file_path'].replace('/', '-')}:{data['focal_method_start_lineno']}.json'''
        )

        tp_cache_file_path = os.path.join(
            save_dir,
            f'''{data['test_prefix_file_path'].replace('/', '-')}:{data['test_prefix_start_lineno']}.json'''
        )

        if os.path.exists(fm_cache_file_path) and os.path.exists(tp_cache_file_path):
            print(f'Skip {i}')
            continue

        #### remove all gradle file, force to use maven ####
        os.system(f'find {repo_path} -type f -name "build.gradle" -delete')
        ####################################################

        #### Mask the ground truth
        test_prefix = data['test_prefix'].replace(JAVA_ASSERT_PLACEHOLDER, JAVA_COM_ASSERT_PLACEHOLDER)
        test_file_path = str(os.path.join(repo_path, data['test_prefix_file_path']))
        original_file_content, masked_file_content = backup_file(
            file_path=test_file_path,
            code=test_prefix,
            start_lineno=data['test_prefix_start_lineno'],
            end_lineno=data['test_prefix_end_lineno'],
        )

        workspace_path = str(os.path.join(args.workspace_dir, data['repo_name']))
        lsp_client = JavaLSPClient(args.jdtls_path, workspace_path, repo_path)
        print("=" * 60)
        print("Starting LSP server...")
        print("=" * 60)
        lsp_client.start_server()

        if not os.path.exists(fm_cache_file_path):
            calls = find_java_function_calls(
                code=data['focal_method'],
                start_lineno=data['focal_method_start_lineno'],
            )
            for c in range(len(calls)):
                calls[c]['definition'] = lsp_client.find_definition(
                    rel_file_path=data['focal_method_file_path'],
                    line=calls[c]['start_line'],
                    character=calls[c]['start_character'],
                )

            pos = get_java_method_name_pos(
                method_code=data['focal_method'],
                start_lineno=data['focal_method_start_lineno'],
            )
            called_by = lsp_client.find_references(
                rel_file_path=data['focal_method_file_path'],
                line=pos[0],
                character=pos[1],
            )

            print('=== Focal Method Calls ===')
            for c in calls: print(c)
            print('=== Focal Method Called By ===')
            for c in called_by: print(c)

            write_json(fm_cache_file_path, {
                'rel_file_path': data['focal_method_file_path'],
                'start_lineno': data['focal_method_start_lineno'],
                'calls': calls,
                'called_by': called_by,
            })

        if not os.path.exists(tp_cache_file_path):
            calls = find_java_function_calls(
                code=test_prefix,
                start_lineno=data['test_prefix_start_lineno'],
            )
            for c in range(len(calls)):
                calls[c]['definition'] = lsp_client.find_definition(
                    rel_file_path=data['test_prefix_file_path'],
                    line=calls[c]['start_line'],
                    character=calls[c]['start_character'],
                )

            print('=== Test Prefix Calls ===')
            for c in calls: print(c)
            write_json(tp_cache_file_path, {
                'rel_file_path': data['test_prefix_file_path'],
                'start_lineno': data['test_prefix_start_lineno'],
                'calls': calls,
                'called_by': [],
            })

        print("\n" + "=" * 60)
        print("Shutting down LSP server...")
        print("=" * 60)
        lsp_client.shutdown()

        #### Recover
        recover_file(file_path=test_file_path)

