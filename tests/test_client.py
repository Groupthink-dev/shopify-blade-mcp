"""Tests for client.py — GraphQL API client."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from shopify_blade_mcp.client import (
    AuthError,
    ConnectionError,
    NotFoundError,
    RateLimitError,
    ShopifyClient,
    ThrottledError,
    ValidationError,
)

# ---------------------------------------------------------------------------
# Client construction
# ---------------------------------------------------------------------------


class TestClientConstruction:
    def test_requires_token(self) -> None:
        with pytest.raises(AuthError, match="SHOPIFY_ACCESS_TOKEN"):
            ShopifyClient()

    def test_from_env(self, store_env: None) -> None:
        client = ShopifyClient()
        assert client.store_domain == "test-store.myshopify.com"

    def test_explicit_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SHOPIFY_STORE_DOMAIN", "my-store.myshopify.com")
        client = ShopifyClient(access_token="shpat_explicit")
        assert client.store_domain == "my-store.myshopify.com"


# ---------------------------------------------------------------------------
# GraphQL execution
# ---------------------------------------------------------------------------


class TestExecute:
    @pytest.fixture
    def client(self, store_env: None) -> ShopifyClient:
        return ShopifyClient()

    async def test_successful_query(self, client: ShopifyClient) -> None:
        mock_response = httpx.Response(
            200,
            json={
                "data": {"shop": {"name": "Test Store"}},
                "extensions": {
                    "cost": {
                        "requestedQueryCost": 2,
                        "actualQueryCost": 2,
                        "throttleStatus": {"currentlyAvailable": 1000},
                    }
                },
            },
        )
        with patch.object(client._http, "post", return_value=mock_response):
            result = await client.execute("query { shop { name } }")
            assert result == {"shop": {"name": "Test Store"}}
            assert client.last_cost is not None

    async def test_graphql_errors(self, client: ShopifyClient) -> None:
        mock_response = httpx.Response(
            200,
            json={"errors": [{"message": "Field not found", "extensions": {"code": "FIELD_ERROR"}}]},
        )
        with patch.object(client._http, "post", return_value=mock_response):
            with pytest.raises(ValidationError, match="Field not found"):
                await client.execute("query { invalid }")

    async def test_access_denied(self, client: ShopifyClient) -> None:
        mock_response = httpx.Response(
            200,
            json={"errors": [{"message": "Access denied", "extensions": {"code": "ACCESS_DENIED"}}]},
        )
        with patch.object(client._http, "post", return_value=mock_response):
            with pytest.raises(AuthError, match="Access denied"):
                await client.execute("query { restricted }")

    async def test_throttled(self, client: ShopifyClient) -> None:
        mock_response = httpx.Response(
            200,
            json={"errors": [{"message": "Throttled", "extensions": {"code": "THROTTLED"}}]},
        )
        with patch.object(client._http, "post", return_value=mock_response):
            with pytest.raises(ThrottledError):
                await client.execute("query { expensive }")

    async def test_http_401(self, client: ShopifyClient) -> None:
        mock_response = httpx.Response(401, text="Unauthorized")
        with patch.object(client._http, "post", return_value=mock_response):
            with pytest.raises(AuthError, match="401"):
                await client.execute("query { shop { name } }")

    async def test_http_404(self, client: ShopifyClient) -> None:
        mock_response = httpx.Response(404, text="Not Found")
        with patch.object(client._http, "post", return_value=mock_response):
            with pytest.raises(NotFoundError, match="404"):
                await client.execute("query { shop { name } }")

    async def test_http_429(self, client: ShopifyClient) -> None:
        mock_response = httpx.Response(429, text="Rate limited")
        with patch.object(client._http, "post", return_value=mock_response):
            with pytest.raises(RateLimitError):
                await client.execute("query { shop { name } }")

    async def test_connection_error(self, client: ShopifyClient) -> None:
        with patch.object(client._http, "post", side_effect=httpx.ConnectError("Connection refused")):
            with pytest.raises(ConnectionError, match="Connection refused"):
                await client.execute("query { shop { name } }")

    async def test_timeout_error(self, client: ShopifyClient) -> None:
        with patch.object(client._http, "post", side_effect=httpx.TimeoutException("Timed out")):
            with pytest.raises(ConnectionError, match="timed out"):
                await client.execute("query { shop { name } }")

    async def test_user_errors_in_mutation(self, client: ShopifyClient) -> None:
        mock_response = httpx.Response(
            200,
            json={
                "data": {
                    "productCreate": {
                        "product": None,
                        "userErrors": [{"field": ["title"], "message": "Title can't be blank"}],
                    }
                }
            },
        )
        with patch.object(client._http, "post", return_value=mock_response):
            with pytest.raises(ValidationError, match="Title can't be blank"):
                await client.execute("mutation { ... }")

    async def test_credential_scrubbing_in_errors(self, client: ShopifyClient) -> None:
        mock_response = httpx.Response(
            401,
            text="Invalid token: shpat_abc123def456",
        )
        with patch.object(client._http, "post", return_value=mock_response):
            with pytest.raises(AuthError) as exc_info:
                await client.execute("query { shop { name } }")
            assert "shpat_" not in str(exc_info.value)

    async def test_cost_tracking(self, client: ShopifyClient) -> None:
        mock_response = httpx.Response(
            200,
            json={
                "data": {"shop": {"name": "Test"}},
                "extensions": {
                    "cost": {
                        "requestedQueryCost": 5,
                        "actualQueryCost": 3,
                        "throttleStatus": {"maximumAvailable": 1000, "currentlyAvailable": 997},
                    }
                },
            },
        )
        with patch.object(client._http, "post", return_value=mock_response):
            await client.execute("query { shop { name } }")
            assert client.last_cost is not None
            assert client.last_cost["actualQueryCost"] == 3


# ---------------------------------------------------------------------------
# Resource methods
# ---------------------------------------------------------------------------


class TestResourceMethods:
    @pytest.fixture
    def client(self, store_env: None) -> ShopifyClient:
        return ShopifyClient()

    async def test_list_products(self, client: ShopifyClient) -> None:
        mock_response = httpx.Response(
            200,
            json={"data": {"products": {"edges": [], "pageInfo": {"hasNextPage": False}}}},
        )
        with patch.object(client._http, "post", return_value=mock_response) as mock_post:
            await client.list_products(query="title:shirt", limit=10)
            call_args = mock_post.call_args
            body = call_args.kwargs.get("json", {})
            assert body["variables"]["first"] == 10
            assert body["variables"]["query"] == "title:shirt"

    async def test_get_product_normalizes_id(self, client: ShopifyClient) -> None:
        mock_response = httpx.Response(200, json={"data": {"product": {"id": "gid://shopify/Product/123"}}})
        with patch.object(client._http, "post", return_value=mock_response) as mock_post:
            await client.get_product("123")
            body = mock_post.call_args.kwargs.get("json", {})
            assert body["variables"]["id"] == "gid://shopify/Product/123"

    async def test_create_product(self, client: ShopifyClient) -> None:
        mock_response = httpx.Response(
            200,
            json={
                "data": {
                    "productCreate": {
                        "product": {
                            "id": "gid://shopify/Product/999",
                            "title": "New",
                            "handle": "new",
                            "status": "DRAFT",
                        },
                        "userErrors": [],
                    }
                }
            },
        )
        with patch.object(client._http, "post", return_value=mock_response):
            result = await client.create_product({"title": "New"})
            assert result["productCreate"]["product"]["id"] == "gid://shopify/Product/999"

    async def test_list_orders(self, client: ShopifyClient) -> None:
        mock_response = httpx.Response(
            200,
            json={"data": {"orders": {"edges": [], "pageInfo": {"hasNextPage": False}}}},
        )
        with patch.object(client._http, "post", return_value=mock_response):
            result = await client.list_orders(limit=5)
            assert "orders" in result

    async def test_get_customer(self, client: ShopifyClient) -> None:
        mock_response = httpx.Response(
            200,
            json={
                "data": {
                    "customer": {
                        "id": "gid://shopify/Customer/500",
                        "displayName": "John",
                    }
                }
            },
        )
        with patch.object(client._http, "post", return_value=mock_response):
            result = await client.get_customer("500")
            assert result["customer"]["displayName"] == "John"

    async def test_list_webhooks(self, client: ShopifyClient) -> None:
        mock_response = httpx.Response(
            200,
            json={
                "data": {
                    "webhookSubscriptions": {
                        "edges": [],
                        "pageInfo": {"hasNextPage": False},
                    }
                }
            },
        )
        with patch.object(client._http, "post", return_value=mock_response):
            result = await client.list_webhooks()
            assert "webhookSubscriptions" in result

    async def test_get_shop(self, client: ShopifyClient) -> None:
        mock_response = httpx.Response(200, json={"data": {"shop": {"name": "Test Store", "currencyCode": "USD"}}})
        with patch.object(client._http, "post", return_value=mock_response):
            result = await client.get_shop()
            assert result["shop"]["name"] == "Test Store"


# ---------------------------------------------------------------------------
# Webhook verification
# ---------------------------------------------------------------------------


class TestWebhookVerification:
    def test_valid_signature(self) -> None:
        import base64
        import hashlib
        import hmac

        secret = "test_secret"
        body = '{"id": 123, "email": "test@example.com"}'
        expected_hmac = base64.b64encode(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()).decode()

        result = ShopifyClient.verify_webhook_signature(body, expected_hmac, secret)
        assert result["valid"] is True
        assert result["data"]["id"] == 123

    def test_invalid_signature(self) -> None:
        result = ShopifyClient.verify_webhook_signature('{"id": 123}', "invalid_hmac", "secret")
        assert result["valid"] is False
        assert "mismatch" in result.get("error", "").lower()

    def test_invalid_json_body(self) -> None:
        import base64
        import hashlib
        import hmac

        secret = "test_secret"
        body = "not json"
        hmac_val = base64.b64encode(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()).decode()

        result = ShopifyClient.verify_webhook_signature(body, hmac_val, secret)
        assert result["valid"] is False
