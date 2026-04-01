"""Shopify Admin GraphQL API client.

Async wrapper over ``httpx.AsyncClient`` with typed exceptions,
cost-based rate limit tracking, cursor pagination, and credential
scrubbing. GraphQL-native — no REST API dependency.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from typing import Any

import httpx

from shopify_blade_mcp.models import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    get_graphql_url,
    normalize_id,
    scrub_secrets,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ShopifyError(Exception):
    """Base exception for Shopify client errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AuthError(ShopifyError):
    """Authentication failed — invalid or expired access token."""


class NotFoundError(ShopifyError):
    """Requested resource not found."""


class RateLimitError(ShopifyError):
    """Rate limit exceeded — back off and retry."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class ValidationError(ShopifyError):
    """Request validation failed — invalid parameters or GraphQL errors."""


class ThrottledError(ShopifyError):
    """GraphQL query cost exceeded available points."""


class ConnectionError(ShopifyError):  # noqa: A001
    """Cannot connect to Shopify API."""


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


def _classify_graphql_errors(errors: list[dict[str, Any]]) -> ShopifyError:
    """Map GraphQL error responses to typed exceptions."""
    messages = []
    for err in errors:
        msg = err.get("message", "Unknown error")
        messages.append(scrub_secrets(msg))

        # Check for specific error codes
        extensions = err.get("extensions", {})
        code = extensions.get("code", "")

        if code == "ACCESS_DENIED":
            return AuthError(scrub_secrets(msg))
        if code == "THROTTLED":
            return ThrottledError(scrub_secrets(msg))

    combined = "; ".join(messages)
    return ValidationError(combined)


def _classify_http_error(status_code: int, body: str) -> ShopifyError:
    """Map HTTP status code to a typed exception."""
    clean_body = scrub_secrets(body[:500])

    if status_code in (401, 403):
        return AuthError(f"HTTP {status_code}: {clean_body}")
    if status_code == 404:
        return NotFoundError(f"HTTP {status_code}: {clean_body}")
    if status_code == 429:
        return RateLimitError(f"HTTP {status_code}: Rate limit exceeded")
    return ShopifyError(f"HTTP {status_code}: {clean_body}", status_code=status_code)


# ---------------------------------------------------------------------------
# GraphQL query fragments
# ---------------------------------------------------------------------------

# Reusable fragments for common fields to keep queries DRY
MONEY_FIELDS = "amount currencyCode"

PRODUCT_FIELDS = """
    id
    title
    handle
    status
    productType
    vendor
    tags
    createdAt
    updatedAt
    totalInventory
    tracksInventory
    priceRangeV2 {
        minVariantPrice { amount currencyCode }
        maxVariantPrice { amount currencyCode }
    }
"""

PRODUCT_DETAIL_FIELDS = """
    id
    title
    handle
    descriptionHtml
    status
    productType
    vendor
    tags
    createdAt
    updatedAt
    totalInventory
    tracksInventory
    onlineStoreUrl
    options { id name values }
    priceRangeV2 {
        minVariantPrice { amount currencyCode }
        maxVariantPrice { amount currencyCode }
    }
    variants(first: 20) {
        edges {
            node {
                id
                title
                sku
                price
                compareAtPrice
                inventoryQuantity
                selectedOptions { name value }
            }
        }
    }
    images(first: 5) {
        edges {
            node { id url altText }
        }
    }
    seo { title description }
"""

ORDER_FIELDS = """
    id
    name
    createdAt
    displayFinancialStatus
    displayFulfillmentStatus
    totalPriceSet { shopMoney { amount currencyCode } }
    subtotalPriceSet { shopMoney { amount currencyCode } }
    totalTaxSet { shopMoney { amount currencyCode } }
    customer { id displayName email }
    lineItems(first: 5) {
        edges {
            node {
                title
                quantity
                originalTotalSet { shopMoney { amount currencyCode } }
            }
        }
    }
