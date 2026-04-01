"""Tests for models.py — gates, GID helpers, scrubbing, money formatting."""

from __future__ import annotations

import pytest

from shopify_blade_mcp.models import (
    format_money,
    from_gid,
    get_api_version,
    get_graphql_url,
    get_store_domain,
    is_write_enabled,
    normalize_id,
    parse_order_name,
    require_confirm,
    require_write,
    scrub_secrets,
    to_gid,
)

# ---------------------------------------------------------------------------
# GID helpers
# ---------------------------------------------------------------------------


class TestToGid:
    def test_product(self) -> None:
        assert to_gid("product", 123) == "gid://shopify/Product/123"

    def test_order(self) -> None:
        assert to_gid("order", "456") == "gid://shopify/Order/456"

    def test_customer(self) -> None:
        assert to_gid("customer", 789) == "gid://shopify/Customer/789"

    def test_variant(self) -> None:
        assert to_gid("variant", 100) == "gid://shopify/ProductVariant/100"

    def test_collection(self) -> None:
        assert to_gid("collection", 50) == "gid://shopify/Collection/50"

    def test_webhook(self) -> None:
        assert to_gid("webhook", 10) == "gid://shopify/WebhookSubscription/10"

    def test_unknown_type(self) -> None:
        assert to_gid("widget", 1) == "gid://shopify/Widget/1"


class TestFromGid:
    def test_full_gid(self) -> None:
        assert from_gid("gid://shopify/Product/123") == "123"

    def test_numeric_passthrough(self) -> None:
        assert from_gid("123") == "123"

    def test_nested_gid(self) -> None:
        assert from_gid("gid://shopify/ProductVariant/456") == "456"


class TestNormalizeId:
    def test_numeric_string(self) -> None:
        assert normalize_id("product", "123") == "gid://shopify/Product/123"

    def test_full_gid(self) -> None:
        gid = "gid://shopify/Product/123"
        assert normalize_id("product", gid) == gid

    def test_different_type(self) -> None:
        assert normalize_id("order", "999") == "gid://shopify/Order/999"


class TestParseOrderName:
    def test_with_hash(self) -> None:
        assert parse_order_name("#1001") == "1001"

    def test_without_hash(self) -> None:
        assert parse_order_name("1001") == "1001"

    def test_with_spaces(self) -> None:
        assert parse_order_name(" #1001 ") == "1001"

    def test_invalid(self) -> None:
        assert parse_order_name("abc") is None

    def test_empty(self) -> None:
        assert parse_order_name("") is None


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


class TestGetStoreDomain:
    def test_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SHOPIFY_STORE_DOMAIN", "my-store.myshopify.com")
        assert get_store_domain() == "my-store.myshopify.com"

    def test_strips_protocol(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SHOPIFY_STORE_DOMAIN", "https://my-store.myshopify.com/")
        assert get_store_domain() == "my-store.myshopify.com"

    def test_missing(self) -> None:
        with pytest.raises(ValueError, match="SHOPIFY_STORE_DOMAIN is required"):
            get_store_domain()

    def test_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SHOPIFY_STORE_DOMAIN", "")
        with pytest.raises(ValueError):
            get_store_domain()


class TestGetApiVersion:
    def test_default(self) -> None:
        assert get_api_version() == "2025-04"

    def test_custom(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SHOPIFY_API_VERSION", "2026-01")
        assert get_api_version() == "2026-01"


class TestGetGraphqlUrl:
    def test_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SHOPIFY_STORE_DOMAIN", "my-store.myshopify.com")
        assert get_graphql_url() == "https://my-store.myshopify.com/admin/api/2025-04/graphql.json"

    def test_custom_version(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SHOPIFY_STORE_DOMAIN", "my-store.myshopify.com")
        monkeypatch.setenv("SHOPIFY_API_VERSION", "2026-01")
        assert get_graphql_url() == "https://my-store.myshopify.com/admin/api/2026-01/graphql.json"


# ---------------------------------------------------------------------------
# Write gate
# ---------------------------------------------------------------------------


class TestWriteGate:
    def test_disabled_by_default(self) -> None:
        assert not is_write_enabled()

    def test_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SHOPIFY_WRITE_ENABLED", "true")
        assert is_write_enabled()

    def test_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SHOPIFY_WRITE_ENABLED", "True")
        assert is_write_enabled()

    def test_require_write_disabled(self) -> None:
        result = require_write()
        assert result is not None
        assert "disabled" in result.lower()

    def test_require_write_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SHOPIFY_WRITE_ENABLED", "true")
        assert require_write() is None


# ---------------------------------------------------------------------------
# Confirm gate
# ---------------------------------------------------------------------------


class TestConfirmGate:
    def test_not_confirmed(self) -> None:
        result = require_confirm(False, "Delete product")
        assert result is not None
        assert "confirm=true" in result
        assert "Delete product" in result

    def test_confirmed(self) -> None:
        assert require_confirm(True, "Delete product") is None


# ---------------------------------------------------------------------------
# Money formatting
# ---------------------------------------------------------------------------


class TestFormatMoney:
    def test_usd(self) -> None:
        assert format_money("29.99", "USD") == "$29.99 USD"

    def test_eur(self) -> None:
        assert format_money("19.50", "EUR") == "€19.50 EUR"

    def test_gbp(self) -> None:
        assert format_money("15.00", "GBP") == "£15.00 GBP"

    def test_aud(self) -> None:
        assert format_money("45.00", "AUD") == "A$45.00 AUD"

    def test_jpy_zero_decimal(self) -> None:
        assert format_money("1000", "JPY") == "¥1000 JPY"

    def test_zero(self) -> None:
        assert format_money("0", "USD") == "$0.00 USD"

    def test_invalid_amount(self) -> None:
        assert format_money("invalid", "USD") == "invalid USD"

    def test_unknown_currency(self) -> None:
        assert format_money("10.00", "XYZ") == "10.00 XYZ"


# ---------------------------------------------------------------------------
# Token scrubbing
# ---------------------------------------------------------------------------


class TestScrubSecrets:
    def test_access_token(self) -> None:
        text = "Error: Invalid token shpat_abc123def456"
        result = scrub_secrets(text)
        assert "shpat_" not in result
        assert "****" in result

    def test_custom_app_token(self) -> None:
        text = "Auth failed: shpca_abc123"
        result = scrub_secrets(text)
        assert "shpca_" not in result

    def test_shared_secret(self) -> None:
        text = "Secret: shpss_abc123"
        result = scrub_secrets(text)
        assert "shpss_" not in result

    def test_bearer_token(self) -> None:
        text = "Authorization: Bearer super_secret_token"
        result = scrub_secrets(text)
        assert "super_secret_token" not in result

    def test_no_secrets(self) -> None:
        text = "Normal error message"
        assert scrub_secrets(text) == text

    def test_multiple_patterns(self) -> None:
        text = "Token shpat_abc123 and Bearer xyz"
        result = scrub_secrets(text)
        assert "shpat_" not in result
        assert "xyz" not in result
