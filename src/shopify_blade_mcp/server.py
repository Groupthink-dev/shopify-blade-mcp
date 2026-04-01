"""Shopify Blade MCP Server — Shopify Admin GraphQL API operations.

Token-efficient by default: pipe-delimited lists, field selection,
human-readable money, null-field omission. Write operations gated
behind SHOPIFY_WRITE_ENABLED=true. Destructive operations require
confirm=true.

44 tools covering products, orders, customers, inventory, collections,
fulfillment, discounts, metafields, webhooks, and analytics.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from shopify_blade_mcp.client import ShopifyClient, ShopifyError
from shopify_blade_mcp.formatters import (
    format_analytics_result,
    format_collection_detail,
    format_collection_list,
    format_customer_detail,
    format_customer_list,
    format_discount_list,
    format_fulfillment_created,
    format_fulfillment_orders,
    format_inventory_adjustment,
    format_inventory_levels,
    format_locations,
    format_metafield_list,
    format_metafield_set,
    format_mutation_result,
    format_order_detail,
    format_order_list,
    format_product_detail,
    format_product_list,
    format_shop_info,
    format_webhook_created,
    format_webhook_list,
    format_webhook_verification,
)
from shopify_blade_mcp.models import DEFAULT_LIMIT, require_confirm, require_write

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Transport configuration
# ---------------------------------------------------------------------------

TRANSPORT = os.environ.get("SHOPIFY_MCP_TRANSPORT", "stdio")
HTTP_HOST = os.environ.get("SHOPIFY_MCP_HOST", "127.0.0.1")
HTTP_PORT = int(os.environ.get("SHOPIFY_MCP_PORT", "8770"))

# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "ShopifyBlade",
    instructions=(
        "Shopify Admin API operations via GraphQL. Manage products, orders, "
        "customers, inventory, collections, fulfillment, discounts, metafields, "
        "webhooks, and analytics. Token-efficient responses with pipe-delimited "
        "lists, field selection, and human-readable money. "
        "Write operations require SHOPIFY_WRITE_ENABLED=true. "
        "Destructive operations (delete, cancel, refund) require confirm=true."
    ),
)

# Lazy-initialized client
_client: ShopifyClient | None = None


async def _get_client() -> ShopifyClient:
    """Get or create the ShopifyClient singleton."""
    global _client  # noqa: PLW0603
    if _client is None:
        _client = ShopifyClient()
        logger.info("ShopifyClient: store=%s", _client.store_domain)
    return _client


def _error(e: ShopifyError) -> str:
    """Format a client error as a user-friendly string."""
    return f"Error: {e}"


# ===========================================================================
# Meta tools (2)
# ===========================================================================


@mcp.tool
async def shopify_info() -> str:
    """Show Shopify store connectivity, configuration, and write gate status."""
    try:
        client = await _get_client()
        store = client.store_domain
        write = "enabled" if os.environ.get("SHOPIFY_WRITE_ENABLED", "").lower() == "true" else "disabled"
        webhook = "configured" if os.environ.get("SHOPIFY_WEBHOOK_SECRET", "").strip() else "not configured"
        api_version = os.environ.get("SHOPIFY_API_VERSION", "2025-04")
        return f"Store: {store}\nAPI version: {api_version}\nAPI: connected\nWrites: {write}\nWebhook secret: {webhook}"
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_shop() -> str:
    """Get store information — name, plan, domain, currency, timezone, address."""
    try:
        client = await _get_client()
        result = await client.get_shop()
        return format_shop_info(result)
    except ShopifyError as e:
        return _error(e)


# ===========================================================================
# Location tools (1)
# ===========================================================================


@mcp.tool
async def shopify_locations() -> str:
    """List store locations with address and fulfillment service info."""
    try:
        client = await _get_client()
        result = await client.get_locations()
        return format_locations(result)
    except ShopifyError as e:
        return _error(e)


# ===========================================================================
# Product tools (6)
# ===========================================================================


@mcp.tool
async def shopify_products(
    query: Annotated[
        str | None,
        Field(description="Search query (e.g., 'title:shirt', 'status:active', 'vendor:Nike')"),
    ] = None,
    limit: Annotated[int, Field(description="Max results (default 20, max 250)")] = DEFAULT_LIMIT,
    after: Annotated[str | None, Field(description="Cursor for pagination (from previous result)")] = None,
) -> str:
    """List products with optional search. Returns: ID | title | status | price | inventory | vendor."""
    try:
        client = await _get_client()
        result = await client.list_products(query=query, limit=limit, after=after)
        return format_product_list(result)
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_product(
    id: Annotated[str, Field(description="Product ID (numeric or GID)")],
) -> str:
    """Get full product details — variants, images, options, SEO, inventory."""
    try:
        client = await _get_client()
        result = await client.get_product(id)
        return format_product_detail(result)
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_create_product(
    title: Annotated[str, Field(description="Product title")],
    product_type: Annotated[str | None, Field(description="Product type (e.g., 'Shirts')")] = None,
    vendor: Annotated[str | None, Field(description="Vendor name")] = None,
    tags: Annotated[str | None, Field(description="Comma-separated tags")] = None,
    description_html: Annotated[str | None, Field(description="HTML description")] = None,
    status: Annotated[str | None, Field(description="ACTIVE, DRAFT, or ARCHIVED")] = None,
) -> str:
    """Create a product. Requires SHOPIFY_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        input_data: dict = {"title": title}
        if product_type:
            input_data["productType"] = product_type
        if vendor:
            input_data["vendor"] = vendor
        if tags:
            input_data["tags"] = [t.strip() for t in tags.split(",")]
        if description_html:
            input_data["descriptionHtml"] = description_html
        if status:
            input_data["status"] = status.upper()
        result = await client.create_product(input_data)
        return format_mutation_result(result, "product", "created")
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_update_product(
    id: Annotated[str, Field(description="Product ID (numeric or GID)")],
    title: Annotated[str | None, Field(description="New title")] = None,
    product_type: Annotated[str | None, Field(description="New product type")] = None,
    vendor: Annotated[str | None, Field(description="New vendor")] = None,
    tags: Annotated[str | None, Field(description="Comma-separated tags (replaces existing)")] = None,
    description_html: Annotated[str | None, Field(description="New HTML description")] = None,
    status: Annotated[str | None, Field(description="ACTIVE, DRAFT, or ARCHIVED")] = None,
) -> str:
    """Update a product. Requires SHOPIFY_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        input_data: dict = {}
        if title:
            input_data["title"] = title
        if product_type:
            input_data["productType"] = product_type
        if vendor:
            input_data["vendor"] = vendor
        if tags is not None:
            input_data["tags"] = [t.strip() for t in tags.split(",")]
        if description_html:
            input_data["descriptionHtml"] = description_html
        if status:
            input_data["status"] = status.upper()
        result = await client.update_product(id, input_data)
        return format_mutation_result(result, "product", "updated")
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_delete_product(
    id: Annotated[str, Field(description="Product ID (numeric or GID)")],
    confirm: Annotated[bool, Field(description="Must be true to delete")] = False,
) -> str:
    """Delete a product. Requires SHOPIFY_WRITE_ENABLED=true and confirm=true."""
    if err := require_write():
        return err
    if err := require_confirm(confirm, "Product deletion"):
        return err
    try:
        client = await _get_client()
        result = await client.delete_product(id)
        return format_mutation_result(result, "product", "deleted")
    except ShopifyError as e:
        return _error(e)


# ===========================================================================
# Order tools (8)
# ===========================================================================


@mcp.tool
async def shopify_orders(
    query: Annotated[
        str | None,
        Field(
            description="Search query (e.g., 'financial_status:paid', "
            "'fulfillment_status:unfulfilled', 'created_at:>2026-01-01')"
        ),
    ] = None,
    limit: Annotated[int, Field(description="Max results (default 20, max 250)")] = DEFAULT_LIMIT,
    after: Annotated[str | None, Field(description="Cursor for pagination")] = None,
) -> str:
    """List orders with optional search. Returns: name | date | financial | fulfillment | total | customer | items."""
    try:
        client = await _get_client()
        result = await client.list_orders(query=query, limit=limit, after=after)
        return format_order_list(result)
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_order(
    id: Annotated[str, Field(description="Order ID (numeric, GID, or name like '#1001')")],
) -> str:
    """Get full order details — items, customer, addresses, fulfillments, transactions, refunds."""
    try:
        client = await _get_client()
        # Try order name lookup first (e.g., '#1001')
        if id.startswith("#") or (id.isdigit() and len(id) <= 6):
            from shopify_blade_mcp.models import parse_order_name

            name_num = parse_order_name(id)
            if name_num:
                search_result = await client.search_orders_by_name(id)
                edges = search_result.get("orders", {}).get("edges", [])
                if edges:
                    order_gid = edges[0]["node"]["id"]
                    result = await client.get_order(order_gid)
                    return format_order_detail(result)
                return f"No order found with name '{id}'."

        result = await client.get_order(id)
        return format_order_detail(result)
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_update_order_note(
    id: Annotated[str, Field(description="Order ID (numeric or GID)")],
    note: Annotated[str, Field(description="New note text")],
) -> str:
    """Update the note on an order. Requires SHOPIFY_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        result = await client.update_order_note(id, note)
        return format_mutation_result(result, "order", "note updated")
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_add_order_tags(
    id: Annotated[str, Field(description="Order ID (numeric or GID)")],
    tags: Annotated[str, Field(description="Comma-separated tags to add")],
) -> str:
    """Add tags to an order. Requires SHOPIFY_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        tag_list = [t.strip() for t in tags.split(",")]
        result = await client.add_order_tags(id, tag_list)
        return format_mutation_result(result, "order", "tags added")
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_close_order(
    id: Annotated[str, Field(description="Order ID (numeric or GID)")],
) -> str:
    """Close an order. Requires SHOPIFY_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        result = await client.close_order(id)
        return format_mutation_result(result, "order", "closed")
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_cancel_order(
    id: Annotated[str, Field(description="Order ID (numeric or GID)")],
    reason: Annotated[
        str | None,
        Field(description="Cancel reason: CUSTOMER, DECLINED, FRAUD, INVENTORY, OTHER"),
    ] = None,
    refund: Annotated[bool, Field(description="Issue a refund")] = False,
    restock: Annotated[bool, Field(description="Restock inventory")] = False,
    confirm: Annotated[bool, Field(description="Must be true to cancel")] = False,
) -> str:
    """Cancel an order. Requires SHOPIFY_WRITE_ENABLED=true and confirm=true."""
    if err := require_write():
        return err
    if err := require_confirm(confirm, "Order cancellation"):
        return err
    try:
        client = await _get_client()
        result = await client.cancel_order(id, reason=reason, refund=refund, restock=restock)
        # Check for orderCancelUserErrors
        cancel_result = result.get("orderCancel", {})
        user_errors = cancel_result.get("orderCancelUserErrors", [])
        if user_errors:
            return "Error: " + "; ".join(e.get("message", "?") for e in user_errors)
        return "Order cancelled."
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_search_orders(
    name: Annotated[str | None, Field(description="Order name (e.g., '#1001' or '1001')")] = None,
    email: Annotated[str | None, Field(description="Customer email")] = None,
    financial_status: Annotated[
        str | None,
        Field(description="authorized, paid, partially_paid, partially_refunded, pending, refunded, voided"),
    ] = None,
    fulfillment_status: Annotated[str | None, Field(description="fulfilled, partial, unfulfilled, restocked")] = None,
    created_after: Annotated[str | None, Field(description="ISO date (e.g., '2026-01-01')")] = None,
    created_before: Annotated[str | None, Field(description="ISO date")] = None,
    limit: Annotated[int, Field(description="Max results (default 20)")] = DEFAULT_LIMIT,
) -> str:
    """Search orders by name, email, status, or date range."""
    try:
        client = await _get_client()
        query_parts = []
        if name:
            clean = name.lstrip("#")
            query_parts.append(f"name:{clean}")
        if email:
            query_parts.append(f"email:{email}")
        if financial_status:
            query_parts.append(f"financial_status:{financial_status}")
        if fulfillment_status:
            query_parts.append(f"fulfillment_status:{fulfillment_status}")
        if created_after:
            query_parts.append(f"created_at:>{created_after}")
        if created_before:
            query_parts.append(f"created_at:<{created_before}")

        query = " ".join(query_parts) if query_parts else None
        result = await client.list_orders(query=query, limit=limit)
        return format_order_list(result)
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_order_fulfillments(
    id: Annotated[str, Field(description="Order ID (numeric or GID)")],
) -> str:
    """List fulfillment orders for an order — shows what needs to be fulfilled."""
    try:
        client = await _get_client()
        result = await client.list_fulfillment_orders(id)
        return format_fulfillment_orders(result)
    except ShopifyError as e:
        return _error(e)


