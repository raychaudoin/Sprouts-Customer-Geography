"""Public-only tests for exploratory MODEL-14 Overture Generation 2."""

from __future__ import annotations

import copy
from contextlib import contextmanager
import csv
import json
import math
from pathlib import Path
import unittest
from uuid import uuid4

from shapely.geometry import box

from sprouts_customer_geography.model14.overture_generation2 import (
    AcceptedTractSupport,
    FEATURE_IDS,
    INTENSITY_FEATURES,
    MIX_DIVERSITY_FEATURES,
    _empty_component,
    _load_tract_components,
    _write_components,
    _write_matrix,
    aggregate_commercial_features,
    load_generation2_contract,
)
from sprouts_customer_geography.pipe01.canonical import content_digest
from sprouts_customer_geography.pipe01.errors import ConformanceError


REPOSITORY = Path(__file__).resolve().parents[1]
GENERATION2_CONTRACT_PATH = REPOSITORY / "config/model14/experimental_overture_generation2_contract.json"
GENERATION2_COMMITMENT_PATH = REPOSITORY / "config/model14/target_blind_overture_generation2_commitment.json"
GENERATION1_CONTRACT_PATH = REPOSITORY / "config/model14/experimental_public_feature_contract.json"
GENERATION1_COMMITMENT_PATH = REPOSITORY / "config/model14/target_blind_public_feature_commitment.json"

EXPECTED_FEATURE_IDS = (
    "overture_log_commercial_places_tract",
    "overture_log_shopping_places_tract",
    "overture_log_food_and_drink_places_tract",
    "overture_log_grocery_places_tract",
    "overture_log_commercial_places_5mi",
    "overture_log_shopping_places_5mi",
    "overture_log_food_and_drink_places_5mi",
    "overture_log_restaurant_places_5mi",
    "overture_log_grocery_places_5mi",
    "overture_log_fitness_wellness_places_5mi",
    "overture_log_health_care_places_5mi",
    "overture_basic_category_gini_simpson_diversity_5mi",
    "overture_grocery_share_of_commercial_5mi",
    "overture_shopping_share_of_commercial_5mi",
    "overture_food_and_drink_share_of_commercial_5mi",
)

EXPECTED_CANDIDATE_SETS = {
    "A_model13_reproduced_generation2": [],
    "B_model13_plus_all_generation2_commercial": ["intensity_count", "mix_diversity"],
    "C_model13_plus_generation2_intensity": ["intensity_count"],
    "D_model13_plus_generation2_mix_diversity": ["mix_diversity"],
}

SOURCE_HEADER = [
    "id",
    "version",
    "longitude",
    "latitude",
    "bbox_xmin",
    "bbox_xmax",
    "bbox_ymin",
    "bbox_ymax",
    "confidence",
    "operating_status",
    "basic_category",
    "taxonomy_primary",
    "taxonomy_hierarchy",
]


def _json_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"expected JSON object: {path.name}")
    return value


def _assert_self_hash(test: unittest.TestCase, value: dict[str, object]) -> str:
    semantic = copy.deepcopy(value)
    recorded = semantic.pop("content_sha256")
    test.assertIsInstance(recorded, str)
    test.assertEqual(recorded, content_digest(semantic))
    return str(recorded)


def _component(
    geoid: str,
    state: str,
    *,
    commercial: int = 0,
    shopping: int = 0,
    food: int = 0,
    restaurant: int = 0,
    grocery: int = 0,
    fitness: int = 0,
    health: int = 0,
    basic_counts: dict[str, int] | None = None,
) -> dict[str, object]:
    categories = dict(sorted((basic_counts or {}).items()))
    return {
        "tract_geoid": geoid,
        "state": state,
        "state_fips": geoid[:2],
        "commercial_place_count": commercial,
        "shopping_place_count": shopping,
        "food_and_drink_place_count": food,
        "restaurant_place_count": restaurant,
        "grocery_place_count": grocery,
        "fitness_wellness_place_count": fitness,
        "health_care_place_count": health,
        "basic_category_eligible_count": sum(categories.values()),
        "basic_category_counts": categories,
    }


