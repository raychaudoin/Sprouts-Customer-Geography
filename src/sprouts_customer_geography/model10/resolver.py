"""MODEL-10 exact protected-handle resolution without discovery."""

from __future__ import annotations

import json
from pathlib import Path, PurePath
from typing import Any, Mapping

from sprouts_customer_geography.pipe01.canonical import content_digest
from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.pipe02.resolver import ResolvedHandle, _is_within


REGISTRY_ID = "MODEL10_PROTECTED_HANDLE_REGISTRY_V1"
REGISTRY_VERSION = "1.0.0"
REQUIRED_REQUEST_FIELDS = frozenset(
    {
        "model04_package_handle",
        "model04_verification_material_handle",
        "successor_workbook_handles",
        "materialization_output_root_handle",
    }
)
SOURCE_AUTHORITY_FIELDS = frozenset(
    {
        "authority_id",
        "provenance_class",
        "source_workbook_identity",
        "workbook_handle",
        "byte_hash_permitted",
        "projection_id",
        "expected_observation_count",
        "expected_forecast_vintages",
        "expected_markets",
    }
)


class ProtectedHandleResolver:
    """Resolve only explicit MODEL-10 resources beneath explicit protected roots."""

    def __init__(self, registry: Mapping[str, Any], registry_path: Path, repository_root: Path):
        self.repository_root = repository_root.resolve()
        self.registry_path = registry_path.resolve()
        require(
            not _is_within(self.registry_path, self.repository_root),
            "PROTECTED_REGISTRY_INSIDE_REPOSITORY",
            "MODEL-10 registry must remain outside Git",
        )
        require(
            registry.get("registry_id") == REGISTRY_ID
            and registry.get("version") == REGISTRY_VERSION,
            "PROTECTED_REGISTRY_IDENTITY_MISMATCH",
            "MODEL-10 registry identity or version differs",
        )
        roots = registry.get("protected_roots")
        resources = registry.get("resources")
        request = registry.get("materialization_request")
        sources = registry.get("successor_source_authorities")
        require(isinstance(roots, Mapping) and roots, "PROTECTED_ROOTS_UNRESOLVED", "no protected roots supplied")
        require(isinstance(resources, Mapping) and resources, "PROTECTED_RESOURCES_UNRESOLVED", "no protected resources supplied")
        require(
            isinstance(request, Mapping) and set(request) == REQUIRED_REQUEST_FIELDS,
            "MATERIALIZATION_REQUEST_INVALID",
            "materialization request fields differ from the exact contract",
        )
        require(isinstance(sources, list) and sources, "SUCCESSOR_SOURCE_AUTHORITIES_UNRESOLVED", "no successor sources supplied")

        self._roots: dict[str, Path] = {}
        for handle, raw_path in roots.items():
            require(isinstance(handle, str) and handle.startswith("proot-"), "PROTECTED_ROOT_HANDLE_INVALID", "root handles must be opaque")
            require(isinstance(raw_path, str) and raw_path, "PROTECTED_ROOT_PATH_INVALID", "protected root path is missing")
            root = Path(raw_path)
            require(root.is_absolute(), "PROTECTED_ROOT_PATH_INVALID", "protected root must be absolute")
            resolved = root.resolve()
            require(not _is_within(resolved, self.repository_root), "PROTECTED_ROOT_INSIDE_REPOSITORY", "protected root must remain outside Git")
            self._roots[handle] = resolved

        self._resources = dict(resources)
        self.materialization_request = dict(request)
        source_authorities: dict[str, dict[str, Any]] = {}
        workbook_handles: set[str] = set()
        for source in sources:
            require(isinstance(source, Mapping) and set(source) == SOURCE_AUTHORITY_FIELDS, "SUCCESSOR_SOURCE_AUTHORITY_INVALID", "successor source authority fields differ")
            identity = source.get("source_workbook_identity")
            handle = source.get("workbook_handle")
            require(isinstance(identity, str) and identity and identity not in source_authorities, "SUCCESSOR_SOURCE_IDENTITY_INVALID", "successor workbook identity is missing or duplicate")
            require(isinstance(handle, str) and handle.startswith("phandle-") and handle not in workbook_handles, "SUCCESSOR_SOURCE_HANDLE_INVALID", "successor workbook handle is missing or duplicate")
            require(source.get("byte_hash_permitted") is False, "SUCCESSOR_SOURCE_HASH_POLICY_INVALID", "whole protected workbooks must not be hashed")
            require(source.get("projection_id") == "MODEL04_TARGET_BLIND_A_I_IDENTITY_PROJECTION_V1", "SUCCESSOR_PROJECTION_IDENTITY_MISMATCH", "successor projection must reuse MODEL-04 A:I")
            require(isinstance(source.get("expected_observation_count"), int) and source["expected_observation_count"] > 0, "SUCCESSOR_EXPECTED_COUNT_INVALID", "protected expected observation count is required")
            require(set(source.get("expected_forecast_vintages", [])) <= {2024, 2025, 2026} and source.get("expected_forecast_vintages"), "SUCCESSOR_VINTAGE_AUTHORITY_INVALID", "source vintages must be Wisconsin 2024 2025 or 2026")
            expected_markets = source.get("expected_markets")
            require(
                isinstance(expected_markets, list)
                and expected_markets
                and len(expected_markets) == len(set(expected_markets))
                and all(isinstance(market, str) and market.strip() for market in expected_markets),
                "SUCCESSOR_MARKET_AUTHORITY_INVALID",
                "source market lineage authority must contain distinct nonempty values",
            )
            source_authorities[identity] = dict(source)
            workbook_handles.add(handle)
        requested = request.get("successor_workbook_handles")
        require(isinstance(requested, list) and len(requested) == len(set(requested)) and set(requested) == workbook_handles, "SUCCESSOR_SOURCE_HANDLE_MISMATCH", "request must name every and only authorized successor workbook")
        all_vintages = {year for source in sources for year in source["expected_forecast_vintages"]}
        require(all_vintages == {2024, 2025, 2026}, "SUCCESSOR_COHORT_VINTAGE_INCOMPLETE", "complete 2024 2025 and 2026 authority is required")
        self.successor_source_authorities = source_authorities
        self.registry_identity = "protected-handle-registry:sha256:" + content_digest(
            {
                "registry_id": registry["registry_id"],
                "version": registry["version"],
                "root_handles": sorted(self._roots),
                "resources": self._resources,
                "materialization_request": self.materialization_request,
                "successor_source_authorities": [source_authorities[key] for key in sorted(source_authorities)],
            }
        )

    @classmethod
    def load(cls, registry_path: Path, repository_root: Path) -> "ProtectedHandleResolver":
        path = registry_path.resolve()
        require(path.is_file(), "AUTHORITATIVE_ACCESS_REGISTRY_UNRESOLVED", "explicit MODEL-10 registry is absent")
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ConformanceError("PROTECTED_REGISTRY_INVALID", "MODEL-10 registry is unreadable") from exc
        require(isinstance(document, Mapping), "PROTECTED_REGISTRY_INVALID", "MODEL-10 registry must be an object")
        return cls(document, path, repository_root)

    def resolve(self, handle: str, expected_kind: str, *, must_exist: bool = True) -> ResolvedHandle:
        require(isinstance(handle, str) and handle.startswith("phandle-"), "PROTECTED_HANDLE_INVALID", "resource handle must be opaque")
        resource = self._resources.get(handle)
        require(isinstance(resource, Mapping), "PROTECTED_HANDLE_UNRESOLVED", "exact protected handle is absent")
        require(resource.get("kind") == expected_kind, "PROTECTED_HANDLE_KIND_MISMATCH", "protected handle has wrong authority kind")
        root_handle = resource.get("root_handle")
        require(root_handle in self._roots, "PROTECTED_ROOT_HANDLE_UNRESOLVED", "protected root handle is absent")
        relative = resource.get("relative_path")
        require(isinstance(relative, str) and relative, "PROTECTED_RELATIVE_PATH_INVALID", "protected relative path is absent")
        pure = PurePath(relative)
        require(not pure.is_absolute() and ".." not in pure.parts and "." not in pure.parts, "PROTECTED_PATH_TRAVERSAL_REJECTED", "protected path traversal rejected")
        root = self._roots[str(root_handle)]
        candidate = (root / Path(relative)).resolve()
        require(_is_within(candidate, root), "PROTECTED_PATH_CONTAINMENT_FAILED", "resolved resource escapes protected root")
        if must_exist:
            if expected_kind.endswith("_root"):
                require(candidate.is_dir(), "PROTECTED_DIRECTORY_UNRESOLVED", "protected directory is absent")
            else:
                require(candidate.is_file(), "PROTECTED_FILE_UNRESOLVED", "protected file is absent")
        return ResolvedHandle(handle, expected_kind, candidate)


def load_authorized_registry(registry_path: Path | None, repository_root: Path) -> ProtectedHandleResolver:
    require(registry_path is not None, "AUTHORITATIVE_ACCESS_REGISTRY_UNRESOLVED", "no MODEL-10 registry supplied")
    return ProtectedHandleResolver.load(registry_path, repository_root)
