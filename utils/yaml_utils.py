import yaml
from typing import Any


def read_yaml(file_path: str) -> Any:
    with open(file_path, 'r') as f:
        data = yaml.safe_load(f)
    return data


