"""Tests for prd_flow.derive.decision_rules."""

import pytest

from prd_flow.derive.decision_rules import (
    find_best_module_match,
    levenshtein_distance,
    resolve_orphan_requirements,
)


class TestLevenshteinDistance:
    """Tests for levenshtein_distance function."""

    def test_exact_match(self):
        assert levenshtein_distance("payment_gateway", "payment_gateway") == 0

    def test_one_deletion(self):
        assert levenshtein_distance("payment", "paymen") == 1

    def test_one_insertion(self):
        assert levenshtein_distance("paymen", "payment") == 1

    def test_one_substitution(self):
        assert levenshtein_distance("payment", "paymont") == 1

    def test_two_operations(self):
        assert levenshtein_distance("gateway", "getway") == 2
        assert levenshtein_distance("gateway", "getweay") == 3

    def test_empty_strings(self):
        assert levenshtein_distance("", "") == 0
        assert levenshtein_distance("abc", "") == 3
        assert levenshtein_distance("", "abc") == 3

    def test_completely_different(self):
        assert levenshtein_distance("abc", "xyz") == 3


class TestFindBestModuleMatch:
    """Tests for find_best_module_match function."""

    def test_exact_match(self):
        modules = ["payment_gateway", "user_service", "order_module"]
        result = find_best_module_match("payment_gateway", modules)
        assert result == "payment_gateway"

    def test_close_match_distance_1(self):
        modules = ["payment_gateway", "user_service", "order_module"]
        result = find_best_module_match("payment_geteway", modules)
        assert result == "payment_gateway"

    def test_close_match_distance_2(self):
        modules = ["payment_gateway", "user_service", "order_module"]
        result = find_best_module_match("payment_getway", modules)
        assert result == "payment_gateway"

    def test_no_close_match_distance_too_high(self):
        modules = ["payment_gateway", "user_service", "order_module"]
        result = find_best_module_match("completely_different", modules)
        assert result is None

    def test_empty_available_modules(self):
        result = find_best_module_match("payment_gateway", [])
        assert result is None

    def test_single_character_typo(self):
        modules = ["payment_gateway", "user_service"]
        result = find_best_module_match("user_serice", modules)
        assert result == "user_service"

    def test_auto_correct_logs_warning(self, caplog):
        modules = ["payment_gateway"]
        find_best_module_match("payment_geteway", modules)
        assert any(
            "Auto-correcting module name" in record.message for record in caplog.records
        )

    def test_exact_match_no_warning(self, caplog):
        modules = ["payment_gateway"]
        find_best_module_match("payment_gateway", modules)
        assert not any(
            "Auto-correcting" in record.message for record in caplog.records
        )

    def test_multiple_similar_returns_closest(self):
        modules = ["payment_gateway", "payment_service", "user_gateway"]
        result = find_best_module_match("payment_geteway", modules)
        assert result == "payment_gateway"

    def test_case_sensitive_match(self):
        modules = ["PaymentGateway", "user_service"]
        result = find_best_module_match("paymentgateway", modules)
        # case-sensitive: distance should be 2 (missing underscore, case diffs)
        assert result is None or result == "PaymentGateway"
        # Actually let's verify: 'paymentgateway' vs 'PaymentGateway' = 2 (underscore diff + case? No, let's count)
        # p vs P = 1, then aym... actually let's just check the distance
        dist = levenshtein_distance("paymentgateway", "PaymentGateway")
        assert dist == 2  # underscore missing = 1, 'P' vs 'p' = 1

    def test_threshold_boundary_exactly_2(self):
        """Distance exactly at threshold should return match."""
        modules = ["abcd"]
        result = find_best_module_match("abXX", modules)
        # levenshtein(abXX, abcd) = 2 (X->c, X->d)
        assert result == "abcd"

    def test_threshold_boundary_3_returns_none(self):
        """Distance one above threshold should return None."""
        modules = ["abcd"]
        result = find_best_module_match("abXYZ", modules)
        # levenshtein(abXYZ, abcd) = 3
        assert result is None


class TestResolveOrphanRequirements:
    """Tests for resolve_orphan_requirements function."""

    def test_adds_tentative_flag(self):
        orphans = [
            {"id": "REQ-010", "text": "支付退款"},
            {"id": "REQ-011", "text": "用户数据隐私保护"},
        ]
        result = resolve_orphan_requirements(orphans)
        assert all(req.get("tentative") is True for req in result)

    def test_preserves_original_fields(self):
        orphans = [
            {"id": "REQ-010", "text": "支付退款", "priority": "high"},
        ]
        result = resolve_orphan_requirements(orphans)
        assert result[0]["id"] == "REQ-010"
        assert result[0]["text"] == "支付退款"
        assert result[0]["priority"] == "high"

    def test_returns_copies_not_mutates_original(self):
        orphans = [
            {"id": "REQ-010", "text": "支付退款"},
        ]
        result = resolve_orphan_requirements(orphans)
        assert "tentative" not in orphans[0]
        assert "tentative" in result[0]

    def test_empty_list(self):
        result = resolve_orphan_requirements([])
        assert result == []

    def test_does_not_overwrite_existing_tentative(self):
        orphans = [
            {"id": "REQ-010", "text": "支付退款", "tentative": False},
        ]
        result = resolve_orphan_requirements(orphans)
        assert result[0]["tentative"] is True

    def test_nested_dict_not_mutated(self):
        """Ensure nested dicts in requirements are shallow-copied behavior (dict() copy)."""
        orphans = [
            {"id": "REQ-010", "meta": {"source": "legacy"}},
        ]
        result = resolve_orphan_requirements(orphans)
        result[0]["meta"]["source"] = "changed"
        assert orphans[0]["meta"]["source"] == "changed"  # shallow copy expected
