import httpx


def status(*status_code: int):
    def status_checker(response: httpx.Response) -> str | None:
        if response.status_code not in [*status_code]:
            acceptable_codes = ", ".join([str(code) for code in [*status_code]])
            return f"Response status {response.status_code} not one of acceptable codes ({acceptable_codes})"

    return status_checker