def _source_row(
    place_id: str,
    point: tuple[float, float],
    *,
    confidence: float | None = 0.9,
    status: str = "open",
    hierarchy: list[str] | None = None,
    primary: str | None = None,
    basic_category: str = "",
) -> dict[str, object]:
    longitude, latitude = point
    path = [] if hierarchy is None else hierarchy
    return {
        "id": place_id,
        "version": 1,
        "longitude": longitude,
        "latitude": latitude,
        "bbox_xmin": longitude - 0.00001,
        "bbox_xmax": longitude + 0.00001,
        "bbox_ymin": latitude - 0.00001,
        "bbox_ymax": latitude + 0.00001,
        "confidence": "" if confidence is None else confidence,
        "operating_status": status,
        "basic_category": basic_category,
        "taxonomy_primary": "" if primary is None else primary,
        "taxonomy_hierarchy": "" if hierarchy is None else json.dumps(path, separators=(",", ":")),
    }


def _write_source(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SOURCE_HEADER, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


@contextmanager
def _temporary_files(*names: str):
    root = REPOSITORY / ".tmp"
    root.mkdir(exist_ok=True)
    token = uuid4().hex
    paths = tuple(root / f"model14_g2_{token}_{name}" for name in names)
    try:
        yield paths
    finally:
        for path in paths:
            path.unlink(missing_ok=True)


def _synthetic_supports() -> tuple[dict[str, AcceptedTractSupport], dict[str, tuple[float, float]]]:
    """Build public synthetic geometry with accepted MI/WI tract accounting."""

    supports: dict[str, AcceptedTractSupport] = {}
    points: dict[str, tuple[float, float]] = {}
    for state, prefix, count, origin in (
        ("MI", "26", 3017, (-86.5, 42.5)),
        ("WI", "55", 1542, (-90.5, 44.5)),
    ):
        geometries = {}
        for index in range(count):
            column = index % 64
            row = index // 64
            longitude = origin[0] + column * 0.01
            latitude = origin[1] + row * 0.01
            geoid = prefix + f"{index:09d}"
            geometries[geoid] = box(
                longitude - 0.003,
                latitude - 0.003,
                longitude + 0.003,
                latitude + 0.003,
            )
            if index < 4:
                points[f"{state}{index}"] = (longitude, latitude)
        supports[state] = AcceptedTractSupport(state, None, geometries)
    return supports, points


class Model14OvertureGeneration2AuthorityTests(unittest.TestCase):
    def test_contract_and_commitment_are_self_hashed_exploratory_and_fixed(self) -> None:
        contract = load_generation2_contract(REPOSITORY)
        commitment = _json_object(GENERATION2_COMMITMENT_PATH)
        contract_hash = _assert_self_hash(self, contract)
        _assert_self_hash(self, commitment)

        self.assertEqual(contract["source"]["release"], "2026-07-22.0")
        self.assertEqual(contract["source"]["schema_version"], "v1.18.0")
        self.assertEqual(contract["source"]["retrieval_date"], "2026-08-27")
        self.assertEqual(
            contract["source"]["query_identity"],
            "MODEL14_OVERTURE_PLACES_MI_WI_EXACT_POINT_ENVELOPE_V1",
        )
        self.assertEqual(contract["geography"]["source_point_crs"], "EPSG:4326")
        self.assertEqual(contract["geography"]["accepted_tract_polygon_crs"], "EPSG:4269")
        self.assertFalse(contract["geography"]["production_datum_authority_claimed"])
        self.assertTrue(contract["taxonomy_rules"]["hierarchy_values_must_be_unique"])
        self.assertTrue(contract["exploratory"])
        self.assertFalse(contract["confirmatory"])
        self.assertTrue(contract["prior_generation_aggregate_results_known"])
        self.assertFalse(contract["production_source_authority"])
        self.assertEqual(FEATURE_IDS, EXPECTED_FEATURE_IDS)
        self.assertEqual(tuple(item["feature_id"] for item in contract["feature_catalog"]), EXPECTED_FEATURE_IDS)
        self.assertEqual(contract["feature_count"], 15)
        self.assertEqual(tuple(INTENSITY_FEATURES), EXPECTED_FEATURE_IDS[:11])
        self.assertEqual(tuple(MIX_DIVERSITY_FEATURES), EXPECTED_FEATURE_IDS[11:])
        self.assertEqual(contract["candidate_sets"], EXPECTED_CANDIDATE_SETS)
        self.assertFalse(contract["generation1_combination_justified"])

        self.assertEqual(commitment["state"], "EXPLORATORY_GENERATION2_TARGET_BLIND_PUBLIC_FEATURES_FROZEN")
        self.assertTrue(commitment["exploratory"])
        self.assertFalse(commitment["confirmatory"])
        self.assertEqual(commitment["contract"]["content_sha256"], contract_hash)
        self.assertEqual(commitment["feature_catalog"]["feature_order"], list(EXPECTED_FEATURE_IDS))
        self.assertEqual(commitment["candidate_sets_frozen"], list(EXPECTED_CANDIDATE_SETS))
        self.assertFalse(commitment["generation1_combination_included"])
        chronology = commitment["chronology"]
        self.assertTrue(chronology["generation2_definitions_frozen_before_generation2_target_access"])
        self.assertTrue(chronology["generation2_full_tract_matrix_frozen_before_generation2_target_access"])
        self.assertEqual(chronology["generation2_target_values_accessed"], 0)
        self.assertEqual(chronology["generation2_protected_anchor_rows_accessed"], 0)
        self.assertFalse(chronology["sealed_or_prospective_evidence_accessed"])
        self.assertTrue(chronology["prior_generation_results_known_and_disclosed_as_exploratory"])
        self.assertEqual(commitment["tract_matrix"]["tract_count"], 4559)
        self.assertEqual(commitment["tract_matrix"]["michigan_tract_count"], 3017)
        self.assertEqual(commitment["tract_matrix"]["wisconsin_tract_count"], 1542)
        self.assertFalse(commitment["tract_matrix"]["tract_rows_dropped"])
        self.assertFalse(commitment["tract_matrix"]["missing_to_zero"])
        self.assertEqual(commitment["tract_matrix"]["determinism_state"], "DETERMINISTIC_BYTE_IDENTICAL")

    def test_generation1_target_blind_authority_remains_semantically_unchanged(self) -> None:
        contract = _json_object(GENERATION1_CONTRACT_PATH)
        commitment = _json_object(GENERATION1_COMMITMENT_PATH)
        self.assertEqual(
            _assert_self_hash(self, contract),
            "f426bd5a99d2d1c4e2d0063cd3fd42db58c67efe1ef9c91dca4e5b3ad3c3cad6",
        )
        self.assertEqual(
            _assert_self_hash(self, commitment),
            "3c899bae5e4104441e10924268baf99002426b249e51c820dcafc4394e7723ff",
        )
        self.assertEqual(commitment["state"], "TARGET_BLIND_PUBLIC_FEATURES_FROZEN")
        self.assertEqual(commitment["chronology"]["target_values_accessed"], 0)
        self.assertEqual(commitment["chronology"]["protected_anchor_rows_accessed"], 0)
        self.assertFalse(commitment["chronology"]["sealed_or_prospective_evidence_accessed"])
        self.assertEqual(commitment["public_matrix_commitment"]["row_count"], 4559)
        generation2 = _json_object(GENERATION2_COMMITMENT_PATH)
        self.assertEqual(generation2["generation1_checkpoint"], "b41f0e8d96c717654e861d1673d87d57cf42b0cf")
        self.assertTrue(generation2["generation1_evidence_preserved_unchanged"])

    def test_contract_excludes_deprecated_identity_and_protected_fields(self) -> None:
        contract = load_generation2_contract(REPOSITORY)
        commitment = _json_object(GENERATION2_COMMITMENT_PATH)
        selected = set(contract["source"]["selected_columns"])
        forbidden_source_fields = {
            "categories",
            "categories.primary",
            "categories.alternate",
            "names",
            "brand",
            "providers",
            "sources",
            "addresses",
        }
        self.assertFalse(selected & forbidden_source_fields)
        for flag in ("deprecated_categories_field_used", "names_used", "brands_used", "providers_used", "addresses_used"):
            self.assertFalse(contract["source"][flag])
        self.assertFalse(contract["taxonomy_rules"]["alternates_used"])
        self.assertFalse(commitment["source"]["deprecated_categories_field_used"])
        self.assertFalse(commitment["source"]["names_brands_providers_used"])
        forbidden_feature_tokens = (
            "race",
            "ethnicity",
            "religion",
            "protected",
            "sprouts",
            "competitor",
            "brand",
            "provider",
        )
        self.assertFalse(
            any(token in feature.lower() for feature in FEATURE_IDS for token in forbidden_feature_tokens)
        )
        public_module = (REPOSITORY / "src/sprouts_customer_geography/model14/overture_generation2.py").read_text(encoding="utf-8")
        for protected_surface in (
            "ProtectedHandleResolver",
            "MODEL13_AUTHORITY_REGISTRY",
            "model13.resolver",
            "_development_rows",
            "isolated_sales",
            "canonical_target_blind_coordinate",
        ):
            self.assertNotIn(protected_surface, public_module)


class Model14OvertureGeneration2RuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.supports, cls.points = _synthetic_supports()
        cls.contract = load_generation2_contract(REPOSITORY)

    def _load_rows(self, rows: list[dict[str, object]]) -> tuple[dict[str, dict[str, object]], dict[str, object]]:
        with _temporary_files("synthetic_overture.csv") as (source,):
            _write_source(source, rows)
            return _load_tract_components(source, self.supports, self.contract)

    def test_quality_status_taxonomy_and_identity_rules_on_public_fixtures(self) -> None:
        mi0 = self.points["MI0"]
        mi1 = self.points["MI1"]
        mi2 = self.points["MI2"]
        mi3 = self.points["MI3"]
        wi0 = self.points["WI0"]
        rows = [
            _source_row("a", mi0, confidence=0.71, hierarchy=["shopping", "grocery_store"], primary="grocery_store", basic_category="grocery_store"),
            _source_row("b", wi0, status="", hierarchy=["food_and_drink", "restaurant"], primary="restaurant", basic_category="restaurant"),
            _source_row("c", mi0, status="temporarily_closed", hierarchy=["shopping", "grocery_store"], primary="grocery_store"),
            _source_row("d", mi0, confidence=0.9, status="permanently_closed", hierarchy=["shopping", "grocery_store"], primary="grocery_store"),
            _source_row("e", mi0, confidence=0.7, hierarchy=["shopping", "grocery_store"], primary="grocery_store"),
            _source_row("f", mi0, confidence=None, hierarchy=["shopping", "grocery_store"], primary="grocery_store"),
            _source_row("g", mi0, hierarchy=None, primary=None),
            _source_row("h", mi0, hierarchy=["shopping", "grocery_store"], primary="market"),
            _source_row("i", mi0, hierarchy=["education", "school"], primary="school", basic_category="school"),
            _source_row("j", (0.0, 0.0), hierarchy=["shopping", "grocery_store"], primary="grocery_store"),
            _source_row("k", mi1, hierarchy=["sports_and_recreation", "sport_or_fitness_facility", "gym"], primary="gym", basic_category="gym"),
            _source_row("l", mi2, hierarchy=["health_care", "clinic"], primary="clinic", basic_category="clinic"),
            _source_row("m", mi0, status="", hierarchy=["shopping", "grocery_store"], primary="grocery_store", basic_category="grocery_store"),
            _source_row("n", mi3, hierarchy=["shopping", "store"], primary="store", basic_category=""),
        ]
        components, report = self._load_rows(rows)

        mi0_component = components["26000000000"]
        self.assertEqual(mi0_component["commercial_place_count"], 2)
        self.assertEqual(mi0_component["shopping_place_count"], 2)
        self.assertEqual(mi0_component["grocery_place_count"], 2)
        self.assertEqual(mi0_component["basic_category_eligible_count"], 2)
        self.assertEqual(mi0_component["basic_category_counts"], {"grocery_store": 2})
        self.assertEqual(components["55000000000"]["restaurant_place_count"], 1)
        self.assertEqual(components["26000000001"]["fitness_wellness_place_count"], 1)
        self.assertEqual(components["26000000002"]["health_care_place_count"], 1)
        self.assertEqual(components["26000000003"]["commercial_place_count"], 1)
        self.assertEqual(components["26000000003"]["basic_category_eligible_count"], 0)

        self.assertEqual(report["source_envelope_row_count"], len(rows))
        self.assertEqual(report["excluded_known_closed_status"], 2)
        self.assertEqual(report["permanently_closed_nonzero_confidence"], 1)
        self.assertEqual(report["excluded_confidence_not_above_0_7"], 2)
        self.assertEqual(report["excluded_missing_taxonomy"], 1)
        self.assertEqual(report["excluded_taxonomy_primary_hierarchy_mismatch"], 1)
        self.assertEqual(report["excluded_noncommercial_top_level"], 1)
        self.assertEqual(report["outside_accepted_support"], 1)
        self.assertEqual(report["assigned_commercial_place_count"], 6)
        self.assertEqual(report["assigned_commercial_place_count_by_state"], {"MI": 5, "WI": 1})
        self.assertEqual(report["assigned_with_basic_category"], 5)
        self.assertEqual(report["assigned_missing_basic_category"], 1)
        self.assertEqual(report["unique_gers_id_rule"], "strictly increasing canonical extract; duplicate fails")
        self.assertFalse(report["provider_identity_used"])
        self.assertFalse(report["name_brand_identity_used"])

    def test_duplicate_or_unsorted_gers_identity_and_invalid_status_fail_closed(self) -> None:
        point = self.points["MI0"]
        valid = _source_row(
            "same",
            point,
            hierarchy=["shopping", "grocery_store"],
            primary="grocery_store",
        )
        with self.assertRaisesRegex(ConformanceError, "MODEL14_G2_PLACE_ID_DUPLICATE_OR_UNSORTED"):
            self._load_rows([valid, dict(valid)])

        second = _source_row(
            "before",
            point,
            hierarchy=["shopping", "grocery_store"],
            primary="grocery_store",
        )
        with self.assertRaisesRegex(ConformanceError, "MODEL14_G2_PLACE_ID_DUPLICATE_OR_UNSORTED"):
            self._load_rows([valid, second])

        invalid_status = _source_row(
            "status",
            point,
            status="unknown",
            hierarchy=["shopping", "grocery_store"],
            primary="grocery_store",
        )
        with self.assertRaisesRegex(ConformanceError, "MODEL14_G2_OPERATING_STATUS_INVALID"):
            self._load_rows([invalid_status])

    def test_optional_bbox_and_unique_hierarchy_follow_frozen_schema_qa(self) -> None:
        point = self.points["MI0"]
        null_bbox = _source_row(
            "bbox-null",
            point,
            hierarchy=["shopping", "grocery_store"],
            primary="grocery_store",
        )
        for field in ("bbox_xmin", "bbox_xmax", "bbox_ymin", "bbox_ymax"):
            null_bbox[field] = ""
        components, report = self._load_rows([null_bbox])
        self.assertEqual(components["26000000000"]["grocery_place_count"], 1)
        self.assertEqual(report["source_null_bbox_count"], 1)
        self.assertEqual(report.get("source_present_bbox_count", 0), 0)

        partial_bbox = dict(null_bbox)
        partial_bbox["id"] = "bbox-partial"
        partial_bbox["bbox_xmin"] = point[0]
        with self.assertRaisesRegex(ConformanceError, "MODEL14_G2_PLACE_BBOX_INVALID"):
            self._load_rows([partial_bbox])

        duplicate_hierarchy = _source_row(
            "taxonomy-duplicate",
            point,
            hierarchy=["shopping", "shopping"],
            primary="shopping",
        )
        components, report = self._load_rows([duplicate_hierarchy])
        self.assertEqual(components["26000000000"]["commercial_place_count"], 0)
        self.assertEqual(report["excluded_invalid_taxonomy_structure"], 1)

    def test_zero_counts_are_observed_but_zero_denominators_remain_missing(self) -> None:
        geoid = "26001000100"
        empty = _empty_component("MI", geoid)
        features = aggregate_commercial_features({geoid: empty}, [geoid], geoid)
        self.assertEqual(tuple(features), FEATURE_IDS)
        self.assertTrue(all(features[feature] == 0.0 for feature in INTENSITY_FEATURES))
        self.assertTrue(all(features[feature] is None for feature in MIX_DIVERSITY_FEATURES))

        categorized = _component(
            geoid,
            "MI",
            commercial=2,
            basic_counts={"bank": 2},
        )
        observed = aggregate_commercial_features({geoid: categorized}, [geoid], geoid)
        self.assertEqual(observed["overture_grocery_share_of_commercial_5mi"], 0.0)
        self.assertEqual(observed["overture_shopping_share_of_commercial_5mi"], 0.0)
        self.assertEqual(observed["overture_food_and_drink_share_of_commercial_5mi"], 0.0)
        self.assertEqual(observed["overture_basic_category_gini_simpson_diversity_5mi"], 0.0)

    def test_tract_local_and_five_mile_aggregation_are_state_isolated(self) -> None:
        mi_anchor = "26001000100"
        mi_neighbor = "26001000200"
        wi_neighbor = "55001000100"
        components = {
            mi_anchor: _component(
                mi_anchor,
                "MI",
                commercial=2,
                shopping=1,
                food=1,
                restaurant=1,
                basic_counts={"restaurant": 1, "store": 1},
            ),
            mi_neighbor: _component(
                mi_neighbor,
                "MI",
                commercial=3,
                shopping=2,
                grocery=1,
                basic_counts={"store": 3},
            ),
            wi_neighbor: _component(
                wi_neighbor,
                "WI",
                commercial=4,
                shopping=4,
                grocery=2,
                basic_counts={"store": 4},
            ),
        }
        features = aggregate_commercial_features(
            components,
            [mi_anchor, mi_neighbor],
            mi_anchor,
        )
        self.assertAlmostEqual(features["overture_log_commercial_places_tract"], math.log1p(2))
        self.assertAlmostEqual(features["overture_log_commercial_places_5mi"], math.log1p(5))
        self.assertAlmostEqual(features["overture_log_shopping_places_5mi"], math.log1p(3))
        self.assertAlmostEqual(features["overture_grocery_share_of_commercial_5mi"], 1 / 5)
        self.assertAlmostEqual(features["overture_shopping_share_of_commercial_5mi"], 3 / 5)
        self.assertAlmostEqual(features["overture_food_and_drink_share_of_commercial_5mi"], 1 / 5)
        self.assertAlmostEqual(
            features["overture_basic_category_gini_simpson_diversity_5mi"],
            1.0 - (4 / 5) ** 2 - (1 / 5) ** 2,
        )

        with self.assertRaisesRegex(ConformanceError, "MODEL14_G2_CONTEXT_STATE_MISMATCH"):
            aggregate_commercial_features(
                components,
                [mi_anchor, wi_neighbor],
                mi_anchor,
            )
        with self.assertRaisesRegex(ConformanceError, "MODEL14_G2_CONTEXT_GEOID_INVALID"):
            aggregate_commercial_features(
                components,
                [mi_neighbor],
                mi_anchor,
            )

    def test_component_and_feature_writers_are_input_order_deterministic(self) -> None:
        mi_geoid = "26001000100"
        wi_geoid = "55001000100"
        mi = _component(
            mi_geoid,
            "MI",
            commercial=3,
            shopping=2,
            grocery=1,
            basic_counts={"grocery_store": 1, "store": 2},
        )
        wi = _component(
            wi_geoid,
            "WI",
            commercial=2,
            food=2,
            restaurant=1,
            basic_counts={"restaurant": 1, "takeaway": 1},
        )
        first_components = {wi_geoid: wi, mi_geoid: mi}
        second_components = {mi_geoid: mi, wi_geoid: wi}
        first_matrix = {
            wi_geoid: {
                "tract_geoid": wi_geoid,
                "state": "WI",
                "state_fips": "55",
                **aggregate_commercial_features(first_components, [wi_geoid], wi_geoid),
            },
            mi_geoid: {
                "tract_geoid": mi_geoid,
                "state": "MI",
                "state_fips": "26",
                **aggregate_commercial_features(first_components, [mi_geoid], mi_geoid),
            },
        }
        second_matrix = {
            mi_geoid: first_matrix[mi_geoid],
            wi_geoid: first_matrix[wi_geoid],
        }

        with _temporary_files(
            "first_components.csv",
            "second_components.csv",
            "first_matrix.csv",
            "second_matrix.csv",
        ) as (
            first_component_path,
            second_component_path,
            first_matrix_path,
            second_matrix_path,
        ):
            _write_components(first_component_path, first_components)
            _write_components(second_component_path, second_components)
            _write_matrix(first_matrix_path, first_matrix)
            _write_matrix(second_matrix_path, second_matrix)
            self.assertEqual(first_component_path.read_bytes(), second_component_path.read_bytes())
            self.assertEqual(first_matrix_path.read_bytes(), second_matrix_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
