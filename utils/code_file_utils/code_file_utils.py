import os

from ..file_utils import read_file, write_file
from typing import List, Tuple


def read_code_content(file_path: str, start_lineno: int, end_lineno: int) -> str:
    content = read_file(file_path)
    lines = content.splitlines()
    code_content = lines[start_lineno - 1 : end_lineno]
    code_content = '\n'.join(code_content)
    return code_content


def replace_code_lines(file_code: str, code: str, start_lineno: int, end_lineno: int) -> str:
    file_code_lines = file_code.splitlines()
    code_lines = code.splitlines()
    return '\n'.join(file_code_lines[:start_lineno - 1] + code_lines + file_code_lines[end_lineno:])


import re
def clean_content(content: str):
    return re.sub(r'[\u2028\u2029]', '', content)


def replace_code_content(file_path: str, code_content: str, start_lineno: int, end_lineno: int) -> Tuple[int, int, str]:
    """
    All lineno starts from 1

    For example:

    [1]
    ...
    [5] def func():
    [6]     a = 1
    [7]     b = 2
    [8]
    ...

    start_lineno = 5
    end_lineno = 7

    Args:
        file_path:
        code_content:
        start_lineno:
        end_lineno:

    Returns:
        new_start_lineno, new_end_lineno, replaced_code
    """
    code_content_lines = code_content.splitlines()
    lns = len(code_content_lines)
    new_start_lineno = start_lineno
    new_end_lineno = start_lineno + lns - 1

    content = read_file(file_path)
    lines = content.splitlines()
    replaced_code = '\n'.join(lines[start_lineno - 1 : end_lineno])
    new_lines = lines[ : start_lineno - 1] + code_content_lines + lines[end_lineno : ]
    write_file(file_path, '\n'.join(new_lines))
    return new_start_lineno, new_end_lineno, replaced_code


class ReplaceFileCache:
    def __init__(self):
        self.replace_cache = []
        self.idx = 0

    def replace_code_content(
            self,
            file_path: str,
            code_content: str,
            start_lineno: int,
            end_lineno: int,
    ) -> Tuple:
        new_start_lineno, new_end_lineno, replaced_code = replace_code_content(file_path, code_content, start_lineno, end_lineno)
        self.replace_cache.append({
            'idx': self.idx,
            'file_path': file_path,
            'new_start_lineno': new_start_lineno,
            'new_end_lineno': new_end_lineno,
            'replaced_code': replaced_code,
        })
        self.idx += 1
        return new_start_lineno, new_end_lineno, replaced_code

    def recover_all(self) -> bool:
        while len(self.replace_cache) > 0:
            self.recover()
        self.idx = 0
        return True

    def recover(self) -> Tuple:
        repl = self.replace_cache.pop()
        new_start_lineno, new_end_lineno, replaced_code = replace_code_content(
            file_path=repl['file_path'],
            code_content=repl['replaced_code'],
            start_lineno=repl['new_start_lineno'],
            end_lineno=repl['new_end_lineno'],
        )
        self.idx -= 1
        return new_start_lineno, new_end_lineno, replaced_code


def get_relative_path(repo_path: str, file_path: str) -> str:
    rel_path = os.path.relpath(file_path, repo_path)
    return str(rel_path)


from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from typing import List, Dict
from utils import read_file


def single_file_rag(
        functions: List[Dict],
        query_func: str,
        top_k: int = 10,
) -> List[int]:
    """

    Args:
        functions:
            {
                "body": "..."
            }
        query_func:
        top_k:

    Returns:

    """
    functions_body = [f['body'] for f in functions]
    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform(functions_body + [query_func])
    sim = cosine_similarity(tfidf_matrix[-1:], tfidf_matrix[:-1])[0]
    top_indices = sim.argsort()[::-1][:top_k]
    return top_indices
