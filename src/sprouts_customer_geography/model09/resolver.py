"""Exact-handle protected resolver for MODEL-09."""

from __future__ import annotations

import json
from pathlib import Path, PurePath
from typing import Any, Mapping

from sprouts_customer_geography.pipe01.canonical import content_digest
from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.pipe02.resolver import ResolvedHandle, _is_within


REGISTRY_ID = "MODEL09_PROTECTED_HANDLE_REGISTRY_V1"
REGISTRY_VERSION = "1.0.0"
REQUEST_FIELDS = frozenset(
    {
        "pipe04_binding_handle",
        "pipe04_ready_marker_handle",
        "model10_package_handle",
        "model10_ready_marker_handle",
        "acs_source_handle",
        "tiger_source_handle",
        "model09_output_root_handle",
    }
)


class ProtectedHandleResolver:
    """Resolve only exact MODEL-09 handles beneath declared protected roots."""

    def __init__(self, registry: Mapping[str, Any], registry_path: Path, repository_root: Path):
        self.repository_root = repository_root.resolve()
        self.registry_path = registry_path.resolve()
        require(not _is_within(self.registry_path, self.repository_root), "PROTECTED_REGISTRY_INSIDE_REPOSITORY", "MODEL-09 registry must remain outside Git")
        require(registry.get("registry_id") == REGISTRY_ID and registry.get("version") == REGISTRY_VERSION, "PROTECTED_REGISTRY_IDENTITY_MISMATCH", "MODEL-09 registry identity/version mismatch")
        roots = registry.get("protected_roots")
        resources = registry.get("resources")
        request = registry.get("development_request")
        require(isinstance(roots, Mapping) and roots, "PROTECTED_ROOTS_UNRESOLVED", "no protected roots supplied")
        require(isinstance(resources, Mapping) and resources, "PROTECTED_RESOURCES_UNRESOLVED", "no protected handles supplied")
        require(isinstance(request, Mapping) and set(request) == REQUEST_FIELDS, "DEVELOPMENT_REQUEST_INVALID", "MODEL-09 request fields differ from contract")
        self._roots: dict[str, Path] = {}
        for handle, raw_path in roots.items():
            require(isinstance(handle, str) and handle.startswith("proot-"), "PROTECTED_ROOT_HANDLE_INVALID", "root handles must be opaque")
            require(isinstance(raw_path, str) and Path(raw_path).is_absolute(), "PROTECTED_ROOT_PATH_INVALID", "protected roots must be absolute")
            resolved = Path(raw_path).resolve()
            require(not _is_within(resolved, self.repository_root), "PROTECTED_ROOT_INSIDE_REPOSITORY", "protected roots must remain outside Git")
            self._roots[handle] = resolved
        self._resources = dict(resources)
        self.development_request = dict(request)
        semantic = {
            "registry_id": REGISTRY_ID,
            "version": REGISTRY_VERSION,
            "root_handles": sorted(self._roots),
            "resources": self._resources,
            "development_request": self.development_request,
        }
        self.registry_identity = "protected-handle-registry:sha256:" + content_digest(semantic)

    @classmethod
    def load(cls, registry_path: Path, repository_root: Path) -> "ProtectedHandleResolver":
        path = registry_path.resolve()
        require(path.is_file(), "AUTHORITATIVE_ACCESS_REGISTRY_UNRESOLVED", "explicit MODEL-09 registry is absent")
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ConformanceError("PROTECTED_REGISTRY_INVALID", "MODEL-09 registry is unreadable") from exc
        require(isinstance(document, Mapping), "PROTECTED_REGISTRY_INVALID", "MODEL-09 registry must be an object")
        return cls(document, path, repository_root)

    def resolve(self, handle: str, expected_kind: str, *, must_exist: bool = True) -> ResolvedHandle:
        require(isinstance(handle, str) and handle.startswith("phandle-"), "PROTECTED_HANDLE_INVALID", "resource handles must be opaque")
        resource = self._resources.get(handle)
        require(isinstance(resource, Mapping), "PROTECTED_HANDLE_UNRESOLVED", "exact protected handle is absent")
        require(resource.get("kind") == expected_kind, "PROTECTED_HANDLE_KIND_MISMATCH", "protected handle has the wrong authority class")
        root_handle = resource.get("root_handle")
        require(root_handle in self._roots, "PROTECTED_ROOT_HANDLE_UNRESOLVED", "resource root is not authorized")
        relative = resource.get("relative_path")
        require(isinstance(relative, str) and relative, "PROTECTED_RELATIVE_PATH_INVALID", "resource relative path is missing")
        pure = PurePath(relative)
        require(not pure.is_absolute() and ".." not in pure.parts and "." not in pure.parts, "PROTECTED_PATH_TRAVERSAL_REJECTED", "resource path escapes its root")
        root = self._roots[str(root_handle)]
        candidate = (root / Path(relative)).resolve()
        require(_is_within(candidate, root), "PROTECTED_PATH_CONTAINMENT_FAILED", "resolved resource escapes its root")
        if must_exist:
            if expected_kind.endswith("_root"):
                require(candidate.is_dir(), "PROTECTED_DIRECTORY_UNRESOLVED", "exact protected directory does not resolve")
            else:
                require(candidate.is_file(), "PROTECTED_FILE_UNRESOLVED", "exact protected file does not resolve")
        return ResolvedHandle(handle, expected_kind, candidate)


def load_authorized_registry(registry_path: Path | None, repository_root: Path) -> ProtectedHandleResolver:
    require(registry_path is not None, "AUTHORITATIVE_ACCESS_REGISTRY_UNRESOLVED", "no MODEL-09 protected registry was explicitly supplied")
    return ProtectedHandleResolver.load(registry_path, repository_root)
