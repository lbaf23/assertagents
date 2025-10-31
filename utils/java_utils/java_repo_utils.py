from typing import Optional, Dict, Tuple, List
from tree_sitter import Node, Parser, Language
import tree_sitter_java

from ..file_utils import read_file


def _get_byte_offset_from_lsp_position(source_code: str, line: int, character: int) -> Optional[int]:
    lines = source_code.splitlines(keepends=True)
    if 0 <= line < len(lines):
        offset = sum(len(line_content.encode('utf-8')) for line_content in lines[:line])
        offset += len(lines[line][:character].encode('utf-8'))
        return offset
    return None


def _find_node_at_byte_offset(node, target_byte_offset):
    if node.start_byte <= target_byte_offset < node.end_byte:
        for child in node.children:
            found_child = _find_node_at_byte_offset(child, target_byte_offset)
            if found_child:
                return found_child
        return node
    return None


def _get_node_line_range(node):
    start_line = node.start_point[0]
    end_line = node.end_point[0]
    return start_line, end_line


def _find_decorator_start_line_ast(source_code: str, root_node, current_start_line_0b, decorator_type):
    lines = source_code.splitlines(keepends=True)
    element_start_byte_offset = sum(len(line_content.encode('utf-8')) for line_content in lines[:current_start_line_0b])

    def traverse_tree_for_decorators(node, found_decorators):
        if node.type == decorator_type:
            if node.end_byte <= element_start_byte_offset:
                annotation_start_line = node.start_point[0]
                if annotation_start_line < current_start_line_0b:
                    found_decorators.append(annotation_start_line)

        for child in node.children:
            traverse_tree_for_decorators(child, found_decorators)

    all_found_annotation_lines = []
    traverse_tree_for_decorators(root_node, all_found_annotation_lines)

    if not all_found_annotation_lines:
        return current_start_line_0b

    highest_relevant_annotation_line = max(all_found_annotation_lines)

    annotation_lines_set = set(all_found_annotation_lines)
    current_line = highest_relevant_annotation_line
    while current_line > 0 and current_line - 1 in annotation_lines_set:
        current_line -= 1

    decorator_start_line = current_line

    return decorator_start_line


def _extract_name_from_node(node, parent_type):
    for child in node.children:
        if child.type == 'identifier':
            name_text = node.text[child.start_byte - node.start_byte : child.end_byte - node.start_byte].decode('utf-8')
            return name_text
    return ""


def get_java_target_source(file_path: str, line: int, character: int) -> Optional[Dict]:
    file_content = read_file(file_path)
    file_lines = file_content.splitlines()
    parser = Parser(language=Language(tree_sitter_java.language()))
    tree = parser.parse(bytes(file_content, "utf-8"))
    root_node = tree.root_node

    target_position_bytes = _get_byte_offset_from_lsp_position(file_content, line, character)
    if target_position_bytes is None:
        return None

    target_node = _find_node_at_byte_offset(root_node, target_position_bytes)

    if not target_node:
        return None

    result = None
    current_node = target_node

    while current_node and current_node != root_node:
        if current_node.type == 'method_declaration':
            start_line, end_line = _get_node_line_range(current_node)
            decorator_start_line = _find_decorator_start_line_ast(file_content, root_node, start_line, 'annotation')
            name = _extract_name_from_node(current_node, 'method_declaration')

            start_lineno = min(decorator_start_line + 1, start_line + 1)
            end_lineno = end_line + 1
            result = {
                'type': 'method',
                'name': name,
                'body': '\n'.join(file_lines[start_lineno - 1: end_lineno]),
                'start_lineno': start_lineno,
                'end_lineno': end_lineno
            }
            break

        elif current_node.type == 'class_declaration':
            start_line, end_line = _get_node_line_range(current_node)
            decorator_start_line = _find_decorator_start_line_ast(file_content, root_node, start_line, 'annotation')
            name = _extract_name_from_node(current_node, 'class_declaration')

            start_lineno = min(decorator_start_line + 1, start_line + 1)
            end_lineno = end_line + 1
            result = {
                'type': 'class',
                'name': name,
                'body': '\n'.join(file_lines[start_lineno - 1: end_lineno]),
                'start_lineno': start_lineno,
                'end_lineno': end_lineno
            }
            break

        elif current_node.type == 'interface_declaration':
            start_line, end_line = _get_node_line_range(current_node)
            decorator_start_line = _find_decorator_start_line_ast(file_content, root_node, start_line, 'annotation')
            name = _extract_name_from_node(current_node, 'interface_declaration')

            start_lineno = min(decorator_start_line + 1, start_line + 1)
            end_lineno = end_line + 1
            result = {
                'type': 'interface',
                'name': name,
                'body': '\n'.join(file_lines[start_lineno - 1: end_lineno]),
                'start_lineno': start_lineno,
                'end_lineno': end_lineno
            }
            break

        elif current_node.type == 'enum_declaration':
            start_line, end_line = _get_node_line_range(current_node)
            decorator_start_line = _find_decorator_start_line_ast(file_content, root_node, start_line, 'annotation')
            name = _extract_name_from_node(current_node, 'enum_declaration')

            start_lineno = min(decorator_start_line + 1, start_line + 1)
            end_lineno = end_line + 1
            result = {
                'type': 'enum',
                'name': name,
                'body': '\n'.join(file_lines[start_lineno - 1: end_lineno]),
                'start_lineno': start_lineno,
                'end_lineno': end_lineno
            }
            break

        current_node = current_node.parent
    return result