# ===========================================================================
# Customer tools (5)
# ===========================================================================


@mcp.tool
async def shopify_customers(
    query: Annotated[str | None, Field(description="Search query (e.g., 'email:john@example.com', 'tag:VIP')")] = None,
    limit: Annotated[int, Field(description="Max results (default 20, max 250)")] = DEFAULT_LIMIT,
    after: Annotated[str | None, Field(description="Cursor for pagination")] = None,
) -> str:
    """List customers with optional search. Returns: ID | name | email | state | orders | spent."""
    try:
        client = await _get_client()
        result = await client.list_customers(query=query, limit=limit, after=after)
        return format_customer_list(result)
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_customer(
    id: Annotated[str, Field(description="Customer ID (numeric or GID)")],
) -> str:
    """Get full customer details — address, order history, tags, notes."""
    try:
        client = await _get_client()
        result = await client.get_customer(id)
        return format_customer_detail(result)
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_search_customers(
    email: Annotated[str | None, Field(description="Customer email")] = None,
    name: Annotated[str | None, Field(description="Customer name")] = None,
    tag: Annotated[str | None, Field(description="Customer tag")] = None,
    limit: Annotated[int, Field(description="Max results (default 20)")] = DEFAULT_LIMIT,
) -> str:
    """Search customers by email, name, or tag."""
    try:
        client = await _get_client()
        query_parts = []
        if email:
            query_parts.append(f"email:{email}")
        if name:
            query_parts.append(name)
        if tag:
            query_parts.append(f"tag:{tag}")

        query = " ".join(query_parts) if query_parts else None
        result = await client.list_customers(query=query, limit=limit)
        return format_customer_list(result)
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_create_customer(
    email: Annotated[str, Field(description="Customer email")],
    first_name: Annotated[str | None, Field(description="First name")] = None,
    last_name: Annotated[str | None, Field(description="Last name")] = None,
    phone: Annotated[str | None, Field(description="Phone number")] = None,
    note: Annotated[str | None, Field(description="Customer note")] = None,
    tags: Annotated[str | None, Field(description="Comma-separated tags")] = None,
) -> str:
    """Create a customer. Requires SHOPIFY_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        input_data: dict = {"email": email}
        if first_name:
            input_data["firstName"] = first_name
        if last_name:
            input_data["lastName"] = last_name
        if phone:
            input_data["phone"] = phone
        if note:
            input_data["note"] = note
        if tags:
            input_data["tags"] = [t.strip() for t in tags.split(",")]
        result = await client.create_customer(input_data)
        return format_mutation_result(result, "customer", "created")
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_update_customer(
    id: Annotated[str, Field(description="Customer ID (numeric or GID)")],
    email: Annotated[str | None, Field(description="New email")] = None,
    first_name: Annotated[str | None, Field(description="New first name")] = None,
    last_name: Annotated[str | None, Field(description="New last name")] = None,
    phone: Annotated[str | None, Field(description="New phone")] = None,
    note: Annotated[str | None, Field(description="New note")] = None,
    tags: Annotated[str | None, Field(description="Comma-separated tags (replaces existing)")] = None,
) -> str:
    """Update a customer. Requires SHOPIFY_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        input_data: dict = {}
        if email:
            input_data["email"] = email
        if first_name:
            input_data["firstName"] = first_name
        if last_name:
            input_data["lastName"] = last_name
        if phone:
            input_data["phone"] = phone
        if note is not None:
            input_data["note"] = note
        if tags is not None:
            input_data["tags"] = [t.strip() for t in tags.split(",")]
        result = await client.update_customer(id, input_data)
        return format_mutation_result(result, "customer", "updated")
    except ShopifyError as e:
        return _error(e)


