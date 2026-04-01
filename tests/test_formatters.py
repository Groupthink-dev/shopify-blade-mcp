"""Tests for formatters.py — token-efficient output formatting."""

from __future__ import annotations

from shopify_blade_mcp.formatters import (
    format_analytics_result,
    format_collection_detail,
    format_collection_list,
    format_customer_detail,
    format_customer_list,
    format_date,
    format_datetime,
    format_inventory_adjustment,
    format_inventory_levels,
    format_money_set,
    format_mutation_result,
    format_order_detail,
    format_order_list,
    format_pagination,
    format_price_range,
    format_product_detail,
    format_product_list,
    format_shop_info,
    format_webhook_list,
    format_webhook_verification,
    short_id,
)

# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------


class TestFormatDatetime:
    def test_utc(self) -> None:
        assert format_datetime("2026-03-15T14:30:00Z") == "2026-03-15 14:30"

    def test_offset(self) -> None:
        assert format_datetime("2026-03-15T14:30:00+00:00") == "2026-03-15 14:30"

    def test_none(self) -> None:
        assert format_datetime(None) == "?"

    def test_empty(self) -> None:
        assert format_datetime("") == "?"


class TestFormatDate:
    def test_full_datetime(self) -> None:
        assert format_date("2026-03-15T14:30:00Z") == "2026-03-15"

    def test_date_only(self) -> None:
        assert format_date("2026-03-15") == "2026-03-15"

    def test_none(self) -> None:
        assert format_date(None) == "?"


# ---------------------------------------------------------------------------
# Money helpers
# ---------------------------------------------------------------------------


class TestFormatMoneySet:
    def test_shop_money(self) -> None:
        result = format_money_set({"shopMoney": {"amount": "29.99", "currencyCode": "USD"}})
        assert result == "$29.99 USD"

    def test_direct_money(self) -> None:
        result = format_money_set({"amount": "10.00", "currencyCode": "EUR"})
        assert result == "€10.00 EUR"

    def test_none(self) -> None:
        assert format_money_set(None) == "?"


class TestFormatPriceRange:
    def test_single_price(self) -> None:
        pr = {
            "minVariantPrice": {"amount": "29.99", "currencyCode": "USD"},
            "maxVariantPrice": {"amount": "29.99", "currencyCode": "USD"},
        }
        assert format_price_range(pr) == "$29.99 USD"

    def test_range(self) -> None:
        pr = {
            "minVariantPrice": {"amount": "19.99", "currencyCode": "USD"},
            "maxVariantPrice": {"amount": "39.99", "currencyCode": "USD"},
        }
        result = format_price_range(pr)
        assert "$19.99" in result
        assert "$39.99" in result

    def test_none(self) -> None:
        assert format_price_range(None) == "?"


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class TestFormatPagination:
    def test_has_next(self) -> None:
        edges = [{"cursor": "abc123"}]
        page_info = {"hasNextPage": True}
        result = format_pagination(edges, page_info, 1)
        assert 'after="abc123"' in result

    def test_no_next(self) -> None:
        edges = [{"cursor": "abc123"}]
        page_info = {"hasNextPage": False}
        assert format_pagination(edges, page_info, 1) == ""

    def test_none_page_info(self) -> None:
        assert format_pagination([], None, 0) == ""


# ---------------------------------------------------------------------------
# Short ID
# ---------------------------------------------------------------------------


class TestShortId:
    def test_gid(self) -> None:
        assert short_id("gid://shopify/Product/123") == "123"

    def test_none(self) -> None:
        assert short_id(None) == "?"

    def test_numeric(self) -> None:
        assert short_id("456") == "456"


# ---------------------------------------------------------------------------
# Product formatters
# ---------------------------------------------------------------------------


class TestFormatProductList:
    def test_with_products(self, sample_product_list: dict) -> None:
        result = format_product_list(sample_product_list)
        assert "Classic T-Shirt" in result
        assert "Denim Jacket" in result
        assert "123" in result
        assert "active" in result
        assert "draft" in result
        assert "TestBrand" in result
        assert "inv=150" in result

    def test_empty(self) -> None:
        result = format_product_list({"products": {"edges": []}})
        assert "No products found" in result

    def test_pagination_hint(self, sample_product_list: dict) -> None:
        result = format_product_list(sample_product_list)
        assert "more results" in result
        assert "cursor_def" in result


