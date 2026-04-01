"""Shared constants, types, and gates for Shopify Blade MCP server."""

from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------

DEFAULT_LIMIT = 20
MAX_LIMIT = 250  # Shopify GraphQL max per query
MAX_BODY_CHARS = 50_000

# ---------------------------------------------------------------------------
# Shopify API configuration
# ---------------------------------------------------------------------------

DEFAULT_API_VERSION = "2025-04"

CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "AUD": "A$",
    "CAD": "C$",
    "NZD": "NZ$",
    "HKD": "HK$",
    "SGD": "S$",
    "JPY": "¥",
    "CNY": "¥",
    "CHF": "CHF ",
    "SEK": "kr",
    "NOK": "kr",
    "DKK": "kr",
    "INR": "₹",
    "BRL": "R$",
    "KRW": "₩",
    "MXN": "MX$",
    "PLN": "zł",
    "THB": "฿",
    "TRY": "₺",
}

ZERO_DECIMAL_CURRENCIES: set[str] = {"JPY", "KRW", "VND"}

# Order financial/fulfillment status values
ORDER_FINANCIAL_STATUSES = {
    "authorized",
    "paid",
    "partially_paid",
    "partially_refunded",
    "pending",
    "refunded",
    "voided",
}
ORDER_FULFILLMENT_STATUSES = {"fulfilled", "partial", "unfulfilled", "restocked"}

# ---------------------------------------------------------------------------
# GID helpers
# ---------------------------------------------------------------------------

GID_PREFIX = "gid://shopify/"

# Map of resource type names to their GID type
GID_TYPES: dict[str, str] = {
    "product": "Product",
    "variant": "ProductVariant",
    "order": "Order",
    "customer": "Customer",
    "collection": "Collection",
    "inventory_item": "InventoryItem",
    "inventory_level": "InventoryLevel",
    "location": "Location",
    "fulfillment": "Fulfillment",
    "fulfillment_order": "FulfillmentOrder",
    "discount": "DiscountNode",
    "discount_code": "DiscountCodeNode",
    "discount_automatic": "DiscountAutomaticNode",
    "metafield": "Metafield",
    "webhook": "WebhookSubscription",
    "image": "MediaImage",
    "draft_order": "DraftOrder",
}


def to_gid(resource_type: str, numeric_id: str | int) -> str:
    """Convert a numeric ID to a Shopify Global ID.

    Examples:
        to_gid("product", 123) -> "gid://shopify/Product/123"
        to_gid("order", "456") -> "gid://shopify/Order/456"
    """
    gid_type = GID_TYPES.get(resource_type, resource_type.title())
    return f"{GID_PREFIX}{gid_type}/{numeric_id}"


def from_gid(gid: str) -> str:
    """Extract the numeric ID from a Shopify Global ID.

    Examples:
        from_gid("gid://shopify/Product/123") -> "123"
        from_gid("123") -> "123"  # passthrough for plain IDs
    """
    if gid.startswith(GID_PREFIX):
        return gid.rsplit("/", 1)[-1]
    return gid


def normalize_id(resource_type: str, id_value: str) -> str:
    """Normalize an ID to a GID — accepts numeric, plain, or full GID.

    Examples:
        normalize_id("product", "123") -> "gid://shopify/Product/123"
        normalize_id("product", "gid://shopify/Product/123") -> "gid://shopify/Product/123"
    """
    if id_value.startswith(GID_PREFIX):
        return id_value
    return to_gid(resource_type, id_value)


def parse_order_name(name: str) -> str | None:
    """Extract the numeric portion from an order name like '#1001'.

    Returns None if the name doesn't match the expected format.
    """
    match = re.match(r"#?(\d+)", name.strip())
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


def get_store_domain() -> str:
    """Return the configured store domain.

    Raises:
        ValueError: If SHOPIFY_STORE_DOMAIN is not set.
    """
    domain = os.environ.get("SHOPIFY_STORE_DOMAIN", "").strip()
    if not domain:
        raise ValueError(
            "SHOPIFY_STORE_DOMAIN is required. Set it to your store's myshopify.com domain "
            "(e.g., 'my-store.myshopify.com')."
        )
    # Strip protocol if accidentally included
    domain = domain.replace("https://", "").replace("http://", "").rstrip("/")
    return domain


def get_api_version() -> str:
    """Return the configured API version (default: 2025-04)."""
    return os.environ.get("SHOPIFY_API_VERSION", DEFAULT_API_VERSION).strip()


def get_graphql_url() -> str:
    """Build the Admin GraphQL API URL."""
    domain = get_store_domain()
    version = get_api_version()
    return f"https://{domain}/admin/api/{version}/graphql.json"


# ---------------------------------------------------------------------------
# Write gate
# ---------------------------------------------------------------------------


def is_write_enabled() -> bool:
    """Check if write operations are enabled via env var."""
    return os.environ.get("SHOPIFY_WRITE_ENABLED", "").lower() == "true"


def require_write() -> str | None:
    """Return an error message if writes are disabled, else None."""
    if not is_write_enabled():
        return "Error: Write operations are disabled. Set SHOPIFY_WRITE_ENABLED=true to enable."
    return None


# ---------------------------------------------------------------------------
# Confirm gate (for destructive operations)
# ---------------------------------------------------------------------------


def require_confirm(confirm: bool, action: str) -> str | None:
    """Return an error message if confirm is False for a destructive operation.

    This is a second gate beyond require_write() for operations that are
    difficult or impossible to reverse (cancel order, delete product, refund).
    """
    if not confirm:
        return f"Error: {action} requires confirm=true. This action may be difficult to reverse."
    return None


# ---------------------------------------------------------------------------
# Money formatting
# ---------------------------------------------------------------------------


def format_money(amount: str, currency_code: str) -> str:
    """Format a Shopify money amount for human-readable output.

    Shopify stores amounts as decimal strings (e.g., "29.99").

    Examples:
        format_money("29.99", "USD") -> "$29.99 USD"
        format_money("1000", "JPY") -> "¥1000 JPY"
    """
    try:
        value = float(amount)
    except (ValueError, TypeError):
        return f"{amount} {currency_code}"

    symbol = CURRENCY_SYMBOLS.get(currency_code, "")

    if currency_code in ZERO_DECIMAL_CURRENCIES:
        return f"{symbol}{int(value)} {currency_code}"

    return f"{symbol}{value:.2f} {currency_code}"


# ---------------------------------------------------------------------------
# Token scrubbing
# ---------------------------------------------------------------------------

_SCRUB_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"shpat_[a-fA-F0-9]+"),  # Shopify Admin API access tokens
    re.compile(r"shpca_[a-fA-F0-9]+"),  # Shopify custom app tokens
    re.compile(r"shpss_[a-fA-F0-9]+"),  # Shopify shared secret
    re.compile(r"Bearer\s+[^\s]+", re.IGNORECASE),  # Bearer tokens
]


def scrub_secrets(text: str) -> str:
    """Remove API keys and tokens from text to prevent leakage."""
    result = text
    for pattern in _SCRUB_PATTERNS:
        result = pattern.sub("****", result)
    return result
