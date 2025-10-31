"""
All lineno starts from 1

"""

from tree_sitter import Parser
import tree_sitter_java
from tree_sitter import Language

from typing import List, Dict, Optional, Tuple


JAVA_ASSERT_PLACEHOLDER = '<AssertPlaceHolder>;'
JAVA_COM_ASSERT_PLACEHOLDER = '// <AssertPlaceHolder>;'


def get_java_function_ranges(java_code: str):
    parser = Parser(language=Language(tree_sitter_java.language()))
    code_bytes = bytes(java_code, 'utf-8')
    tree = parser.parse(code_bytes)
    root_node = tree.root_node

    results = []

    def find_preceding_comment(func_node):
        comment_start_lineno = None

        parent = func_node.parent
        if not parent:
            return None

        siblings = parent.children
        idx = siblings.index(func_node)

        i = idx - 1
        while i >= 0:
            node = siblings[i]
            if node.type in {'comment', 'block_comment', 'line_comment'}:
                node_start_line, node_end_line = node.start_point[0], node.end_point[0]
                has_code_on_same_line = False
                for other_node in siblings:
                    if other_node != node \
                            and other_node.type not in {'comment', 'block_comment', 'line_comment'}:
                        other_start_line, other_end_line = other_node.start_point[0], other_node.end_point[0]
                        if (
                                other_start_line <= node_start_line <= other_end_line
                                or other_start_line <= node_end_line <= other_end_line
                                or node_start_line <= other_start_line <= node_end_line
                                or node_start_line <= other_end_line <= node_end_line
                        ) and (
                                other_start_line == node_start_line or other_end_line == node_start_line
                        ):
                            has_code_on_same_line = True
                            break

                if not has_code_on_same_line and node.end_point[0] < func_node.start_point[0]:
                    comment_start_lineno = node.start_point[0] + 1
            elif node.type not in (';', 'block', 'empty_statement'):
                break
            i -= 1
        return comment_start_lineno

    type_map = {
        'method_declaration': 'method',
        'constructor_declaration': 'constructor',
        'class_declaration': 'class'
    }
    def traverse(node, parent):
        curr = None
        if node.type in {'method_declaration', 'constructor_declaration', 'class_declaration'}:
            name = None

            start_lineno = node.start_point[0] + 1
            end_lineno = node.end_point[0] + 1

            body_start_lineno = end_lineno
            body_end_lineno = end_lineno
            for child in node.children:
                if child.type == 'identifier':
                    name = code_bytes[child.start_byte:child.end_byte].decode('utf-8')
                elif node.type == 'method_declaration' and child.type == 'block':
                    body_start_lineno = child.start_point[0] + 1
                    body_end_lineno = child.end_point[0] + 1
                elif node.type == 'constructor_declaration' and child.type == 'constructor_body':
                    body_start_lineno = child.start_point[0] + 1
                    body_end_lineno = child.end_point[0] + 1
                elif node.type == 'class_declaration' and child.type == 'class_body':
                    body_start_lineno = child.start_point[0] + 1
                    body_end_lineno = child.end_point[0] + 1

            if name is not None:
                comment_start_lineno = find_preceding_comment(node)
                if comment_start_lineno is not None:
                    start_lineno = min(comment_start_lineno, start_lineno)

                curr = {
                    'type': type_map[node.type],
                    'name': name,
                    'start_lineno': start_lineno,
                    'end_lineno': end_lineno,
                    'body_start_lineno': body_start_lineno,
                    'body_end_lineno': body_end_lineno,
                    'parent': [],
                    'children': [],
                }

        if parent is not None and curr is not None:
            parent['children'].append(curr['start_lineno'])
            curr['parent'].append(parent['start_lineno'])

        if curr is not None:
            results.append(curr)

        if node.type not in {'method_declaration', 'constructor_declaration'}:
            for child in node.children:
                traverse(child, curr if curr is not None else parent)

    traverse(root_node, None)
    return results


def remove_java_preview_comments(code: str, preview_with_lineno: bool = True):
    lines = code.splitlines()
    j = 0
    while j < len(lines):
        if preview_with_lineno:
            line = lines[j][lines[j].index(']') + 1 : ].lstrip()
        else:
            line = lines[j].lstrip()
        if line.startswith('/*'):
            while True:
                if preview_with_lineno:
                    line = lines[j][lines[j].index(']') + 1:].lstrip()
                else:
                    line = lines[j].lstrip()
                if line.endswith('*/'):
                    j += 1
                    break
                j += 1
            break
        elif line == '':
            j += 1
        else:
            break
    if j > 0:
        lines = lines[j : ]
    return '\n'.join(lines)


