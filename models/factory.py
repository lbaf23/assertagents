from typing import Dict, Any
from .models import ModelBase
from .openai_api_models import OpenAIAPIModels
from .vllm_models import VllmModels


def model_factory(
        model_type: str = 'vllm',
        model_path: str = 'Qwen/Qwen2.5-Coder-7B-Instruct',
        model_args: Dict[str, Any] = None,
        name: str = '',
        **args
) -> ModelBase:
    if name == '':
        name = model_path

    if model_type == 'vllm':
        model = VllmModels(name, model_path, model_args, **args)
    elif model_type == 'openai_api':
        model = OpenAIAPIModels(name, model_path, model_args, **args)
    else:
        raise NotImplementedError

    print(f'{model_type}: {model_path} loaded.', flush=True)
    return model