def find_java_function_calls(code: str, start_lineno: int) -> List:
    parser = Parser(language=Language(tree_sitter_java.language()))
    code_bytes = bytes(code, "utf8")
    tree = parser.parse(code_bytes)
    calls = []
    def find_function_calls(node: Node):
        if node.type == "method_invocation":
            name_node = node.child_by_field_name("name")
            if name_node:
                start_line, start_character = name_node.start_point
                end_line, end_character = name_node.end_point
                calls.append({
                    'type': 'method',
                    'name': code_bytes[name_node.start_byte:name_node.end_byte].decode('utf8'),
                    'start_line': start_line + start_lineno - 1,
                    'start_character': start_character,
                    'end_line': end_line + start_lineno - 1,
                    'end_character': end_character
                })
        elif node.type == "object_creation_expression":
            type_node = node.child_by_field_name("type")
            if type_node:
                start_line, start_character = type_node.start_point
                end_line, end_character = type_node.end_point
                calls.append({
                    'type': "constructor",
                    'name': code[type_node.start_byte:type_node.end_byte],
                    'start_line': start_line + start_lineno - 1,
                    'start_character': start_character,
                    'end_line': end_line + start_lineno - 1,
                    'end_character': end_character
                })

        for child in node.children:
            find_function_calls(child)

    find_function_calls(tree.root_node)
    return calls


def analyze_java_method_calls(code: str, start_lineno: int) -> List:
    code = f'''\
class Example {{
{code}
}}
'''
    parser = Parser(language=Language(tree_sitter_java.language()))
    tree = parser.parse(bytes(code, "utf8"))
    root_node = tree.root_node

    calls = []

    def traverse(node: Node):
        if node.type == "method_invocation":
            name_node = node.child_by_field_name("name")
            if name_node:
                start_line, start_col = name_node.start_point  # (line, column)
                calls.append({
                    "type": "method",
                    "name": code[name_node.start_byte:name_node.end_byte],
                    "line": start_line - 1 + start_lineno - 1,
                    "character": start_col
                })
        elif node.type == "object_creation_expression":
            type_node = node.child_by_field_name("type")
            if type_node:
                calls.append({
                    "type": "constructor",
                    "name": code[type_node.start_byte:type_node.end_byte],
                    "line": type_node.start_point[0] - 1 + start_lineno - 1,
                    "character": type_node.start_point[1]
                })

        for child in node.children:
            traverse(child)

    traverse(root_node)
    return calls
