from collections import Counter
from typing import override

from translator_tom import CURIE
from translator_tom.v2_0 import Response

from analysis.base_analysis import Analysis, AnalysisOutput


class NodeFrequency(Analysis):
    """node frequency across kg edges."""

    @override
    @staticmethod
    def analyze(response: Response) -> AnalysisOutput:
        kg = response.message.knowledge_graph
        counts: Counter[CURIE] = Counter()
        if kg is not None:
            for edge in kg.edges.values():
                counts[edge.subject] += 1
                counts[edge.object] += 1
        # most_common() orders by descending frequency; dict preserves that order.
        return dict(counts.most_common())