class TestFormatProductDetail:
    def test_full_product(self, sample_product_detail: dict) -> None:
        result = format_product_detail(sample_product_detail)
        assert "Classic T-Shirt" in result
        assert "123" in result
        assert "active" in result
        assert "TestBrand" in result
        assert "Shirts" in result
        assert "$29.99" in result
        assert "Variants" in result
        assert "TSH-S" in result
        assert "S, M, L, XL" in result
        assert "SEO" in result

    def test_not_found(self) -> None:
        assert "not found" in format_product_detail({"product": None})


# ---------------------------------------------------------------------------
# Order formatters
# ---------------------------------------------------------------------------


class TestFormatOrderList:
    def test_with_orders(self, sample_order_list: dict) -> None:
        result = format_order_list(sample_order_list)
        assert "#1001" in result
        assert "paid" in result
        assert "unfulfilled" in result
        assert "$59.98" in result
        assert "John Doe" in result

    def test_empty(self) -> None:
        result = format_order_list({"orders": {"edges": []}})
        assert "No orders found" in result


class TestFormatOrderDetail:
    def test_full_order(self, sample_order_detail: dict) -> None:
        result = format_order_detail(sample_order_detail)
        assert "#1001" in result
        assert "paid" in result
        assert "unfulfilled" in result
        assert "John Doe" in result
        assert "$64.97" in result
        assert "Classic T-Shirt" in result
        assert "123 Main St" in result
        assert "SALE" in result
        assert "shopify_payments" in result
        assert "gift wrap" in result
        assert "rush" in result

    def test_not_found(self) -> None:
        assert "not found" in format_order_detail({"order": None})


# ---------------------------------------------------------------------------
# Customer formatters
# ---------------------------------------------------------------------------


class TestFormatCustomerList:
    def test_with_customers(self, sample_customer_list: dict) -> None:
        result = format_customer_list(sample_customer_list)
        assert "John Doe" in result
        assert "john@example.com" in result
        assert "enabled" in result
        assert "orders=5" in result

    def test_empty(self) -> None:
        result = format_customer_list({"customers": {"edges": []}})
        assert "No customers found" in result


class TestFormatCustomerDetail:
    def test_full_customer(self) -> None:
        data = {
            "customer": {
                "id": "gid://shopify/Customer/500",
                "displayName": "John Doe",
                "firstName": "John",
                "lastName": "Doe",
                "email": "john@example.com",
                "phone": "+15551234567",
                "state": "ENABLED",
                "numberOfOrders": "5",
                "amountSpent": {"amount": "299.95", "currencyCode": "USD"},
                "createdAt": "2026-01-15T10:00:00Z",
                "updatedAt": "2026-03-25T15:30:00Z",
                "tags": ["VIP"],
                "note": "Loyal customer",
                "verifiedEmail": True,
                "taxExempt": False,
                "taxExemptions": [],
                "defaultAddress": {
                    "address1": "123 Main St",
                    "address2": None,
                    "city": "New York",
                    "province": "NY",
                    "country": "US",
                    "zip": "10001",
                    "phone": "+15551234567",
                },
                "addresses": [],
            }
        }
        result = format_customer_detail(data)
        assert "John Doe" in result
        assert "john@example.com" in result
        assert "verified" in result
        assert "VIP" in result
        assert "Loyal customer" in result

    def test_not_found(self) -> None:
        assert "not found" in format_customer_detail({"customer": None})


# ---------------------------------------------------------------------------
# Inventory formatters
# ---------------------------------------------------------------------------