"""

ORDER_DETAIL_FIELDS = """
    id
    name
    createdAt
    updatedAt
    closedAt
    cancelledAt
    cancelReason
    displayFinancialStatus
    displayFulfillmentStatus
    note
    tags
    totalPriceSet { shopMoney { amount currencyCode } }
    subtotalPriceSet { shopMoney { amount currencyCode } }
    totalTaxSet { shopMoney { amount currencyCode } }
    totalShippingPriceSet { shopMoney { amount currencyCode } }
    totalDiscountsSet { shopMoney { amount currencyCode } }
    totalRefundedSet { shopMoney { amount currencyCode } }
    currentTotalPriceSet { shopMoney { amount currencyCode } }
    customer { id displayName email phone }
    shippingAddress {
        address1
        address2
        city
        province
        country
        zip
    }
    billingAddress {
        address1
        city
        province
        country
        zip
    }
    lineItems(first: 50) {
        edges {
            node {
                id
                title
                quantity
                sku
                originalTotalSet { shopMoney { amount currencyCode } }
                variant { id title }
            }
        }
    }
    fulfillments {
        id
        status
        trackingInfo { number url company }
        createdAt
    }
    refunds {
        id
        createdAt
        totalRefundedSet { shopMoney { amount currencyCode } }
        note
    }
    transactions(first: 10) {
        id
        kind
        status
        amountSet { shopMoney { amount currencyCode } }
        gateway
        createdAt
    }
"""

CUSTOMER_FIELDS = """
    id
    displayName
    email
    phone
    state
    numberOfOrders
    amountSpent { amount currencyCode }
    createdAt
    updatedAt
    tags
    verifiedEmail
"""

CUSTOMER_DETAIL_FIELDS = """
    id
    displayName
    firstName
    lastName
    email
    phone
    state
    numberOfOrders
    amountSpent { amount currencyCode }
    createdAt
    updatedAt
    tags
    note
    verifiedEmail
    taxExempt
    taxExemptions
    defaultAddress {
        address1
        address2
        city
        province
        country
        zip
        phone
    }
    addresses {
        address1
        city
        province
        country
        zip
    }
"""

COLLECTION_FIELDS = """
    id
    title
    handle
    sortOrder
    productsCount { count }
    updatedAt
"""

COLLECTION_DETAIL_FIELDS = """
    id
    title
    handle
    descriptionHtml
    sortOrder
    productsCount { count }
    updatedAt
    ruleSet {
        appliedDisjunctively
        rules { column relation condition }
    }
    seo { title description }
    image { url altText }
