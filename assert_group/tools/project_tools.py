from typing import Annotated, Tuple


class ProjectTools:
    def start_debugger(self):
        raise NotImplementedError

    def close_debugger(self):
        raise NotImplementedError


    async def static_check_assert(
            self,
            assert_code: Annotated[str, "The generated assert statement."]
    ) -> Tuple:
        raise NotImplementedError

    async def run_test(
            self,
            assert_code: Annotated[str, "The generated assert statement."]
    ) -> Tuple:
        raise NotImplementedError

    ### Tools Ended ###
    def close(self):
        raise NotImplementedError