# ===========================================================================
# Inventory tools (4)
# ===========================================================================


@mcp.tool
async def shopify_inventory(
    location_id: Annotated[
        str | None,
        Field(description="Location ID to filter by (numeric or GID). Omit to list locations."),
    ] = None,
    limit: Annotated[int, Field(description="Max results (default 20)")] = DEFAULT_LIMIT,
    after: Annotated[str | None, Field(description="Cursor for pagination")] = None,
) -> str:
    """Get inventory levels by location, or list all locations if no location specified."""
    try:
        client = await _get_client()
        result = await client.get_inventory_levels(location_id=location_id, limit=limit, after=after)
        return format_inventory_levels(result)
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_adjust_inventory(
    inventory_item_id: Annotated[str, Field(description="Inventory item ID (numeric or GID)")],
    location_id: Annotated[str, Field(description="Location ID (numeric or GID)")],
    delta: Annotated[int, Field(description="Quantity change (+/- integer)")],
    reason: Annotated[str | None, Field(description="Adjustment reason")] = None,
) -> str:
    """Adjust inventory by a delta amount. Requires SHOPIFY_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        result = await client.adjust_inventory(inventory_item_id, location_id, delta, reason=reason)
        return format_inventory_adjustment(result)
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_set_inventory(
    inventory_item_id: Annotated[str, Field(description="Inventory item ID (numeric or GID)")],
    location_id: Annotated[str, Field(description="Location ID (numeric or GID)")],
    quantity: Annotated[int, Field(description="Absolute quantity to set")],
    confirm: Annotated[bool, Field(description="Must be true to override inventory")] = False,
) -> str:
    """Set inventory to an absolute quantity. Requires SHOPIFY_WRITE_ENABLED=true and confirm=true."""
    if err := require_write():
        return err
    if err := require_confirm(confirm, "Inventory override"):
        return err
    try:
        client = await _get_client()
        result = await client.set_inventory(inventory_item_id, location_id, quantity)
        return format_inventory_adjustment(result)
    except ShopifyError as e:
        return _error(e)


# ===========================================================================
# Collection tools (4)
# ===========================================================================


@mcp.tool
async def shopify_collections(
    query: Annotated[str | None, Field(description="Search query (e.g., 'title:Summer')")] = None,
    limit: Annotated[int, Field(description="Max results (default 20)")] = DEFAULT_LIMIT,
    after: Annotated[str | None, Field(description="Cursor for pagination")] = None,
) -> str:
    """List collections. Returns: ID | title | handle | product count | sort order."""
    try:
        client = await _get_client()
        result = await client.list_collections(query=query, limit=limit, after=after)
        return format_collection_list(result)
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_collection(
    id: Annotated[str, Field(description="Collection ID (numeric or GID)")],
) -> str:
    """Get full collection details — rules (if smart collection), SEO, product count."""
    try:
        client = await _get_client()
        result = await client.get_collection(id)
        return format_collection_detail(result)
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_create_collection(
    title: Annotated[str, Field(description="Collection title")],
    description_html: Annotated[str | None, Field(description="HTML description")] = None,
    sort_order: Annotated[
        str | None,
        Field(
            description="Sort order: ALPHA_ASC, ALPHA_DESC, BEST_SELLING, "
            "CREATED, CREATED_DESC, MANUAL, PRICE_ASC, PRICE_DESC"
        ),
    ] = None,
) -> str:
    """Create a custom collection. Requires SHOPIFY_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        input_data: dict = {"title": title}
        if description_html:
            input_data["descriptionHtml"] = description_html
        if sort_order:
            input_data["sortOrder"] = sort_order.upper()
        result = await client.create_collection(input_data)
        return format_mutation_result(result, "collection", "created")
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_collection_add_products(
    collection_id: Annotated[str, Field(description="Collection ID (numeric or GID)")],
    product_ids: Annotated[str, Field(description="Comma-separated product IDs to add")],
) -> str:
    """Add products to a collection. Requires SHOPIFY_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        ids = [pid.strip() for pid in product_ids.split(",")]
        result = await client.add_products_to_collection(collection_id, ids)
        return format_mutation_result(result, "collection", "products added")
    except ShopifyError as e:
        return _error(e)


# ===========================================================================
# Fulfillment tools (3)
# ===========================================================================


@mcp.tool
async def shopify_create_fulfillment(
    fulfillment_order_id: Annotated[str, Field(description="Fulfillment order ID (from shopify_order_fulfillments)")],
    tracking_number: Annotated[str | None, Field(description="Tracking number")] = None,
    tracking_url: Annotated[str | None, Field(description="Tracking URL")] = None,
    tracking_company: Annotated[str | None, Field(description="Shipping carrier name")] = None,
    notify_customer: Annotated[bool, Field(description="Send notification email (default true)")] = True,
) -> str:
    """Create a fulfillment for a fulfillment order. Requires SHOPIFY_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        result = await client.create_fulfillment(
            fulfillment_order_id,
            tracking_number=tracking_number,
            tracking_url=tracking_url,
            tracking_company=tracking_company,
            notify_customer=notify_customer,
        )
        return format_fulfillment_created(result)
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_update_tracking(
    fulfillment_id: Annotated[str, Field(description="Fulfillment ID (numeric or GID)")],
    tracking_number: Annotated[str | None, Field(description="New tracking number")] = None,
    tracking_url: Annotated[str | None, Field(description="New tracking URL")] = None,
    tracking_company: Annotated[str | None, Field(description="New shipping carrier")] = None,
    notify_customer: Annotated[bool, Field(description="Send notification email")] = False,
) -> str:
    """Update tracking information on a fulfillment. Requires SHOPIFY_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        result = await client.update_tracking(
            fulfillment_id,
            tracking_number=tracking_number,
            tracking_url=tracking_url,
            tracking_company=tracking_company,
            notify_customer=notify_customer,
        )
        return format_mutation_result(result, "fulfillment", "tracking updated")
    except ShopifyError as e:
        return _error(e)


# ===========================================================================
# Discount tools (3)
# ===========================================================================


@mcp.tool
async def shopify_discounts(
    query: Annotated[str | None, Field(description="Search query (e.g., 'status:active')")] = None,
    limit: Annotated[int, Field(description="Max results (default 20)")] = DEFAULT_LIMIT,
    after: Annotated[str | None, Field(description="Cursor for pagination")] = None,
) -> str:
    """List discount codes. Returns: ID | code | title | status | value | usage."""
    try:
        client = await _get_client()
        result = await client.list_discounts(query=query, limit=limit, after=after)
        return format_discount_list(result)
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_create_discount(
    title: Annotated[str, Field(description="Discount title")],
    code: Annotated[str, Field(description="Discount code (e.g., 'SAVE20')")],
    percentage: Annotated[float | None, Field(description="Percentage off (e.g., 20.0 for 20%)")] = None,
    amount: Annotated[float | None, Field(description="Fixed amount off (in store currency)")] = None,
    starts_at: Annotated[str | None, Field(description="Start date (ISO 8601)")] = None,
    ends_at: Annotated[str | None, Field(description="End date (ISO 8601)")] = None,
    usage_limit: Annotated[int | None, Field(description="Max total uses")] = None,
    once_per_customer: Annotated[bool, Field(description="Limit to one use per customer")] = False,
) -> str:
    """Create a basic discount code. Requires SHOPIFY_WRITE_ENABLED=true. Specify either percentage or amount."""
    if err := require_write():
        return err
    if not percentage and not amount:
        return "Error: Specify either percentage (e.g., 20.0) or amount (e.g., 10.00)."
    try:
        client = await _get_client()

        # Build the discount input
        value: dict
        if percentage:
            value = {"percentage": percentage / 100}  # Shopify expects decimal
        else:
            value = {"discountAmount": {"amount": str(amount), "appliesOnEachItem": False}}

        input_data: dict = {
            "title": title,
            "code": code,
            "startsAt": starts_at or "2026-01-01T00:00:00Z",
            "customerGets": {
                "value": value,
                "items": {"allItems": True},
            },
            "customerSelection": {"allCustomers": True},
            "appliesOncePerCustomer": once_per_customer,
        }
        if ends_at:
            input_data["endsAt"] = ends_at
        if usage_limit:
            input_data["usageLimit"] = usage_limit

        result = await client.create_basic_discount(input_data)
        return format_mutation_result(result, "discount", "created")
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_delete_discount(
    id: Annotated[str, Field(description="Discount node ID (numeric or GID)")],
    confirm: Annotated[bool, Field(description="Must be true to delete")] = False,
) -> str:
    """Delete a discount code. Requires SHOPIFY_WRITE_ENABLED=true and confirm=true."""
    if err := require_write():
        return err
    if err := require_confirm(confirm, "Discount deletion"):
        return err
    try:
        client = await _get_client()
        result = await client.delete_discount(id)
        return format_mutation_result(result, "discount", "deleted")
    except ShopifyError as e:
        return _error(e)


# ===========================================================================
# Metafield tools (3)
# ===========================================================================


@mcp.tool
async def shopify_metafields(
    owner_type: Annotated[str, Field(description="Resource type: product, order, customer, collection")],
    owner_id: Annotated[str, Field(description="Resource ID (numeric or GID)")],
    namespace: Annotated[str | None, Field(description="Filter by namespace")] = None,
    limit: Annotated[int, Field(description="Max results (default 20)")] = DEFAULT_LIMIT,
) -> str:
    """Get metafields for a resource."""
    try:
        client = await _get_client()
        result = await client.get_metafields(owner_type, owner_id, namespace=namespace, limit=limit)
        return format_metafield_list(result, owner_type)
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_set_metafield(
    owner_id: Annotated[str, Field(description="Resource GID (e.g., 'gid://shopify/Product/123')")],
    namespace: Annotated[str, Field(description="Metafield namespace")],
    key: Annotated[str, Field(description="Metafield key")],
    value: Annotated[str, Field(description="Metafield value")],
    type: Annotated[
        str,
        Field(description="Metafield type (e.g., 'single_line_text_field', 'number_integer', 'json', 'boolean')"),
    ],
) -> str:
    """Set a metafield on a resource. Requires SHOPIFY_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        result = await client.set_metafields(
            [
                {
                    "ownerId": owner_id,
                    "namespace": namespace,
                    "key": key,
                    "value": value,
                    "type": type,
                }
            ]
        )
        return format_metafield_set(result)
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_delete_metafield(
    id: Annotated[str, Field(description="Metafield ID (numeric or GID)")],
    confirm: Annotated[bool, Field(description="Must be true to delete")] = False,
) -> str:
    """Delete a metafield. Requires SHOPIFY_WRITE_ENABLED=true and confirm=true."""
    if err := require_write():
        return err
    if err := require_confirm(confirm, "Metafield deletion"):
        return err
    try:
        client = await _get_client()
        result = await client.delete_metafield(id)
        return format_mutation_result(result, "metafield", "deleted")
    except ShopifyError as e:
        return _error(e)


