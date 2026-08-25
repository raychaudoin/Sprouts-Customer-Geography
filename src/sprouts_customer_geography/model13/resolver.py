"""Exact protected registry resolution for MODEL-13."""

from __future__ import annotations

import json
from pathlib import Path, PurePath
from typing import Any, Mapping

from sprouts_customer_geography.pipe01.canonical import content_digest
from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.pipe02.resolver import ResolvedHandle, _is_within


REGISTRY_ID = "MODEL13_PROTECTED_HANDLE_REGISTRY_V1"
REGISTRY_VERSION = "1.0.0"
REQUEST_FIELDS = frozenset(
    {
        "model11_registry_handle",
        "model12_registry_handle",
        "pipe05_registry_handle",
        "pipe05_ready_run_handle",
        "model13_output_root_handle",
    }
)
DIRECTORY_KINDS = frozenset({"pipe05_ready_run", "model13_output_root"})


class ProtectedHandleResolver:
    """Resolve only registry-declared predecessor registries, run, and output root."""

    def __init__(self, registry: Mapping[str, Any], registry_path: Path, repository_root: Path):
        self.repository_root = repository_root.resolve()
        self.registry_path = registry_path.resolve()
        require(not _is_within(self.registry_path, self.repository_root), "PROTECTED_REGISTRY_INSIDE_REPOSITORY", "MODEL-13 registry must remain outside Git")
        require(registry.get("registry_id") == REGISTRY_ID and registry.get("version") == REGISTRY_VERSION, "PROTECTED_REGISTRY_IDENTITY_MISMATCH", "MODEL-13 registry identity or version differs")
        roots = registry.get("protected_roots")
        resources = registry.get("resources")
        request = registry.get("execution_request")
        require(isinstance(roots, Mapping) and roots, "PROTECTED_ROOTS_UNRESOLVED", "MODEL-13 protected roots are absent")
        require(isinstance(resources, Mapping) and resources, "PROTECTED_RESOURCES_UNRESOLVED", "MODEL-13 protected resources are absent")
        require(isinstance(request, Mapping) and set(request) == REQUEST_FIELDS, "MODEL13_EXECUTION_REQUEST_INVALID", "MODEL-13 execution request fields differ")
        self._roots: dict[str, Path] = {}
        for handle, raw in roots.items():
            require(isinstance(handle, str) and handle.startswith("proot-") and isinstance(raw, str) and Path(raw).is_absolute(), "PROTECTED_ROOT_PATH_INVALID", "MODEL-13 roots require opaque handles and absolute paths")
            path = Path(raw).resolve()
            require(path.is_dir() and not _is_within(path, self.repository_root), "PROTECTED_ROOT_PATH_INVALID", "MODEL-13 protected roots must exist outside Git")
            self._roots[handle] = path
        self._resources = dict(resources)
        self.execution_request = dict(request)
        semantic = {"registry_id": REGISTRY_ID, "version": REGISTRY_VERSION, "root_handles": sorted(self._roots), "resources": self._resources, "execution_request": self.execution_request}
        self.registry_identity = "protected-handle-registry:sha256:" + content_digest(semantic)

    @classmethod
    def load(cls, registry_path: Path, repository_root: Path) -> "ProtectedHandleResolver":
        path = registry_path.resolve()
        require(path.is_file(), "AUTHORITATIVE_ACCESS_REGISTRY_UNRESOLVED", "explicit MODEL-13 registry is absent")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ConformanceError("PROTECTED_REGISTRY_INVALID", "MODEL-13 registry is unreadable") from exc
        require(isinstance(value, Mapping), "PROTECTED_REGISTRY_INVALID", "MODEL-13 registry must be an object")
        return cls(value, path, repository_root)

    def resolve(self, handle: str, expected_kind: str, *, must_exist: bool = True) -> ResolvedHandle:
        require(isinstance(handle, str) and handle.startswith("phandle-"), "PROTECTED_HANDLE_INVALID", "MODEL-13 resource handle must be opaque")
        resource = self._resources.get(handle)
        require(isinstance(resource, Mapping), "PROTECTED_HANDLE_UNRESOLVED", "exact MODEL-13 protected handle is absent")
        require(resource.get("kind") == expected_kind, "PROTECTED_HANDLE_KIND_MISMATCH", "MODEL-13 protected handle has the wrong kind")
        root_handle = resource.get("root_handle")
        require(root_handle in self._roots, "PROTECTED_ROOT_HANDLE_UNRESOLVED", "MODEL-13 resource root is absent")
        relative = resource.get("relative_path")
        require(isinstance(relative, str) and relative, "PROTECTED_RELATIVE_PATH_INVALID", "MODEL-13 relative path is absent")
        pure = PurePath(relative)
        require(not pure.is_absolute() and ".." not in pure.parts and "." not in pure.parts, "PROTECTED_PATH_TRAVERSAL_REJECTED", "MODEL-13 protected path traversal rejected")
        root = self._roots[str(root_handle)]
        candidate = (root / Path(relative)).resolve()
        require(_is_within(candidate, root), "PROTECTED_PATH_CONTAINMENT_FAILED", "MODEL-13 resource escapes its declared root")
        if must_exist:
            require(candidate.is_dir() if expected_kind in DIRECTORY_KINDS else candidate.is_file(), "PROTECTED_RESOURCE_UNRESOLVED", "exact MODEL-13 protected resource is absent")
        return ResolvedHandle(handle, expected_kind, candidate)


def load_authorized_registry(registry_path: Path | None, repository_root: Path) -> ProtectedHandleResolver:
    require(registry_path is not None, "AUTHORITATIVE_ACCESS_REGISTRY_UNRESOLVED", "no MODEL-13 protected registry was explicitly supplied")
    return ProtectedHandleResolver.load(registry_path, repository_root)
