from vllm import LLM, SamplingParams
from typing import List, Dict, Any, Union
import torch
import os
import json
from vllm.lora.request import LoRARequest
from .models import ModelBase


class VllmModels(ModelBase):
    def __init__(
            self,
            name: str,
            model_path: str,
            model_args: Dict[str, Any] = None,
            model_dtype: str = 'bf16',
            **args
    ):
        if model_args is None:
            model_args = {}

        gpus = torch.cuda.device_count()
        self.name = name
        # 'auto', 'half', 'float16', 'bfloat16', 'float', 'float32'

        dtype = 'bfloat16'
        if model_dtype == 'bf16':
            dtype = 'bfloat16'
        elif model_dtype == 'fp16':
            dtype = 'float16'
        elif model_dtype == 'fp32':
            dtype = 'float32'
        elif model_dtype == 'int4':
            model_args['quantization'] = 'bitsandbytes'
        else:
            raise NotImplementedError

        # Check whether lora path
        if os.path.exists(os.path.join(model_path, 'adapter_config.json')):
            self.enable_lora = True
            self.lora_path = model_path

            adapter_config = json.load(open(os.path.join(model_path, 'adapter_config.json')))
            base_model_path = adapter_config['base_model_name_or_path']

            model_args['enable_lora'] = True
            model_args['max_lora_rank'] = adapter_config['r']
            # model_args['qlora_adapter_name_or_path'] = model_path

            model_path = base_model_path
        else:
            self.enable_lora = False

        self.model_path = model_path
        self.model = LLM(
            model=model_path,
            # max_model_len=max_model_len,
            dtype=dtype,
            # tensor_parallel_size=gpus,
            data_parallel_size=gpus,
            **model_args
        )

    def generate_chat(
            self,
            messages_list: List[List],
            sampling_args: Dict[str, Any],
            generation_args: Dict[str, Any] = None,
    ) -> Dict:
        """
        Args:
            sampling_args (Dict[str, Any]):
                n (int):
                top_p (float): 
                top_k (int):
                min_p (float):
                temperature (float): 
                max_tokens (int): 
                stop (List[str]):
            generation_args (Dict[str, Any]):

        Returns:
            (Dict[str, List]):
                outputs (List[str]):
                input_tokens (List[int]):
                output_tokens (List[int])
        """
        assert len(messages_list) > 0
        if generation_args is None:
            generation_args = {}

        if type(messages_list[0]) != list:
            messages_list = [messages_list]

        params = SamplingParams(**sampling_args)

        if self.enable_lora:
            generation_args['lora_request'] = LoRARequest('lora_adapter', 1, self.lora_path)

        ret = self.model.chat(
            messages=messages_list,
            sampling_params=params,
            **generation_args
        )

        if sampling_args.__contains__('n') and sampling_args['n'] > 1:
            outputs = [[o.text for o in r.outputs] for r in ret]
            input_tokens = [len(r.prompt_token_ids) for r in ret]
            output_tokens = [[len(o.token_ids) for o in r.outputs] for r in ret]
        else:
            outputs = [r.outputs[0].text for r in ret]
            input_tokens = [len(r.prompt_token_ids) for r in ret]
            output_tokens = [len(r.outputs[0].token_ids) for r in ret]

        return {
            'outputs': outputs,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
        }

    def generate_completion(
            self,
            prompt_list: List[str],
            sampling_args: Dict[str, Any],
            generation_args: Dict[str, Any] = None,
    ) -> Dict:
        assert len(prompt_list) > 0
        if generation_args is None:
            generation_args = {}

        if type(prompt_list) != list:
            prompt_list = [prompt_list]

        params = SamplingParams(**sampling_args)

        if self.enable_lora:
            generation_args['lora_request'] = LoRARequest('lora_adapter', 1, self.lora_path)

        ret = self.model.generate(
            prompts=prompt_list,
            sampling_params=params,
            **generation_args
        )

        outputs = [r.outputs[0].text for r in ret]
        input_tokens = [len(r.prompt_token_ids) for r in ret]
        output_tokens = [len(r.outputs[0].token_ids) for r in ret]

        return {
            'outputs': outputs,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
        }

    def generate_embedding(
            self,
            prompt_list: List[str],
            generation_args: Dict = None,
    ) -> Dict[str, Any]:
        if generation_args is None:
            generation_args = {}

        ret = self.model.embed(
            prompt_list,
            **generation_args,
        )

        outputs = [r.outputs.embedding for r in ret]
        input_tokens = [len(r.prompt_token_ids) for r in ret]
        output_tokens = [len(o) for o in outputs]

        return {
            'outputs': outputs,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
        }