# ===========================================================================
# Webhook tools (3)
# ===========================================================================


@mcp.tool
async def shopify_webhooks(
    limit: Annotated[int, Field(description="Max results (default 20)")] = DEFAULT_LIMIT,
    after: Annotated[str | None, Field(description="Cursor for pagination")] = None,
) -> str:
    """List webhook subscriptions. Returns: ID | topic | callback URL | format."""
    try:
        client = await _get_client()
        result = await client.list_webhooks(limit=limit, after=after)
        return format_webhook_list(result)
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_create_webhook(
    topic: Annotated[
        str,
        Field(description="Webhook topic (e.g., 'ORDERS_CREATE', 'PRODUCTS_UPDATE', 'CUSTOMERS_CREATE')"),
    ],
    callback_url: Annotated[str, Field(description="HTTPS URL to receive webhooks")],
    format: Annotated[str, Field(description="Payload format: JSON or XML")] = "JSON",
) -> str:
    """Create a webhook subscription. Requires SHOPIFY_WRITE_ENABLED=true."""
    if err := require_write():
        return err
    try:
        client = await _get_client()
        result = await client.create_webhook(topic, callback_url, webhook_format=format)
        return format_webhook_created(result)
    except ShopifyError as e:
        return _error(e)


@mcp.tool
async def shopify_delete_webhook(
    id: Annotated[str, Field(description="Webhook subscription ID (numeric or GID)")],
    confirm: Annotated[bool, Field(description="Must be true to delete")] = False,
) -> str:
    """Delete a webhook subscription. Requires SHOPIFY_WRITE_ENABLED=true and confirm=true."""
    if err := require_write():
        return err
    if err := require_confirm(confirm, "Webhook deletion"):
        return err
    try:
        client = await _get_client()
        result = await client.delete_webhook(id)
        return format_mutation_result(result, "webhook", "deleted")
    except ShopifyError as e:
        return _error(e)