def remove_java_preview_imports(code: str, preview_with_lineno: bool = True) -> str:
    lines = code.splitlines()
    j = 0
    while j < len(lines):
        if preview_with_lineno:
            line = lines[j][lines[j].index(']') + 1 : ].lstrip()
        else:
            line = lines[j].lstrip()
        if line.startswith('package') or line.startswith('import'):
            while True:
                if preview_with_lineno:
                    line = lines[j][lines[j].index(']') + 1:].lstrip()
                else:
                    line = lines[j].lstrip()
                if line.startswith('package') or line.startswith('import') or line.strip() == '':
                    j += 1
                else:
                    break
            break
        elif line == '':
            j += 1
        else:
            break
    if j > 0:
        lines = lines[j : ]
    return '\n'.join(lines)



def contains_idx(lst1, lst2) -> bool:
    for l1 in lst1:
        if l1 in lst2:
            return True
    return False

def contains_range(l1, l2, nos) -> bool:
    for no in nos:
        if l1 <= no <= l2:
            return True
    return False

def get_java_file_content_preview(code: str, show_target_start_linenos: List[int], preview_add_lineno: bool = True) -> str:
    lines = code.splitlines()
    linenos = [i + 1 for i in range(len(lines))]
    targets = get_java_function_ranges(code)

    result_lines = []
    result_linenos = []
    start_index = 0
    targets = sorted(targets, key=lambda t: t['start_lineno'])

    show_target = set()
    for target in targets:
        if target['start_lineno'] in show_target_start_linenos:
            show_target.add(target['start_lineno'])
        elif target['children'] == [] and contains_range(target['start_lineno'], target['end_lineno'], show_target_start_linenos):
            show_target.add(target['start_lineno'])

    has_split = False
    for target in targets:
        if not show_target.__contains__(target['start_lineno']):
            if contains_idx(target['children'], show_target):
                has_split = False
            elif contains_idx(target['parent'], show_target):
                # Skip method body
                lines[target['body_start_lineno'] - 1] += ' /* Folded */ }'
                result_lines += lines[start_index : target['body_start_lineno']]
                result_linenos += linenos[start_index : target['body_start_lineno']]
                start_index = target['end_lineno']
                has_split = False
            else:
                # Skip total method
                result_lines += lines[start_index : target['start_lineno'] - 1]
                result_linenos += linenos[start_index : target['start_lineno'] - 1]

                if not has_split:
                    result_lines.append('...')
                    result_linenos.append('...')
                    has_split = True

                start_index = target['end_lineno']
        else:
            has_split = False

    result_lines += lines[start_index:]
    result_linenos += linenos[start_index:]

    skip_spaces = set()
    space_start = False
    for i in range(len(result_lines)):
        if result_lines[i].strip() == '':
            if space_start:
                skip_spaces.add(i)
            else:
                space_start = True
        else:
            space_start = False

    preview = ''
    for i in range(len(result_lines)):
        if i not in skip_spaces:
            if preview_add_lineno:
                preview += f'[{result_linenos[i]}] ' + result_lines[i] + '\n'
            else:
                preview += result_lines[i] + '\n'
    return preview.rstrip()


def make_java_method_mask_table(calls: List, mask_table: Dict = {}, mid_start: int = 0, cid_start: int = 0) -> Tuple[Dict, int, int]:
    mask_map = {}
    for call in calls:
        if call['definition'] is not None:
            if mask_table.__contains__(call['name']):
                continue

            if call['type'] == 'constructor':
                new_name = f'Class{cid_start}'
                cid_start += 1
            else:
                new_name = f'method{mid_start}'
                mid_start += 1
            mask_map[call['name']] = new_name
    return mask_map, mid_start, cid_start


def mask_java_code(code: str, mask_table: Dict[str, str]) -> str:
    sorted_mask_table = sorted(mask_table.keys(), key=len, reverse=True)
    for original in sorted_mask_table:
        new_name = mask_table[original]
        code = code.replace(original, new_name)
    return code


