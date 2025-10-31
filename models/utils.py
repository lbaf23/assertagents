from transformers import StoppingCriteria, StoppingCriteriaList
import torch
from typing import List


class TokenStoppingCriteria(StoppingCriteria):
    def __init__(self, stop_ids: List[List]):
        self.stop_ids = stop_ids

    def endswith(self, input_id):
        for ids in self.stop_ids:
            l = len(ids)
            if len(input_id) >= l and list(input_id[-l:].detach().cpu().numpy()) == ids:
                return True
        return False

    def __call__(self, input_ids: torch.LongTensor, score: torch.FloatTensor, **kwargs):
        if self.endswith(input_ids[0]):
            return True
        return False


def get_stop_criteria(tokenizer, stop_strs: List[str]):
    return StoppingCriteriaList([TokenStoppingCriteria([tokenizer(i, add_special_tokens=False).input_ids for i in stop_strs])])
