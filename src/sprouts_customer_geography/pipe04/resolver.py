"""PIPE-04 exact-handle registry on the accepted PIPE protected architecture."""

from __future__ import annotations

import json
from pathlib import Path, PurePath
from typing import Any, Mapping

from sprouts_customer_geography.pipe01.canonical import content_digest
from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.pipe02.resolver import ResolvedHandle, _is_within


REGISTRY_ID = "PIPE04_PROTECTED_HANDLE_REGISTRY_V1"
REGISTRY_VERSION = "1.0.0"
REQUEST_FIELDS = frozenset(
    {
        "model10_package_handle",
        "model10_commitment_evidence_handle",
        "model10_commitment_nonce_handle",
        "model10_ready_marker_handle",
        "wisconsin_development_target_workbook_handles",
        "binding_output_root_handle",
    }
)
SOURCE_FIELDS = frozenset(
    {
        "authority_id",
        "provenance_class",
        "source_workbook_identity",
        "workbook_handle",
        "byte_hash_permitted",
        "projection",
    }
)


class ProtectedHandleResolver:
    """Resolve only exact PIPE-04 handles beneath authorized protected roots."""

    def __init__(self, registry: Mapping[str, Any], registry_path: Path, repository_root: Path):
        self.repository_root = repository_root.resolve()
        self.registry_path = registry_path.resolve()
        require(
            not _is_within(self.registry_path, self.repository_root),
            "PROTECTED_REGISTRY_INSIDE_REPOSITORY",
            "the protected registry must remain outside Git",
        )
        require(
            registry.get("registry_id") == REGISTRY_ID
            and registry.get("version") == REGISTRY_VERSION,
            "PROTECTED_REGISTRY_IDENTITY_MISMATCH",
            "PIPE-04 protected registry identity/version mismatch",
        )
        roots = registry.get("protected_roots")
        resources = registry.get("resources")
        request = registry.get("binding_request")
        sources = registry.get("target_source_authorities")
        require(isinstance(roots, Mapping) and roots, "PROTECTED_ROOTS_UNRESOLVED", "no protected roots were supplied")
        require(isinstance(resources, Mapping) and resources, "PROTECTED_RESOURCES_UNRESOLVED", "no protected handles were supplied")
        require(isinstance(request, Mapping) and set(request) == REQUEST_FIELDS, "BINDING_REQUEST_INVALID", "binding request fields differ from PIPE-04")
        require(isinstance(sources, list) and sources, "TARGET_SOURCE_AUTHORITIES_UNRESOLVED", "exact target-source authorities were not supplied")

        source_authorities: dict[str, dict[str, Any]] = {}
        workbook_handles: set[str] = set()
        for source in sources:
            require(isinstance(source, Mapping) and set(source) == SOURCE_FIELDS, "TARGET_SOURCE_AUTHORITY_INVALID", "target-source fields differ from PIPE-04")
            identity = source.get("source_workbook_identity")
            handle = source.get("workbook_handle")
            require(isinstance(identity, str) and identity and identity not in source_authorities, "TARGET_SOURCE_IDENTITY_INVALID", "target-source identity is missing or duplicate")
            require(isinstance(handle, str) and handle.startswith("phandle-") and handle not in workbook_handles, "TARGET_SOURCE_HANDLE_INVALID", "target-source handles must be distinct and opaque")
            require(source.get("byte_hash_permitted") is False, "TARGET_SOURCE_HASH_POLICY_INVALID", "target workbooks must not be broadly hashed")
            require(bool(source.get("authority_id")) and bool(source.get("provenance_class")) and isinstance(source.get("projection"), Mapping), "TARGET_SOURCE_AUTHORITY_UNRESOLVED", "target-source authority is incomplete")
            source_authorities[identity] = dict(source)
            workbook_handles.add(handle)
        requested = request.get("wisconsin_development_target_workbook_handles")
        require(isinstance(requested, list) and len(requested) == len(set(requested)) and set(requested) == workbook_handles, "TARGET_SOURCE_HANDLE_MISMATCH", "binding request must name exactly the authorized target workbooks")

        self._roots: dict[str, Path] = {}
        for handle, raw_path in roots.items():
            require(isinstance(handle, str) and handle.startswith("proot-"), "PROTECTED_ROOT_HANDLE_INVALID", "root handles must be opaque")
            require(isinstance(raw_path, str) and raw_path, "PROTECTED_ROOT_PATH_INVALID", "protected root path is missing")
            path = Path(raw_path)
            require(path.is_absolute(), "PROTECTED_ROOT_PATH_INVALID", "protected root path must be absolute")
            resolved = path.resolve()
            require(not _is_within(resolved, self.repository_root), "PROTECTED_ROOT_INSIDE_REPOSITORY", "protected roots must remain outside Git")
            self._roots[handle] = resolved

        self._resources = dict(resources)
        self.binding_request = dict(request)
        self.target_source_authorities = source_authorities
        semantic = {
            "registry_id": registry["registry_id"],
            "version": registry["version"],
            "root_handles": sorted(self._roots),
            "resources": self._resources,
            "binding_request": self.binding_request,
            "target_source_authorities": [source_authorities[key] for key in sorted(source_authorities)],
        }
        self.registry_identity = "protected-handle-registry:sha256:" + content_digest(semantic)

    @classmethod
    def load(cls, registry_path: Path, repository_root: Path) -> "ProtectedHandleResolver":
        path = registry_path.resolve()
        require(path.is_file(), "AUTHORITATIVE_ACCESS_REGISTRY_UNRESOLVED", "explicit protected registry is absent")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ConformanceError("PROTECTED_REGISTRY_INVALID", "protected registry is unreadable") from exc
        require(isinstance(value, Mapping), "PROTECTED_REGISTRY_INVALID", "protected registry must be an object")
        return cls(value, path, repository_root)

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
            if expected_kind.endswith("_root") or expected_kind.endswith("_directory"):
                require(candidate.is_dir(), "PROTECTED_DIRECTORY_UNRESOLVED", "exact protected directory does not resolve")
            else:
                require(candidate.is_file(), "PROTECTED_FILE_UNRESOLVED", "exact protected file does not resolve")
        return ResolvedHandle(handle, expected_kind, candidate)


def load_authorized_registry(registry_path: Path | None, repository_root: Path) -> ProtectedHandleResolver:
    require(registry_path is not None, "AUTHORITATIVE_ACCESS_REGISTRY_UNRESOLVED", "no protected registry was explicitly supplied")
    return ProtectedHandleResolver.load(registry_path, repository_root)
