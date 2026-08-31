from rich.console import Console

console = Console(stderr=True)
"""The shared runner console (stderr); print through it to inherit the runner's render hooks.

A leaf module (no intra-package imports) so anything — including a query file's `FollowUp` —
can import it without a cycle.
"""