class TestFormatInventoryLevels:
    def test_with_location(self) -> None:
        data = {
            "location": {
                "id": "gid://shopify/Location/1",
                "name": "Main Warehouse",
                "inventoryLevels": {
                    "edges": [
                        {
                            "node": {
                                "id": "gid://shopify/InventoryLevel/1",
                                "quantities": [
                                    {"name": "available", "quantity": 50},
                                    {"name": "committed", "quantity": 5},
                                    {"name": "on_hand", "quantity": 55},
                                ],
                                "item": {
                                    "id": "gid://shopify/InventoryItem/1",
                                    "sku": "TSH-M",
                                    "variant": {
                                        "id": "gid://shopify/ProductVariant/101",
                                        "title": "M",
                                        "product": {"id": "gid://shopify/Product/123", "title": "Classic T-Shirt"},
                                    },
                                },
                            },
                            "cursor": "inv_cursor",
                        }
                    ],
                    "pageInfo": {"hasNextPage": False},
                },
            }
        }
        result = format_inventory_levels(data)
        assert "Main Warehouse" in result
        assert "Classic T-Shirt" in result
        assert "TSH-M" in result
        assert "avail=50" in result
        assert "committed=5" in result

    def test_locations_list(self) -> None:
        data = {
            "locations": {
                "edges": [
                    {
                        "node": {
                            "id": "gid://shopify/Location/1",
                            "name": "Main Warehouse",
                            "isActive": True,
                            "address": {
                                "address1": "123 Industrial Ave",
                                "city": "NYC",
                                "province": "NY",
                                "country": "US",
                            },
                        }
                    }
                ]
            }
        }
        result = format_inventory_levels(data)
        assert "Locations" in result
        assert "Main Warehouse" in result
        assert "active" in result


class TestFormatInventoryAdjustment:
    def test_adjustment(self) -> None:
        data = {
            "inventoryAdjustQuantities": {
                "inventoryAdjustmentGroup": {
                    "reason": "correction",
                    "changes": [
                        {
                            "name": "available",
                            "delta": 10,
                            "quantityAfterChange": 60,
                            "item": {"id": "gid://shopify/InventoryItem/1", "sku": "TSH-M"},
                            "location": {"id": "gid://shopify/Location/1", "name": "Main Warehouse"},
                        }
                    ],
                }
            }
        }
        result = format_inventory_adjustment(data)
        assert "correction" in result
        assert "+10" in result
        assert "60" in result
        assert "TSH-M" in result


# ---------------------------------------------------------------------------
# Collection formatters
# ---------------------------------------------------------------------------


class TestFormatCollectionList:
    def test_with_collections(self) -> None:
        data = {
            "collections": {
                "edges": [
                    {
                        "node": {
                            "id": "gid://shopify/Collection/10",
                            "title": "Summer Sale",
                            "handle": "summer-sale",
                            "sortOrder": "BEST_SELLING",
                            "productsCount": {"count": 25},
                            "updatedAt": "2026-03-20T10:00:00Z",
                        },
                        "cursor": "coll_cursor",
                    }
                ],
                "pageInfo": {"hasNextPage": False},
            }
        }
        result = format_collection_list(data)
        assert "Summer Sale" in result
        assert "25 products" in result
        assert "BEST_SELLING" in result


class TestFormatCollectionDetail:
    def test_smart_collection(self) -> None:
        data = {
            "collection": {
                "id": "gid://shopify/Collection/10",
                "title": "Summer Sale",
                "handle": "summer-sale",
                "descriptionHtml": "<p>Summer items</p>",
                "sortOrder": "BEST_SELLING",
                "productsCount": {"count": 25},
                "updatedAt": "2026-03-20T10:00:00Z",
                "ruleSet": {
                    "appliedDisjunctively": False,
                    "rules": [{"column": "TAG", "relation": "EQUALS", "condition": "summer"}],
                },
                "seo": {"title": "Summer Sale", "description": None},
                "image": None,
            }
        }
        result = format_collection_detail(data)
        assert "Summer Sale" in result
        assert "Rules" in result
        assert "TAG" in result
        assert "ALL" in result


# ---------------------------------------------------------------------------
# Webhook formatters
# ---------------------------------------------------------------------------