# ===========================================================================
# Analytics tools (1)
# ===========================================================================


@mcp.tool
async def shopify_analytics(
    query: Annotated[
        str,
        Field(description="ShopifyQL query (e.g., 'FROM sales SHOW total_sales BY day SINCE -30d UNTIL today')"),
    ],
) -> str:
    """Run a ShopifyQL analytics query. Returns tabular data with columns and rows.

    Common ShopifyQL patterns:
    - FROM sales SHOW total_sales, order_count SINCE -30d
    - FROM sales SHOW total_sales BY product_title SINCE -7d ORDER BY total_sales DESC LIMIT 10
    - FROM orders SHOW count BY day SINCE -30d UNTIL today
    - FROM products SHOW sum(inventory_quantity) BY product_title ORDER BY sum(inventory_quantity) ASC LIMIT 20
    """
    try:
        client = await _get_client()
        result = await client.run_shopifyql(query)
        return format_analytics_result(result)
    except ShopifyError as e:
        return _error(e)


# ===========================================================================
# Webhook verification tool (1)
# ===========================================================================


@mcp.tool
async def shopify_verify_webhook(
    raw_body: Annotated[str, Field(description="Raw webhook request body")],
    hmac_header: Annotated[str, Field(description="Value of X-Shopify-Hmac-SHA256 header")],
) -> str:
    """Verify a Shopify webhook HMAC-SHA256 signature. Requires SHOPIFY_WEBHOOK_SECRET env var."""
    secret = os.environ.get("SHOPIFY_WEBHOOK_SECRET", "").strip()
    if not secret:
        return "Error: SHOPIFY_WEBHOOK_SECRET environment variable is required for webhook verification."
    result = ShopifyClient.verify_webhook_signature(raw_body, hmac_header, secret)
    return format_webhook_verification(result)


# ===========================================================================
# Server entry point
# ===========================================================================


def main() -> None:
    """Run the MCP server."""
    if TRANSPORT == "http":
        mcp.run(transport="sse", host=HTTP_HOST, port=HTTP_PORT)
    else:
        mcp.run(transport="stdio")