def mask_java_method_calls(method_code: str, start_lineno: int, calls: List) -> Tuple[str, List]:
    method_lines = method_code.splitlines()
    line_splits = {}
    for call in calls:
        if call['definition'] is not None and call['start_line'] == call['end_line']:
            line = call['start_line'] - start_lineno + 1
            if not line_splits.__contains__(line):
                line_splits[line] = [[call['start_character'], call['end_character'], call['type']]]
            else:
                line_splits[line].append([call['start_character'], call['end_character'], call['type']])

    masked_info = []
    class_i = 0
    method_i = 0
    for line in line_splits.keys():
        splits = line_splits[line]
        splits = sorted(splits, key=lambda t: t[0])
        code_line = method_lines[line]
        ret_code_line = ''
        last_end = 0
        for split in splits:
            if split[2] == 'constructor':
                mk = f'Class{class_i}'
                class_i += 1
            else:
                mk = f'method{method_i}'
                method_i += 1
            ret_code_line += code_line[last_end : split[0]] + mk
            last_end = split[1]
            masked_info.append({
                'lineno': line + start_lineno,
                'replace_line': line + start_lineno - 1,
                'replace_character': split[0],
                'original_name': code_line[split[0] : split[1]],
                'new_name': mk
            })
        ret_code_line += code_line[last_end : ]
        method_lines[line] = ret_code_line

    masked_code = '\n'.join(method_lines)
    return masked_code, masked_info


def get_java_function_body_inline(
        code: str,
        lineno: int,
        show_parent_class: bool,
        preview_add_lineno: bool = True,
) -> Optional[Dict]:
    """
    Return a java function code that contains lineno
    """
    functions = get_java_function_ranges(code)
    lines = code.splitlines()
    linenos = [(i + 1) for i in range(len(lines))]

    target = None
    for function in functions:
        if function['start_lineno'] <= lineno <= function['end_lineno'] \
                and (target is None or function['start_lineno'] > target['start_lineno']):
            target = function

    if target is None:
        return None

    if target['type'] == 'class' or show_parent_class:
        if not preview_add_lineno and target['end_lineno'] - target['start_lineno'] + 1 <= 100:
            result_lines = lines[target['start_lineno'] - 1: target['end_lineno']]
            preview = '\n'.join(result_lines)
        else:
            preview = get_java_file_content_preview(code, [target['start_lineno']], preview_add_lineno)
            preview = remove_java_preview_comments(preview, preview_with_lineno=preview_add_lineno)
            preview = remove_java_preview_imports(preview, preview_with_lineno=preview_add_lineno)
    elif target['type'] == 'constructor':
        preview = get_java_file_content_preview(code, [target['start_lineno']], preview_add_lineno)
        preview = remove_java_preview_comments(preview, preview_with_lineno=preview_add_lineno)
        preview = remove_java_preview_imports(preview, preview_with_lineno=preview_add_lineno)
    else:
        result_lines = lines[target['start_lineno'] - 1 : target['end_lineno']]
        result_linenos = linenos[target['start_lineno'] - 1 : target['end_lineno']]
        if preview_add_lineno:
            for i in range(len(result_lines)):
                result_lines[i] = f'[{result_linenos[i]}] ' + result_lines[i]
        preview = '\n'.join(result_lines)
    return {
        'preview': preview,
        'type': target['type'],
        'start_lineno': target['start_lineno'],
        'end_lineno': target['end_lineno'],
        'body_start_lineno': target['body_start_lineno'],
        'body_end_lineno': target['body_end_lineno'],
    }


def get_lineno(java_code: str, stmt: str, start_lineno: int) -> int:
    lineno = start_lineno
    lines = java_code.splitlines()
    for line in lines:
        if line.strip() == stmt:
            return lineno
        lineno += 1
    return -1


def get_java_method_name(method_code: str) -> str:
    java_lang = Language(tree_sitter_java.language())
    parser = Parser()
    parser.language = java_lang

    code_bytes = bytes(method_code, 'utf-8')
    tree = parser.parse(code_bytes)

    for node in tree.root_node.children:
        if node.type == 'method_declaration':
            for child in node.children:
                if child.type == 'identifier':
                    return code_bytes[child.start_byte:child.end_byte].decode('utf-8')

    return ''


def remove_sps(code: str) -> str:
    lines = code.splitlines()
    sps = min([len(l) - len(l.lstrip()) for l in lines if l.strip() != ''])
    lines = [l[sps: ] for l in lines]
    return '\n'.join(lines)

from utils.code_file_utils.code_file_utils import single_file_rag

def get_java_test_class_assert_preview(code: str, test_prefix: str, max_test_functions: int = 10) -> str:
    target_ranges = get_java_function_ranges(code)
    lines = code.splitlines()

    functions = []
    for target in target_ranges:
        if target['type'] in {'method'}:
            function_body = '\n'.join(lines[target['start_lineno'] - 1: target['end_lineno']])
            if function_body.__contains__('assert'):
                target['body'] = function_body
                functions.append(target)
    if len(functions) > 0:
        selected_idx = single_file_rag(
            functions=functions,
            query_func=test_prefix.replace(JAVA_COM_ASSERT_PLACEHOLDER, ''),
            top_k=max_test_functions,
        )
        selected_functions = [remove_sps(functions[i]['body']) for i in selected_idx]
        return '\n\n\n'.join(selected_functions)
    else:
        return remove_sps(test_prefix)



