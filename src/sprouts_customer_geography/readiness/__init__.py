"""Durable protected-local recovery and schema-bound readiness publication."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .store import ProjectState, ResolvedAsset

__all__ = [
    "ProjectState",
    "ResolvedAsset",
    "bootstrap_from_app01_settings",
    "default_state_root",
    "initialize_project_state",
    "migrate_model15_parser_incident",
    "recover_project_state",
]


def __getattr__(name: str) -> Any:
    """Load protected-state operations only when a caller explicitly requests one."""

    if name in __all__:
        from . import store

        return getattr(store, name)
    raise AttributeError(name)
