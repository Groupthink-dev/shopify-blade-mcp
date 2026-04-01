"""Token-efficient output formatters for Shopify data.

Design principles:
- Concise by default (one line per item)
- Null fields omitted
- Pipe-delimited lists
- Lists capped and annotated with total count
- Money in human-readable format ($29.99 USD)
- Dates in short format (2026-03-15 14:30)
- GIDs shortened to numeric IDs for display
"""

from __future__ import annotations

from typing import Any

from shopify_blade_mcp.models import format_money, from_gid

# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------


def format_datetime(iso_str: str | None) -> str:
    """Format ISO datetime to short form: '2026-03-15T14:30:00Z' -> '2026-03-15 14:30'."""
    if not iso_str:
        return "?"
    clean = iso_str.replace("Z", "").replace("+00:00", "")
    return clean[:16].replace("T", " ")


def format_date(iso_str: str | None) -> str:
    """Format ISO datetime to date only: '2026-03-15T14:30:00Z' -> '2026-03-15'."""
    if not iso_str:
        return "?"
    return iso_str[:10]


# ---------------------------------------------------------------------------
# Money helpers
# ---------------------------------------------------------------------------


def format_money_set(money_set: dict[str, Any] | None) -> str:
    """Format a Shopify MoneyV2 or MoneyBag shopMoney field."""
    if not money_set:
        return "?"
    shop_money = money_set.get("shopMoney") or money_set
    amount = shop_money.get("amount", "0")
    currency = shop_money.get("currencyCode", "???")
    return format_money(amount, currency)


def format_price_range(price_range: dict[str, Any] | None) -> str:
    """Format a price range (min-max)."""
    if not price_range:
        return "?"
    min_price = price_range.get("minVariantPrice", {})
    max_price = price_range.get("maxVariantPrice", {})
    min_str = format_money(min_price.get("amount", "0"), min_price.get("currencyCode", "???"))
    max_str = format_money(max_price.get("amount", "0"), max_price.get("currencyCode", "???"))
    if min_str == max_str:
        return min_str
    return f"{min_str}–{max_str}"


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def format_pagination(edges: list[dict[str, Any]], page_info: dict[str, Any] | None, shown: int) -> str:
    """Generate pagination hint.

    Returns:
        Hint string like '... more (pass after="cursor" to continue)' or empty.
    """
    if not page_info or not page_info.get("hasNextPage"):
        return ""
    last_cursor = edges[-1].get("cursor", "") if edges else ""
    if last_cursor:
        return f'\n... more results (pass after="{last_cursor}" to continue)'
    return "\n... more results available"


# ---------------------------------------------------------------------------
# Short ID helper
# ---------------------------------------------------------------------------


def short_id(gid: str | None) -> str:
    """Display a GID as its numeric portion."""
    if not gid:
        return "?"
    return from_gid(gid)


# ---------------------------------------------------------------------------
# Product formatters
# ---------------------------------------------------------------------------


def format_product_list(data: dict[str, Any]) -> str:
    """Format product list as pipe-delimited rows."""
    products = data.get("products", {})
    edges = products.get("edges", [])
    if not edges:
        return "No products found."

    lines = []
    for edge in edges:
        node = edge.get("node", {})
        pid = short_id(node.get("id"))
        title = node.get("title", "?")
        status = node.get("status", "?").lower()
        vendor = node.get("vendor", "")
        price = format_price_range(node.get("priceRangeV2"))
        inventory = node.get("totalInventory", "?")
        parts = [pid, title, status, price, f"inv={inventory}"]
        if vendor:
            parts.append(vendor)
        lines.append(" | ".join(str(p) for p in parts))

    result = "\n".join(lines)
    page_hint = format_pagination(edges, products.get("pageInfo"), len(edges))
    return result + page_hint


