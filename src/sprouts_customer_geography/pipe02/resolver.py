"""Exact protected-handle resolution without filesystem discovery."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any, Mapping

from sprouts_customer_geography.pipe01.canonical import content_digest
from sprouts_customer_geography.pipe01.errors import ConformanceError, require


REGISTRY_ID = "PIPE02_PROTECTED_HANDLE_REGISTRY_V1"
REGISTRY_VERSION = "1.1.0"
PRIOR_VINTAGE_TEMPORAL_SOURCE = "PRIOR_VINTAGE_TEMPORAL_SOURCE"
CURRENT_2026_TEMPORAL_SOURCE = "2026_TEMPORAL_SOURCE"
REQUIRED_TARGET_SOURCE_ROLES = frozenset(
    {PRIOR_VINTAGE_TEMPORAL_SOURCE, CURRENT_2026_TEMPORAL_SOURCE}
)
TARGET_REQUEST_FIELD_BY_ROLE = {
    PRIOR_VINTAGE_TEMPORAL_SOURCE: "prior_vintage_target_workbook_handle",
    CURRENT_2026_TEMPORAL_SOURCE: "current_2026_target_workbook_handle",
}
REQUIRED_BINDING_REQUEST_FIELDS = frozenset(
    {
        "model04_package_handle",
        "model04_verification_material_handle",
        "pipe01_run_directory_handle",
        *TARGET_REQUEST_FIELD_BY_ROLE.values(),
        "binding_output_root_handle",
    }
)


def _is_within(candidate: Path, parent: Path) -> bool:
    try:
        candidate.relative_to(parent)
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class ResolvedHandle:
    handle: str
    kind: str
    path: Path


class ProtectedHandleResolver:
    """Resolve only exact handles declared by one protected-local registry.

    The interface deliberately has no search, glob, filename, sibling, or list
    operation.  A caller must already possess the authoritative opaque handle.
    """

    def __init__(self, registry: Mapping[str, Any], registry_path: Path, repository_root: Path):
        self.repository_root = repository_root.resolve()
        self.registry_path = registry_path.resolve()
        require(not _is_within(self.registry_path, self.repository_root), "PROTECTED_REGISTRY_INSIDE_REPOSITORY", "the protected authority registry must remain outside Git")
        require(registry.get("registry_id") == REGISTRY_ID and registry.get("version") == REGISTRY_VERSION, "PROTECTED_REGISTRY_IDENTITY_MISMATCH", "protected registry identity/version mismatch")
        roots = registry.get("protected_roots")
        resources = registry.get("resources")
        request = registry.get("binding_request")
        target_sources = registry.get("target_source_authorities")
        require(isinstance(roots, Mapping) and roots, "PROTECTED_ROOTS_UNRESOLVED", "no authorized protected roots were supplied")
        require(isinstance(resources, Mapping) and resources, "PROTECTED_RESOURCES_UNRESOLVED", "no authorized protected handles were supplied")
        require(isinstance(request, Mapping), "BINDING_REQUEST_UNRESOLVED", "the exact binding request was not supplied")
        require(
            "target_source_authority" not in registry,
            "SINGLE_TARGET_SOURCE_CONTRACT_REJECTED",
            "the superseded single-target-source contract is prohibited",
        )
        require(
            isinstance(target_sources, list),
            "TARGET_SOURCE_AUTHORITIES_UNRESOLVED",
            "the two target-source authorities were not supplied",
        )
        role_authorities: dict[str, dict[str, Any]] = {}
        workbook_handles: set[str] = set()
        for target_source in target_sources:
            require(
                isinstance(target_source, Mapping),
                "TARGET_SOURCE_AUTHORITY_INVALID",
                "each target-source authority must be an object",
            )
            source_role = target_source.get("source_role")
            require(
                source_role in REQUIRED_TARGET_SOURCE_ROLES,
                "TARGET_SOURCE_ROLE_UNKNOWN",
                "target-source authority has an unknown role",
            )
            require(
                str(source_role) not in role_authorities,
                "TARGET_SOURCE_ROLE_DUPLICATE",
                "target-source roles must be unique",
            )
            workbook_handle = target_source.get("workbook_handle")
            require(
                isinstance(workbook_handle, str) and workbook_handle.startswith("phandle-"),
                "TARGET_SOURCE_HANDLE_INVALID",
                "target-source authority must identify one opaque workbook handle",
            )
            require(
                workbook_handle not in workbook_handles,
                "TARGET_SOURCE_HANDLE_REUSED",
                "the two independently governed target roles must use distinct workbook handles",
            )
            workbook_handles.add(workbook_handle)
            role_authorities[str(source_role)] = dict(target_source)
        require(
            set(role_authorities) == REQUIRED_TARGET_SOURCE_ROLES,
            "TARGET_SOURCE_ROLES_INCOMPLETE",
            "exactly the prior-vintage and 2026 target-source roles are required",
        )
        require(
            set(request) == REQUIRED_BINDING_REQUEST_FIELDS,
            "BINDING_REQUEST_INVALID",
            "binding request must contain exactly the required protected handles",
        )
        for source_role, request_field in TARGET_REQUEST_FIELD_BY_ROLE.items():
            require(
                request.get(request_field) == role_authorities[source_role]["workbook_handle"],
                "TARGET_SOURCE_HANDLE_MISMATCH",
                "binding request target handle is misbound to its source role",
            )
        self._roots: dict[str, Path] = {}
        for handle, raw_path in roots.items():
            require(isinstance(handle, str) and handle.startswith("proot-"), "PROTECTED_ROOT_HANDLE_INVALID", "protected-root handles must be opaque proot-* identifiers")
            require(isinstance(raw_path, str) and bool(raw_path), "PROTECTED_ROOT_PATH_INVALID", "protected-root path is missing")
            root = Path(raw_path)
            require(root.is_absolute(), "PROTECTED_ROOT_PATH_INVALID", "protected-root path must be absolute")
            resolved = root.resolve()
            require(not _is_within(resolved, self.repository_root), "PROTECTED_ROOT_INSIDE_REPOSITORY", "protected roots must remain outside Git")
            self._roots[handle] = resolved
        self._resources = dict(resources)
        self.binding_request = dict(request)
        self.target_source_authorities = role_authorities
        semantic_registry = {
            "registry_id": registry["registry_id"],
            "version": registry["version"],
            "root_handles": sorted(self._roots),
            "resources": self._resources,
            "binding_request": self.binding_request,
            "target_source_authorities": [
                self.target_source_authorities[role]
                for role in sorted(self.target_source_authorities)
            ],
        }
        self.registry_identity = f"protected-handle-registry:sha256:{content_digest(semantic_registry)}"

    @classmethod
    def load(cls, registry_path: Path, repository_root: Path) -> "ProtectedHandleResolver":
        path = registry_path.resolve()
        require(path.is_file(), "AUTHORITATIVE_ACCESS_REGISTRY_UNRESOLVED", "the explicitly supplied protected authority registry is absent")
        try:
            registry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ConformanceError("PROTECTED_REGISTRY_INVALID", "the protected authority registry is unreadable") from exc
        require(isinstance(registry, Mapping), "PROTECTED_REGISTRY_INVALID", "the protected authority registry must be an object")
        return cls(registry, path, repository_root)

    def resolve(self, handle: str, expected_kind: str, *, must_exist: bool = True) -> ResolvedHandle:
        require(isinstance(handle, str) and handle.startswith("phandle-"), "PROTECTED_HANDLE_INVALID", "resource handles must be opaque phandle-* identifiers")
        resource = self._resources.get(handle)
        require(isinstance(resource, Mapping), "PROTECTED_HANDLE_UNRESOLVED", "the exact protected handle is not present in the authority registry")
        require(resource.get("kind") == expected_kind, "PROTECTED_HANDLE_KIND_MISMATCH", "protected handle has the wrong authority class")
        root_handle = resource.get("root_handle")
        require(root_handle in self._roots, "PROTECTED_ROOT_HANDLE_UNRESOLVED", "resource root handle is not authorized")
        relative = resource.get("relative_path")
        require(isinstance(relative, str) and bool(relative), "PROTECTED_RELATIVE_PATH_INVALID", "resource relative path is missing")
        pure = PurePath(relative)
        require(not pure.is_absolute() and ".." not in pure.parts and "." not in pure.parts, "PROTECTED_PATH_TRAVERSAL_REJECTED", "resource paths must be contained relative paths")
        root = self._roots[str(root_handle)]
        candidate = (root / Path(relative)).resolve()
        require(_is_within(candidate, root), "PROTECTED_PATH_CONTAINMENT_FAILED", "resolved resource escapes its authorized protected root")
        if must_exist:
            if expected_kind.endswith("_directory") or expected_kind.endswith("_root"):
                require(candidate.is_dir(), "PROTECTED_DIRECTORY_UNRESOLVED", "the exact protected directory handle does not resolve")
            else:
                require(candidate.is_file(), "PROTECTED_FILE_UNRESOLVED", "the exact protected file handle does not resolve")
        return ResolvedHandle(handle, expected_kind, candidate)


def load_authorized_registry(registry_path: Path | None, repository_root: Path) -> ProtectedHandleResolver:
    require(registry_path is not None, "AUTHORITATIVE_ACCESS_REGISTRY_UNRESOLVED", "no protected authority registry handle/path was explicitly supplied")
    return ProtectedHandleResolver.load(registry_path, repository_root)
