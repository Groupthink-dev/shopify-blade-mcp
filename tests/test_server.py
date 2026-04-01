"""Tests for server.py — MCP tool integration tests."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from shopify_blade_mcp.server import (
    shopify_add_order_tags,
    shopify_adjust_inventory,
    shopify_analytics,
    shopify_cancel_order,
    shopify_close_order,
    shopify_collection,
    shopify_collection_add_products,
    shopify_collections,
    shopify_create_collection,
    shopify_create_customer,
    shopify_create_discount,
    shopify_create_fulfillment,
    shopify_create_product,
    shopify_create_webhook,
    shopify_customer,
    shopify_customers,
    shopify_delete_discount,
    shopify_delete_metafield,
    shopify_delete_product,
    shopify_delete_webhook,
    shopify_discounts,
    shopify_info,
    shopify_inventory,
    shopify_locations,
    shopify_metafields,
    shopify_order,
    shopify_order_fulfillments,
    shopify_orders,
    shopify_product,
    shopify_products,
    shopify_search_customers,
    shopify_search_orders,
    shopify_set_inventory,
    shopify_set_metafield,
    shopify_shop,
    shopify_update_customer,
    shopify_update_order_note,
    shopify_update_product,
    shopify_update_tracking,
    shopify_verify_webhook,
    shopify_webhooks,
)

# ===========================================================================
# Meta tools
# ===========================================================================


class TestShopifyInfo:
    async def test_connected(self, mock_client: AsyncMock) -> None:
        result = await shopify_info()
        assert "test-store" in result
        assert "connected" in result
        assert "disabled" in result  # write gate off by default

    async def test_write_enabled(self, mock_write_client: AsyncMock, monkeypatch: pytest.MonkeyPatch) -> None:
        result = await shopify_info()
        assert "enabled" in result


class TestShopifyShop:
    async def test_shop_info(self, mock_client: AsyncMock) -> None:
        mock_client.get_shop.return_value = {
            "shop": {
                "name": "Test Store",
                "myshopifyDomain": "test-store.myshopify.com",
                "email": "owner@test.com",
                "plan": {"displayName": "Basic", "partnerDevelopment": False, "shopifyPlus": False},
                "currencyCode": "USD",
                "timezoneAbbreviation": "EST",
                "ianaTimezone": "America/New_York",
                "primaryDomain": {"host": "test-store.com", "url": "https://test-store.com"},
                "billingAddress": None,
                "features": {"storefront": True},
            }
        }
        result = await shopify_shop()
        assert "Test Store" in result
        assert "USD" in result


class TestShopifyLocations:
    async def test_locations(self, mock_client: AsyncMock) -> None:
        mock_client.get_locations.return_value = {
            "locations": {
                "edges": [
                    {
                        "node": {
                            "id": "gid://shopify/Location/1",
                            "name": "Warehouse",
                            "isActive": True,
                            "isPrimary": True,
                            "fulfillmentService": None,
                            "address": {
                                "address1": "123 Main",
                                "city": "NYC",
                                "province": "NY",
                                "country": "US",
                                "zip": "10001",
                            },
                        }
                    }
                ]
            }
        }
        result = await shopify_locations()
        assert "Warehouse" in result


# ===========================================================================
# Product tools
# ===========================================================================


class TestProductTools:
    async def test_list_products(self, mock_client: AsyncMock, sample_product_list: dict) -> None:
        mock_client.list_products.return_value = sample_product_list
        result = await shopify_products()
        assert "Classic T-Shirt" in result
        assert "Denim Jacket" in result

    async def test_list_products_with_query(self, mock_client: AsyncMock, sample_product_list: dict) -> None:
        mock_client.list_products.return_value = sample_product_list
        await shopify_products(query="status:active")
        mock_client.list_products.assert_called_once_with(query="status:active", limit=20, after=None)

    async def test_get_product(self, mock_client: AsyncMock, sample_product_detail: dict) -> None:
        mock_client.get_product.return_value = sample_product_detail
        result = await shopify_product(id="123")
        assert "Classic T-Shirt" in result
        assert "Variants" in result

    async def test_create_product_write_disabled(self, mock_client: AsyncMock) -> None:
        result = await shopify_create_product(title="New Product")
        assert "disabled" in result.lower()

    async def test_create_product_write_enabled(self, mock_write_client: AsyncMock) -> None:
        mock_write_client.create_product.return_value = {
            "productCreate": {
                "product": {
                    "id": "gid://shopify/Product/999",
                    "title": "New Product",
                    "handle": "new-product",
                    "status": "DRAFT",
                },
                "userErrors": [],
            }
        }
        result = await shopify_create_product(title="New Product", vendor="TestBrand", tags="summer,cotton")
        assert "999" in result

    async def test_update_product_write_disabled(self, mock_client: AsyncMock) -> None:
        result = await shopify_update_product(id="123", title="Updated")
        assert "disabled" in result.lower()

    async def test_delete_product_no_confirm(self, mock_write_client: AsyncMock) -> None:
        result = await shopify_delete_product(id="123")
        assert "confirm=true" in result

    async def test_delete_product_confirmed(self, mock_write_client: AsyncMock) -> None:
        mock_write_client.delete_product.return_value = {
            "productDelete": {
                "deletedProductId": "gid://shopify/Product/123",
                "userErrors": [],
            }
        }
        result = await shopify_delete_product(id="123", confirm=True)
        assert "deleted" in result.lower()


# ===========================================================================
# Order tools
# ===========================================================================


class TestOrderTools:
    async def test_list_orders(self, mock_client: AsyncMock, sample_order_list: dict) -> None:
        mock_client.list_orders.return_value = sample_order_list
        result = await shopify_orders()
        assert "#1001" in result

    async def test_get_order_by_id(self, mock_client: AsyncMock, sample_order_detail: dict) -> None:
        mock_client.get_order.return_value = sample_order_detail
        result = await shopify_order(id="gid://shopify/Order/1001")
        assert "#1001" in result
        assert "John Doe" in result

    async def test_get_order_by_name(
        self,
        mock_client: AsyncMock,
        sample_order_detail: dict,
        sample_order_list: dict,
    ) -> None:
        mock_client.search_orders_by_name.return_value = sample_order_list
        mock_client.get_order.return_value = sample_order_detail
        result = await shopify_order(id="#1001")
        assert "#1001" in result

    async def test_search_orders(self, mock_client: AsyncMock, sample_order_list: dict) -> None:
        mock_client.list_orders.return_value = sample_order_list
        result = await shopify_search_orders(financial_status="paid", fulfillment_status="unfulfilled")
        assert "#1001" in result

    async def test_update_order_note_write_disabled(self, mock_client: AsyncMock) -> None:
        result = await shopify_update_order_note(id="1001", note="Test note")
        assert "disabled" in result.lower()

    async def test_close_order_write_disabled(self, mock_client: AsyncMock) -> None:
        result = await shopify_close_order(id="1001")
        assert "disabled" in result.lower()

    async def test_cancel_order_no_confirm(self, mock_write_client: AsyncMock) -> None:
        result = await shopify_cancel_order(id="1001")
        assert "confirm=true" in result

    async def test_cancel_order_confirmed(self, mock_write_client: AsyncMock) -> None:
        mock_write_client.cancel_order.return_value = {"orderCancel": {"orderCancelUserErrors": []}}
        result = await shopify_cancel_order(id="1001", confirm=True)
        assert "cancelled" in result.lower()

    async def test_add_order_tags_write_disabled(self, mock_client: AsyncMock) -> None:
        result = await shopify_add_order_tags(id="1001", tags="rush,priority")
        assert "disabled" in result.lower()

    async def test_order_fulfillments(self, mock_client: AsyncMock) -> None:
        mock_client.list_fulfillment_orders.return_value = {
            "order": {
                "fulfillmentOrders": {
                    "edges": [
                        {
                            "node": {
                                "id": "gid://shopify/FulfillmentOrder/1",
                                "status": "OPEN",
                                "assignedLocation": {"name": "Warehouse"},
                                "lineItems": {"edges": []},
                            }
                        }
                    ]
                }
            }
        }
        result = await shopify_order_fulfillments(id="1001")
        assert "Warehouse" in result


# ===========================================================================
# Customer tools
# ===========================================================================


class TestCustomerTools:
    async def test_list_customers(self, mock_client: AsyncMock, sample_customer_list: dict) -> None:
        mock_client.list_customers.return_value = sample_customer_list
        result = await shopify_customers()
        assert "John Doe" in result

    async def test_get_customer(self, mock_client: AsyncMock) -> None:
        mock_client.get_customer.return_value = {
            "customer": {
                "id": "gid://shopify/Customer/500",
                "displayName": "John Doe",
                "firstName": "John",
                "lastName": "Doe",
                "email": "john@example.com",
                "phone": None,
                "state": "ENABLED",
                "numberOfOrders": "5",
                "amountSpent": {"amount": "299.95", "currencyCode": "USD"},
                "createdAt": "2026-01-15T10:00:00Z",
                "updatedAt": "2026-03-25T15:30:00Z",
                "tags": [],
                "note": None,
                "verifiedEmail": True,
                "taxExempt": False,
                "taxExemptions": [],
                "defaultAddress": None,
                "addresses": [],
            }
        }
        result = await shopify_customer(id="500")
        assert "John Doe" in result
        assert "verified" in result

    async def test_search_customers(self, mock_client: AsyncMock, sample_customer_list: dict) -> None:
        mock_client.list_customers.return_value = sample_customer_list
        result = await shopify_search_customers(email="john@example.com")
        assert "John Doe" in result

    async def test_create_customer_write_disabled(self, mock_client: AsyncMock) -> None:
        result = await shopify_create_customer(email="new@example.com")
        assert "disabled" in result.lower()

    async def test_create_customer_write_enabled(self, mock_write_client: AsyncMock) -> None:
        mock_write_client.create_customer.return_value = {
            "customerCreate": {
                "customer": {
                    "id": "gid://shopify/Customer/999",
                    "displayName": "Jane Doe",
                    "email": "jane@example.com",
                },
                "userErrors": [],
            }
        }
        result = await shopify_create_customer(email="jane@example.com", first_name="Jane", last_name="Doe")
        assert "999" in result

    async def test_update_customer_write_disabled(self, mock_client: AsyncMock) -> None:
        result = await shopify_update_customer(id="500", note="Updated")
        assert "disabled" in result.lower()


# ===========================================================================
# Inventory tools
# ===========================================================================


class TestInventoryTools:
    async def test_list_locations(self, mock_client: AsyncMock) -> None:
        mock_client.get_inventory_levels.return_value = {
            "locations": {
                "edges": [
                    {"node": {"id": "gid://shopify/Location/1", "name": "Warehouse", "isActive": True, "address": {}}}
                ]
            }
        }
        result = await shopify_inventory()
        assert "Warehouse" in result

    async def test_adjust_inventory_write_disabled(self, mock_client: AsyncMock) -> None:
        result = await shopify_adjust_inventory(inventory_item_id="1", location_id="1", delta=10)
        assert "disabled" in result.lower()

    async def test_set_inventory_no_confirm(self, mock_write_client: AsyncMock) -> None:
        result = await shopify_set_inventory(inventory_item_id="1", location_id="1", quantity=100)
        assert "confirm=true" in result

    async def test_set_inventory_confirmed(self, mock_write_client: AsyncMock) -> None:
        mock_write_client.set_inventory.return_value = {
            "inventorySetOnHandQuantities": {
                "inventoryAdjustmentGroup": {
                    "reason": "correction",
                    "changes": [
                        {
                            "name": "on_hand",
                            "delta": 50,
                            "quantityAfterChange": 100,
                            "item": {"id": "1", "sku": "TSH-M"},
                            "location": {"id": "1", "name": "Warehouse"},
                        }
                    ],
                },
                "userErrors": [],
            }
        }
        result = await shopify_set_inventory(inventory_item_id="1", location_id="1", quantity=100, confirm=True)
        assert "correction" in result


# ===========================================================================
# Collection tools
# ===========================================================================


class TestCollectionTools:
    async def test_list_collections(self, mock_client: AsyncMock) -> None:
        mock_client.list_collections.return_value = {
            "collections": {
                "edges": [
                    {
                        "node": {
                            "id": "gid://shopify/Collection/10",
                            "title": "Summer",
                            "handle": "summer",
                            "sortOrder": "BEST_SELLING",
                            "productsCount": {"count": 15},
                            "updatedAt": "2026-03-20T10:00:00Z",
                        },
                        "cursor": "c1",
                    }
                ],
                "pageInfo": {"hasNextPage": False},
            }
        }
        result = await shopify_collections()
        assert "Summer" in result

    async def test_get_collection(self, mock_client: AsyncMock) -> None:
        mock_client.get_collection.return_value = {
            "collection": {
                "id": "gid://shopify/Collection/10",
                "title": "Summer",
                "handle": "summer",
                "sortOrder": "BEST_SELLING",
                "productsCount": {"count": 15},
                "updatedAt": "2026-03-20T10:00:00Z",
                "descriptionHtml": None,
                "ruleSet": None,
                "seo": {},
                "image": None,
            }
        }
        result = await shopify_collection(id="10")
        assert "Summer" in result

    async def test_create_collection_write_disabled(self, mock_client: AsyncMock) -> None:
        result = await shopify_create_collection(title="New Collection")
        assert "disabled" in result.lower()

    async def test_add_products_write_disabled(self, mock_client: AsyncMock) -> None:
        result = await shopify_collection_add_products(collection_id="10", product_ids="123,456")
        assert "disabled" in result.lower()


# ===========================================================================
# Fulfillment tools
# ===========================================================================


class TestFulfillmentTools:
    async def test_create_fulfillment_write_disabled(self, mock_client: AsyncMock) -> None:
        result = await shopify_create_fulfillment(fulfillment_order_id="1")
        assert "disabled" in result.lower()

    async def test_create_fulfillment_write_enabled(self, mock_write_client: AsyncMock) -> None:
        mock_write_client.create_fulfillment.return_value = {
            "fulfillmentCreateV2": {
                "fulfillment": {
                    "id": "gid://shopify/Fulfillment/1",
                    "status": "SUCCESS",
                    "trackingInfo": {
                        "number": "1Z999",
                        "company": "UPS",
                        "url": None,
                    },
                    "createdAt": "2026-03-25T16:00:00Z",
                },
                "userErrors": [],
            }
        }
        result = await shopify_create_fulfillment(
            fulfillment_order_id="1",
            tracking_number="1Z999",
            tracking_company="UPS",
        )
        assert "1Z999" in result

    async def test_update_tracking_write_disabled(self, mock_client: AsyncMock) -> None:
        result = await shopify_update_tracking(fulfillment_id="1", tracking_number="1Z999")
        assert "disabled" in result.lower()


# ===========================================================================
# Discount tools
# ===========================================================================


class TestDiscountTools:
    async def test_list_discounts(self, mock_client: AsyncMock) -> None:
        mock_client.list_discounts.return_value = {
            "codeDiscountNodes": {
                "edges": [
                    {
                        "node": {
                            "id": "gid://shopify/DiscountCodeNode/1",
                            "codeDiscount": {
                                "title": "Summer Sale",
                                "status": "ACTIVE",
                                "startsAt": "2026-06-01T00:00:00Z",
                                "endsAt": "2026-08-31T23:59:59Z",
                                "codes": {"edges": [{"node": {"code": "SAVE20"}}]},
                                "customerGets": {"value": {"percentage": 0.2}},
                                "usageLimit": 100,
                                "asyncUsageCount": 42,
                            },
                        },
                        "cursor": "d1",
                    }
                ],
                "pageInfo": {"hasNextPage": False},
            }
        }
        result = await shopify_discounts()
        assert "SAVE20" in result
        assert "20%" in result

    async def test_create_discount_write_disabled(self, mock_client: AsyncMock) -> None:
        result = await shopify_create_discount(title="Test", code="TEST10", percentage=10.0)
        assert "disabled" in result.lower()

    async def test_create_discount_no_value(self, mock_write_client: AsyncMock) -> None:
        result = await shopify_create_discount(title="Test", code="TEST")
        assert "percentage" in result.lower() or "amount" in result.lower()

    async def test_delete_discount_no_confirm(self, mock_write_client: AsyncMock) -> None:
        result = await shopify_delete_discount(id="1")
        assert "confirm=true" in result


# ===========================================================================
# Metafield tools
# ===========================================================================


class TestMetafieldTools:
    async def test_get_metafields(self, mock_client: AsyncMock) -> None:
        mock_client.get_metafields.return_value = {
            "product": {
                "id": "gid://shopify/Product/123",
                "metafields": {
                    "edges": [
                        {
                            "node": {
                                "id": "gid://shopify/Metafield/1",
                                "namespace": "custom",
                                "key": "color",
                                "value": "red",
                                "type": "single_line_text_field",
                                "updatedAt": "2026-03-20T10:00:00Z",
                            }
                        }
                    ]
                },
            }
        }
        result = await shopify_metafields(owner_type="product", owner_id="123")
        assert "custom.color" in result
        assert "red" in result

    async def test_set_metafield_write_disabled(self, mock_client: AsyncMock) -> None:
        result = await shopify_set_metafield(
            owner_id="gid://shopify/Product/123",
            namespace="custom",
            key="color",
            value="blue",
            type="single_line_text_field",
        )
        assert "disabled" in result.lower()

    async def test_delete_metafield_no_confirm(self, mock_write_client: AsyncMock) -> None:
        result = await shopify_delete_metafield(id="1")
        assert "confirm=true" in result


# ===========================================================================
# Webhook tools
# ===========================================================================


class TestWebhookTools:
    async def test_list_webhooks(self, mock_client: AsyncMock) -> None:
        mock_client.list_webhooks.return_value = {
            "webhookSubscriptions": {
                "edges": [
                    {
                        "node": {
                            "id": "gid://shopify/WebhookSubscription/1",
                            "topic": "ORDERS_CREATE",
                            "endpoint": {
                                "callbackUrl": "https://example.com/webhook",
                            },
                            "format": "JSON",
                            "createdAt": "2026-03-01T10:00:00Z",
                            "updatedAt": "2026-03-01T10:00:00Z",
                        },
                        "cursor": "w1",
                    }
                ],
                "pageInfo": {"hasNextPage": False},
            }
        }
        result = await shopify_webhooks()
        assert "ORDERS_CREATE" in result

    async def test_create_webhook_write_disabled(self, mock_client: AsyncMock) -> None:
        result = await shopify_create_webhook(topic="ORDERS_CREATE", callback_url="https://example.com/webhook")
        assert "disabled" in result.lower()

    async def test_delete_webhook_no_confirm(self, mock_write_client: AsyncMock) -> None:
        result = await shopify_delete_webhook(id="1")
        assert "confirm=true" in result


# ===========================================================================
# Analytics
# ===========================================================================


class TestAnalytics:
    async def test_shopifyql(self, mock_client: AsyncMock) -> None:
        mock_client.run_shopifyql.return_value = {
            "shopifyqlQuery": {
                "__typename": "TableResponse",
                "tableData": {
                    "columns": [{"name": "day", "dataType": "DATE"}, {"name": "total_sales", "dataType": "MONEY"}],
                    "rowData": [["2026-03-25", "$100.00"]],
                },
                "parseErrors": [],
            }
        }
        result = await shopify_analytics(query="FROM sales SHOW total_sales BY day SINCE -7d")
        assert "day" in result
        assert "$100.00" in result


# ===========================================================================
# Webhook verification
# ===========================================================================


class TestWebhookVerification:
    async def test_no_secret(self, mock_client: AsyncMock) -> None:
        result = await shopify_verify_webhook(raw_body="{}", hmac_header="abc")
        assert "SHOPIFY_WEBHOOK_SECRET" in result

    async def test_with_secret(self, webhook_env: None) -> None:
        import base64
        import hashlib
        import hmac

        secret = "test_webhook_secret_123"
        body = '{"id": 123}'
        hmac_val = base64.b64encode(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()).decode()

        # Need to mock _get_client since webhook_env sets store_env
        from unittest.mock import patch

        mock = AsyncMock()
        with patch("shopify_blade_mcp.server._get_client", return_value=mock):
            result = await shopify_verify_webhook(raw_body=body, hmac_header=hmac_val)
            assert "VALID" in result
