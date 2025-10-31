from typing import List, Dict, Any
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
import torch
from .utils import get_stop_criteria
from .models import ModelBase


class QwenModels(ModelBase):
    def __init__(
            self,
            name: str = 'qwen',
            model_path: str = 'Qwen/Qwen2.5-Coder-7B-Instruct',
            max_length: int = 8192,
            dtype: str = 'bf16',
            **args
    ):
        model_args = {}
        if dtype == 'bf16':
            model_args['torch_dtype'] = torch.bfloat16
        elif dtype == 'fp16':
            model_args['torch_dtype'] = torch.float16
        elif dtype == 'int8':
            model_args['quantization_config'] = BitsAndBytesConfig(load_in_8bit=True)
        elif dtype == 'int4':
            model_args['quantization_config'] = BitsAndBytesConfig(load_in_4bit=True)

        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            device_map='auto',
            **model_args
        )
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)

        self.max_length = max_length
        self.name = name

    def generate(
            self,
            prompt: str,
            max_tokens: int = 1024,
            stop_strs: List[str] = [],
            temperature: float = 0.8
    ) -> Dict[str, Any]:
        inputs = self.tokenizer(prompt, return_tensors='pt').to(self.model.device)
        input_tokens = len(inputs.input_ids[0])
        outputs = self.model.generate(
            **inputs,
            do_sample=True,
            max_new_tokens=min(max_tokens, self.max_length - input_tokens),
            temperature=temperature,
            stopping_criteria=get_stop_criteria(self.tokenizer, stop_strs),
        )
        output = outputs[0][input_tokens : ]
        output_tokens = len(output)
        output = self.tokenizer.decode(output, skip_special_tokens=True)
        return {
            'output': output,
            'tokens_count': {
                'input_tokens': input_tokens,
                'output_tokens': output_tokens
            }
        }

    def generate_chat(
            self,
            messages: List[Dict],
            sampling_args: Dict[str, Any] = {},
            stop_strs: List[str] = [],
    ) -> Dict[str, Dict]:
        inputs = self.tokenizer.apply_chat_template(messages, return_tensors='pt', return_dict=True, add_generation_prompt=True).to(self.model.device)
        input_tokens = len(inputs.input_ids[0])

        generation_args = {**sampling_args}
        generation_args['max_new_tokens'] = min(generation_args['max_tokens'], self.max_length - input_tokens),
        generation_args.pop('max_tokens')
        
        outputs = self.model.generate(
            **inputs,
            do_sample=True,
            **generation_args,
            stopping_criteria=get_stop_criteria(self.tokenizer, stop_strs),
        )
        output = outputs[0][input_tokens : ]
        output_tokens = len(output)
        output = self.tokenizer.decode(output, skip_special_tokens=True)
        return {
            'output': output,
            'tokens': {
                'input_tokens': input_tokens,
                'output_tokens': output_tokens
            }
        }