class TestFormatWebhookList:
    def test_with_webhooks(self) -> None:
        data = {
            "webhookSubscriptions": {
                "edges": [
                    {
                        "node": {
                            "id": "gid://shopify/WebhookSubscription/1",
                            "topic": "ORDERS_CREATE",
                            "endpoint": {"callbackUrl": "https://example.com/webhook"},
                            "format": "JSON",
                            "createdAt": "2026-03-01T10:00:00Z",
                            "updatedAt": "2026-03-01T10:00:00Z",
                        },
                        "cursor": "wh_cursor",
                    }
                ],
                "pageInfo": {"hasNextPage": False},
            }
        }
        result = format_webhook_list(data)
        assert "ORDERS_CREATE" in result
        assert "https://example.com/webhook" in result

    def test_empty(self) -> None:
        result = format_webhook_list({"webhookSubscriptions": {"edges": []}})
        assert "No webhook" in result


class TestFormatWebhookVerification:
    def test_valid(self) -> None:
        result = format_webhook_verification({"valid": True})
        assert "VALID" in result

    def test_invalid(self) -> None:
        result = format_webhook_verification({"valid": False, "error": "Signature mismatch"})
        assert "INVALID" in result
        assert "mismatch" in result


# ---------------------------------------------------------------------------
# Shop formatters
# ---------------------------------------------------------------------------


class TestFormatShopInfo:
    def test_full_shop(self) -> None:
        data = {
            "shop": {
                "id": "gid://shopify/Shop/1",
                "name": "Test Store",
                "email": "owner@test.com",
                "url": "https://test-store.myshopify.com",
                "myshopifyDomain": "test-store.myshopify.com",
                "primaryDomain": {"url": "https://test-store.com", "host": "test-store.com"},
                "plan": {"displayName": "Basic", "partnerDevelopment": False, "shopifyPlus": False},
                "currencyCode": "USD",
                "weightUnit": "POUNDS",
                "timezoneAbbreviation": "EST",
                "ianaTimezone": "America/New_York",
                "billingAddress": {
                    "address1": "123 Main St",
                    "city": "New York",
                    "province": "NY",
                    "country": "US",
                    "zip": "10001",
                },
                "features": {"storefront": True},
            }
        }
        result = format_shop_info(data)
        assert "Test Store" in result
        assert "test-store.myshopify.com" in result
        assert "test-store.com" in result
        assert "Basic" in result
        assert "USD" in result

    def test_not_available(self) -> None:
        assert "not available" in format_shop_info({"shop": None})


# ---------------------------------------------------------------------------
# Analytics formatters
# ---------------------------------------------------------------------------


class TestFormatAnalyticsResult:
    def test_table_response(self) -> None:
        data = {
            "shopifyqlQuery": {
                "__typename": "TableResponse",
                "tableData": {
                    "columns": [
                        {"name": "day", "dataType": "DATE"},
                        {"name": "total_sales", "dataType": "MONEY"},
                    ],
                    "rowData": [
                        ["2026-03-25", "$100.00"],
                        ["2026-03-26", "$150.00"],
                    ],
                },
                "parseErrors": [],
            }
        }
        result = format_analytics_result(data)
        assert "day" in result
        assert "total_sales" in result
        assert "$100.00" in result
        assert "$150.00" in result

    def test_parse_error(self) -> None:
        data = {
            "shopifyqlQuery": {
                "__typename": "TableResponse",
                "parseErrors": [
                    {
                        "code": "SYNTAX_ERROR",
                        "message": "Unexpected token",
                        "range": {
                            "start": {"line": 1, "character": 5},
                            "end": {"line": 1, "character": 10},
                        },
                    },
                ],
            }
        }
        result = format_analytics_result(data)
        assert "parse error" in result.lower()
        assert "Unexpected token" in result


# ---------------------------------------------------------------------------
# Mutation result formatters
# ---------------------------------------------------------------------------


class TestFormatMutationResult:
    def test_created(self) -> None:
        data = {"productCreate": {"product": {"id": "gid://shopify/Product/123", "title": "New Product"}}}
        result = format_mutation_result(data, "product", "created")
        assert "123" in result
        assert "New Product" in result

    def test_deleted(self) -> None:
        data = {"productDelete": {"deletedProductId": "gid://shopify/Product/123"}}
        result = format_mutation_result(data, "product", "deleted")
        assert "deleted" in result.lower()
        assert "123" in result
