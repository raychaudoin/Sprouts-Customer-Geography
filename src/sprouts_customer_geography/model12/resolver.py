"""Bounded protected and accepted-public dependency resolution for MODEL-12."""

from __future__ import annotations

import json
from pathlib import Path, PurePath
from typing import Any, Mapping, Sequence

from sprouts_customer_geography.pipe01.canonical import content_digest
from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.pipe02.resolver import ResolvedHandle, _is_within


REGISTRY_ID = "MODEL12_PROTECTED_HANDLE_REGISTRY_V1"
REGISTRY_VERSION = "1.0.0"
REQUEST_FIELDS = frozenset(
    {
        "michigan_source_handle",
        "model11_development_package_handle",
        "model11_development_ready_marker_handle",
        "model11_development_manifest_handle",
        "model11_feature_freeze_package_handle",
        "model11_feature_freeze_ready_marker_handle",
        "model12_output_root_handle",
    }
)
PUBLIC_DEPENDENCY_FIELDS = frozenset({"data04_ready_dir", "geo05_support_dir"})
SOURCE_AUTHORITY_FIELDS = frozenset(
    {
        "source_authority_id",
        "source_root_handle",
        "exact_basename",
        "workbook_handle",
        "whole_workbook_hash_permitted",
        "expected_forecast_vintages",
        "header_alias_overrides",
    }
)
CANONICAL_PROJECTION_FIELDS = frozenset(
    {"vintage", "seed_point_id", "address", "city", "state", "zip", "latitude", "longitude", "market"}
)


def resolve_exact_basename(source_root: Path, exact_basename: str) -> Path:
    """Resolve one immediate file by exact basename without recursive discovery."""

    root = source_root.resolve()
    require(root.is_dir(), "MODEL12_SOURCE_ROOT_UNRESOLVED", "authorized source root is absent")
    require(
        isinstance(exact_basename, str)
        and bool(exact_basename.strip())
        and PurePath(exact_basename).name == exact_basename
        and Path(exact_basename).suffix == "",
        "MODEL12_EXACT_SOURCE_BASENAME_INVALID",
        "exact source basename must not contain a path or extension",
    )
    matches = [entry.resolve() for entry in root.iterdir() if entry.is_file() and entry.stem == exact_basename]
    require(len(matches) == 1, "MODEL12_EXACT_SOURCE_BASENAME_UNRESOLVED", "exactly one authorized source basename match is required")
    require(_is_within(matches[0], root), "PROTECTED_PATH_CONTAINMENT_FAILED", "exact source escapes its authorized root")
    return matches[0]


