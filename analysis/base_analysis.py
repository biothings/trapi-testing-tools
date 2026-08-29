from abc import ABC, abstractmethod
from typing import ClassVar

import typer
from translator_tom.v1_6 import Response

AnalysisOutput = dict | list
"""A JSON-serializable analysis result."""


class Analysis(ABC):
    """A static class for a single argument-free analysis with consistent I/O.

    Writing a docstring on implemented classes means the docstring will be used
    when printing the analysis, minus the final period.
    """

    @staticmethod
    @abstractmethod
    def analyze(response: Response) -> AnalysisOutput:
        """Transform a TRAPI response into some JSON-serializable output."""


class ParametrizedAnalysis(ABC):
    """An analysis that takes arguments via its own Typer layer.

    Implementations must set `app` to a `typer.Typer` with exactly one command.
    The command receives the parsed `Response` as the Click context object
    (read it via `ctx.obj`), resolves any missing arguments interactively
    (prompting the user using the response), and returns the JSON-serializable
    output. Arguments may also be supplied on the CLI after a `--` separator.

    Writing a docstring on implemented classes means the docstring will be used
    when printing the analysis, minus the final period.
    """

    app: ClassVar[typer.Typer]
    """The Typer layer declaring this analysis' arguments/options."""

    @classmethod
    def run(cls, response: Response, args: list[str]) -> AnalysisOutput | None:
        """Invoke the Typer layer with forwarded args, injecting the response.

        Returns the command's output, or None if nothing was produced (e.g. when
        the forwarded args were `--help`).
        """
        result = cls.app(
            args=args,
            obj=response,
            prog_name=f"tt analyze {cls.__name__}",
            standalone_mode=False,
        )
        return result if isinstance(result, dict | list) else None


AnalysisClass = type[Analysis] | type[ParametrizedAnalysis]
"""Either kind of analysis class (used for discovery/selection)."""
