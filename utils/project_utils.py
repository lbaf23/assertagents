from .file_utils import read_file


def read_code_content(file_path: str, start_lineno: int, end_lineno: int) -> str:
    content = read_file(file_path)
    lines = content.splitlines()
    code_content = lines[start_lineno - 1 : end_lineno]
    code_content = '\n'.join(code_content)
    return code_content