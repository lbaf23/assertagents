import shutil
import os
from typing import Tuple

from .code_file_utils import replace_code_lines
from ..file_utils import read_file, write_file


def backup_file(file_path: str, code: str, start_lineno: int, end_lineno: int) -> Tuple:
    backup_file_path = file_path[ : file_path.rindex('.')] + '.backup'
    shutil.copy(file_path, backup_file_path)
    original_file_content = read_file(file_path)
    masked_file_content = replace_code_lines(
        file_code=original_file_content,
        code=code,
        start_lineno=start_lineno,
        end_lineno=end_lineno,
    )
    write_file(file_path, masked_file_content)
    return original_file_content, masked_file_content


def recover_file(file_path: str) -> bool:
    backup_file_path = file_path[ : file_path.rindex('.')] + '.backup'
    if not os.path.exists(backup_file_path):
        return False
    shutil.copy(backup_file_path, file_path)
    os.remove(backup_file_path)
    return True
