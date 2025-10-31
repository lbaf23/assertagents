from typing import Union, List, Dict
import os
from . import create_dirs, delete_dirs
from .jsonl_utils import append_jsonl


class JsonlLog:
    def __init__(self, log_dir: str):
        self.log_dir = log_dir
        delete_dirs(log_dir)
        create_dirs(log_dir)

    def print_log(self, file_id: str, data: Union[Dict, List]):
        log_file = os.path.join(self.log_dir, f'{file_id}.jsonl')
        append_jsonl(log_file, data)
