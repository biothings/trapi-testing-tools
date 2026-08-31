from typing import override

import httpx
from translator_tom.v2_0 import Response

from analysis.base_analysis import Analysis, AnalysisOutput
from tests.battery import standard_battery_2_0


class StandardBattery(Analysis):
    """standard test battery results."""

    @override
    @staticmethod
    def analyze(response: Response) -> AnalysisOutput:
        # rebuild an httpx.Response from the model (status assumed 200) for the tests
        http_response = httpx.Response(200, content=response.to_json(as_str=False))
        results = list[dict]()
        for test in standard_battery_2_0():
            name = test.__doc__.removesuffix(".") if test.__doc__ else test.__name__
            try:
                result = test.test(http_response)
                results.append(
                    {"test": name, "passed": result.passed, "info": result.info}
                )
            except Exception as error:
                results.append(
                    {"test": name, "passed": False, "info": f"error: {error!r}"}
                )
        return results