"""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class ShopifyClient:
    """Async Shopify Admin GraphQL API client.

    Uses ``httpx.AsyncClient`` for direct GraphQL API access. All methods
    are async — no thread wrapping needed.

    Args:
        access_token: Shopify Admin API access token. Defaults to
            ``SHOPIFY_ACCESS_TOKEN`` env var.
    """

    def __init__(self, access_token: str | None = None) -> None:
        self._access_token = access_token or os.environ.get("SHOPIFY_ACCESS_TOKEN", "").strip()
        if not self._access_token:
            raise AuthError("SHOPIFY_ACCESS_TOKEN environment variable is required.")

        self._graphql_url = get_graphql_url()

        self._http = httpx.AsyncClient(
            headers={
                "X-Shopify-Access-Token": self._access_token,
                "Content-Type": "application/json",
                "User-Agent": "shopify-blade-mcp/0.1.0",
            },
            timeout=30.0,
        )

        # Track API cost for rate limit awareness
        self._last_cost: dict[str, Any] | None = None

    @property
    def store_domain(self) -> str:
        """Extract store domain from the configured URL."""
        return self._graphql_url.split("/admin/")[0].replace("https://", "")

    @property
    def last_cost(self) -> dict[str, Any] | None:
        """Last query cost from the API (requested, actual, throttle status)."""
        return self._last_cost

    # ------------------------------------------------------------------
    # Core GraphQL execution
    # ------------------------------------------------------------------

    async def execute(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a GraphQL query/mutation with error handling.

        Returns the 'data' portion of the response. Raises typed exceptions
        for errors.
        """
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            response = await self._http.post(self._graphql_url, json=payload)
        except httpx.ConnectError as e:
            raise ConnectionError(scrub_secrets(str(e))) from e
        except httpx.TimeoutException as e:
            raise ConnectionError(f"Request timed out: {scrub_secrets(str(e))}") from e
        except httpx.HTTPError as e:
            raise ShopifyError(scrub_secrets(str(e))) from e

        if not response.is_success:
            raise _classify_http_error(response.status_code, response.text)

        try:
            body = response.json()
        except (json.JSONDecodeError, ValueError):
            raise ShopifyError("Non-JSON response from Shopify API")

        # Track cost for rate limit awareness
        extensions = body.get("extensions", {})
        cost = extensions.get("cost")
        if cost:
            self._last_cost = cost
            throttle = cost.get("throttleStatus", {})
            available = throttle.get("currentlyAvailable", 0)
            if available < 50:
                logger.warning("Low API cost budget: %d points remaining", available)

        # Handle GraphQL errors
        errors = body.get("errors")
        if errors:
            raise _classify_graphql_errors(errors)

        # Handle userErrors in mutations
        data = body.get("data", {})
        for key, value in data.items():
            if isinstance(value, dict):
                user_errors = value.get("userErrors") or value.get("customerUserErrors") or []
                if user_errors:
                    messages = [scrub_secrets(e.get("message", "Unknown error")) for e in user_errors]
                    fields = [e.get("field", []) for e in user_errors]
                    detail = "; ".join(f"{'/'.join(f) if f else '?'}: {m}" for f, m in zip(fields, messages))
                    raise ValidationError(detail)

        return dict(data)

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    async def list_products(
        self,
        query: str | None = None,
        limit: int = DEFAULT_LIMIT,
        after: str | None = None,
    ) -> dict[str, Any]:
        """List products with optional search query."""
        gql = f"""
        query listProducts($first: Int!, $after: String, $query: String) {{
            products(first: $first, after: $after, query: $query) {{
                edges {{
                    node {{ {PRODUCT_FIELDS} }}
                    cursor
                }}
                pageInfo {{ hasNextPage }}
            }}
        }}
        """
        variables: dict[str, Any] = {"first": min(limit, MAX_LIMIT)}
        if after:
            variables["after"] = after
        if query:
            variables["query"] = query
        return await self.execute(gql, variables)

    async def get_product(self, product_id: str) -> dict[str, Any]:
        """Get a product by ID (numeric or GID)."""
        gql = f"""
        query getProduct($id: ID!) {{
            product(id: $id) {{ {PRODUCT_DETAIL_FIELDS} }}
        }}
        """
        return await self.execute(gql, {"id": normalize_id("product", product_id)})

    async def create_product(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Create a product."""
        gql = """
        mutation createProduct($input: ProductInput!) {
            productCreate(input: $input) {
                product { id title handle status }
                userErrors { field message }
            }
        }
        """
        return await self.execute(gql, {"input": input_data})

    async def update_product(self, product_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Update a product."""
        input_data["id"] = normalize_id("product", product_id)
        gql = """
        mutation updateProduct($input: ProductInput!) {
            productUpdate(input: $input) {
                product { id title handle status }
                userErrors { field message }
            }
        }
        """
        return await self.execute(gql, {"input": input_data})

    async def delete_product(self, product_id: str) -> dict[str, Any]:
        """Delete a product."""
        gql = """
        mutation deleteProduct($input: ProductDeleteInput!) {
            productDelete(input: $input) {
                deletedProductId
                userErrors { field message }
            }
        }
        """
        return await self.execute(gql, {"input": {"id": normalize_id("product", product_id)}})

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    async def list_orders(
        self,
        query: str | None = None,
        limit: int = DEFAULT_LIMIT,
        after: str | None = None,
    ) -> dict[str, Any]:
        """List orders with optional search query."""
        gql = f"""
        query listOrders($first: Int!, $after: String, $query: String) {{
            orders(first: $first, after: $after, query: $query) {{
                edges {{
                    node {{ {ORDER_FIELDS} }}
                    cursor
                }}
                pageInfo {{ hasNextPage }}
            }}
        }}
        """
        variables: dict[str, Any] = {"first": min(limit, MAX_LIMIT)}
        if after:
            variables["after"] = after
        if query:
            variables["query"] = query
        return await self.execute(gql, variables)

    async def get_order(self, order_id: str) -> dict[str, Any]:
        """Get an order by ID (numeric or GID)."""
        gql = f"""
        query getOrder($id: ID!) {{
            order(id: $id) {{ {ORDER_DETAIL_FIELDS} }}
        }}
        """
        return await self.execute(gql, {"id": normalize_id("order", order_id)})

    async def search_orders_by_name(self, name: str) -> dict[str, Any]:
        """Search for orders by name (e.g., '#1001')."""
        # Strip # prefix if present for the query
        clean_name = name.lstrip("#")
        return await self.list_orders(query=f"name:{clean_name}", limit=5)

    async def close_order(self, order_id: str) -> dict[str, Any]:
        """Close an order."""
        gql = """
        mutation closeOrder($input: OrderCloseInput!) {
            orderClose(input: $input) {
                order { id name displayFinancialStatus displayFulfillmentStatus }
                userErrors { field message }
            }
        }
        """
        return await self.execute(gql, {"input": {"id": normalize_id("order", order_id)}})

    async def cancel_order(
        self,
        order_id: str,
        reason: str | None = None,
        refund: bool = False,
        restock: bool = False,
    ) -> dict[str, Any]:
        """Cancel an order."""
        gql = """
        mutation cancelOrder($orderId: ID!, $reason: OrderCancelReason!, $refund: Boolean!, $restock: Boolean!) {
            orderCancel(orderId: $orderId, reason: $reason, refund: $refund, restock: $restock) {
                orderCancelUserErrors { field message code }
            }
        }
        """
        cancel_reason = (reason or "OTHER").upper()
        return await self.execute(
            gql,
            {
                "orderId": normalize_id("order", order_id),
                "reason": cancel_reason,
                "refund": refund,
                "restock": restock,
            },
        )

    async def update_order_note(self, order_id: str, note: str) -> dict[str, Any]:
        """Update the note on an order."""
        gql = """
        mutation updateOrder($input: OrderInput!) {
            orderUpdate(input: $input) {
                order { id name note }
                userErrors { field message }
            }
        }
        """
        return await self.execute(gql, {"input": {"id": normalize_id("order", order_id), "note": note}})

    async def add_order_tags(self, order_id: str, tags: list[str]) -> dict[str, Any]:
        """Add tags to an order."""
        gql = """
        mutation addTags($id: ID!, $tags: [String!]!) {
            tagsAdd(id: $id, tags: $tags) {
                node { ... on Order { id name tags } }
                userErrors { field message }
            }
        }
        """
        return await self.execute(gql, {"id": normalize_id("order", order_id), "tags": tags})

    # ------------------------------------------------------------------
    # Customers
    # ------------------------------------------------------------------

    async def list_customers(
        self,
        query: str | None = None,
        limit: int = DEFAULT_LIMIT,
        after: str | None = None,
    ) -> dict[str, Any]:
        """List customers with optional search query."""
        gql = f"""
        query listCustomers($first: Int!, $after: String, $query: String) {{
            customers(first: $first, after: $after, query: $query) {{
                edges {{
                    node {{ {CUSTOMER_FIELDS} }}
                    cursor
                }}
                pageInfo {{ hasNextPage }}
            }}
        }}
        """
        variables: dict[str, Any] = {"first": min(limit, MAX_LIMIT)}
        if after:
            variables["after"] = after
        if query:
            variables["query"] = query
        return await self.execute(gql, variables)

    async def get_customer(self, customer_id: str) -> dict[str, Any]:
        """Get a customer by ID (numeric or GID)."""
        gql = f"""
        query getCustomer($id: ID!) {{
            customer(id: $id) {{ {CUSTOMER_DETAIL_FIELDS} }}
        }}
        """
        return await self.execute(gql, {"id": normalize_id("customer", customer_id)})

    async def create_customer(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Create a customer."""
        gql = """
        mutation createCustomer($input: CustomerInput!) {
            customerCreate(input: $input) {
                customer { id displayName email }
                userErrors { field message }
            }
        }
        """
        return await self.execute(gql, {"input": input_data})

    async def update_customer(self, customer_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Update a customer."""
        input_data["id"] = normalize_id("customer", customer_id)
        gql = """
        mutation updateCustomer($input: CustomerInput!) {
            customerUpdate(input: $input) {
                customer { id displayName email }
                userErrors { field message }
            }
        }
        """
        return await self.execute(gql, {"input": input_data})

    # ------------------------------------------------------------------
    # Inventory
    # ------------------------------------------------------------------

    async def get_inventory_levels(
        self,
        location_id: str | None = None,
        limit: int = DEFAULT_LIMIT,
        after: str | None = None,
    ) -> dict[str, Any]:
        """Get inventory levels, optionally filtered by location."""
        if location_id:
            gql = """
            query inventoryLevels($id: ID!, $first: Int!, $after: String) {
                location(id: $id) {
                    id
                    name
                    inventoryLevels(first: $first, after: $after) {
                        edges {
                            node {
                                id
                                quantities(names: ["available", "committed", "on_hand"]) {
                                    name
                                    quantity
                                }
                                item { id sku variant { id title product { id title } } }
                            }
                            cursor
                        }
                        pageInfo { hasNextPage }
                    }
                }
            }
            """
            variables: dict[str, Any] = {
                "id": normalize_id("location", location_id),
                "first": min(limit, MAX_LIMIT),
            }
            if after:
                variables["after"] = after
            return await self.execute(gql, variables)
        else:
            gql = """
            query locations($first: Int!) {
                locations(first: $first) {
                    edges {
                        node {
                            id
                            name
                            isActive
                            address { address1 city province country }
                        }
                    }
                }
            }
            """
            return await self.execute(gql, {"first": min(limit, MAX_LIMIT)})

    async def adjust_inventory(
        self,
        inventory_item_id: str,
        location_id: str,
        delta: int,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Adjust inventory quantity by a delta amount."""
        gql = """
        mutation adjustInventory($input: InventoryAdjustQuantitiesInput!) {
            inventoryAdjustQuantities(input: $input) {
                inventoryAdjustmentGroup {
                    reason
                    changes {
                        name
                        delta
                        quantityAfterChange
                        item { id sku }
                        location { id name }
                    }
                }
                userErrors { field message }
            }
        }
        """
        changes = [
            {
                "inventoryItemId": normalize_id("inventory_item", inventory_item_id),
                "locationId": normalize_id("location", location_id),
                "delta": delta,
                "name": "available",
            }
        ]
        input_data: dict[str, Any] = {"changes": changes, "name": "available"}
        if reason:
            input_data["reason"] = reason
        return await self.execute(gql, {"input": input_data})

    async def set_inventory(
        self,
        inventory_item_id: str,
        location_id: str,
        quantity: int,
    ) -> dict[str, Any]:
        """Set inventory quantity to an absolute value."""
        gql = """
        mutation setInventory($input: InventorySetOnHandQuantitiesInput!) {
            inventorySetOnHandQuantities(input: $input) {
                inventoryAdjustmentGroup {
                    reason
                    changes {
                        name
                        delta
                        quantityAfterChange
                        item { id sku }
                        location { id name }
                    }
                }
                userErrors { field message }
            }
        }
        """
        return await self.execute(
            gql,
            {
                "input": {
                    "reason": "correction",
                    "setQuantities": [
                        {
                            "inventoryItemId": normalize_id("inventory_item", inventory_item_id),
                            "locationId": normalize_id("location", location_id),
                            "quantity": quantity,
                        }
                    ],
                }
            },
        )

    # ------------------------------------------------------------------
    # Collections
    # ------------------------------------------------------------------

    async def list_collections(
        self,
        query: str | None = None,
        limit: int = DEFAULT_LIMIT,
        after: str | None = None,
    ) -> dict[str, Any]:
        """List collections."""
        gql = f"""
        query listCollections($first: Int!, $after: String, $query: String) {{
            collections(first: $first, after: $after, query: $query) {{
                edges {{
                    node {{ {COLLECTION_FIELDS} }}
                    cursor
                }}
                pageInfo {{ hasNextPage }}
            }}
        }}
        """
        variables: dict[str, Any] = {"first": min(limit, MAX_LIMIT)}
        if after:
            variables["after"] = after
        if query:
            variables["query"] = query
        return await self.execute(gql, variables)

    async def get_collection(self, collection_id: str) -> dict[str, Any]:
        """Get a collection by ID."""
        gql = f"""
        query getCollection($id: ID!) {{
            collection(id: $id) {{ {COLLECTION_DETAIL_FIELDS} }}
        }}
        """
        return await self.execute(gql, {"id": normalize_id("collection", collection_id)})

    async def create_collection(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Create a custom collection."""
        gql = """
        mutation createCollection($input: CollectionInput!) {
            collectionCreate(input: $input) {
                collection { id title handle }
                userErrors { field message }
            }
        }
        """
        return await self.execute(gql, {"input": input_data})

    async def add_products_to_collection(self, collection_id: str, product_ids: list[str]) -> dict[str, Any]:
        """Add products to a collection."""
        gql = """
        mutation addProducts($id: ID!, $productIds: [ID!]!) {
            collectionAddProducts(id: $id, productIds: $productIds) {
                collection { id title productsCount { count } }
                userErrors { field message }
            }
        }
        """
        normalized_ids = [normalize_id("product", pid) for pid in product_ids]
        return await self.execute(
            gql,
            {
                "id": normalize_id("collection", collection_id),
                "productIds": normalized_ids,
            },
        )

    # ------------------------------------------------------------------
    # Fulfillment
    # ------------------------------------------------------------------

    async def list_fulfillment_orders(self, order_id: str) -> dict[str, Any]:
        """List fulfillment orders for an order."""
        gql = """
        query fulfillmentOrders($id: ID!) {
            order(id: $id) {
                fulfillmentOrders(first: 20) {
                    edges {
                        node {
                            id
                            status
                            assignedLocation { name }
                            lineItems(first: 50) {
                                edges {
                                    node {
                                        id
                                        totalQuantity
                                        remainingQuantity
                                        lineItem { title sku }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        """
        return await self.execute(gql, {"id": normalize_id("order", order_id)})

    async def create_fulfillment(
        self,
        fulfillment_order_id: str,
        tracking_number: str | None = None,
        tracking_url: str | None = None,
        tracking_company: str | None = None,
        notify_customer: bool = True,
    ) -> dict[str, Any]:
        """Create a fulfillment."""
        gql = """
        mutation createFulfillment($fulfillment: FulfillmentV2Input!) {
            fulfillmentCreateV2(fulfillment: $fulfillment) {
                fulfillment {
                    id
                    status
                    trackingInfo { number url company }
                    createdAt
                }
                userErrors { field message }
            }
        }
        """
        line_items_by_fo = [{"fulfillmentOrderId": normalize_id("fulfillment_order", fulfillment_order_id)}]

        tracking_info: dict[str, Any] = {}
        if tracking_number:
            tracking_info["number"] = tracking_number
        if tracking_url:
            tracking_info["url"] = tracking_url
        if tracking_company:
            tracking_info["company"] = tracking_company

        fulfillment_input: dict[str, Any] = {
            "lineItemsByFulfillmentOrder": line_items_by_fo,
            "notifyCustomer": notify_customer,
        }
        if tracking_info:
            fulfillment_input["trackingInfo"] = tracking_info

        return await self.execute(gql, {"fulfillment": fulfillment_input})

    async def update_tracking(
        self,
        fulfillment_id: str,
        tracking_number: str | None = None,
        tracking_url: str | None = None,
        tracking_company: str | None = None,
        notify_customer: bool = False,
    ) -> dict[str, Any]:
        """Update tracking information on a fulfillment."""
        # Use a simpler mutation that's less error-prone
        tracking_input: dict[str, Any] = {}
        if tracking_number:
            tracking_input["number"] = tracking_number
        if tracking_url:
            tracking_input["url"] = tracking_url
        if tracking_company:
            tracking_input["company"] = tracking_company

        gql_simple = """
        mutation updateTracking(
            $fulfillmentId: ID!
            $trackingInfoInput: FulfillmentTrackingInput!
            $notifyCustomer: Boolean
        ) {
            fulfillmentTrackingInfoUpdateV2(
                fulfillmentId: $fulfillmentId
                trackingInfoInput: $trackingInfoInput
                notifyCustomer: $notifyCustomer
            ) {
                fulfillment { id status trackingInfo { number url company } }
                userErrors { field message }
            }
        }
        """
        return await self.execute(
            gql_simple,
            {
                "fulfillmentId": normalize_id("fulfillment", fulfillment_id),
                "trackingInfoInput": tracking_input,
                "notifyCustomer": notify_customer,
            },
        )

    # ------------------------------------------------------------------
    # Discounts
    # ------------------------------------------------------------------

    async def list_discounts(
        self,
        query: str | None = None,
        limit: int = DEFAULT_LIMIT,
        after: str | None = None,
    ) -> dict[str, Any]:
        """List discount codes."""
        gql = """
        query listDiscounts($first: Int!, $after: String, $query: String) {
            codeDiscountNodes(first: $first, after: $after, query: $query) {
                edges {
                    node {
                        id
                        codeDiscount {
                            ... on DiscountCodeBasic {
                                title
                                status
                                startsAt
                                endsAt
                                codes(first: 1) { edges { node { code } } }
                                customerGets {
                                    value {
                                        ... on DiscountPercentage { percentage }
                                        ... on DiscountAmount { amount { amount currencyCode } }
                                    }
                                }
                                usageLimit
                                asyncUsageCount
                            }
                            ... on DiscountCodeFreeShipping {
                                title
                                status
                                startsAt
                                endsAt
                                codes(first: 1) { edges { node { code } } }
                                usageLimit
                                asyncUsageCount
                            }
                            ... on DiscountCodeBxgy {
                                title
                                status
                                startsAt
                                endsAt
                                codes(first: 1) { edges { node { code } } }
                                usageLimit
                                asyncUsageCount
                            }
                        }
                    }
                    cursor
                }
                pageInfo { hasNextPage }
            }
        }
        """
        variables: dict[str, Any] = {"first": min(limit, MAX_LIMIT)}
        if after:
            variables["after"] = after
        if query:
            variables["query"] = query
        return await self.execute(gql, variables)

    async def create_basic_discount(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Create a basic discount code."""
        gql = """
        mutation createDiscount($basicCodeDiscount: DiscountCodeBasicInput!) {
            discountCodeBasicCreate(basicCodeDiscount: $basicCodeDiscount) {
                codeDiscountNode {
                    id
                    codeDiscount {
                        ... on DiscountCodeBasic { title status codes(first: 1) { edges { node { code } } } }
                    }
                }
                userErrors { field message }
            }
        }
        """
        return await self.execute(gql, {"basicCodeDiscount": input_data})

    async def delete_discount(self, discount_id: str) -> dict[str, Any]:
        """Delete a discount code."""
        gql = """
        mutation deleteDiscount($id: ID!) {
            discountCodeDelete(id: $id) {
                deletedCodeDiscountId
                userErrors { field message }
            }
        }
        """
        return await self.execute(gql, {"id": normalize_id("discount_code", discount_id)})

    # ------------------------------------------------------------------
    # Metafields
    # ------------------------------------------------------------------

    async def get_metafields(
        self,
        owner_type: str,
        owner_id: str,
        namespace: str | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        """Get metafields for a resource."""
        resource_query = owner_type.lower()
        gql = f"""
        query getMetafields($id: ID!, $first: Int!, $namespace: String) {{
            {resource_query}(id: $id) {{
                id
                metafields(first: $first, namespace: $namespace) {{
                    edges {{
                        node {{
                            id
                            namespace
                            key
                            value
                            type
                            updatedAt
                        }}
                    }}
                }}
            }}
        }}
        """
        variables: dict[str, Any] = {
            "id": normalize_id(resource_query, owner_id),
            "first": min(limit, MAX_LIMIT),
        }
        if namespace:
            variables["namespace"] = namespace
        return await self.execute(gql, variables)

    async def set_metafields(self, metafields: list[dict[str, Any]]) -> dict[str, Any]:
        """Set one or more metafields."""
        gql = """
        mutation setMetafields($metafields: [MetafieldsSetInput!]!) {
            metafieldsSet(metafields: $metafields) {
                metafields {
                    id
                    namespace
                    key
                    value
                    type
                }
                userErrors { field message }
            }
        }
        """
        return await self.execute(gql, {"metafields": metafields})

    async def delete_metafield(self, metafield_id: str) -> dict[str, Any]:
        """Delete a metafield."""
        gql = """
        mutation deleteMetafield($input: MetafieldDeleteInput!) {
            metafieldDelete(input: $input) {
                deletedId
                userErrors { field message }
            }
        }
        """
        return await self.execute(gql, {"input": {"id": normalize_id("metafield", metafield_id)}})

    # ------------------------------------------------------------------
    # Webhooks
    # ------------------------------------------------------------------

    async def list_webhooks(
        self,
        limit: int = DEFAULT_LIMIT,
        after: str | None = None,
    ) -> dict[str, Any]:
        """List webhook subscriptions."""
        gql = """
        query listWebhooks($first: Int!, $after: String) {
            webhookSubscriptions(first: $first, after: $after) {
                edges {
                    node {
                        id
                        topic
                        endpoint {
                            ... on WebhookHttpEndpoint { callbackUrl }
                            ... on WebhookEventBridgeEndpoint { arn }
                            ... on WebhookPubSubEndpoint { pubSubProject pubSubTopic }
                        }
                        format
                        createdAt
                        updatedAt
                    }
                    cursor
                }
                pageInfo { hasNextPage }
            }
        }
        """
        variables: dict[str, Any] = {"first": min(limit, MAX_LIMIT)}
        if after:
            variables["after"] = after
        return await self.execute(gql, variables)

    async def create_webhook(
        self,
        topic: str,
        callback_url: str,
        webhook_format: str = "JSON",
    ) -> dict[str, Any]:
        """Create a webhook subscription."""
        gql = """
        mutation createWebhook($topic: WebhookSubscriptionTopic!, $webhookSubscription: WebhookSubscriptionInput!) {
            webhookSubscriptionCreate(topic: $topic, webhookSubscription: $webhookSubscription) {
                webhookSubscription {
                    id
                    topic
                    endpoint { ... on WebhookHttpEndpoint { callbackUrl } }
                    format
                }
                userErrors { field message }
            }
        }
        """
        return await self.execute(
            gql,
            {
                "topic": topic,
                "webhookSubscription": {
                    "callbackUrl": callback_url,
                    "format": webhook_format.upper(),
                },
            },
        )

    async def delete_webhook(self, webhook_id: str) -> dict[str, Any]:
        """Delete a webhook subscription."""
        gql = """
        mutation deleteWebhook($id: ID!) {
            webhookSubscriptionDelete(id: $id) {
                deletedWebhookSubscriptionId
                userErrors { field message }
            }
        }
        """
        return await self.execute(gql, {"id": normalize_id("webhook", webhook_id)})

    # ------------------------------------------------------------------
    # Shop
    # ------------------------------------------------------------------

    async def get_shop(self) -> dict[str, Any]:
        """Get store information."""
        gql = """
        query getShop {
            shop {
                id
                name
                email
                url
                myshopifyDomain
                primaryDomain { url host }
                plan { displayName partnerDevelopment shopifyPlus }
                currencyCode
                weightUnit
                timezoneAbbreviation
                ianaTimezone
                billingAddress {
                    address1
                    city
                    province
                    country
                    zip
                }
                features {
                    storefront
                }
            }
        }
        """
        return await self.execute(gql)

    async def get_locations(self) -> dict[str, Any]:
        """Get store locations."""
        gql = """
        query getLocations {
            locations(first: 50) {
                edges {
                    node {
                        id
                        name
                        isActive
                        isPrimary
                        fulfillmentService { serviceName }
                        address { address1 city province country zip }
                    }
                }
            }
        }
        """
        return await self.execute(gql)

    # ------------------------------------------------------------------
    # Analytics (ShopifyQL)
    # ------------------------------------------------------------------

    async def run_shopifyql(self, query: str) -> dict[str, Any]:
        """Run a ShopifyQL analytics query."""
        gql = """
        query runAnalytics($query: String!) {
            shopifyqlQuery(query: $query) {
                __typename
                ... on TableResponse {
                    tableData {
                        columns { name dataType }
                        rowData
                    }
                }
                parseErrors { code message range { start { line character } end { line character } } }
            }
        }
        """
        return await self.execute(gql, {"query": query})

    # ------------------------------------------------------------------
    # Webhook Verification
    # ------------------------------------------------------------------

    @staticmethod
    def verify_webhook_signature(
        raw_body: str,
        hmac_header: str,
        webhook_secret: str,
    ) -> dict[str, Any]:
        """Verify a Shopify webhook HMAC-SHA256 signature.

        Shopify sends the HMAC in the X-Shopify-Hmac-SHA256 header as
        a base64-encoded value.

        Returns:
            Dict with 'valid' bool and parsed event data if valid.
        """
        import base64

        try:
            expected = base64.b64encode(
                hmac.new(
                    webhook_secret.encode("utf-8"),
                    raw_body.encode("utf-8"),
                    hashlib.sha256,
                ).digest()
            ).decode("utf-8")

            if not hmac.compare_digest(expected, hmac_header):
                return {"valid": False, "error": "Signature mismatch"}

            event = json.loads(raw_body)
            return {
                "valid": True,
                "data": event,
            }
        except (ValueError, json.JSONDecodeError) as e:
            return {"valid": False, "error": scrub_secrets(str(e))}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()
