from typing import List, Dict, Any


class ModelBase:
    name: str
    description: str

    def generate_response(
            self,
            messages_list: List[List[Dict]],
            sampling_args: Dict[str, Any],
            generation_args: Dict[str, Any] = None,
    ) -> Dict[str, List]:
        raise NotImplementedError

    def generate_chat(
            self,
            messages_list: List[List[Dict]],
            sampling_args: Dict[str, Any],
            generation_args: Dict[str, Any] = None,
    ) -> Dict[str, List]:
        raise NotImplementedError

    def generate_completion(
            self,
            prompt_list: List[str],
            sampling_args: Dict[str, Any],
            generation_args: Dict[str, Any] = None,
    ) -> Dict[str, List]:
        raise NotImplementedError

    def generate_embedding(
            self,
            prompt_list: List[str],
            generation_args: Dict[str, Any] = None,
    ) -> Dict:
        raise NotImplementedError