# def get_java_test_class_assert_preview(code: str, max_test_functions: int = 10) -> str:
#     targets = get_java_function_ranges(code)
#     lines = code.splitlines()
#
#     exclude_functions_linenos = []
#     for target in targets:
#         if target['type'] in {'method'}:
#             function_body = '\n'.join(lines[target['start_lineno'] - 1 : target['end_lineno']])
#             if function_body.__contains__('assert'):
#                 exclude_functions_linenos.append(target['start_lineno'])
#                 if len(exclude_functions_linenos) >= max_test_functions:
#                     break
#     return get_java_file_content_preview(code, exclude_functions_linenos)





# def fold_java_function_body(java_code: str, exclude_functions_key: List[str] = []) -> str:
#     """
#     Return a java class skeleton, fold all functions' body except exclude_functions_key(function_name:lineno)
#
#     Args:
#         java_code:
#         exclude_functions_key:
#
#     Returns:
#
#     """
#     functions = get_java_function_ranges(java_code)
#     lines = java_code.splitlines()
#     linenos = [(i + 1) for i in range(len(lines))]
#
#     results = []
#     results_linenos = []
#     start_index = 0
#     for function in functions:
#         if f'''{function['function_name']}:{function['function_start_lineno']}''' not in exclude_functions_key:
#             lines[function['body_start_lineno'] - 1] += ' /* Folded */ }'
#             results += lines[start_index : function['body_start_lineno']]
#             results_linenos += linenos[start_index : function['body_start_lineno']]
#             start_index = function['body_end_lineno']
#     results += lines[start_index:]
#     results_linenos += linenos[start_index:]
#
#     for i in range(len(results)):
#         results[i] = f'[{results_linenos[i]}] ' + results[i]
#     return '\n'.join(results)
#
#
# def fold_java_function(java_code: str, exclude_functions_key: List[str] = []) -> str:
#     """
#     Return a java class skeleton, remove all functions except exclude_functions_key
#     Args:
#         java_code:
#         exclude_functions_key: function_name:function_start_lineno
#
#     Returns:
#
#     """
#     functions = get_java_function_ranges(java_code)
#     lines = java_code.splitlines()
#     linenos = [(i + 1) for i in range(len(lines))]
#
#     results = []
#     results_linenos = []
#     start_index = 0
#     folded = False
#     for function in functions:
#         if f'''{function['function_name']}:{function['function_start_lineno']}''' not in exclude_functions_key:
#             start_lineno = function['function_start_lineno']
#             if function['comment_start_lineno'] != -1:
#                 start_lineno = function['comment_start_lineno']
#
#             if not folded:
#                 results += lines[start_index: start_lineno - 1]
#                 results_linenos += linenos[start_index: start_lineno - 1]
#
#                 results.append('...')
#                 results_linenos.append('')
#             folded = True
#             start_index = function['function_end_lineno']
#         else:
#             folded = False
#
#     results += lines[start_index:]
#     results_linenos += linenos[start_index:]
#
#     res = ''
#     add_split = False
#     for i in range(len(results)):
#         if results_linenos[i] == '':
#             if add_split:
#                 continue
#             else:
#                 res += '...' + '\n'
#                 add_split = True
#         else:
#             add_split = False
#             res += f'[{results_linenos[i]}] ' + results[i] + '\n'
#
#     return res
#
#
# def get_java_function_body(java_code: str, function_name: str = '', lineno: int = -1) -> str:
#     """
#     Return a java function code
#     Args:
#         java_code:
#         function_name:
#         lineno: function start line number, to distinguish overloaded functions
#
#     Returns:
#
#     """
#     assert not (function_name == '' and lineno == -1)
#
#     functions = get_java_function_ranges(java_code)
#     lines = java_code.splitlines()
#     linenos = [(i + 1) for i in range(len(lines))]
#
#     target_function = None
#     for function in functions:
#         if (function['function_name'] == function_name or function_name == '') and (lineno == function['function_start_lineno'] or lineno == -1):
#             target_function = function
#             break
#
#     if target_function is None:
#         return ''
#
#     results = lines[target_function['function_start_lineno'] - 1 : target_function['function_end_lineno']]
#     results_linenos = linenos[target_function['function_start_lineno'] - 1 : target_function['function_end_lineno']]
#     for i in range(len(results)):
#         results[i] = f'[{results_linenos[i]}] ' + results[i]
#     return '\n'.join(results)

