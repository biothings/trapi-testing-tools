from typing import override

import httpx

from tests import trapi
from tests.base_test import Test, TestResult
from tests.params import Comparison, CountTest, bind, count_result


class NodeCount(CountTest):
    """metakg has nodes."""

    subject = "metakg nodes"

    @override
    @staticmethod
    def test(
        response: httpx.Response, *, expected: int = 0, comparison: Comparison = "gt"
    ) -> TestResult:
        model = trapi.parse_metakg_or_fail(response)
        if isinstance(model, TestResult):
            return model
        return count_result(NodeCount.subject, len(model.nodes), expected, comparison)


class EdgeCount(CountTest):
    """metakg has edges."""

    subject = "metakg edges"

    @override
    @staticmethod
    def test(
        response: httpx.Response, *, expected: int = 0, comparison: Comparison = "gt"
    ) -> TestResult:
        model = trapi.parse_metakg_or_fail(response)
        if isinstance(model, TestResult):
            return model
        return count_result(EdgeCount.subject, len(model.edges), expected, comparison)


class MetaEdgesAdvertise(Test):
    """every metakg edge advertises the given provenance fields."""

    @override
    @staticmethod
    def test(
        response: httpx.Response,
        *,
        fields: tuple[str, ...] = ("knowledge_levels", "agent_types", "sources"),
    ) -> TestResult:
        model = trapi.parse_metakg_or_fail(response)
        if isinstance(model, TestResult):
            return model

        # 2.0 adds these per-MetaEdge provenance fields; each must be present and non-empty.
        total = len(model.edges)
        summary: list[str] = []
        for field in fields:
            missing = [e for e in model.edges if not getattr(e, f"{field}_list")]
            if missing:
                examples = ", ".join(
                    f"{e.subject} -{e.predicate}-> {e.object}" for e in missing[:3]
                )
                summary.append(f"{field}: {len(missing)}/{total} edges lack it ({examples})")

        return TestResult(len(summary) == 0, summary or None)

    @classmethod
    def expect(cls, *fields: str) -> type[Test]:
        """A variant asserting every metakg edge advertises each of ``fields``."""
        return bind(
            cls, name=f"metakg edges advertise {', '.join(fields)}", fields=fields
        )
