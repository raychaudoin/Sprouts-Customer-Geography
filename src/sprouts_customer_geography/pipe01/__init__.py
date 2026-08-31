"""PIPE-01 target-blind freeze package implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .pipeline import PretargetPipeline
    from .run import ProtectedRun

__all__ = ["PretargetPipeline", "ProtectedRun"]


def __getattr__(name: str) -> Any:
    """Preserve public imports without executing analytical modules on package import."""

    if name == "PretargetPipeline":
        from .pipeline import PretargetPipeline

        return PretargetPipeline
    if name == "ProtectedRun":
        from .run import ProtectedRun

        return ProtectedRun
    raise AttributeError(name)
