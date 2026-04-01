"""Shared fixtures for Shopify Blade MCP tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure clean env for every test — no real API keys leak."""
    monkeypatch.delenv("SHOPIFY_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("SHOPIFY_STORE_DOMAIN", raising=False)
    monkeypatch.delenv("SHOPIFY_WRITE_ENABLED", raising=False)
    monkeypatch.delenv("SHOPIFY_API_VERSION", raising=False)
    monkeypatch.delenv("SHOPIFY_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("SHOPIFY_MCP_TRANSPORT", raising=False)
    monkeypatch.delenv("SHOPIFY_MCP_API_TOKEN", raising=False)
    # Reset client singleton
    import shopify_blade_mcp.server as server_mod

    server_mod._client = None


@pytest.fixture
def store_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up test store env vars."""
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "shpat_test_token_12345")
    monkeypatch.setenv("SHOPIFY_STORE_DOMAIN", "test-store.myshopify.com")


@pytest.fixture
def write_env(store_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up env with write access."""
    monkeypatch.setenv("SHOPIFY_WRITE_ENABLED", "true")


@pytest.fixture
def webhook_env(store_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up env with webhook secret."""
    monkeypatch.setenv("SHOPIFY_WEBHOOK_SECRET", "test_webhook_secret_123")


@pytest.fixture
def mock_client(store_env: None) -> AsyncMock:
    """Provide a mocked ShopifyClient."""
    mock = AsyncMock()
    mock.store_domain = "test-store.myshopify.com"
    mock.last_cost = None
    patcher = patch("shopify_blade_mcp.server._get_client", return_value=mock)
    patcher.start()
    yield mock
    patcher.stop()


@pytest.fixture
def mock_write_client(write_env: None) -> AsyncMock:
    """Provide a mocked ShopifyClient with write access."""
    mock = AsyncMock()
    mock.store_domain = "test-store.myshopify.com"
    mock.last_cost = None
    patcher = patch("shopify_blade_mcp.server._get_client", return_value=mock)
    patcher.start()
    yield mock
    patcher.stop()


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_product_list() -> dict:
    """Sample product list response."""
    return {
        "products": {
            "edges": [
                {
                    "node": {
                        "id": "gid://shopify/Product/123",
                        "title": "Classic T-Shirt",
                        "handle": "classic-t-shirt",
                        "status": "ACTIVE",
                        "productType": "Shirts",
                        "vendor": "TestBrand",
                        "tags": ["summer", "cotton"],
                        "createdAt": "2026-03-15T10:00:00Z",
                        "updatedAt": "2026-03-20T14:30:00Z",
                        "totalInventory": 150,
                        "tracksInventory": True,
                        "priceRangeV2": {
                            "minVariantPrice": {"amount": "29.99", "currencyCode": "USD"},
                            "maxVariantPrice": {"amount": "39.99", "currencyCode": "USD"},
                        },
                    },
                    "cursor": "cursor_abc",
                },
                {
                    "node": {
                        "id": "gid://shopify/Product/456",
                        "title": "Denim Jacket",
                        "handle": "denim-jacket",
                        "status": "DRAFT",
                        "productType": "Outerwear",
                        "vendor": "TestBrand",
                        "tags": ["winter"],
                        "createdAt": "2026-03-16T11:00:00Z",
                        "updatedAt": "2026-03-21T09:00:00Z",
                        "totalInventory": 50,
                        "tracksInventory": True,
                        "priceRangeV2": {
                            "minVariantPrice": {"amount": "89.99", "currencyCode": "USD"},
                            "maxVariantPrice": {"amount": "89.99", "currencyCode": "USD"},
                        },
                    },
                    "cursor": "cursor_def",
                },
            ],
            "pageInfo": {"hasNextPage": True},
        }
    }


@pytest.fixture
def sample_product_detail() -> dict:
    """Sample single product response."""
    return {
        "product": {
            "id": "gid://shopify/Product/123",
            "title": "Classic T-Shirt",
            "handle": "classic-t-shirt",
            "descriptionHtml": "<p>A classic cotton t-shirt.</p>",
            "status": "ACTIVE",
            "productType": "Shirts",
            "vendor": "TestBrand",
            "tags": ["summer", "cotton"],
            "createdAt": "2026-03-15T10:00:00Z",
            "updatedAt": "2026-03-20T14:30:00Z",
            "totalInventory": 150,
            "tracksInventory": True,
            "onlineStoreUrl": "https://test-store.com/products/classic-t-shirt",
            "options": [{"id": "gid://shopify/ProductOption/1", "name": "Size", "values": ["S", "M", "L", "XL"]}],
            "priceRangeV2": {
                "minVariantPrice": {"amount": "29.99", "currencyCode": "USD"},
                "maxVariantPrice": {"amount": "39.99", "currencyCode": "USD"},
            },
            "variants": {
                "edges": [
                    {
                        "node": {
                            "id": "gid://shopify/ProductVariant/100",
                            "title": "S",
                            "sku": "TSH-S",
                            "price": "29.99",
                            "compareAtPrice": None,
                            "inventoryQuantity": 40,
                            "selectedOptions": [{"name": "Size", "value": "S"}],
                        }
                    },
                    {
                        "node": {
                            "id": "gid://shopify/ProductVariant/101",
                            "title": "M",
                            "sku": "TSH-M",
                            "price": "29.99",
                            "compareAtPrice": None,
                            "inventoryQuantity": 60,
                            "selectedOptions": [{"name": "Size", "value": "M"}],
                        }
                    },
                ]
            },
            "images": {
                "edges": [
                    {
                        "node": {
                            "id": "gid://shopify/MediaImage/1",
                            "url": "https://cdn.shopify.com/test.jpg",
                            "altText": "Front view",
                        },
                    }
                ]
            },
            "seo": {"title": "Classic T-Shirt | TestBrand", "description": "Premium cotton t-shirt"},
        }
    }


@pytest.fixture
def sample_order_list() -> dict:
    """Sample order list response."""
    return {
        "orders": {
            "edges": [
                {
                    "node": {
                        "id": "gid://shopify/Order/1001",
                        "name": "#1001",
                        "createdAt": "2026-03-25T15:30:00Z",
                        "displayFinancialStatus": "PAID",
                        "displayFulfillmentStatus": "UNFULFILLED",
                        "totalPriceSet": {"shopMoney": {"amount": "59.98", "currencyCode": "USD"}},
                        "subtotalPriceSet": {"shopMoney": {"amount": "59.98", "currencyCode": "USD"}},
                        "totalTaxSet": {"shopMoney": {"amount": "0.00", "currencyCode": "USD"}},
                        "customer": {
                            "id": "gid://shopify/Customer/500",
                            "displayName": "John Doe",
                            "email": "john@example.com",
                        },
                        "lineItems": {
                            "edges": [
                                {
                                    "node": {
                                        "title": "Classic T-Shirt",
                                        "quantity": 2,
                                        "originalTotalSet": {
                                            "shopMoney": {
                                                "amount": "59.98",
                                                "currencyCode": "USD",
                                            },
                                        },
                                    }
                                },
                            ]
                        },
                    },
                    "cursor": "order_cursor_1",
                }
            ],
            "pageInfo": {"hasNextPage": False},
        }
    }


@pytest.fixture
def sample_order_detail() -> dict:
    """Sample single order response."""
    return {
        "order": {
            "id": "gid://shopify/Order/1001",
            "name": "#1001",
            "createdAt": "2026-03-25T15:30:00Z",
            "updatedAt": "2026-03-25T16:00:00Z",
            "closedAt": None,
            "cancelledAt": None,
            "cancelReason": None,
            "displayFinancialStatus": "PAID",
            "displayFulfillmentStatus": "UNFULFILLED",
            "note": "Please gift wrap",
            "tags": ["rush", "gift"],
            "totalPriceSet": {"shopMoney": {"amount": "64.97", "currencyCode": "USD"}},
            "subtotalPriceSet": {"shopMoney": {"amount": "59.98", "currencyCode": "USD"}},
            "totalTaxSet": {"shopMoney": {"amount": "4.99", "currencyCode": "USD"}},
            "totalShippingPriceSet": {"shopMoney": {"amount": "0.00", "currencyCode": "USD"}},
            "totalDiscountsSet": {"shopMoney": {"amount": "0.00", "currencyCode": "USD"}},
            "totalRefundedSet": {"shopMoney": {"amount": "0.00", "currencyCode": "USD"}},
            "currentTotalPriceSet": {"shopMoney": {"amount": "64.97", "currencyCode": "USD"}},
            "customer": {
                "id": "gid://shopify/Customer/500",
                "displayName": "John Doe",
                "email": "john@example.com",
                "phone": "+15551234567",
            },
            "shippingAddress": {
                "address1": "123 Main St",
                "address2": None,
                "city": "New York",
                "province": "NY",
                "country": "US",
                "zip": "10001",
            },
            "billingAddress": {
                "address1": "123 Main St",
                "city": "New York",
                "province": "NY",
                "country": "US",
                "zip": "10001",
            },
            "lineItems": {
                "edges": [
                    {
                        "node": {
                            "id": "gid://shopify/LineItem/1",
                            "title": "Classic T-Shirt",
                            "quantity": 2,
                            "sku": "TSH-M",
                            "originalTotalSet": {"shopMoney": {"amount": "59.98", "currencyCode": "USD"}},
                            "variant": {"id": "gid://shopify/ProductVariant/101", "title": "M"},
                        }
                    },
                ]
            },
            "fulfillments": [],
            "refunds": [],
            "transactions": [
                {
                    "id": "gid://shopify/OrderTransaction/1",
                    "kind": "SALE",
                    "status": "SUCCESS",
                    "amountSet": {"shopMoney": {"amount": "64.97", "currencyCode": "USD"}},
                    "gateway": "shopify_payments",
                    "createdAt": "2026-03-25T15:30:00Z",
                }
            ],
        }
    }


@pytest.fixture
def sample_customer_list() -> dict:
    """Sample customer list response."""
    return {
        "customers": {
            "edges": [
                {
                    "node": {
                        "id": "gid://shopify/Customer/500",
                        "displayName": "John Doe",
                        "email": "john@example.com",
                        "phone": "+15551234567",
                        "state": "ENABLED",
                        "numberOfOrders": "5",
                        "amountSpent": {"amount": "299.95", "currencyCode": "USD"},
                        "createdAt": "2026-01-15T10:00:00Z",
                        "updatedAt": "2026-03-25T15:30:00Z",
                        "tags": ["VIP"],
                        "verifiedEmail": True,
                    },
                    "cursor": "cust_cursor_1",
                }
            ],
            "pageInfo": {"hasNextPage": False},
        }
    }
