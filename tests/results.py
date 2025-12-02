import httpx


def result_count(response: httpx.Response) -> str | None:
    body = response.json()
    no_results = len(body["message"]["results"]) == 0
    if no_results:
        return "0 results"


def no_results(response: httpx.Response) -> str | None:
    body = response.json()
    no_results = len(body["message"]["results"]) == 0
    if not no_results:
        return ">0 results"
