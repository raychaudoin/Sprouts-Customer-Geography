"""PIPE-03 successor registry using the accepted exact-handle architecture."""

from __future__ import annotations

import json
from pathlib import Path, PurePath
from typing import Any, Mapping

from sprouts_customer_geography.pipe01.canonical import content_digest
from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.pipe02.resolver import ResolvedHandle, _is_within


REGISTRY_ID = "PIPE03_PROTECTED_HANDLE_REGISTRY_V1"
REGISTRY_VERSION = "1.0.0"
REQUIRED_BINDING_REQUEST_FIELDS = frozenset(
    {
        "model04_package_handle",
        "model04_verification_material_handle",
        "wisconsin_development_target_workbook_handles",
        "binding_output_root_handle",
    }
)


class ProtectedHandleResolver:
    """Resolve only exact PIPE-03 handles beneath authorized protected roots.

    This successor retains the PIPE-02 registry shape and deliberately exposes
    no search, glob, filename, sibling, directory-listing, or preview method.
    """

    def __init__(self, registry: Mapping[str, Any], registry_path: Path, repository_root: Path):
        self.repository_root = repository_root.resolve()
        self.registry_path = registry_path.resolve()
        require(
            not _is_within(self.registry_path, self.repository_root),
            "PROTECTED_REGISTRY_INSIDE_REPOSITORY",
            "the protected authority registry must remain outside Git",
        )
        require(
            registry.get("registry_id") == REGISTRY_ID
            and registry.get("version") == REGISTRY_VERSION,
            "PROTECTED_REGISTRY_IDENTITY_MISMATCH",
            "PIPE-03 protected registry identity/version mismatch",
        )
        roots = registry.get("protected_roots")
        resources = registry.get("resources")
        request = registry.get("binding_request")
        target_sources = registry.get("target_source_authorities")
        require(
            isinstance(roots, Mapping) and roots,
            "PROTECTED_ROOTS_UNRESOLVED",
            "no authorized protected roots were supplied",
        )
        require(
            isinstance(resources, Mapping) and resources,
            "PROTECTED_RESOURCES_UNRESOLVED",
            "no authorized protected handles were supplied",
        )
        require(
            isinstance(request, Mapping) and set(request) == REQUIRED_BINDING_REQUEST_FIELDS,
            "BINDING_REQUEST_INVALID",
            "binding request must contain exactly the required protected handles",
        )
        require(
            isinstance(target_sources, list) and bool(target_sources),
            "TARGET_SOURCE_AUTHORITIES_UNRESOLVED",
            "the exact Wisconsin target-source authorities were not supplied",
        )
        source_authorities: dict[str, dict[str, Any]] = {}
        workbook_handles: set[str] = set()
        exact_fields = {
            "authority_id",
            "provenance_class",
            "source_workbook_identity",
            "workbook_handle",
            "byte_hash_permitted",
            "projection",
        }
        for target_source in target_sources:
            require(
                isinstance(target_source, Mapping) and set(target_source) == exact_fields,
                "TARGET_SOURCE_AUTHORITY_INVALID",
                "target-source authority fields differ from the exact PIPE-03 contract",
            )
            workbook_identity = target_source.get("source_workbook_identity")
            workbook_handle = target_source.get("workbook_handle")
            require(
                isinstance(workbook_identity, str) and bool(workbook_identity),
                "TARGET_SOURCE_IDENTITY_INVALID",
                "target-source authority must retain its exact workbook identity",
            )
            require(
                workbook_identity not in source_authorities,
                "TARGET_SOURCE_IDENTITY_DUPLICATE",
                "target-source workbook identities must be unique",
            )
            require(
                isinstance(workbook_handle, str)
                and workbook_handle.startswith("phandle-")
                and workbook_handle not in workbook_handles,
                "TARGET_SOURCE_HANDLE_INVALID",
                "target-source authorities must use distinct opaque workbook handles",
            )
            require(
                target_source.get("byte_hash_permitted") is False,
                "TARGET_SOURCE_HASH_POLICY_INVALID",
                "target workbooks must not be broadly hashed",
            )
            require(
                bool(target_source.get("authority_id"))
                and bool(target_source.get("provenance_class"))
                and isinstance(target_source.get("projection"), Mapping),
                "TARGET_SOURCE_AUTHORITY_UNRESOLVED",
                "target-source identity, provenance, or projection is incomplete",
            )
            source_authorities[workbook_identity] = dict(target_source)
            workbook_handles.add(workbook_handle)
        request_handles = request.get("wisconsin_development_target_workbook_handles")
        require(
            isinstance(request_handles, list)
            and len(request_handles) == len(set(request_handles))
            and set(request_handles) == workbook_handles,
            "TARGET_SOURCE_HANDLE_MISMATCH",
            "binding request must name exactly the authorized target-source handles",
        )

        self._roots: dict[str, Path] = {}
        for handle, raw_path in roots.items():
            require(
                isinstance(handle, str) and handle.startswith("proot-"),
                "PROTECTED_ROOT_HANDLE_INVALID",
                "protected-root handles must be opaque proot-* identifiers",
            )
            require(
                isinstance(raw_path, str) and bool(raw_path),
                "PROTECTED_ROOT_PATH_INVALID",
                "protected-root path is missing",
            )
            root = Path(raw_path)
            require(
                root.is_absolute(),
                "PROTECTED_ROOT_PATH_INVALID",
                "protected-root path must be absolute",
            )
            resolved = root.resolve()
            require(
                not _is_within(resolved, self.repository_root),
                "PROTECTED_ROOT_INSIDE_REPOSITORY",
                "protected roots must remain outside Git",
            )
            self._roots[handle] = resolved

        self._resources = dict(resources)
        self.binding_request = dict(request)
        self.target_source_authorities = source_authorities
        semantic_registry = {
            "registry_id": registry["registry_id"],
            "version": registry["version"],
            "root_handles": sorted(self._roots),
            "resources": self._resources,
            "binding_request": self.binding_request,
            "target_source_authorities": [
                self.target_source_authorities[identity]
                for identity in sorted(self.target_source_authorities)
            ],
        }
        self.registry_identity = (
            "protected-handle-registry:sha256:"
            f"{content_digest(semantic_registry)}"
        )

    @classmethod
    def load(cls, registry_path: Path, repository_root: Path) -> "ProtectedHandleResolver":
        path = registry_path.resolve()
        require(
            path.is_file(),
            "AUTHORITATIVE_ACCESS_REGISTRY_UNRESOLVED",
            "the explicitly supplied protected authority registry is absent",
        )
        try:
            registry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ConformanceError(
                "PROTECTED_REGISTRY_INVALID",
                "the protected authority registry is unreadable",
            ) from exc
        require(
            isinstance(registry, Mapping),
            "PROTECTED_REGISTRY_INVALID",
            "the protected authority registry must be an object",
        )
        return cls(registry, path, repository_root)

    def resolve(
        self,
        handle: str,
        expected_kind: str,
        *,
        must_exist: bool = True,
    ) -> ResolvedHandle:
        require(
            isinstance(handle, str) and handle.startswith("phandle-"),
            "PROTECTED_HANDLE_INVALID",
            "resource handles must be opaque phandle-* identifiers",
        )
        resource = self._resources.get(handle)
        require(
            isinstance(resource, Mapping),
            "PROTECTED_HANDLE_UNRESOLVED",
            "the exact protected handle is absent from the authority registry",
        )
        require(
            resource.get("kind") == expected_kind,
            "PROTECTED_HANDLE_KIND_MISMATCH",
            "protected handle has the wrong authority class",
        )
        root_handle = resource.get("root_handle")
        require(
            root_handle in self._roots,
            "PROTECTED_ROOT_HANDLE_UNRESOLVED",
            "resource root handle is not authorized",
        )
        relative = resource.get("relative_path")
        require(
            isinstance(relative, str) and bool(relative),
            "PROTECTED_RELATIVE_PATH_INVALID",
            "resource relative path is missing",
        )
        pure = PurePath(relative)
        require(
            not pure.is_absolute() and ".." not in pure.parts and "." not in pure.parts,
            "PROTECTED_PATH_TRAVERSAL_REJECTED",
            "resource paths must be contained relative paths",
        )
        root = self._roots[str(root_handle)]
        candidate = (root / Path(relative)).resolve()
        require(
            _is_within(candidate, root),
            "PROTECTED_PATH_CONTAINMENT_FAILED",
            "resolved resource escapes its authorized protected root",
        )
        if must_exist:
            if expected_kind.endswith("_directory") or expected_kind.endswith("_root"):
                require(
                    candidate.is_dir(),
                    "PROTECTED_DIRECTORY_UNRESOLVED",
                    "the exact protected directory handle does not resolve",
                )
            else:
                require(
                    candidate.is_file(),
                    "PROTECTED_FILE_UNRESOLVED",
                    "the exact protected file handle does not resolve",
                )
        return ResolvedHandle(handle, expected_kind, candidate)


def load_authorized_registry(
    registry_path: Path | None,
    repository_root: Path,
) -> ProtectedHandleResolver:
    require(
        registry_path is not None,
        "AUTHORITATIVE_ACCESS_REGISTRY_UNRESOLVED",
        "no protected authority registry handle/path was explicitly supplied",
    )
    return ProtectedHandleResolver.load(registry_path, repository_root)
