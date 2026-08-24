"""PIPE-05 exact-handle resolution on accepted PIPE/MODEL mechanics."""

from __future__ import annotations

import json
from pathlib import Path, PurePath
from typing import Any, Mapping

from sprouts_customer_geography.model12.resolver import resolve_exact_basename
from sprouts_customer_geography.pipe01.canonical import content_digest
from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.pipe02.resolver import ResolvedHandle, _is_within


REGISTRY_ID = "PIPE05_PROTECTED_HANDLE_REGISTRY_V1"
REGISTRY_VERSION = "1.0.0"
STAGE_NAMES = ("identity", "public_features", "frozen_scoring")
STAGE_FIELDS = frozenset({"package_handle", "ready_marker_handle", "commitment_evidence_handle", "commitment_nonce_handle"})
MATERIALIZATION_FIELDS = frozenset({"ordinal", "run_ready_marker_handle", "stages"})
SOURCE_FIELDS = frozenset({"source_authority_id", "source_root_handle", "exact_basename", "workbook_handle", "whole_workbook_hash_permitted", "projection"})
REQUEST_FIELDS = frozenset({"primary_identity_authority_ordinal", "michigan_target_source_handle", "binding_output_root_handle"})


class ProtectedHandleResolver:
    """Resolve only registry-named PIPE-05 resources beneath authorized roots."""

    def __init__(self, registry: Mapping[str, Any], registry_path: Path, repository_root: Path):
        self.repository_root = repository_root.resolve()
        self.registry_path = registry_path.resolve()
        require(not _is_within(self.registry_path, self.repository_root), "PROTECTED_REGISTRY_INSIDE_REPOSITORY", "PIPE-05 registry must remain outside Git")
        require(registry.get("registry_id") == REGISTRY_ID and registry.get("version") == REGISTRY_VERSION, "PROTECTED_REGISTRY_IDENTITY_MISMATCH", "PIPE-05 registry identity or version differs")
        roots = registry.get("protected_roots")
        resources = registry.get("resources")
        materializations = registry.get("model12_materialization_authorities")
        source = registry.get("source_authority")
        request = registry.get("binding_request")
        require(isinstance(roots, Mapping) and roots, "PROTECTED_ROOTS_UNRESOLVED", "no protected roots supplied")
        require(isinstance(resources, Mapping) and resources, "PROTECTED_RESOURCES_UNRESOLVED", "no protected resources supplied")
        require(isinstance(materializations, list) and len(materializations) == 2, "MODEL12_MATERIALIZATION_AUTHORITIES_INVALID", "exactly two accepted MODEL-12 materializations are required")
        require(isinstance(source, Mapping) and set(source) == SOURCE_FIELDS, "PIPE05_SOURCE_AUTHORITY_INVALID", "PIPE-05 source authority fields differ")
        require(isinstance(request, Mapping) and set(request) == REQUEST_FIELDS and request.get("primary_identity_authority_ordinal") == 1, "PIPE05_BINDING_REQUEST_INVALID", "PIPE-05 binding request fields differ")

        self._roots: dict[str, Path] = {}
        for handle, raw_path in roots.items():
            require(isinstance(handle, str) and handle.startswith("proot-") and isinstance(raw_path, str) and Path(raw_path).is_absolute(), "PROTECTED_ROOT_PATH_INVALID", "protected roots require opaque handles and absolute paths")
            resolved = Path(raw_path).resolve()
            require(resolved.is_dir() and not _is_within(resolved, self.repository_root), "PROTECTED_ROOT_PATH_INVALID", "protected roots must exist outside Git")
            self._roots[handle] = resolved
        self._resources = dict(resources)

        normalized_materializations: list[dict[str, Any]] = []
        for item in materializations:
            require(isinstance(item, Mapping) and set(item) == MATERIALIZATION_FIELDS, "MODEL12_MATERIALIZATION_AUTHORITY_INVALID", "MODEL-12 materialization authority fields differ")
            stages = item.get("stages")
            require(isinstance(stages, Mapping) and set(stages) == set(STAGE_NAMES), "MODEL12_STAGE_AUTHORITY_INVALID", "MODEL-12 stage authority inventory differs")
            for stage in STAGE_NAMES:
                require(isinstance(stages[stage], Mapping) and set(stages[stage]) == STAGE_FIELDS, "MODEL12_STAGE_AUTHORITY_INVALID", "MODEL-12 stage authority handles differ")
            normalized_materializations.append({"ordinal": item.get("ordinal"), "run_ready_marker_handle": item.get("run_ready_marker_handle"), "stages": {stage: dict(stages[stage]) for stage in STAGE_NAMES}})
        require([item["ordinal"] for item in normalized_materializations] == [1, 2], "MODEL12_MATERIALIZATION_AUTHORITY_INVALID", "MODEL-12 materialization ordinals must be exactly one and two")

        require(
            isinstance(source.get("source_authority_id"), str)
            and bool(source.get("source_authority_id"))
            and source.get("source_root_handle") in self._roots
            and isinstance(source.get("workbook_handle"), str)
            and str(source.get("workbook_handle")).startswith("phandle-")
            and source.get("whole_workbook_hash_permitted") is False
            and isinstance(source.get("projection"), Mapping),
            "PIPE05_SOURCE_AUTHORITY_INVALID",
            "PIPE-05 source identity hash or projection authority differs",
        )
        require(request.get("michigan_target_source_handle") == source.get("workbook_handle"), "PIPE05_SOURCE_HANDLE_MISMATCH", "source authority and binding request handles differ")
        self.materialization_authorities = normalized_materializations
        self.source_authority = dict(source)
        self.binding_request = dict(request)
        semantic = {
            "registry_id": REGISTRY_ID,
            "version": REGISTRY_VERSION,
            "root_handles": sorted(self._roots),
            "resources": self._resources,
            "model12_materialization_authorities": self.materialization_authorities,
            "source_authority": self.source_authority,
            "binding_request": self.binding_request,
        }
        self.registry_identity = "protected-handle-registry:sha256:" + content_digest(semantic)

    @classmethod
    def load(cls, registry_path: Path, repository_root: Path) -> "ProtectedHandleResolver":
        path = registry_path.resolve()
        require(path.is_file(), "AUTHORITATIVE_ACCESS_REGISTRY_UNRESOLVED", "explicit PIPE-05 registry is absent")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ConformanceError("PROTECTED_REGISTRY_INVALID", "PIPE-05 registry is unreadable") from exc
        require(isinstance(value, Mapping), "PROTECTED_REGISTRY_INVALID", "PIPE-05 registry must be an object")
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
        handle = str(self.binding_request["michigan_target_source_handle"])
        resource = self.resolve(handle, "michigan_isolated_sales_target_source")
        exact = resolve_exact_basename(self._roots[str(self.source_authority["source_root_handle"])], str(self.source_authority["exact_basename"]))
        require(resource.path == exact, "PIPE05_SOURCE_RESOURCE_MISMATCH", "declared source resource is not the exact authorized basename match")
        return resource


def load_authorized_registry(registry_path: Path | None, repository_root: Path) -> ProtectedHandleResolver:
    require(registry_path is not None, "AUTHORITATIVE_ACCESS_REGISTRY_UNRESOLVED", "no PIPE-05 protected registry was explicitly supplied")
    return ProtectedHandleResolver.load(registry_path, repository_root)
