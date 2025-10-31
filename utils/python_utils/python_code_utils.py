from typing import Optional, Tuple
from tree_sitter import Language, Parser
import tree_sitter_python


def get_python_method_name_pos(method_code: str, start_lineno: int) -> Optional[Tuple]:
    parser = Parser(language=Language(tree_sitter_python.language()))
    code_bytes = bytes(method_code, 'utf-8')
    tree = parser.parse(code_bytes)
    def find_method_pos(node):
        for node in node.children:
            if node.type == 'decorated_definition':
                return find_method_pos(node)
            elif node.type in {'function_definition', 'class_definition'}:
                for child in node.children:
                    if child.type == 'identifier':
                        line = child.start_point[0]
                        character = child.start_point[1]
                        return (line + start_lineno - 1, character)
    return find_method_pos(tree.root_node)
