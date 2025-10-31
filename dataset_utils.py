from typing import List, Dict
from utils import read_jsonl



def read_dataset(dataset_name: str) -> List[Dict]:
    if dataset_name == 'teco500':
        return read_jsonl('data/teco500.jsonl')

    elif dataset_name == 'py500':
        return read_jsonl(f'data/py500.jsonl')

    else:
        raise NotImplementedError(f'Dataset {dataset_name} not implemented')