def format_product_detail(data: dict[str, Any]) -> str:
    """Format a single product with variants and images."""
    p = data.get("product")
    if not p:
        return "Product not found."

    lines = [
        f"Product: {p.get('title', '?')} ({short_id(p.get('id'))})",
        f"Status: {(p.get('status') or '?').lower()}",
        f"Handle: {p.get('handle', '?')}",
    ]

    if p.get("vendor"):
        lines.append(f"Vendor: {p['vendor']}")
    if p.get("productType"):
        lines.append(f"Type: {p['productType']}")

    price = format_price_range(p.get("priceRangeV2"))
    lines.append(f"Price: {price}")

    inv = p.get("totalInventory")
    if inv is not None:
        lines.append(f"Inventory: {inv}")

    if p.get("tags"):
        lines.append(f"Tags: {', '.join(p['tags'])}")

    if p.get("onlineStoreUrl"):
        lines.append(f"URL: {p['onlineStoreUrl']}")

    lines.append(f"Created: {format_datetime(p.get('createdAt'))}")

    # Options
    options = p.get("options", [])
    if options:
        lines.append("\nOptions:")
        for opt in options:
            lines.append(f"  {opt.get('name', '?')}: {', '.join(opt.get('values', []))}")

    # Variants
    variants = p.get("variants", {}).get("edges", [])
    if variants:
        lines.append(f"\nVariants ({len(variants)}):")
        for edge in variants:
            v = edge.get("node", {})
            vid = short_id(v.get("id"))
            vtitle = v.get("title", "?")
            vprice = v.get("price", "?")
            vsku = v.get("sku", "")
            vinv = v.get("inventoryQuantity", "?")
            sku_part = f" SKU={vsku}" if vsku else ""
            lines.append(f"  {vid} | {vtitle} | ${vprice} | inv={vinv}{sku_part}")

    # SEO
    seo = p.get("seo", {})
    if seo and (seo.get("title") or seo.get("description")):
        lines.append("\nSEO:")
        if seo.get("title"):
            lines.append(f"  Title: {seo['title']}")
        if seo.get("description"):
            lines.append(f"  Description: {seo['description'][:100]}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Order formatters
# ---------------------------------------------------------------------------


def format_order_list(data: dict[str, Any]) -> str:
    """Format order list as pipe-delimited rows."""
    orders = data.get("orders", {})
    edges = orders.get("edges", [])
    if not edges:
        return "No orders found."

    lines = []
    for edge in edges:
        node = edge.get("node", {})
        name = node.get("name", "?")
        date = format_date(node.get("createdAt"))
        financial = (node.get("displayFinancialStatus") or "?").lower()
        fulfillment = (node.get("displayFulfillmentStatus") or "?").lower()
        total = format_money_set(node.get("totalPriceSet"))
        customer = node.get("customer", {})
        cust_name = customer.get("displayName", "guest") if customer else "guest"

        line_items = node.get("lineItems", {}).get("edges", [])
        item_count = len(line_items)
        item_summary = f"{item_count} item{'s' if item_count != 1 else ''}"

        lines.append(f"{name} | {date} | {financial} | {fulfillment} | {total} | {cust_name} | {item_summary}")

    result = "\n".join(lines)
    page_hint = format_pagination(edges, orders.get("pageInfo"), len(edges))
    return result + page_hint


def format_order_detail(data: dict[str, Any]) -> str:
    """Format a single order with full details."""
    o = data.get("order")
    if not o:
        return "Order not found."

    lines = [
        f"Order: {o.get('name', '?')} ({short_id(o.get('id'))})",
        f"Status: {(o.get('displayFinancialStatus') or '?').lower()}"
        f" / {(o.get('displayFulfillmentStatus') or '?').lower()}",
        f"Created: {format_datetime(o.get('createdAt'))}",
    ]

    if o.get("closedAt"):
        lines.append(f"Closed: {format_datetime(o['closedAt'])}")
    if o.get("cancelledAt"):
        lines.append(f"Cancelled: {format_datetime(o['cancelledAt'])} ({o.get('cancelReason', '?')})")

    # Money
    lines.append(f"\nSubtotal: {format_money_set(o.get('subtotalPriceSet'))}")
    lines.append(f"Tax: {format_money_set(o.get('totalTaxSet'))}")

    shipping = o.get("totalShippingPriceSet")
    if shipping:
        lines.append(f"Shipping: {format_money_set(shipping)}")

    discounts = o.get("totalDiscountsSet")
    if discounts:
        lines.append(f"Discounts: -{format_money_set(discounts)}")

    lines.append(f"Total: {format_money_set(o.get('totalPriceSet'))}")

    refunded = o.get("totalRefundedSet")
    if refunded:
        lines.append(f"Refunded: {format_money_set(refunded)}")
        lines.append(f"Current total: {format_money_set(o.get('currentTotalPriceSet'))}")

    # Customer
    customer = o.get("customer")
    if customer:
        cust_parts = [customer.get("displayName", "?")]
        if customer.get("email"):
            cust_parts.append(customer["email"])
        lines.append(f"\nCustomer: {' | '.join(cust_parts)}")

    # Addresses
    shipping_addr = o.get("shippingAddress")
    if shipping_addr:
        addr = _format_address(shipping_addr)
        lines.append(f"Ship to: {addr}")

    # Line items
    line_items = o.get("lineItems", {}).get("edges", [])
    if line_items:
        lines.append(f"\nItems ({len(line_items)}):")
        for edge in line_items:
            item = edge.get("node", {})
            title = item.get("title", "?")
            qty = item.get("quantity", 1)
            total = format_money_set(item.get("originalTotalSet"))
            sku = item.get("sku", "")
            sku_part = f" SKU={sku}" if sku else ""
            lines.append(f"  {qty}x {title} | {total}{sku_part}")

    # Note/tags
    if o.get("note"):
        lines.append(f"\nNote: {o['note']}")
    if o.get("tags"):
        lines.append(f"Tags: {', '.join(o['tags'])}")

    # Fulfillments
    fulfillments = o.get("fulfillments", [])
    if fulfillments:
        lines.append(f"\nFulfillments ({len(fulfillments)}):")
        for f in fulfillments:
            fid = short_id(f.get("id"))
            status = (f.get("status") or "?").lower()
            tracking = f.get("trackingInfo", [])
            tracking_str = ""
            if tracking:
                t = tracking[0] if isinstance(tracking, list) else tracking
                parts = []
                if t.get("company"):
                    parts.append(t["company"])
                if t.get("number"):
                    parts.append(t["number"])
                tracking_str = f" ({', '.join(parts)})" if parts else ""
            lines.append(f"  {fid} | {status}{tracking_str} | {format_datetime(f.get('createdAt'))}")

    # Transactions
    transactions = o.get("transactions", [])
    if transactions:
        lines.append(f"\nTransactions ({len(transactions)}):")
        for t in transactions:
            kind = t.get("kind", "?")
            status = t.get("status", "?")
            amount = format_money_set(t.get("amountSet"))
            gateway = t.get("gateway", "?")
            lines.append(f"  {kind} | {status} | {amount} | {gateway}")

    return "\n".join(lines)


def _format_address(addr: dict[str, Any]) -> str:
    """Format an address to a single line."""
    parts = []
    if addr.get("address1"):
        parts.append(addr["address1"])
    if addr.get("city"):
        parts.append(addr["city"])
    if addr.get("province"):
        parts.append(addr["province"])
    if addr.get("country"):
        parts.append(addr["country"])
    if addr.get("zip"):
        parts.append(addr["zip"])
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Customer formatters
# ---------------------------------------------------------------------------


def format_customer_list(data: dict[str, Any]) -> str:
    """Format customer list as pipe-delimited rows."""
    customers = data.get("customers", {})
    edges = customers.get("edges", [])
    if not edges:
        return "No customers found."

    lines = []
    for edge in edges:
        node = edge.get("node", {})
        cid = short_id(node.get("id"))
        name = node.get("displayName", "?")
        email = node.get("email", "")
        state = (node.get("state") or "?").lower()
        orders = node.get("numberOfOrders", "?")
        spent = format_money_set(node.get("amountSpent"))
        parts = [cid, name, email, state, f"orders={orders}", f"spent={spent}"]
        lines.append(" | ".join(str(p) for p in parts))

    result = "\n".join(lines)
    page_hint = format_pagination(edges, customers.get("pageInfo"), len(edges))
    return result + page_hint


def format_customer_detail(data: dict[str, Any]) -> str:
    """Format a single customer with full details."""
    c = data.get("customer")
    if not c:
        return "Customer not found."

    lines = [
        f"Customer: {c.get('displayName', '?')} ({short_id(c.get('id'))})",
    ]

    if c.get("firstName") or c.get("lastName"):
        lines.append(f"Name: {c.get('firstName', '')} {c.get('lastName', '')}".strip())

    if c.get("email"):
        verified = " (verified)" if c.get("verifiedEmail") else " (unverified)"
        lines.append(f"Email: {c['email']}{verified}")

    if c.get("phone"):
        lines.append(f"Phone: {c['phone']}")

    lines.append(f"State: {(c.get('state') or '?').lower()}")
    lines.append(f"Orders: {c.get('numberOfOrders', '?')}")
    lines.append(f"Total spent: {format_money_set(c.get('amountSpent'))}")
    lines.append(f"Created: {format_datetime(c.get('createdAt'))}")

    if c.get("note"):
        lines.append(f"Note: {c['note']}")
    if c.get("tags"):
        lines.append(f"Tags: {', '.join(c['tags'])}")

    if c.get("taxExempt"):
        lines.append("Tax exempt: yes")

    # Default address
    default_addr = c.get("defaultAddress")
    if default_addr:
        lines.append(f"\nDefault address: {_format_address(default_addr)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Inventory formatters
# ---------------------------------------------------------------------------


def format_inventory_levels(data: dict[str, Any]) -> str:
    """Format inventory levels."""
    location = data.get("location")
    if location:
        levels = location.get("inventoryLevels", {}).get("edges", [])
        if not levels:
            return f"No inventory at {location.get('name', '?')}."

        lines = [f"Inventory at {location.get('name', '?')}:"]
        for edge in levels:
            node = edge.get("node", {})
            item = node.get("item", {})
            sku = item.get("sku", "")
            variant = item.get("variant", {})
            product = variant.get("product", {}) if variant else {}
            product_title = product.get("title", "?") if product else "?"
            variant_title = variant.get("title", "") if variant else ""

            quantities = {q["name"]: q["quantity"] for q in node.get("quantities", [])}
            available = quantities.get("available", "?")
            committed = quantities.get("committed", 0)
            on_hand = quantities.get("on_hand", "?")

            parts = [product_title]
            if variant_title and variant_title != "Default Title":
                parts[0] += f" / {variant_title}"
            if sku:
                parts.append(f"SKU={sku}")
            parts.append(f"avail={available}")
            if committed:
                parts.append(f"committed={committed}")
            parts.append(f"on_hand={on_hand}")
            lines.append("  " + " | ".join(str(p) for p in parts))

        return "\n".join(lines)

    # Locations list
    locations = data.get("locations", {}).get("edges", [])
    if not locations:
        return "No locations found."

    lines = ["Locations:"]
    for edge in locations:
        node = edge.get("node", {})
        lid = short_id(node.get("id"))
        name = node.get("name", "?")
        active = "active" if node.get("isActive") else "inactive"
        addr = node.get("address", {})
        addr_str = _format_address(addr) if addr else ""
        parts = [lid, name, active]
        if addr_str:
            parts.append(addr_str)
        lines.append("  " + " | ".join(parts))

    return "\n".join(lines)


def format_inventory_adjustment(data: dict[str, Any]) -> str:
    """Format inventory adjustment result."""
    group = None
    for key in ("inventoryAdjustQuantities", "inventorySetOnHandQuantities"):
        if key in data:
            group = data[key].get("inventoryAdjustmentGroup")
            break

    if not group:
        return "Inventory adjusted."

    changes = group.get("changes", [])
    lines = [f"Inventory adjusted (reason: {group.get('reason', '?')}):"]
    for change in changes:
        item = change.get("item", {})
        location = change.get("location", {})
        sku = item.get("sku", "?")
        loc_name = location.get("name", "?")
        delta = change.get("delta", 0)
        after = change.get("quantityAfterChange", "?")
        sign = "+" if delta > 0 else ""
        lines.append(f"  {sku} @ {loc_name}: {sign}{delta} → {after}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Collection formatters
# ---------------------------------------------------------------------------


def format_collection_list(data: dict[str, Any]) -> str:
    """Format collection list as pipe-delimited rows."""
    collections = data.get("collections", {})
    edges = collections.get("edges", [])
    if not edges:
        return "No collections found."

    lines = []
    for edge in edges:
        node = edge.get("node", {})
        cid = short_id(node.get("id"))
        title = node.get("title", "?")
        handle = node.get("handle", "?")
        count = node.get("productsCount", {}).get("count", "?")
        sort = node.get("sortOrder", "?")
        lines.append(f"{cid} | {title} | /{handle} | {count} products | sort={sort}")

    result = "\n".join(lines)
    page_hint = format_pagination(edges, collections.get("pageInfo"), len(edges))
    return result + page_hint


def format_collection_detail(data: dict[str, Any]) -> str:
    """Format a single collection with full details."""
    c = data.get("collection")
    if not c:
        return "Collection not found."

    lines = [
        f"Collection: {c.get('title', '?')} ({short_id(c.get('id'))})",
        f"Handle: /{c.get('handle', '?')}",
        f"Products: {c.get('productsCount', {}).get('count', '?')}",
        f"Sort: {c.get('sortOrder', '?')}",
    ]

    # Rules (smart collection)
    rule_set = c.get("ruleSet")
    if rule_set:
        disjunctive = "ANY" if rule_set.get("appliedDisjunctively") else "ALL"
        rules = rule_set.get("rules", [])
        lines.append(f"\nRules (match {disjunctive}):")
        for r in rules:
            lines.append(f"  {r.get('column', '?')} {r.get('relation', '?')} {r.get('condition', '?')}")

    seo = c.get("seo", {})
    if seo and (seo.get("title") or seo.get("description")):
        lines.append(f"\nSEO title: {seo.get('title', '—')}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fulfillment formatters
# ---------------------------------------------------------------------------


def format_fulfillment_orders(data: dict[str, Any]) -> str:
    """Format fulfillment orders for an order."""
    order = data.get("order", {})
    fo_edges = order.get("fulfillmentOrders", {}).get("edges", [])
    if not fo_edges:
        return "No fulfillment orders found."

    lines = []
    for edge in fo_edges:
        node = edge.get("node", {})
        foid = short_id(node.get("id"))
        status = (node.get("status") or "?").lower()
        location = node.get("assignedLocation", {}).get("name", "?")

        items = node.get("lineItems", {}).get("edges", [])
        item_parts = []
        for item_edge in items:
            item = item_edge.get("node", {})
            li = item.get("lineItem", {})
            total = item.get("totalQuantity", "?")
            remaining = item.get("remainingQuantity", 0)
            title = li.get("title", "?")
            item_parts.append(f"{title} ({remaining}/{total})")

        lines.append(f"{foid} | {status} | {location}")
        for ip in item_parts:
            lines.append(f"  {ip}")

    return "\n".join(lines)


def format_fulfillment_created(data: dict[str, Any]) -> str:
    """Format fulfillment creation result."""
    result = data.get("fulfillmentCreateV2", {})
    f = result.get("fulfillment")
    if not f:
        return "Fulfillment created."

    fid = short_id(f.get("id"))
    status = (f.get("status") or "?").lower()
    tracking = f.get("trackingInfo", {})
    tracking_str = ""
    if tracking:
        parts = []
        if tracking.get("company"):
            parts.append(tracking["company"])
        if tracking.get("number"):
            parts.append(tracking["number"])
        tracking_str = f" | tracking: {', '.join(parts)}" if parts else ""

    return f"Fulfillment created: {fid} | {status}{tracking_str}"


# ---------------------------------------------------------------------------
# Discount formatters
# ---------------------------------------------------------------------------


def format_discount_list(data: dict[str, Any]) -> str:
    """Format discount list."""
    discounts = data.get("codeDiscountNodes", {})
    edges = discounts.get("edges", [])
    if not edges:
        return "No discounts found."

    lines = []
    for edge in edges:
        node = edge.get("node", {})
        did = short_id(node.get("id"))
        discount = node.get("codeDiscount", {})
        title = discount.get("title", "?")
        status = (discount.get("status") or "?").lower()
        codes = discount.get("codes", {}).get("edges", [])
        code = codes[0]["node"]["code"] if codes else "?"
        usage = discount.get("asyncUsageCount", 0)
        limit = discount.get("usageLimit")
        usage_str = f"{usage}/{limit}" if limit else str(usage)

        # Value
        value = discount.get("customerGets", {}).get("value", {})
        value_str = "?"
        if "percentage" in value:
            value_str = f"{value['percentage'] * 100:.0f}%"
        elif "amount" in value:
            amount = value["amount"]
            value_str = format_money(amount.get("amount", "0"), amount.get("currencyCode", "???"))

        lines.append(f"{did} | {code} | {title} | {status} | {value_str} | used={usage_str}")

    result = "\n".join(lines)
    page_hint = format_pagination(edges, discounts.get("pageInfo"), len(edges))
    return result + page_hint


# ---------------------------------------------------------------------------
# Metafield formatters
# ---------------------------------------------------------------------------


def format_metafield_list(data: dict[str, Any], owner_type: str) -> str:
    """Format metafield list for a resource."""
    resource = data.get(owner_type.lower(), {})
    metafields = resource.get("metafields", {}).get("edges", [])
    if not metafields:
        return f"No metafields on {owner_type} {short_id(resource.get('id'))}."

    lines = [f"Metafields on {owner_type} {short_id(resource.get('id'))}:"]
    for edge in metafields:
        mf = edge.get("node", {})
        mid = short_id(mf.get("id"))
        ns = mf.get("namespace", "?")
        key = mf.get("key", "?")
        mtype = mf.get("type", "?")
        value = mf.get("value", "?")
        # Truncate long values
        if len(str(value)) > 80:
            value = str(value)[:77] + "..."
        lines.append(f"  {mid} | {ns}.{key} | {mtype} | {value}")

    return "\n".join(lines)


def format_metafield_set(data: dict[str, Any]) -> str:
    """Format metafield set result."""
    result = data.get("metafieldsSet", {})
    metafields = result.get("metafields", [])
    if not metafields:
        return "Metafields set."

    lines = ["Metafields set:"]
    for mf in metafields:
        ns = mf.get("namespace", "?")
        key = mf.get("key", "?")
        value = mf.get("value", "?")
        if len(str(value)) > 60:
            value = str(value)[:57] + "..."
        lines.append(f"  {ns}.{key} = {value}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Webhook formatters
# ---------------------------------------------------------------------------


def format_webhook_list(data: dict[str, Any]) -> str:
    """Format webhook subscription list."""
    webhooks = data.get("webhookSubscriptions", {})
    edges = webhooks.get("edges", [])
    if not edges:
        return "No webhook subscriptions."

    lines = []
    for edge in edges:
        node = edge.get("node", {})
        wid = short_id(node.get("id"))
        topic = node.get("topic", "?")
        fmt = node.get("format", "?")
        endpoint = node.get("endpoint", {})
        url = endpoint.get("callbackUrl", "?")
        lines.append(f"{wid} | {topic} | {url} | {fmt}")

    result = "\n".join(lines)
    page_hint = format_pagination(edges, webhooks.get("pageInfo"), len(edges))
    return result + page_hint


def format_webhook_created(data: dict[str, Any]) -> str:
    """Format webhook creation result."""
    result = data.get("webhookSubscriptionCreate", {})
    webhook = result.get("webhookSubscription")
    if not webhook:
        return "Webhook created."

    wid = short_id(webhook.get("id"))
    topic = webhook.get("topic", "?")
    endpoint = webhook.get("endpoint", {})
    url = endpoint.get("callbackUrl", "?")
    fmt = webhook.get("format", "?")
    return f"Webhook created: {wid} | {topic} | {url} | {fmt}"


# ---------------------------------------------------------------------------
# Shop formatters
# ---------------------------------------------------------------------------


def format_shop_info(data: dict[str, Any]) -> str:
    """Format shop information."""
    shop = data.get("shop")
    if not shop:
        return "Shop info not available."

    lines = [
        f"Store: {shop.get('name', '?')}",
        f"Domain: {shop.get('myshopifyDomain', '?')}",
    ]

    primary = shop.get("primaryDomain", {})
    if primary and primary.get("host"):
        lines.append(f"Primary domain: {primary['host']}")

    lines.append(f"Email: {shop.get('email', '?')}")

    plan = shop.get("plan", {})
    if plan:
        plan_name = plan.get("displayName", "?")
        if plan.get("shopifyPlus"):
            plan_name += " (Plus)"
        if plan.get("partnerDevelopment"):
            plan_name += " (dev)"
        lines.append(f"Plan: {plan_name}")

    lines.append(f"Currency: {shop.get('currencyCode', '?')}")
    lines.append(f"Timezone: {shop.get('timezoneAbbreviation', '?')} ({shop.get('ianaTimezone', '?')})")

    addr = shop.get("billingAddress", {})
    if addr:
        lines.append(f"Address: {_format_address(addr)}")

    return "\n".join(lines)


def format_locations(data: dict[str, Any]) -> str:
    """Format locations list."""
    locations = data.get("locations", {}).get("edges", [])
    if not locations:
        return "No locations found."

    lines = ["Locations:"]
    for edge in locations:
        node = edge.get("node", {})
        lid = short_id(node.get("id"))
        name = node.get("name", "?")
        active = "active" if node.get("isActive") else "inactive"
        primary = " (primary)" if node.get("isPrimary") else ""
        svc = node.get("fulfillmentService", {})
        svc_name = svc.get("serviceName", "") if svc else ""
        addr = node.get("address", {})
        addr_str = _format_address(addr) if addr else ""

        parts = [lid, f"{name}{primary}", active]
        if svc_name:
            parts.append(svc_name)
        if addr_str:
            parts.append(addr_str)
        lines.append("  " + " | ".join(parts))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Analytics formatters
# ---------------------------------------------------------------------------


def format_analytics_result(data: dict[str, Any]) -> str:
    """Format ShopifyQL query results."""
    result = data.get("shopifyqlQuery", {})

    # Check for parse errors
    parse_errors = result.get("parseErrors", [])
    if parse_errors:
        lines = ["ShopifyQL parse errors:"]
        for err in parse_errors:
            pos = err.get("range", {}).get("start", {})
            line = pos.get("line", "?")
            char = pos.get("character", "?")
            lines.append(f"  Line {line}:{char} — {err.get('message', '?')}")
        return "\n".join(lines)

    typename = result.get("__typename", "")
    if typename != "TableResponse":
        return f"Unexpected response type: {typename}"

    table = result.get("tableData", {})
    columns = table.get("columns", [])
    rows = table.get("rowData", [])

    if not columns or not rows:
        return "No data returned."

    # Header
    col_names = [c.get("name", "?") for c in columns]
    lines = [" | ".join(col_names)]
    lines.append("-" * len(lines[0]))

    # Rows (cap at 50 for token efficiency)
    display_rows = rows[:50]
    for row in display_rows:
        # rowData is a list of lists (one per row)
        if isinstance(row, list):
            lines.append(" | ".join(str(v) for v in row))
        else:
            lines.append(str(row))

    if len(rows) > 50:
        lines.append(f"\n... {len(rows) - 50} more rows")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Mutation result formatters
# ---------------------------------------------------------------------------


def format_mutation_result(data: dict[str, Any], resource_type: str, action: str) -> str:
    """Generic formatter for simple mutation results."""
    for key, value in data.items():
        if isinstance(value, dict):
            resource = value.get(resource_type)
            if resource:
                rid = short_id(resource.get("id", ""))
                title = resource.get("title") or resource.get("name") or resource.get("displayName") or ""
                return f"{resource_type.title()} {action}: {rid} | {title}".strip()

            deleted_id = value.get(f"deleted{resource_type.title()}Id") or value.get("deletedId")
            if deleted_id:
                return f"{resource_type.title()} deleted: {short_id(deleted_id)}"

    return f"{resource_type.title()} {action} completed."


def format_webhook_verification(result: dict[str, Any]) -> str:
    """Format webhook verification result."""
    if result.get("valid"):
        return "Webhook signature: VALID"
    return f"Webhook signature: INVALID — {result.get('error', 'unknown error')}"