class ProtectedHandleResolver:
    """Resolve exact MODEL-12 resources without broad filesystem discovery."""

    def __init__(self, registry: Mapping[str, Any], registry_path: Path, repository_root: Path):
        self.repository_root = repository_root.resolve()
        self.registry_path = registry_path.resolve()
        require(
            not _is_within(self.registry_path, self.repository_root),
            "PROTECTED_REGISTRY_INSIDE_REPOSITORY",
            "MODEL-12 registry must remain outside Git",
        )
        require(
            registry.get("registry_id") == REGISTRY_ID and registry.get("version") == REGISTRY_VERSION,
            "PROTECTED_REGISTRY_IDENTITY_MISMATCH",
            "MODEL-12 registry identity or version differs",
        )
        roots = registry.get("protected_roots")
        resources = registry.get("resources")
        request = registry.get("materialization_request")
        public = registry.get("public_dependencies")
        source = registry.get("source_authority")
        require(isinstance(roots, Mapping) and roots, "PROTECTED_ROOTS_UNRESOLVED", "no protected roots supplied")
        require(isinstance(resources, Mapping) and resources, "PROTECTED_RESOURCES_UNRESOLVED", "no protected resources supplied")
        require(
            isinstance(request, Mapping) and set(request) == REQUEST_FIELDS,
            "MODEL12_MATERIALIZATION_REQUEST_INVALID",
            "MODEL-12 materialization request fields differ",
        )
        require(
            isinstance(public, Mapping) and set(public) == PUBLIC_DEPENDENCY_FIELDS,
            "MODEL12_PUBLIC_DEPENDENCIES_INVALID",
            "MODEL-12 public dependency fields differ",
        )
        require(
            isinstance(source, Mapping) and set(source) == SOURCE_AUTHORITY_FIELDS,
            "MODEL12_SOURCE_AUTHORITY_INVALID",
            "MODEL-12 source authority fields differ",
        )

        self._roots: dict[str, Path] = {}
        for handle, raw_path in roots.items():
            require(
                isinstance(handle, str) and handle.startswith("proot-")
                and isinstance(raw_path, str) and Path(raw_path).is_absolute(),
                "PROTECTED_ROOT_PATH_INVALID",
                "protected roots require opaque handles and absolute paths",
            )
            resolved = Path(raw_path).resolve()
            require(
                resolved.is_dir() and not _is_within(resolved, self.repository_root),
                "PROTECTED_ROOT_PATH_INVALID",
                "protected roots must exist outside Git",
            )
            self._roots[handle] = resolved
        self._resources = dict(resources)
        self.materialization_request = dict(request)

        self.public_dependencies: dict[str, Path] = {}
        for field, raw_path in public.items():
            require(isinstance(raw_path, str) and Path(raw_path).is_absolute(), "MODEL12_PUBLIC_DEPENDENCY_PATH_INVALID", "public dependency paths must be absolute")
            resolved = Path(raw_path).resolve()
            require(resolved.is_dir(), "MODEL12_PUBLIC_DEPENDENCY_UNRESOLVED", "accepted public dependency directory is absent")
            if _is_within(resolved, self.repository_root):
                relative = resolved.relative_to(self.repository_root).as_posix()
                require(relative == "outputs" or relative.startswith("outputs/"), "MODEL12_PUBLIC_DEPENDENCY_PATH_INVALID", "repository-local public packages must remain under ignored outputs")
            self.public_dependencies[field] = resolved

        source_authority_id = source.get("source_authority_id")
        root_handle = source.get("source_root_handle")
        workbook_handle = source.get("workbook_handle")
        expected_vintages = source.get("expected_forecast_vintages")
        overrides = source.get("header_alias_overrides")
        require(
            isinstance(source_authority_id, str) and bool(source_authority_id)
            and root_handle in self._roots
            and isinstance(workbook_handle, str) and workbook_handle.startswith("phandle-")
            and source.get("whole_workbook_hash_permitted") is False
            and expected_vintages == [2024, 2025, 2026],
            "MODEL12_SOURCE_AUTHORITY_INVALID",
            "MODEL-12 source authority identity scope or hash policy differs",
        )
        require(
            isinstance(overrides, Mapping)
            and set(overrides) <= CANONICAL_PROJECTION_FIELDS
            and all(
                isinstance(values, Sequence)
                and not isinstance(values, (str, bytes))
                and bool(values)
                and all(isinstance(value, str) and bool(value.strip()) for value in values)
                for values in overrides.values()
            ),
            "MODEL12_SOURCE_HEADER_ALIAS_OVERRIDE_INVALID",
            "source header alias overrides are invalid",
        )
        self.source_authority = dict(source)
        self.header_alias_overrides = {str(field): tuple(str(value) for value in values) for field, values in overrides.items()}
        self.upstream_model11_registry_identity = str(registry.get("upstream_model11_registry_identity") or "")
        require(self.upstream_model11_registry_identity.startswith("protected-handle-registry:sha256:"), "MODEL12_MODEL11_REGISTRY_IDENTITY_INVALID", "accepted MODEL-11 registry identity is absent")

        semantic = {
            "registry_id": REGISTRY_ID,
            "version": REGISTRY_VERSION,
            "root_handles": sorted(self._roots),
            "resources": self._resources,
            "materialization_request": self.materialization_request,
            "public_dependency_fields": sorted(self.public_dependencies),
            "source_authority": self.source_authority,
            "upstream_model11_registry_identity": self.upstream_model11_registry_identity,
        }
        self.registry_identity = "protected-handle-registry:sha256:" + content_digest(semantic)

    @classmethod
    def load(cls, registry_path: Path, repository_root: Path) -> "ProtectedHandleResolver":
        path = registry_path.resolve()
        require(path.is_file(), "AUTHORITATIVE_ACCESS_REGISTRY_UNRESOLVED", "explicit MODEL-12 registry is absent")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ConformanceError("PROTECTED_REGISTRY_INVALID", "MODEL-12 registry is unreadable") from exc
        require(isinstance(value, Mapping), "PROTECTED_REGISTRY_INVALID", "MODEL-12 registry must be an object")
        return cls(value, path, repository_root)

    def resolve(self, handle: str, expected_kind: str, *, must_exist: bool = True) -> ResolvedHandle:
        require(isinstance(handle, str) and handle.startswith("phandle-"), "PROTECTED_HANDLE_INVALID", "resource handle must be opaque")
        resource = self._resources.get(handle)
        require(isinstance(resource, Mapping), "PROTECTED_HANDLE_UNRESOLVED", "exact protected handle is absent")
        require(resource.get("kind") == expected_kind, "PROTECTED_HANDLE_KIND_MISMATCH", "protected handle has the wrong authority kind")
        root_handle = resource.get("root_handle")
        require(root_handle in self._roots, "PROTECTED_ROOT_HANDLE_UNRESOLVED", "protected root handle is absent")
        relative = resource.get("relative_path")
        require(isinstance(relative, str) and bool(relative), "PROTECTED_RELATIVE_PATH_INVALID", "protected relative path is absent")
        pure = PurePath(relative)
        require(not pure.is_absolute() and ".." not in pure.parts and "." not in pure.parts, "PROTECTED_PATH_TRAVERSAL_REJECTED", "protected path traversal rejected")
        root = self._roots[str(root_handle)]
        candidate = (root / Path(relative)).resolve()
        require(_is_within(candidate, root), "PROTECTED_PATH_CONTAINMENT_FAILED", "resolved resource escapes its root")
        if must_exist:
            require(candidate.is_dir() if expected_kind.endswith("_root") else candidate.is_file(), "PROTECTED_RESOURCE_UNRESOLVED", "exact protected resource is absent")
        return ResolvedHandle(handle, expected_kind, candidate)

    def resolve_source(self) -> ResolvedHandle:
        request_handle = str(self.materialization_request["michigan_source_handle"])
        resource = self.resolve(request_handle, "michigan_seed_source")
        exact = resolve_exact_basename(self._roots[str(self.source_authority["source_root_handle"])], str(self.source_authority["exact_basename"]))
        require(resource.path == exact, "MODEL12_SOURCE_RESOURCE_MISMATCH", "declared source resource is not the exact authorized basename match")
        require(str(self.source_authority["workbook_handle"]) == request_handle, "MODEL12_SOURCE_RESOURCE_MISMATCH", "source authority and request handles differ")
        return resource


def load_authorized_registry(registry_path: Path | None, repository_root: Path) -> ProtectedHandleResolver:
    require(registry_path is not None, "AUTHORITATIVE_ACCESS_REGISTRY_UNRESOLVED", "no MODEL-12 protected registry was explicitly supplied")
    return ProtectedHandleResolver.load(registry_path, repository_root)
