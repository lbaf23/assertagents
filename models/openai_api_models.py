from typing import List, Dict, Any, Union, Tuple
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor
from tenacity import retry, wait_random_exponential, stop_after_attempt
from tqdm import tqdm
from itertools import repeat
from datetime import datetime
from .models import ModelBase


def extract_think_format(output: str, think_start: str = '<think>', think_end: str = '</think>') -> Tuple:
    think_content = ''
    output_content = output
    if output.__contains__(think_start) and output.__contains__(think_end):
        think_content = output[output.index(think_start) + len(think_start) : output.index(think_end)]
        output_content = output[output.index(think_end) + len(think_end) : ]
    return think_content, output_content


class OpenAIAPIModels(ModelBase):
    def __init__(
            self,
            name: str,
            model_path: str = 'gpt-4o',
            model_args: Dict[str, Any] = None,
            **args
    ) -> None:
        if model_args is None:
            model_args = {}

        self.name = name
        self.model_path = model_path
        self.max_workers = model_args.pop('max_workers', 32)

        if model_args.__contains__('base_url') and model_args.__contains__('api_key'):
            base_url_list = model_args.pop('base_url')
            api_key_list = model_args.pop('api_key')
            if type(base_url_list) is str:
                base_url_list = [base_url_list]
            if type(api_key_list) is str:
                api_key_list = [api_key_list]

            assert len(base_url_list) == len(api_key_list)
            self.client_list = []
            for i in range(len(base_url_list)):
                client = OpenAI(
                    base_url=base_url_list[i],
                    api_key=api_key_list[i],
                    **model_args
                )
                self.client_list.append(client)
        else:
            self.client_list = [
                OpenAI(**model_args)
            ]

        assert len(self.client_list) > 0

        print(f'OpenAI API: {len(self.client_list)} endpoints found.')

    @retry(wait=wait_random_exponential(min=1, max=10), stop=stop_after_attempt(5))
    def _call_chat_api(
            self,
            index: int,
            messages: List,
            sampling_args: Dict[str, Any],
            think_format: bool,
    ) -> Dict:
        extra_args = {}
        if sampling_args.__contains__('top_k'):
            extra_args['top_k'] = sampling_args.pop('top_k')
        if sampling_args.__contains__('min_p'):
            extra_args['min_p'] = sampling_args.pop('min_p')
        if sampling_args.__contains__('repetition_penalty'):
            extra_args['repetition_penalty'] = sampling_args.pop('repetition_penalty')

        # For VLLM prefix cache key
        if sampling_args.__contains__('cache_salt'):
            extra_args['cache_salt'] = sampling_args.pop('cache_salt')

        client = self.client_list[index % len(self.client_list)]

        start_t = datetime.now()
        res = client.chat.completions.create(
            model=self.model_path,
            messages=messages,
            **sampling_args,
            extra_body=extra_args,
        )
        end_t = datetime.now()

        think_content = ''
        output_content = ''
        if sampling_args.__contains__('n') and sampling_args['n'] > 1:
            output = [c.message.content for c in res.choices]
        else:
            output = res.choices[0].message.content
            if think_format:
                think_content, output_content = extract_think_format(output)

        tool_calls = []
        if res.choices[0].message.tool_calls is not None:
            tool_calls = [tc.to_dict() for tc in res.choices[0].message.tool_calls]

        # usage: {'completion_tokens': 1062, 'prompt_tokens': 22, 'total_tokens': 1084, 'completion_tokens_details': {'audio_tokens': 0, 'reasoning_tokens': 0}, 'prompt_tokens_details': {'audio_tokens': 0, 'cached_tokens': 0}}
        return {
            'think_content': think_content,
            'output_content': output_content,
            'output': output,
            'tool_calls': tool_calls,
            'usage': res.usage.to_dict(),
            'seconds': (end_t - start_t).total_seconds(),
        }

    def _batch_call_chat_api(
            self,
            messages_list: List[List],
            sampling_args: Dict[str, Any],
            generation_args: Dict[str, Any],
    ) -> Dict[str, Any]:
        think_content_list = []
        output_content_list = []

        output_list = []
        tool_calls_list = []
        usage_list = []
        seconds_list = []

        index_list = [i for i in range(len(messages_list))]

        with_tqdm = generation_args.get('with_tqdm', False)
        think_format = generation_args.pop('think_format', False)

        if with_tqdm:
            td = tqdm(total=len(messages_list), desc='API Chat')

        with ThreadPoolExecutor(max_workers=self.max_workers * len(self.client_list)) as executor:
            for res in executor.map(self._call_chat_api, index_list, messages_list, repeat(sampling_args), repeat(think_format)):
                think_content_list.append(res['think_content'])
                output_content_list.append(res['output_content'])

                output_list.append(res['output'])
                tool_calls_list.append(res['tool_calls'])
                usage_list.append(res['usage'])
                seconds_list.append(res['seconds'])

                if with_tqdm:
                    td.update(1)

        if with_tqdm:
            td.close()

        return {
            'think_content_list': think_content_list,
            'output_content_list': output_content_list,
            'output_list': output_list,
            'tool_calls_list': tool_calls_list,
            'usage_list': usage_list,
            'seconds_list': seconds_list
        }

    @retry(wait=wait_random_exponential(min=1, max=10), stop=stop_after_attempt(5))
    def _call_response_api(
            self,
            index: int,
            messages: List,
            sampling_args: Dict[str, Any],
    ) -> Dict:
        extra_args = {}
        if sampling_args.__contains__('top_k'):
            extra_args['top_k'] = sampling_args.pop('top_k')
        if sampling_args.__contains__('min_p'):
            extra_args['min_p'] = sampling_args.pop('min_p')
        if sampling_args.__contains__('repetition_penalty'):
            extra_args['repetition_penalty'] = sampling_args.pop('repetition_penalty')

        # For VLLM prefix cache key
        if sampling_args.__contains__('cache_salt'):
            extra_args['cache_salt'] = sampling_args.pop('cache_salt')

        client = self.client_list[index % len(self.client_list)]

        start_t = datetime.now()
        res = client.responses.create(
            model=self.model_path,
            input=messages,
            **sampling_args,
            extra_body=extra_args,
        )
        end_t = datetime.now()

        if sampling_args.__contains__('n') and sampling_args['n'] > 1:
            output = [c.message.content for c in res.choices]
        else:
            output = res.choices[0].message.content

        # usage: {'completion_tokens': 1062, 'prompt_tokens': 22, 'total_tokens': 1084, 'completion_tokens_details': {'audio_tokens': 0, 'reasoning_tokens': 0}, 'prompt_tokens_details': {'audio_tokens': 0, 'cached_tokens': 0}}
        return {
            'output': output,
            'usage': res.usage.to_dict(),
            'seconds': (end_t - start_t).total_seconds(),
        }

    def _batch_call_response_api(
            self,
            messages_list: List[List],
            sampling_args: Dict[str, Any],
            generation_args: Dict[str, Any],
    ) -> Dict[str, Any]:
        output_list = []
        usage_list = []
        seconds_list = []

        index_list = [i for i in range(len(messages_list))]

        with_tqdm = generation_args.get('with_tqdm', False)

        if with_tqdm:
            td = tqdm(total=len(messages_list), desc='API Chat')

        with ThreadPoolExecutor(max_workers=self.max_workers * len(self.client_list)) as executor:
            for res in executor.map(self._call_response_api, index_list, messages_list, repeat(sampling_args)):
                output_list.append(res['output'])
                usage_list.append(res['usage'])
                seconds_list.append(res['seconds'])

                if with_tqdm:
                    td.update(1)

        if with_tqdm:
            td.close()

        return {
            'output_list': output_list,
            'usage_list': usage_list,
            'seconds_list': seconds_list
        }

    @retry(wait=wait_random_exponential(min=1, max=10), stop=stop_after_attempt(5))
    def _call_completion_api(
            self,
            index: int,
            prompt: str,
            sampling_args: Dict,
    ) -> Dict:
        extra_args = {}
        if sampling_args.__contains__('top_k'):
            extra_args['top_k'] = sampling_args.pop('top_k')
        if sampling_args.__contains__('min_p'):
            extra_args['min_p'] = sampling_args.pop('min_p')
        if sampling_args.__contains__('repetition_penalty'):
            extra_args['repetition_penalty'] = sampling_args.pop('repetition_penalty')

        # For VLLM prefix cache key
        if sampling_args.__contains__('cache_salt'):
            extra_args['cache_salt'] = sampling_args.pop('cache_salt')

        client = self.client_list[index % len(self.client_list)]

        start_t = datetime.now()
        res = client.completions.create(
            model=self.model_path,
            prompt=prompt,
            **sampling_args,
            extra_body=extra_args
        )
        end_t = datetime.now()
        return {
            'output': res.choices[0].text,
            'usage': res.usage.to_dict(),
            'seconds': (end_t - start_t).total_seconds(),
        }

    def _batch_call_completion_api(
            self,
            prompt_list: List[List],
            sampling_args: Union[List[Dict], Dict],
            generation_args: Dict[str, Any],
    ) -> Dict[str, Any]:
        output_list = []
        usage_list = []
        seconds_list = []

        index_list = [i for i in range(len(prompt_list))]

        with_tqdm = generation_args.get('with_tqdm', False)

        if with_tqdm:
            td = tqdm(total=len(prompt_list), desc='API Completion')
        with ThreadPoolExecutor(max_workers=self.max_workers * len(self.client_list)) as executor:
            for res in executor.map(
                    self._call_completion_api,
                    index_list,
                    prompt_list,
                    repeat(sampling_args) if type(sampling_args) is dict else sampling_args
            ):
                output_list.append(res['output'])
                usage_list.append(res['usage'])
                seconds_list.append(res['seconds'])

                if with_tqdm:
                    td.update(1)
        if with_tqdm:
            td.close()

        return {
            'output_list': output_list,
            'usage_list': usage_list,
            'seconds_list': seconds_list
        }

    @retry(wait=wait_random_exponential(min=1, max=10), stop=stop_after_attempt(5))
    def _call_embedding_api(
            self,
            index: int,
            prompt: str,
            generation_args: Dict[str, Any],
    ) -> Dict:
        client = self.client_list[index % len(self.client_list)]

        start_t = datetime.now()
        res = client.embeddings.create(
            model=self.model_path,
            input=prompt,
            **generation_args
        )
        end_t = datetime.now()
        return {
            'output': res.data[0].embedding,
            'usage': res.usage.to_dict(),
            'seconds': (end_t - start_t).total_seconds(),
        }

    def _batch_call_embedding_api(
            self,
            prompt_list: List[str],
            generation_args: Dict[str, Any],
    ) -> Dict[str, Any]:
        output_list = []
        usage_list = []
        seconds_list = []

        index_list = [i for i in range(len(prompt_list))]
        with_tqdm = generation_args.get('with_tqdm', False)

        if with_tqdm:
            td = tqdm(total=len(prompt_list), desc='API embedding')
        with ThreadPoolExecutor(max_workers=self.max_workers * len(self.client_list)) as executor:
            for res in executor.map(self._call_embedding_api, index_list, prompt_list, repeat(generation_args)):
                output_list.append(res['output'])
                usage_list.append(res['usage'])
                seconds_list.append(res['seconds'])

                if with_tqdm:
                    td.update(1)
        if with_tqdm:
            td.close()

        return {
            'output_list': output_list,
            'usage_list': usage_list,
            'seconds_list': seconds_list
        }

    def generate_completion(
            self,
            prompt_list: List[str],
            sampling_args: Union[List[Dict], Dict],
            generation_args: Dict[str, Any] = None
    ) -> Dict[str, List]:
        if type(prompt_list) != list:
            prompt_list = [prompt_list]
        if generation_args is None:
            generation_args = {}

        return self._batch_call_completion_api(
            prompt_list=prompt_list,
            sampling_args=sampling_args,
            generation_args=generation_args
        )

    def generate_chat(
            self,
            messages_list: List[List[Dict]],
            sampling_args: Dict[str, Any],
            generation_args: Dict[str, Any] = None
    ) -> Dict[str, List]:
        if type(messages_list[0]) != list:
            messages_list = [messages_list]

        if generation_args is None:
            generation_args = {}

        return self._batch_call_chat_api(
            messages_list=messages_list,
            sampling_args=sampling_args,
            generation_args=generation_args
        )

    def generate_response(
            self,
            messages_list: List[List[Dict]],
            sampling_args: Dict[str, Any],
            generation_args: Dict[str, Any] = None
    ) -> Dict[str, List]:
        if type(messages_list[0]) != list:
            messages_list = [messages_list]

        if generation_args is None:
            generation_args = {}

        return self._batch_call_response_api(
            messages_list=messages_list,
            sampling_args=sampling_args,
            generation_args=generation_args
        )

    def generate_embedding(
            self,
            prompt_list: List[str],
            generation_args: Dict[str, Any] = None
    ) -> Dict:
        if type(prompt_list) != list:
            prompt_list = [prompt_list]

        if generation_args is None:
            generation_args = {}

        return self._batch_call_embedding_api(
            prompt_list=prompt_list,
            generation_args=generation_args
        )
